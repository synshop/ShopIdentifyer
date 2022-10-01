from .crypto import SettingsUtil, CryptoUtil
import base64, logging, time, bcrypt, io
from PIL import Image as PILImage
from PIL import ImageFilter, ImageEnhance

try:
    import identity.config
except Exception as e:
    print("You need to create/install a <project-home>/identity/config.py file and populate it with some values.\n")
    print("Please see https://github.com/munroebot/ShopIdentifyer/blob/master/README.md for more information.")
    quit()

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# TODO: Move to svglib
# TODO: Look at using CursorDictRowsMixIn for db operations

import json
# from svgwrite.image import Image
# from svgwrite.shapes import Rect
import MySQLdb as mysql

from flask import Flask, request, g, flash
from flask import redirect,  make_response
from flask import render_template, jsonify
from flask import session, escape, url_for
from flask import send_file

from flask_mail import Mail, Message

RUN_MODE = 'development'

ENCRYPTION_KEY = SettingsUtil.EncryptionKey.get(RUN_MODE == 'development')

app = Flask(__name__)

app.secret_key = CryptoUtil.decrypt(config.ENCRYPTED_SESSION_KEY,ENCRYPTION_KEY)

app.config['STRIPE_TOKEN'] = CryptoUtil.decrypt(config.ENCRYPTED_STRIPE_TOKEN, ENCRYPTION_KEY)
app.config['DATABASE_PASSWORD'] = CryptoUtil.decrypt(config.ENCRYPTED_DATABASE_PASSWORD, ENCRYPTION_KEY)
app.config['STRIPE_CACHE_REFRESH_CRON'] = config.STRIPE_CACHE_REFRESH_CRON
app.config['STRIPE_CACHE_REFRESH_REACHBACK_MIN'] = config.STRIPE_CACHE_REFRESH_REACHBACK_MIN
app.config['STRIPE_CACHE_REBUILD_CRON'] = config.STRIPE_CACHE_REBUILD_CRON
app.config['ACCESS_CONTROL_HOSTNAME'] = config.ACCESS_CONTROL_HOSTNAME
app.config['ACCESS_CONTROL_SSH_PORT'] = config.ACCESS_CONTROL_SSH_PORT

app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USE_SSL'] = config.MAIL_USE_SSL
app.config['MAIL_USERNAME'] = CryptoUtil.decrypt(config.ENCRYPTED_MAIL_USERNAME,ENCRYPTION_KEY)
app.config['MAIL_PASSWORD'] = CryptoUtil.decrypt(config.ENCRYPTED_MAIL_PASSWORD,ENCRYPTION_KEY)
app.config['ADMIN_PASSPHRASE'] = CryptoUtil.decrypt(config.ENCRYPTED_ADMIN_PASSPHRASE,ENCRYPTION_KEY)
app.config['LOG_FILE'] = config.LOG_FILE

# Logging
file_handler = logging.FileHandler(app.config['LOG_FILE'])
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s: %(message)s'))
file_handler.setLevel(logging.INFO)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(file_handler)

app.logger.info("------------------------------")
app.logger.info("SYN Shop Identifyer Started...")
app.logger.info("------------------------------")

# Imports down here so that they can see the app.config elements
from identity.stripe import get_rebuild_stripe_cache, get_realtime_stripe_info
from identity.stripe import DELINQUENT, IN_GOOD_STANDING,PAST_DUE, D_EMAIL_TEMPLATE
# from identity.models import Member

def connect_db():
    return mysql.connect(host=config.DATABASE_HOST,user=config.DATABASE_USER,passwd=app.config["DATABASE_PASSWORD"],db=config.DATABASE_SCHEMA)

def get_db():
    if not hasattr(g, 'mysql_db'):
        g.mysql_db = connect_db()
    return g.mysql_db

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'mysql_db'):
        g.mysql_db.close()

# Set up the mail sender object
mail = Mail(app)

# Start cron tasks
s1 = BackgroundScheduler()

