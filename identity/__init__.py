
import serial

import gevent

from crypto import SettingsUtil, CryptoUtil

import config
import MySQLdb as mysql

from flask import Flask, request, session, g, Response
from flask import redirect, url_for, abort, make_response
from flask import render_template, flash

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
    return mysql.connect(host=config.DATABASE_HOST,user=config.DATABASE_USER, passwd=app.config["DATABASE_PASSWORD"],db=config.DATABASE_SCHEMA)

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

@app.route('/member')
def show_member():
    db = get_db()
    cur = db.cursor()
    cur.execute('select * from members')
    entries = cur.fetchall()

    return render_template('show_member.html', entries=entries)

def event_stream():
    ser = serial.Serial(config.SERIAL_DEVICE, config.SERIAL_BAUD_RATE, timeout=1)

    while True:
        gevent.sleep(2)
        str1 = ser.readline()
        if len(str1) > 3:
            yield 'data: %s \n\n' % (str1)
            str1 = None

@app.route('/my_event_source')
def sse_request():
    return Response(event_stream(),mimetype='text/event-stream')

@app.route('/')
def page():
    return render_template('sse.html')

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

@app.route("/member/files/<badge_serial>-wavier.pdf")
def member_wavier(badge_serial):
    db = get_db()
    cur = db.cursor()
    cur.execute("select liability_waiver from members where badge_serial = %s", (badge_serial,))
    wavier = cur.fetchone()

    response = make_response(wavier)
    response.headers['Content-Description'] = 'Liability Wavier'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Content-Type'] = 'application/pdf'
    #response.headers['Content-Disposition'] = 'attachment; filename=liability-wavier.pdf'
    response.headers['Content-Disposition'] = 'inline'


    return response

@app.route('/member/files/<badge_serial>-vetted.pdf')
def member_vetted(badge_serial3):
    pass
