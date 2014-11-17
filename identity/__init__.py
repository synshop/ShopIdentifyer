from crypto import SettingsUtil, CryptoUtil

import config
import MySQLdb as mysql

from flask import Flask, request, g
from flask import redirect,  make_response
from flask import render_template, jsonify

# from identity.services import stripe
from identity.models import Member

RUN_MODE = 'development'

ENCRYPTION_KEY = SettingsUtil.EncryptionKey.get(RUN_MODE == 'development')

app = Flask(__name__)

app.config['DEBUG'] = True

app.config['STRIPE_TOKEN'] = CryptoUtil.decrypt(config.ENCRYPTED_STRIPE_TOKEN, ENCRYPTION_KEY)
# app.config['DATBASE_PASSWORD'] = CryptoUtil.decrypt(config.ENCRYPTED_DATABASE_PASSWORD, ENCRYPTION_KEY)
app.config['DATABASE_PASSWORD'] = config.ENCRYPTED_DATABASE_PASSWORD

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

    with open("/Users/bmunroe/avatar-2010-12.jpg", mode='rb') as file:
        badge_photo = file.read()

    with open("/Users/bmunroe/microcontrollers.pdf", mode='rb') as file:
        waiver_pdf = file.read()

    insert_data = ("1234","ACTIVE","Brian Munroe",badge_photo, waiver_pdf)

    db = connect_db()
    cur = db.cursor()
    cur.execute('insert into members (badge_serial, badge_status, full_name, badge_photo, liability_waiver) values (%s,%s,%s,%s,%s)', insert_data)
    db.commit()
    db.close()

@app.route('/member/<badge_serial>')
def show_member(badge_serial):

    db = get_db()
    cur = db.cursor()
    cur.execute('select badge_serial,full_name from members where badge_serial = %s', (badge_serial,))
    entries = cur.fetchall()

    #
    ## Stripe Stuff, Meetup Stuff goes here
    #

    return render_template('show_member.html', entries=entries)

@app.route('/member/photo/<badge_serial>.jpg')
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
    return redirect("/validate", code=302)

@app.route('/validate')
def validate():
    return render_template('validate.html')

@app.route('/validate/manual')
def validate_manual():
    return render_template('validate_manual.html')