# This helps with stripe information lookup performance
# Currently it runs every ~15 minutes and grabs
# the last 15 minutes of data
@s1.scheduled_job(CronTrigger.from_crontab(app.config['STRIPE_CACHE_REFRESH_CRON']))
def refresh_stripe_cache():

    app.logger.info("refreshing stripe cache")
    member_array = get_rebuild_stripe_cache(incremental=True)

    with app.app_context():
        db = get_db()

        for member in member_array:
            cur = db.cursor()

            cur.execute("insert ignore into stripe_cache values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",\
            (member['stripe_id'], member['stripe_created_on'], member['stripe_email'], \
             member['stripe_description'], member['stripe_last_payment_status'],\
             member['stripe_subscription_id'], member['stripe_subscription_product'],\
             member['stripe_subscription_status'], member['stripe_subscription_created_on']))
        
            print(member)

        db.commit()

    app.logger.info("finished refreshing stripe cache")

@s1.scheduled_job(CronTrigger.from_crontab(app.config['STRIPE_CACHE_REBUILD_CRON']))
def rebuild_stripe_cache():

    app.logger.info("nightly stripe cache rebuild")

    member_array = get_rebuild_stripe_cache()

    with app.app_context():
        db = get_db()

        cur = db.cursor()
        cur.execute("delete from stripe_cache")
        db.commit()

        for member in member_array:
            cur = db.cursor()

            cur.execute("insert ignore into stripe_cache values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",\
            (member['stripe_id'], member['stripe_created_on'], member['stripe_email'], \
             member['stripe_description'], member['stripe_last_payment_status'],\
             member['stripe_subscription_id'], member['stripe_subscription_product'],\
             member['stripe_subscription_status'], member['stripe_subscription_created_on']))

        db.commit()

    app.logger.info("finished rebuilding stripe cache")

# End cron tasks

if config.SCHEDULER_ENABLED == True:
    s1.start()

def log_swipe_event(stripe_id=None, badge_status=None, swipe_event=None):
    db = get_db()
    cur = db.cursor()

    print(stripe_id,badge_status,swipe_event)
    cur.execute('insert into event_log values (NULL, %s, %s, NULL, %s)', (stripe_id,badge_status,swipe_event))
    db.commit()

# Check to see if a user is able to login and make changes to the system
def member_is_admin(stripe_id=None):

    try:
        db = get_db()
        cur = db.cursor()
        stmt = "select count(*) from admin_users where stripe_id = %s"
        cur.execute(stmt, (stripe_id,))
        entry = cur.fetchone()
        if entry[0] > 0:
            return True
    except:
        return False

def admin_change_password(stripe_id=None,password=None):

    try:
        db = get_db()
        cur = db.cursor()

        hashed_password = bcrypt.hashpw(password.encode('utf-8'),bcrypt.gensalt())

        stmt = "update admin_users set pwd = %s where stripe_id = %s"
        cur.execute(stmt, (hashed_password, stripe_id,))
        db.commit()
        return True
    except:
        return False

# Check the password for the user login
def check_password(username=None, password=None):

    with app.app_context():

        try:
            db = get_db()
            cur = db.cursor()

            stmt = "select a.pwd from admin_users a where a.stripe_id = (select m.stripe_id from members m where nick_name = %s)"
            cur.execute(stmt, (username,))
            entries = cur.fetchall()
            hashed_password = entries[0][0].encode('utf-8')

            if bcrypt.hashpw(password.encode('utf-8'), hashed_password) == hashed_password:
                passwords_match = True
            else:
                passwords_match = False

        except Exception as e:
            print(e)
            passwords_match = False

        return passwords_match

def get_badge_serials(stripe_id=None):

    with app.app_context():

        try:
            db = get_db()
            cur = db.cursor()

            stmt = "select badge_serial from badges where stripe_id = %s and badge_status = 'ACTIVE'"

            cur.execute(stmt, (stripe_id,))
            entries = cur.fetchall()

            badges = []

            for entry in entries:
                badges.append(entry[0])

        except:
            return "boom"

        return badges

