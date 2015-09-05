from crypto import SettingsUtil, CryptoUtil
import base64

try:
    import config
except:
    print "You need to create/install a <project-home>/identity/config.py file and populate it with some values.\n"
    print "Please see https://github.com/munroebot/ShopIdentifyer/blob/master/README.md for more information."
    quit()

from identity.stripe import get_stripe_cache
from identity.stripe import get_payment_status
from identity.stripe import DELINQUENT, IN_GOOD_STANDING, D_EMAIL_TEMPLATE

import logging

from apscheduler.schedulers.background import BackgroundScheduler

import MySQLdb as mysql

from flask import Flask, request, g, flash
from flask import redirect,  make_response
from flask import render_template, jsonify
from flask import session, escape

from flask_mail import Mail, Message

RUN_MODE = 'development'
#logging.basicConfig()

ENCRYPTION_KEY = SettingsUtil.EncryptionKey.get(RUN_MODE == 'development')

app = Flask(__name__)

app.secret_key = CryptoUtil.decrypt(config.ENCRYPTED_SESSION_KEY,ENCRYPTION_KEY)

app.config['DEBUG'] = True
app.config['STRIPE_TOKEN'] = CryptoUtil.decrypt(config.ENCRYPTED_STRIPE_TOKEN, ENCRYPTION_KEY)
app.config['DATABASE_PASSWORD'] = CryptoUtil.decrypt(config.ENCRYPTED_DATABASE_PASSWORD, ENCRYPTION_KEY)
app.config['STRIPE_CACHE_REFRESH_MINUTES'] = config.STRIPE_CACHE_REFRESH_MINUTES
app.config['ACCESS_CONTROL_HOSTNAME'] = config.ACCESS_CONTROL_HOSTNAME
app.config['ACCESS_CONTROL_SSH_PORT'] = config.ACCESS_CONTROL_SSH_PORT

app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USE_SSL'] = config.MAIL_USE_SSL
app.config['MAIL_USERNAME'] = CryptoUtil.decrypt(config.ENCRYPTED_MAIL_USERNAME,ENCRYPTION_KEY)
app.config['MAIL_PASSWORD'] = CryptoUtil.decrypt(config.ENCRYPTED_MAIL_PASSWORD,ENCRYPTION_KEY)
app.config['ADMIN_PASSPHRASE'] = CryptoUtil.decrypt(config.ENCRYPTED_ADMIN_PASSPHRASE,ENCRYPTION_KEY)

mail = Mail(app)

# Start cron tasks
# This helps with stripe information lookup performance
s1 = BackgroundScheduler()

@s1.scheduled_job('interval', minutes=app.config['STRIPE_CACHE_REFRESH_MINUTES'])
def stripe_cache():

    member_array = get_stripe_cache(key=app.config['STRIPE_TOKEN'])

    with app.app_context():
        db = get_db()

        cur = db.cursor()
        cur.execute('delete from stripe_cache')
        db.commit()

        for member in member_array:
            cur = db.cursor()
            cur.execute("insert into stripe_cache values (%s, %s, %s)",(member['stripe_id'],member['stripe_email'], member["member_sub_plan"]))
            db.commit()

s1.start()

# End cron tasks

def connect_db():
    return mysql.connect(host=config.DATABASE_HOST,
                         user=config.DATABASE_USER,
                         passwd=app.config["DATABASE_PASSWORD"],
                         db=config.DATABASE_SCHEMA)

def get_db():
    if not hasattr(g, 'mysql_db'):
        g.mysql_db = connect_db()
    return g.mysql_db

def log_event(member_id=None,swipe_event=None,log_message=None):
    db = get_db()
    cur = db.cursor()

    cur.execute("insert into event_log (event_id,member_id,event_type,event_message) values (NULL,%s,%s,%s)", (member_id,swipe_event,log_message))
    db.commit()

    return "1"

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'mysql_db'):
        g.mysql_db.close()

