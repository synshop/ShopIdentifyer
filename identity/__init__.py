from crypto import SettingsUtil, CryptoUtil

from identity.stripe import get_stripe_cache
from identity.stripe import get_payment_status

import config
#import logging

from apscheduler.schedulers.background import BackgroundScheduler

import MySQLdb as mysql

from flask import Flask, request, g
from flask import redirect,  make_response
from flask import render_template, jsonify

RUN_MODE = 'development'
# logging.basicConfig()

ENCRYPTION_KEY = SettingsUtil.EncryptionKey.get(RUN_MODE == 'development')

app = Flask(__name__)

app.config['DEBUG'] = True
app.config['STRIPE_TOKEN'] = CryptoUtil.decrypt(config.ENCRYPTED_STRIPE_TOKEN, ENCRYPTION_KEY)
# app.config['DATBASE_PASSWORD'] = CryptoUtil.decrypt(config.ENCRYPTED_DATABASE_PASSWORD, ENCRYPTION_KEY)
app.config['DATABASE_PASSWORD'] = config.ENCRYPTED_DATABASE_PASSWORD
app.config['STRIPE_CACHE_REFRESH_MINUTES'] = config.STRIPE_CACHE_REFRESH_MINUTES

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

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'mysql_db'):
        g.mysql_db.close()

def load_test_data():

    with open("/Users/bmunroe/mug.jpg", mode='rb') as file:
        badge_photo = file.read()

    with open("/Users/bmunroe/liability-waiver.pdf", mode='rb') as file:
        waiver_pdf = file.read()

    with open("/Users/bmunroe/vetted_membership_form.pdf", mode='rb') as file:
        vetted_pdf = file.read()

    db = connect_db()
    cur = db.cursor()

    insert_data = ("53006599FE51","ACTIVE","Aakin Patel","aakin@synshop.org","aakin@aakin.net",badge_photo, waiver_pdf,vetted_pdf,1,"702-123-1234","Aakins Mom","702-123-1235","aakin","aakin")
    cur.execute('insert into members (badge_serial, badge_status, full_name, primary_email, stripe_email,badge_photo, liability_waiver, vetted_membership_form,is_vetted,mobile,emergency_contact_name,emergency_contact_mobile,drupal_name,nick_name) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', insert_data)

    insert_data = ("450052BA9B36","ACTIVE","James Wynhoff","jimmypopali96@gmail.com","jimmypopali96@gmail.com",badge_photo, waiver_pdf,"702-123-1234","Jimmys Mom","702-123-1235","TheProgramGuy","JimmyPop")
    cur.execute('insert into members (badge_serial, badge_status, full_name,  primary_email, stripe_email,badge_photo, liability_waiver,mobile,emergency_contact_name,emergency_contact_mobile,drupal_name,nick_name) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', insert_data)

    db.commit()
    db.close()

@app.route('/member/<badge_serial>')
def show_member(badge_serial):

    swipe_type = request.args.get('s')

    if swipe_type != None:
        swipe = "MANUAL_SWIPE"
    else:
        swipe = "BADGE_SWIPE"

    db = get_db()
    cur = db.cursor()

    cur.execute('select badge_id,badge_serial,badge_status,created_on,changed_on,full_name,nick_name,drupal_name,primary_email,stripe_email,meetup_email,mobile,emergency_contact_name,emergency_contact_mobile,is_vetted from members where badge_serial = %s', (badge_serial,))
    entries = cur.fetchall()
    member = entries[0]

    cur.execute("insert into event_log (event_id,badge_id,event_type) values (NULL,%s, %s)", (member[0],swipe))
    db.commit()

    cur.execute("select stripe_id from stripe_cache where stripe_email = %s", [member[9]])
    entries = cur.fetchall()
    stripe_id = entries[0][0]

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

    if member[14] == 1:
        user['vetted_status'] = "Vetted Member"
    else:
        user["vetted_status"] = "Not Vetted Member"

    user["payment_status"] = get_payment_status(key=app.config['STRIPE_TOKEN'],member_id=stripe_id)

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
    return redirect("/validate/", code=302)

@app.route('/validate/')
def validate():
    return render_template('validate.html')

@app.route('/validate/manual')
def validate_manual():
    return render_template('validate_manual.html')

@app.route('/search',methods=['GET'])
def find_user():
    user = request.args.get('s')

    db = get_db()
    cur = db.cursor()
    cur.execute('select badge_serial,full_name,primary_email from members where full_name like %s', ("%" + user + '%',))
    data = cur.fetchall()

    results = []

    for row in data:
        results.append({'badge_serial':row[0],'full_name':row[1],'primary_email':row[2]})

    return jsonify({'results':results})