def get_subscription_id_from_stripe_cache(stripe_id=None):
    db = get_db()
    cur = db.cursor()
    sql_stmt = "select stripe_subscription_id from stripe_cache where stripe_id = %s"
    cur.execute(sql_stmt, (stripe_id,))

    return cur.fetchall()[0][0]
    
# Fetch a member 'object'
def get_member(stripe_id):

    member = {}

    subscription_id = get_subscription_id_from_stripe_cache(stripe_id)

    # Check and update the stripe cache every time you view member details
    app.logger.info("updating real-time stripe information for %s" % (stripe_id,))
    stripe_info = get_realtime_stripe_info(subscription_id)
    
    member["stripe_status"] = stripe_info['stripe_subscription_status'].upper()
    member['stripe_plan'] = stripe_info['stripe_subscription_product'].upper()
    member['stripe_email'] = stripe_info['stripe_email']

    db = get_db()
    cur = db.cursor()
    cur.execute('update stripe_cache SET stripe_last_payment_status = %s, stripe_subscription_status = %s WHERE stripe_id = %s', (stripe_info['stripe_last_payment_status'], stripe_info['stripe_subscription_status'], stripe_id))
    db.commit()

    sql_stmt = '''select
         member_status,
         created_on,
         changed_on,
         full_name,
         nick_name,
         drupal_id,
         meetup_email,
         mobile,
         emergency_contact_name,
         emergency_contact_mobile,
         is_vetted,
         liability_waiver,
         vetted_membership_form,
         discord_handle,
         locker_num
      from members where stripe_id = %s'''

    cur.execute(sql_stmt, (stripe_info['stripe_id'],))
    entries = cur.fetchall()
    entry = entries[0]

    member["stripe_id"] = stripe_info['stripe_id']
    member["member_status"] = entry[0]
    member["badge_serials"] = get_badge_serials(stripe_info['stripe_id'])
    member["created_on"] = entry[1]
    member["changed_on"] = entry[2]
    member["full_name"] = entry[3]
    member["nick_name"] = entry[4]
    member["drupal_id"] = entry[5]
    member["meetup_email"] = entry[6]
    member["mobile"] = entry[7]
    member["emergency_contact_name"] = entry[8]
    member["emergency_contact_mobile"] = entry[9]
    member["vetted_status"] = entry[10]

    # Flags set to determine if a member has
    # a waiver / vetted membership form on file,
    # or if they are an admin in the system.
    if entry[11] == None:
        member['has_wavier'] = False
    else:
        member['has_wavier'] = True

    if entry[12] == None:
        member['has_vetted'] = False
    else:
        member['has_vetted'] = True

    if member_is_admin(stripe_info['stripe_id']):
        member['is_admin'] = True
    else:
        member['is_admin'] = False

    member["stripe_subscription_id"] = subscription_id
    member["discord_handle"] = entry[13]
    member["locker_num"] = entry[14]

    return member