@app.route('/swipe/', methods=['POST'])
def swipe_badge():

    badge_serial = request.form['tag']
    swipe = "BADGE_SWIPE"

    db = get_db()
    cur = db.cursor()

    try:
        cur.execute('select member_id,badge_serial,badge_status,created_on,changed_on,full_name,nick_name,drupal_name,primary_email,stripe_email,meetup_email,mobile,emergency_contact_name,emergency_contact_mobile,is_vetted from members where badge_serial = %s', (badge_serial,))
        entries = cur.fetchall()
        member = entries[0]
    except IndexError:
        # The user's badge is not in the system
        swipe = "MISSING_BADGE"
        member_id = 0
        log_message = "%s not in system" % (badge_serial,)
        log_event(member_id,swipe,log_message)

        message = {'message':swipe}
        return jsonify(message)

    # Log the swipe event (if the badge is found in the system)
    log_event(member[0],swipe)

    try:
        cur.execute("select stripe_id from stripe_cache where stripe_email = %s", [member[9]])
        print member[9]
        entries = cur.fetchall()
        stripe_id = entries[0][0]
    except IndexError:
        # The user's defined stripe email does not match with with Stripe
        swipe = "MISSING_STRIPE"
        log_event(member[0],swipe)

        message = {'message':swipe}
        return jsonify(message)

    user = {}

    user["badge_serial"] = member[1]
    user["badge_status"] = member[2]
    user["created_on"] = member[3]
    user["changed_on"] = member[4]
    user["full_name"] = member[5]
    user["nick_name"] = member[6]
    user["drupal_name"] = member[7]
    user["primary_email"] = member[8]
    user["meetup_email"] = member[10]
    user["mobile"] = member[11]
    user["emergency_contact_name"] = member[12]
    user["emergency_contact_mobile"] = member[13]

    if member[14] == 'YES':
        user['vetted_status'] = "Vetted Member"
    else:
        user["vetted_status"] = "Not Vetted Member"

    user["payment_status"] = stripe.get_payment_status(key=app.config['STRIPE_TOKEN'],member_id=stripe_id)

    # send an email to folks if user is flagged as delinquent
    if user["payment_status"] == DELINQUENT:

        # This email is for shop management
        msg = Message()
        msg.recipients = ["monitoring@synshop.org"]
        msg.sender = 'SYN Shop Electric Badger <info@synshop.org>'
        msg.subject = "Member %s (%s) is delinquent according to stripe" % (user["full_name"],user["primary_email"])
        msg.body = "%s is swiping in and is delinquent in stripe\n\nMore info can be found here: https://dashboard.stripe.com/customers/%s" % (user["full_name"],stripe_id)
        mail.send(msg)

        # This is for the user
        msg = Message()
        msg.recipients = [user["primary_email"],]
        msg.sender = "SYN Shop Electric Badger <info@synshop.org>"
        msg.subject = "Your payments to SYN Shop are failing!"
        msg.html = D_EMAIL_TEMPLATE % (user["drupal_name"],)
        mail.send(msg)

    message = {'message':"SWIPE_OK"}
    return jsonify(message)

@app.route('/member/new', methods=['GET','POST'])
def new_member():

    # Give me a new form, or if a POST then save the data
    if request.method == "GET":
        return render_template('new_member.html')

    if request.files['liability_wavier_form'].filename != "":
        liability_wavier_form = request.files['liability_wavier_form'].read()

    if request.files['vetted_membership_form'].filename != "":
        vetted_membership_form = request.files['vetted_membership_form'].read()

    # if request.files['badge_photo'].filename != "":
    #    badge_photo = request.files['badge_photo'].read()

    photo_base64 = request.form.get('base64_photo_data',default=None)

    if photo_base64 != None:
        badge_photo = base64.b64decode(photo_base64)

    insert_data = (
        request.form.get('badge_serial'),
        'ACTIVE',
        request.form.get('full_name'),
        request.form.get('nick_name'),
        request.form.get('drupal_name'),
        request.form.get('primary_email'),
        request.form.get('stripe_email'),
        request.form.get('meetup_email'),
        request.form.get('mobile'),
        request.form.get('emergency_contact_name'),
        request.form.get('emergency_contact_mobile'),
        request.form.get('is_vetted','NO'),
        liability_wavier_form,
        vetted_membership_form,
        badge_photo
    )

    db = connect_db()
    cur = db.cursor()
    cur.execute('insert into members (badge_serial,badge_status,full_name,nick_name,drupal_name,primary_email,stripe_email,meetup_email,mobile,emergency_contact_name,emergency_contact_mobile,is_vetted,liability_waiver,vetted_membership_form,badge_photo) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', insert_data)

    db.commit()
    db.close()

    return render_template('new_member.html')

