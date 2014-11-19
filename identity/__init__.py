from crypto import SettingsUtil, CryptoUtil

from identity.stripe import get_stripe_cache
from identity.stripe import get_membership_status

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

# Start cron tasks
# This helps with stripe information lookup performance
s1 = BackgroundScheduler()

@s1.scheduled_job('interval', seconds=30)
def stripe_cache():

    member_array = get_stripe_cache(key=app.config['STRIPE_TOKEN'])

    with app.app_context():
        db = get_db()

        cur = db.cursor()
        cur.execute('delete from stripe_lookup')
        db.commit()

        for member in member_array:
            cur = db.cursor()
            cur.execute("insert into stripe_lookup values (%s, %s, %s)",(member['stripe_id'],member['stripe_email'], member["member_sub_plan"]))
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

    with open("/Users/bmunroe/microcontrollers.pdf", mode='rb') as file:
        waiver_pdf = file.read()

    db = connect_db()
    cur = db.cursor()

    insert_data = ("53006599FE51","ACTIVE","Aakin Patel","aakin@aakin.net",badge_photo, waiver_pdf)
    cur.execute('insert into members (badge_serial, badge_status, full_name, stripe_email,badge_photo, liability_waiver) values (%s,%s,%s,%s,%s,%s)', insert_data)

    insert_data = ("450052BA9B36","ACTIVE","James Wynhoff","jimmypopali96@gmail.com",badge_photo, waiver_pdf)
    cur.execute('insert into members (badge_serial, badge_status, full_name, stripe_email,badge_photo, liability_waiver) values (%s,%s,%s,%s,%s,%s)', insert_data)

    db.commit()
    db.close()

@app.route('/member/<badge_serial>')
def show_member(badge_serial):

    db = get_db()
    cur = db.cursor()
    cur.execute('select badge_serial,badge_status,created_on,changed_on,full_name,nick_name,drupal_name,primary_email,stripe_email,meetup_email,mobile,emergency_contact_name,emergency_contact_mobile from members where badge_serial = %s', (badge_serial,))
    entries = cur.fetchall()
    member = entries[0]

    cur.execute("select stripe_id from stripe_lookup where stripe_email = %s", [member[8]])
    entries = cur.fetchall()
    stripe_id = entries[0][0]

    user = {}

    user["badge_serial"] = member[0]
    user["badge_status"] = member[1]
    user["created_on"] = member[2]
    user["changed_on"] = member[3]
    user["full_name"] = member[4]
    user["nick_name"] = member[5]
    user["drupal_name"] = member[6]
    user["primary_email"] = member[7]
    user["meetup_email"] = member[9]
    user["mobile"] = member[10]
    user["emergency_contact_name"] = member[11]
    user["emergency_contact_mobile"] = member[12]
    user['is_vetted'] = get_membership_status(key=app.config['STRIPE_TOKEN'],member_id=stripe_id)

    return render_template('show_member.html', entry=user)

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