# Update an existing member 'object'
def update_member(request):

    db = connect_db()
    cur = db.cursor()

    if request.files['badge_file'].filename != "":
        badge_photo = request.files['badge_file'].read()
    else:
        badge_base64 = request.form.get('badge_base64_data',default=None)
        if len(badge_base64) != 0:
            badge_photo = base64.b64decode(badge_base64)
        else:
            badge_photo = None
    
    if request.files['liability_file'].filename != "":
        liability_wavier_form = request.files['liability_file'].read()
    else:
        liability_base64 = request.form.get('liability_base64_data',default=None)
        if len(liability_base64) != 0:
            liability_wavier_form = base64.b64decode(liability_base64)
            liability_wavier_form = io.BytesIO(liability_wavier_form)
            image = PILImage.open(liability_wavier_form)
            image = image.transpose(PILImage.Transpose.ROTATE_270)
            enh = ImageEnhance.Contrast(image)
            image = enh.enhance(1.8)
            liability_wavier_form = io.BytesIO()
            image.save(liability_wavier_form,format='PDF')
            liability_wavier_form = liability_wavier_form.getvalue()
        else:
            liability_wavier_form = None

    if request.files['vetted_file'].filename != "":
        vetted_membership_form = request.files['vetted_file'].read()
    else:
        vetted_base64 = request.form.get('vetted_base64_data',default=None)
        if len(vetted_base64) != 0:
            vetted_membership_form = base64.b64decode(vetted_base64)
            vetted_membership_form = io.BytesIO(vetted_membership_form)
            image = PILImage.open(vetted_membership_form)
            image = image.transpose(PILImage.Transpose.ROTATE_270)
            enh = ImageEnhance.Contrast(image)
            image = enh.enhance(1.8)
            vetted_membership_form = io.BytesIO()
            image.save(vetted_membership_form,format='PDF')
            vetted_membership_form = vetted_membership_form.getvalue()            
        else:
            vetted_membership_form = None

    # Do any image / document updates separately, otherwise you will clobber the existing blobs
    
    stripe_id = request.form.get('stripe_id')

    if vetted_membership_form != None:
        cur.execute('update members set vetted_membership_form=%s where stripe_id=%s', (vetted_membership_form,stripe_id))
        db.commit()
    
    if liability_wavier_form != None:
        cur.execute('update members set liability_waiver=%s where stripe_id=%s', (liability_wavier_form,stripe_id))
        db.commit()
    
    if badge_photo != None:
        cur.execute('update members set badge_photo=%s where stripe_id=%s', (badge_photo,stripe_id))
        db.commit()

    insert_data = (
        request.form.get('member_status'),
        request.form.get('full_name'),
        request.form.get('nick_name'),
        request.form.get('meetup_email'),
        request.form.get('mobile'),
        request.form.get('emergency_contact_name'),
        request.form.get('emergency_contact_mobile'),
        request.form.get('is_vetted','NOT VETTED'),
        request.form.get('discord_handle'),
        request.form.get('locker_num'),
        stripe_id
    )

    cur.execute('update members set member_status=%s,full_name=%s,nick_name=%s,meetup_email=%s,mobile=%s,emergency_contact_name=%s,emergency_contact_mobile=%s,is_vetted=%s,discord_handle=%s,locker_num=%s where stripe_id=%s', insert_data)

    db.commit()
    db.close()