@app.route('/member/<badge_serial>/edit', methods=['GET','POST'])
def edit_new_member(badge_serial):

    if request.method == "GET":
        db = connect_db()
        cur = db.cursor()

        cur.execute("select badge_status,created_on,changed_on,full_name,nick_name,drupal_name,primary_email,stripe_email,meetup_email,mobile,emergency_contact_name,emergency_contact_mobile,is_vetted from members where badge_serial = %s", (badge_serial,))
        entries = cur.fetchall()
        member = entries[0]

        user = {}

        user["badge_serial"] = badge_serial
        user["badge_status"] = member[0]
        user["created_on"] = member[1]
        user["changed_on"] = member[2]
        user["full_name"] = member[3]
        user["nick_name"] = member[4]
        user["drupal_name"] = member[5]
        user["primary_email"] = member[6]
        user["stripe_email"] = member[7]
        user["meetup_email"] = member[8]
        user["mobile"] = member[9]
        user["emergency_contact_name"] = member[10]
        user["emergency_contact_mobile"] = member[11]
        user["is_vetted"] = member[12]

        db.commit()
        db.close()

        return render_template('edit_member.html', member=user)

    if request.method == "POST":
        db = connect_db()
        cur = db.cursor()

        if request.files['liability_wavier_form'].filename != "":
            liability_wavier_form = request.files['liability_wavier_form'].read()
            cur.execute('update members set liability_waiver=%s where badge_serial=%s', (liability_wavier_form,badge_serial))
            db.commit()

        if request.files['vetted_membership_form'].filename != "":
            vetted_membership_form = request.files['vetted_membership_form'].read()
            cur.execute('update members set vetted_membership_form=%s where badge_serial=%s', (vetted_membership_form,badge_serial))
            db.commit()

        if request.files['badge_photo'].filename != "":
            badge_photo = request.files['badge_photo'].read()
            cur.execute('update members set badge_photo=%s where badge_serial=%s', (badge_photo,badge_serial))
            db.commit()

        insert_data = (
            request.form.get('badge_status'),
            request.form.get('full_name'),
            request.form.get('nick_name'),
            request.form.get('drupal_name'),
            request.form.get('primary_email'),
            request.form.get('stripe_email'),
            request.form.get('meetup_email'),
            request.form.get('mobile'),
            request.form.get('emergency_contact_name'),
            request.form.get('emergency_contact_mobile'),
            request.form.get('is_vetted','NO'),
            badge_serial
        )

        cur.execute('update members set badge_status=%s,full_name=%s,nick_name=%s,drupal_name=%s,primary_email=%s,stripe_email=%s,meetup_email=%s,mobile=%s,emergency_contact_name=%s,emergency_contact_mobile=%s,is_vetted=%s where badge_serial=%s', insert_data)

        print insert_data

        db.commit()
        db.close()

        return redirect('validate')

@app.route('/member/<badge_serial>')
def show_member(badge_serial):

    swipe_type = request.args.get('s')

    if swipe_type != None:
        swipe = "MANUAL_SWIPE"
    else:
        swipe = "BADGE_SWIPE"

    db = get_db()
    cur = db.cursor()

    cur.execute('select member_id,badge_serial,badge_status,created_on,changed_on,full_name,nick_name,drupal_name,primary_email,stripe_email,meetup_email,mobile,emergency_contact_name,emergency_contact_mobile,is_vetted from members where badge_serial = %s', (badge_serial,))
    entries = cur.fetchall()
    member = entries[0]

    cur.execute("insert into event_log (event_id,member_id,event_type) values (NULL,%s, %s)", (member[0],swipe))
    db.commit()

    try:
        cur.execute("select stripe_id from stripe_cache where stripe_email = %s", [member[9]])
        entries = cur.fetchall()
        stripe_id = entries[0][0]
    except IndexError:
        stripe_id = "DEADBEEF"

    swipe_freq_sql = """
        select
            date(el.created_on) as day, count(1)
        from
            shopidentifyer.members as m
            inner join shopidentifyer.event_log as el
            on (m.member_id = el.member_id)
        where
            el.created_on >= date_add(date(now()), interval -14 day)
            and el.event_type in ("BADGE_SWIPE","MANUAL_SWIPE")
            and m.badge_serial = %s
        group by
            date(el.created_on)
        order by 1 desc
    """

    # cur.execute(swipe_freq_sql, [badge_serial,])

    user = {}

    user["badge_serial"] = member[1]
    user["badge_status"] = member[2]
    user["created_on"] = member[3]
    user["changed_on"] = member[4]
    user["full_name"] = member[5]
    user["nick_name"] = member[6]
    user["drupal_name"] = member[7]
    user["primary_email"] = member[8]
    user["meetup_email"] = member[10]
    user["mobile"] = member[11]
    user["emergency_contact_name"] = member[12]
    user["emergency_contact_mobile"] = member[13]

    if member[14] == 'YES':
        user['vetted_status'] = "Vetted Member"
    else:
        user["vetted_status"] = "Not Vetted Member"

    user["payment_status"] = stripe.get_payment_status(key=app.config['STRIPE_TOKEN'],member_id=stripe_id)

    return render_template('show_member.html', member=user)