# Onboarding process - this attempts to pre-populate some
# fields when setting up a new user.
@app.route('/member/new/<stripe_id>', methods=['GET','POST'])
def new_member_stripe(stripe_id):

    if session.get('logged_in') == None:
        return redirect(url_for("login",_scheme='https',_external=True))

    # Get a new form, or if a POST then save the data
    if request.method == "GET":
        app.logger.info("User %s is onboarding member %s" % (session['username'],stripe_id))

        db = connect_db()
        cur = db.cursor()
        cur.execute('select stripe_email, stripe_description, stripe_last_payment_status, stripe_subscription_product, stripe_subscription_status from stripe_cache where stripe_id = %s', (stripe_id,))
        rows = cur.fetchall()
        member = rows[0]

        x = json.loads(member[1])

        if 'drupal_id' in x:
            drupal_id = x['drupal_id']
        else:
            drupal_id = "-1"

        if 'drupal_legal_name' in x:
            drupal_legal_name = x['drupal_legal_name']
        else:
            drupal_legal_name = "No Legal Name Provided"

        if 'drupal_name' in x:
            drupal_name = x['drupal_name']
        else:
            drupal_name = "Not Provided"

        user = {}

        user["stripe_id"] = stripe_id
        user["full_name"] = drupal_legal_name
        user["drupal_name"] = drupal_name
        user["drupal_id"] = drupal_id
        user["stripe_email"] = member[0]

        if member[2] != None:
            user["stripe_last_payment_status"] = member[2].upper()
        else:
            if member[3] == "Free Membership":
                user["stripe_last_payment_status"] = "NOT AVAILABLE"
            else:
                user["stripe_last_payment_status"] = "STATUS ERROR"

        user["stripe_subscription_product"] = member[3].upper()
        user["stripe_subscription_status"] = member[4].upper()

        rows = None
        if rows:
            user['badge_serial'] = rows[0][0]
        else:
            user['badge_serial'] = -1

        return render_template('new_member.html', member=user)

    if request.method == "POST":
        
        # Need to determine if this is a file upload or an webcam image capture
        # for badge photos, liability waivers, and vetted membership forms

        if request.files['badge_file'].filename != "":
            badge_photo = request.files['badge_file'].read()
        else:
            badge_base64 = request.form.get('badge_base64_data',default=None)
            if len(badge_base64) != 0:
                badge_photo = base64.b64decode(badge_base64)
            else:
                badge_photo = None
        
        if request.files['liability_file'].filename != "":
            liability_wavier_form = request.files['liability_file'].read()
        else:
            liability_base64 = request.form.get('liability_base64_data',default=None)
            if len(liability_base64) != 0:
                liability_wavier_form = base64.b64decode(liability_base64)
                liability_wavier_form = io.BytesIO(liability_wavier_form)
                image = PILImage.open(liability_wavier_form)
                image = image.transpose(PILImage.Transpose.ROTATE_270)
                enh = ImageEnhance.Contrast(image)
                image = enh.enhance(1.8)
                liability_wavier_form = io.BytesIO()
                image.save(liability_wavier_form,format='PDF')
                liability_wavier_form = liability_wavier_form.getvalue()
            else:
                liability_wavier_form = None

        if request.files['vetted_file'].filename != "":
            vetted_membership_form = request.files['vetted_file'].read()
        else:
            vetted_base64 = request.form.get('vetted_base64_data',default=None)
            if len(vetted_base64) != 0:
                vetted_membership_form = base64.b64decode(vetted_base64)
                vetted_membership_form = io.BytesIO(vetted_membership_form)
                image = PILImage.open(vetted_membership_form)
                image = image.transpose(PILImage.Transpose.ROTATE_270)
                enh = ImageEnhance.Contrast(image)
                image = enh.enhance(1.8)
                vetted_membership_form = io.BytesIO()
                image.save(vetted_membership_form,format='PDF')
                vetted_membership_form = vetted_membership_form.getvalue()            
            else:
                vetted_membership_form = None

        insert_data = (
            request.form.get('stripe_id'),
            request.form.get('drupal_id'),
            'ACTIVE',
            request.form.get('full_name'),
            request.form.get('nick_name'),
            request.form.get('meetup_email'),
            request.form.get('mobile'),
            request.form.get('emergency_contact_name'),
            request.form.get('emergency_contact_mobile'),
            request.form.get('is_vetted','NOT VETTED'),
            liability_wavier_form,
            vetted_membership_form,
            badge_photo,
        )

        db = connect_db()
        cur = db.cursor()
        cur.execute('insert into members (stripe_id,drupal_id,member_status,full_name,nick_name,meetup_email,mobile,emergency_contact_name,emergency_contact_mobile,is_vetted,liability_waiver,vetted_membership_form,badge_photo) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', insert_data)
        db.commit()
        db.close()
        
        app.logger.info("User %s successfully onboarded member %s" % (session['username'],stripe_id))
        return redirect(url_for("admin_onboard",_scheme='https',_external=True))

# Show member details
@app.route('/member/<stripe_id>')
def show_member(stripe_id):
    user = get_member(stripe_id)
    return render_template('show_member.html', member=user)

# Edit member details
@app.route('/member/<stripe_id>/edit', methods=['GET','POST'])
def edit_member(stripe_id):

    if session.get('logged_in') == None:
        return redirect(url_for("login",_scheme='https',_external=True))

    if request.method == "GET":
        user = get_member(stripe_id)
        app.logger.info("User %s is editing member %s " % (session['username'],stripe_id))
        return render_template('edit_member.html', member=user)

    if request.method == "POST":
        update_member(request)
        app.logger.info("User %s updated member %s" % (session['username'],stripe_id))
        return redirect(url_for("index",_scheme='https',_external=True))

# Get member badge photo
@app.route('/member/<stripe_id>/files/photo.jpg')
def member_photo(stripe_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("select badge_photo from members where stripe_id = %s", (stripe_id,))
    photo = cur.fetchone()[0]

    try:
        response = make_response(photo)
        response.headers['Content-Description'] = 'Badge Photo'
        response.headers['Content-Type'] = 'image/jpeg'
        response.headers['Content-Disposition'] = 'inline'
    except Exception as e:
        print(e)
        response = make_response("No photo on file, please fix this!")
        response.headers['Content-Description'] = 'Stock Photo'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Content-Type'] = 'text/plain'
        response.headers['Content-Disposition'] = 'inline'

    return response

# Get member liability waiver
@app.route("/member/<stripe_id>/files/liability-waiver.pdf")
def member_wavier(stripe_id):

    db = get_db()
    cur = db.cursor()
    cur.execute("select liability_waiver from members where stripe_id = %s", (stripe_id,))
    wavier = cur.fetchone()[0]

    if wavier[0] == None:
        response = make_response("No Waiver on file, please fix this!")
        response.headers['Content-Description'] = 'Liability Wavier'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Content-Type'] = 'text/plain'
        # response.headers['Content-Disposition'] = 'attachment; filename=liability-wavier.pdf'
        response.headers['Content-Disposition'] = 'inline'
    else:
        response = make_response(wavier)
        response.headers['Content-Description'] = 'Liability Wavier'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Content-Type'] = 'application/pdf'
        # response.headers['Content-Disposition'] = 'attachment; filename=liability-wavier.pdf'
        response.headers['Content-Disposition'] = 'inline'

    return response

# Get member vetted membership form
@app.route('/member/<stripe_id>/files/vetted-membership-form.pdf')
def member_vetted(stripe_id):

    db = get_db()
    cur = db.cursor()
    cur.execute("select vetted_membership_form from members where stripe_id = %s", (stripe_id,))
    vetted = cur.fetchone()[0]

    if vetted[0] == None:
        response = make_response("No signed vetted membership form on file, please fix this!")
        response.headers['Content-Description'] = 'Vetted Membership Form'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Content-Type'] = 'text/plain'
        response.headers['Content-Disposition'] = 'inline'

    else:
        response = make_response(vetted)
        response.headers['Content-Description'] = 'Vetted Membership Form'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline'

    return response

# AJAX service for search_member.html
@app.route('/search', methods=['GET'])
def search_users():
    user = request.args.get('s')

    db = get_db()
    cur = db.cursor()
    cur.execute('select stripe_id,full_name,member_status,is_vetted,liability_waiver,vetted_membership_form from members where full_name like %s', ("%" + user + '%',))
    data = cur.fetchall()

    results = []
    wavier = ""
    vetted_form = ""

    for row in data:

        if row[4] == None:
            wavier = "false"
        else:
            wavier = "true"

        if row[5] == None:
            vetted_form = "false"
        else:
            vetted_form = "true"

        results.append({'stripe_id':row[0],'full_name':row[1],'member_status':row[2],'is_vetted':row[3],'wavier':wavier,'vetted_form':vetted_form})

    return jsonify({'results':results})

# RFID queuing services
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
        print(sys.exc_info()[0])
        message = {'message':"NULL"}

    return jsonify(message)

# Badge Swipe API Endpoint
@app.route('/swipe/', methods=['POST'])
def swipe_badge():

    badge_serial = request.form['tag']

    if request.form.has_key('reader') != False:
        badge_reader = request.form['reader']
    else:
        badge_reader = None

    swipe = "BADGE_SWIPE"

    db = get_db()
    cur = db.cursor()

    try:
        cur.execute('select stripe_id, badge_status from badges where badge_serial = %s', (badge_serial,))
        entries = cur.fetchall()
        member = entries[0]
        log_swipe_event(stripe_id=member[0],badge_status=member[1], swipe_event=swipe)
    except IndexError:
        # The user's badge is not in the system
        swipe = "MISSING_ACCOUNT"
        cur.execute("insert into message_queue (message) values (%s)", (badge_serial,))
        db.commit()
        log_swipe_event(stripe_id=badge_serial,badge_status="ACTIVE",swipe_event=swipe)

    message = {'message':swipe}
    return jsonify(message)

# Landing Page Routes
@app.route('/')
def index():
    return redirect(url_for("admin",_scheme='https',_external=True))

@app.route('/login', methods=['GET', 'POST'])
def login():

    error = ""
    r_to = request.referrer

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        url = request.form['r_to']

        if check_password(username,password):
            session['logged_in'] = True
            session['username'] = username
            app.logger.info("User %s logged in successfully" % (username))
            return redirect(url)
        else:
            error = 'Invalid credentials'
            app.logger.info("User %s failed login attempt" % (username))
            r_to=url

    return render_template('login.html',r_to=r_to,errors=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash('You were logged out')
    return redirect(url_for('index',_scheme='https',_external=True))

@app.route('/admin')
def admin():
    db = get_db()
    cur = db.cursor()
    stmt = """  SELECT 
                    m.stripe_id,
                    s.stripe_subscription_id,
                    m.full_name,
                    m.is_vetted, 
                    m.liability_waiver, 
                    m.vetted_membership_form, 
                    s.stripe_email,
                    s.stripe_subscription_status
                FROM 
                    members m, stripe_cache s
                WHERE
                    m.member_status = "ACTIVE"
                AND
                    m.stripe_id = s.stripe_id
            """
    cur.execute(stmt)
    entries = cur.fetchall()
    return render_template('admin.html',entries=entries)

@app.route('/admin/onboard')
def admin_onboard():
    try:
        if session.get('logged_in'):

            entries_x = []

            db = get_db()
            cur = db.cursor()

            sql_stmt = """
                SELECT
                    stripe_id, 
                    stripe_created_on, 
                    stripe_email, 
                    stripe_description,
                    stripe_last_payment_status,
                    stripe_subscription_product,
                    stripe_subscription_status
                FROM 
                    stripe_cache 
                WHERE
                    stripe_id 
                NOT IN
                    (SELECT stripe_id FROM members) 
                ORDER BY stripe_created_on
            """
            cur.execute(sql_stmt)
            rows = cur.fetchall()

            sql_stmt = "select count(*) from stripe_cache where stripe_subscription_product like '%pause%'"
            cur.execute(sql_stmt)
            paused = cur.fetchall()[0][0]

            for row in rows:

                x = json.loads(row[3])
                if 'drupal_legal_name' in x:
                    drupal_legal_name = x['drupal_legal_name']
                else:
                    drupal_legal_name = "No Legal Name Provided"

                entry_dict = dict(
                    stripe_id=row[0],
                    stripe_email=row[2],
                    drupal_legal_name=drupal_legal_name,
                    stripe_last_payment_status=row[4],
                    stripe_subscription_product=row[5],
                    stripe_subscription_status=row[6])

                entries_x.append(entry_dict)
            return render_template('onboard.html',entries=entries_x, paused_count=paused)
        else:
            return redirect('/login?redirect_to=admin_onboard')
    except Exception as e:
        print(str(e))
        return redirect('/login?redirect_to=admin_onboard')

@app.route('/member/search')
def member_search():
    return render_template('search_member.html')

@app.route('/admin/changepassword/<stripe_id>', methods=['GET','POST'])
def changepassword(stripe_id):

    if session.get('logged_in') == None:
        # app.logger.info("User %s is changing their password" % (session['username'],))

        if request.method == "GET":
            return render_template('changepassword.html',stripe_id=stripe_id)

        if request.method == "POST":
            x = admin_change_password(stripe_id,request.form.get('password1'),)
            return redirect(url_for('index',_scheme='https',_external=True))

    else:
        app.logger.info("Someone tried to hit the change password page without authenticating")
        return render_template('login.html',r_to=request.referrer)

# Widget Testing
@app.route('/widget', methods=['GET','POST'])
def test_widget():
    return render_template('camera-widget.html')