@app.route('/member/<badge_serial>/files/photo.jpg')
def member_photo(badge_serial):

    db = get_db()
    cur = db.cursor()
    cur.execute("select badge_photo from members where badge_serial = %s", (badge_serial,))
    photo = cur.fetchone()

    response = make_response(photo)
    response.headers['Content-Description'] = 'Badge Photo'
    response.headers['Content-Type'] = 'image/jpeg'
    response.headers['Content-Disposition'] = 'inline'

    return response

@app.route("/member/<badge_serial>/files/liability-waiver.pdf")
def member_wavier(badge_serial):

    db = get_db()
    cur = db.cursor()
    cur.execute("select liability_waiver from members where badge_serial = %s", (badge_serial,))
    wavier = cur.fetchone()

    response = make_response(wavier)
    response.headers['Content-Description'] = 'Liability Wavier'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = 'application/pdf'
    # response.headers['Content-Disposition'] = 'attachment; filename=liability-wavier.pdf'
    response.headers['Content-Disposition'] = 'inline'

    return response

@app.route('/member/<badge_serial>/files/vetted-membership-form.pdf')
def member_vetted(badge_serial):

    db = get_db()
    cur = db.cursor()
    cur.execute("select vetted_membership_form from members where badge_serial = %s", (badge_serial,))
    wavier = cur.fetchone()

    response = make_response(wavier)
    response.headers['Content-Description'] = 'Vetted Membership Form'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = 'application/pdf'
    # response.headers['Content-Disposition'] = 'attachment; filename=vetted-membership-form.pdf'
    response.headers['Content-Disposition'] = 'inline'

    return response

@app.route('/member/search')
def member_search():
    return render_template('search_member.html')

@app.route('/search',methods=['GET'])
def search_user():
    user = request.args.get('s')

    db = get_db()
    cur = db.cursor()
    cur.execute('select badge_serial,full_name,primary_email,badge_status from members where full_name like %s', ("%" + user + '%',))
    data = cur.fetchall()

    results = []

    for row in data:
        results.append({'badge_serial':row[0],'full_name':row[1],'primary_email':row[2],'badge_status':row[3]})

    return jsonify({'results':results})

@app.route('/queue/message', methods=['PUT'])
def add_message():

    db = get_db()
    cur = db.cursor()
    message = request.form['message'].strip()
    cur.execute("insert into message_queue (message) values (%s)", (message,))
    db.commit()

    return jsonify({'status':'enqueued successfully'})

@app.route('/queue/message', methods=['DELETE'])
def remove_message():

    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("select message from message_queue limit 1")
        message = cur.fetchall()
        cur.execute("delete from message_queue")
        db.commit()

        message = {'message':message[0]}

    except IndexError:
        message = {'message':"NULL"}

    except:
        import sys
        print sys.exc_info()[0]
        message = {'message':"NULL"}

    return jsonify(message)

@app.route('/')
def index():
    return redirect("/validate", code=302)

@app.route('/validate')
def validate():
    return render_template('validate.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['passphrase'] == app.config['ADMIN_PASSPHRASE']:
            session['logged_in'] = True
            flash('You were logged in')
            if request.form.get('redirect_to'):
                return redirect(request.form.get('redirect_to'))
            else:
                return redirect("/member/search", code=302)

    return render_template('login.html',redirect_to=request.args.get('redirect_to'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out')
    return redirect("/validate")

@app.route('/admin')
def admin():
    try:
        if session['logged_in']:
            return render_template('admin.html')
        else:
            return redirect('/login?redirect_to=/admin')
    except:
        return redirect('/login?redirect_to=/admin')

@app.route('/electric-badger/', methods=['GET', 'POST'])
def electric_badger():

    # http://www.accxproducts.com/content/?page_id=287
    # Add the new badge to the access-controller

    from paramiko.client import SSHClient

    cmd_str = "screen -S access_control -X stuff 'echo \"m 1 254 123457890\"'$(echo -ne '\015')"

    client = SSHClient()
    client.load_system_host_keys()
    client.connect(app.config['ACCESS_CONTROL_HOSTNAME'])
    (stdin, stdout, stderr) = client.exec_command(cmd_str)
    return jsonify({'results':'hello'})
