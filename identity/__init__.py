import base64
import bcrypt
import datetime
import io
import json
import logging
import smtplib
import time
import requests
import urllib

from email.message import EmailMessage
from functools import wraps
from .crypto import SettingsUtil, CryptoUtil
from .models import member

from authlib.integrations.flask_client import OAuth
from authlib.integrations.base_client.errors import OAuthError

try:
    import identity.config as config
except Exception:
    print('ERROR', 'Missing "config.py" file. See https://github.com/synshop/ShopIdentifyer/ for info')
    quit()

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Think about moving to pymysql
import MySQLdb as mysql
import MySQLdb.cursors

from flask import Flask, request, g, flash, redirect, make_response, render_template, jsonify, session, url_for

ENCRYPTION_KEY = SettingsUtil.EncryptionKey.get()

app = Flask(__name__)

try:
    app.secret_key = CryptoUtil.decrypt(config.ENCRYPTED_SESSION_KEY, ENCRYPTION_KEY)
except Exception as e:
    print('ERROR', 'Failed to decrypt "ENCRYPTED_" config variables in "config.py".  Error was:', e)
    quit()

# Encrypted Configuration
app.config['STRIPE_TOKEN'] = CryptoUtil.decrypt(config.ENCRYPTED_STRIPE_TOKEN, ENCRYPTION_KEY)
app.config['DATABASE_PASSWORD'] = CryptoUtil.decrypt(config.ENCRYPTED_DATABASE_PASSWORD, ENCRYPTION_KEY)
app.config['STRIPE_CACHE_REBUILD_CRON'] = config.STRIPE_CACHE_REBUILD_CRON
app.config['MEMBERS_TABLE_REFRESH_CRON'] = config.MEMBERS_TABLE_REFRESH_CRON
app.config['STRIPE_CACHE_DEACTIVATE_CRON'] = config.STRIPE_CACHE_DEACTIVATE_CRON
app.config['SMTP_USERNAME'] = CryptoUtil.decrypt(config.ENCRYPTED_SMTP_USERNAME, ENCRYPTION_KEY)
app.config['SMTP_PASSWORD'] = CryptoUtil.decrypt(config.ENCRYPTED_SMTP_PASSWORD, ENCRYPTION_KEY)
app.config['DISCORD_BOT_TOKEN'] = CryptoUtil.decrypt(config.ENCRYPTED_DISCORD_BOT_TOKEN, ENCRYPTION_KEY)
app.config['AUTH0_CLIENT_SECRET'] = CryptoUtil.decrypt(config.ENCRYPTED_AUTH0_CLIENT_SECRET, ENCRYPTION_KEY)

# Plaintext Configuration
app.config['STRIPE_VERSION'] = config.STRIPE_VERSION
app.config['SMTP_SERVER'] = config.SMTP_SERVER
app.config['SMTP_PORT'] = config.SMTP_PORT

app.config["DISCORD_MANAGE_ROLES"] = config.DISCORD_MANAGE_ROLES
app.config['DISCORD_GUILD_ID'] = config.DISCORD_GUILD_ID
app.config['DISCORD_ROLE_PAID_MEMBER'] = config.DISCORD_ROLE_PAID_MEMBER
app.config['DISCORD_ROLE_VETTED_MEMBER'] = config.DISCORD_ROLE_VETTED_MEMBER

app.config['LOG_FILE'] = config.LOG_FILE
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=12)

app.config['AUTH0_CLIENT_ID'] = config.AUTH0_CLIENT_ID
app.config['AUTH0_DOMAIN'] = config.AUTH0_DOMAIN

# Logging
file_handler = logging.FileHandler(app.config['LOG_FILE'])
file_handler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
file_handler.setLevel(logging.INFO)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(file_handler)

app.logger.info("------------------------------")
app.logger.info("SYN Shop Id Started...")
app.logger.info("------------------------------")

# Imports down here so that they can see the app.config elements
import identity.stripe

oauth = OAuth(app)

oauth.register(
    "auth0",
    client_id=app.config['AUTH0_CLIENT_ID'],
    client_secret=app.config['AUTH0_CLIENT_SECRET'],
    client_kwargs={
        "scope": "openid profile email",
    },
    server_metadata_url=f'https://{app.config["AUTH0_DOMAIN"]}/.well-known/openid-configuration',
)

def connect_db():
    return mysql.connect(
        host=config.DATABASE_HOST,
        user=config.DATABASE_USER,
        passwd=app.config["DATABASE_PASSWORD"],
        db=config.DATABASE_SCHEMA
    )


def get_db():
    if not hasattr(g, 'mysql_db'):
        g.mysql_db = connect_db()
    return g.mysql_db


@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'mysql_db'):
        g.mysql_db.close()


# Start cron tasks
s1 = BackgroundScheduler()

# This helps with stripe information lookup performance
@s1.scheduled_job(CronTrigger.from_crontab(app.config['STRIPE_CACHE_REBUILD_CRON']))
def rebuild_stripe_cache():
    app.logger.info("rebuilding stripe cache")

    member_array = identity.stripe.get_stripe_customers()

    with app.app_context():
        db = get_db()

        cur = db.cursor()
        cur.execute("delete from stripe_cache")
        db.commit()

        for member in member_array:

            cur = db.cursor()
            cur.execute("insert into stripe_cache values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s)",
            (
                member['stripe_id'], 
                member['stripe_created_on'],
                member['stripe_email'],
                member['stripe_full_name'],
                member['stripe_discord_username'],
                member['stripe_last_payment_status'],
                member['stripe_subscription_id'], 
                member['stripe_subscription_description'],
                member['stripe_subscription_status'], 
                member['stripe_subscription_created_on'],
                member['stripe_coupon_description']
            ))

        db.commit()
    
    put_kv_item('stripe_cache_rebuild',datetime.datetime.now())
    app.logger.info("finished rebuilding stripe cache")


# Rebuild members table attributes from stripe_cache
@s1.scheduled_job(CronTrigger.from_crontab(app.config['MEMBERS_TABLE_REFRESH_CRON']))
def refresh_members_table():
    app.logger.info("updating members table")

    with app.app_context():
        db = get_db()

        cur = db.cursor()
        cur.execute("select stripe_id from stripe_cache")
        members = cur.fetchall()
        for member in members:
            pass



# Archive (set m.status to INACTIVE) for members w/o a subscription
# and send a nightly email report
@s1.scheduled_job(CronTrigger.from_crontab(app.config['STRIPE_CACHE_DEACTIVATE_CRON']))
def archive_members_no_sub():
    with app.app_context():

        app.logger.info("[ARCHIVE MEMBERS] - Starting archiving process...")
        db = get_db()
        cur = db.cursor()
        sql = 'select m.stripe_id, m.full_name, created_on, m.discord_username from members m where m.stripe_id not in (select stripe_id from stripe_cache) and m.member_status = "ACTIVE"'

        cur.execute(sql)
        members = cur.fetchall()

        if len(members) != 0:

            for member in members:
                send_member_deactivation_email(member)

                # Remove Vetted and Paid Member Discord Roles if member has a discord handle
                if member[3] != None and app.config["DISCORD_MANAGE_ROLES"]:
                    app.logger.info("[ARCHIVE MEMBERS] - Removing Discord Roles for " + member[0])
                    discord_id = get_member_discord_id(member[3])
                    unassign_discord_role(app.config['DISCORD_ROLE_PAID_MEMBER'], discord_id)
                    unassign_discord_role(app.config['DISCORD_ROLE_VETTED_MEMBER'], discord_id)

            # Do the deactivation
            sql_stmt = 'update members set member_status = "INACTIVE", is_vetted = "NOT VETTED" where stripe_id = %s'
            cur.execute(sql_stmt,(member[0],))
            db.commit()
        else:
            app.logger.info("[ARCHIVE MEMBERS] - No members need archiving.")


if config.SCHEDULER_ENABLED == True:
    s1.start()


# End cron tasks

# Testing Only
def m_inspect_user(email=None):
    member_array = identity.stripe.m_inspect_user(email)


# Push a value in the k,v store
def put_kv_item(k=None,v=None):
    with app.app_context():

        try:
            db = get_db()
            cur = db.cursor()

            s = "INSERT INTO kv_store (k,v) VALUES(%s,%s) ON DUPLICATE KEY UPDATE k=%s, v=%s"
            cur.execute(s, (k,v,k,v))
            db.commit()
            return True
        except Exception as e:
            print(e)
            return False


# Get a value from the k,v store
def get_kv_item(k=None):
    with app.app_context():

        try:
            db = get_db()
            cur = db.cursor()

            stmt = "select v from kv_store where k = %s"
            cur.execute(stmt, (k,))
            entry = cur.fetchone()
            return entry[0]
        except:
            return None

# Determine if user is allowed to log in
def is_admin(email=None):
    with app.app_context():

        try:
            db = get_db()
            cur = db.cursor()

            stmt = "select email from admins where email = %s"
            cur.execute(stmt, (email,))
            entries = cur.fetchall()
            if entries[0][0] == email:
                return True
            else:
                return False
        except Exception as e:
            app.logger.info(e)
            return False
   

# Send a nightly report
def send_member_deactivation_email(member):
    has_tokens = member_has_authorized_rfid(member[0])

    email_subject = "[ARCHIVING MEMBER] - %s no longer has a Stripe subscription" % (member[1],)
    email_body = """
    
    Full Name:
    %s
    
    Account Created On:
    %s

    Has RFID Token(s)
    %s

    """ % (member[1], member[2], has_tokens)

    if config.SMTP_SEND_EMAIL:
        app.logger.info("Sending alert email about archiving a member")
        msg = EmailMessage()
        msg["to"] = config.SMTP_ALERT_TO
        msg["from"] = config.SMTP_ALERT_FROM
        msg["Subject"] = email_subject
        msg.set_content(email_body)
        with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT) as smtp:
            smtp.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
            smtp.send_message(msg)
    else:
        log_message = "[ARCHIVING MEMBERS][EMAIL DISABLED] - Deactivating %s in the system, Has RFIDs = %s" % (
            member[0], has_tokens)
        app.logger.info(log_message)


# Send alert email about a member swiping in
# but is not in good standing
def send_payment_alert_email(sub_id=None):
    stripe_info = identity.stripe.get_realtime_stripe_info(sub_id)
    member = get_member(stripe_info['stripe_id'])

    email_body_data = (
        member['full_name'],
        stripe_info['stripe_subscription_description'],
        stripe_info['stripe_last_payment_status']
    )

    email_subject = "[DOOR ACCESS ALERT] - %s swiped in but has a Stripe issue" % (member['full_name'],)
    email_body = """
    The following member swiped in but their Stripe status is delinquent
    or in a Paused membership state (or they have a Free membership):

    Name:
    %s
    
    Stripe Subscription:
    %s
    
    Last Payment Status:
    %s

    """ % email_body_data

    if config.SMTP_SEND_EMAIL:
        app.logger.info("Sending alert email regarding a delinquent door swipe")
        msg = EmailMessage()
        msg["to"] = config.SMTP_ALERT_TO
        msg["from"] = config.SMTP_ALERT_FROM
        msg["Subject"] = email_subject
        msg.set_content(email_body)
        with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT) as smtp:
            smtp.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
            smtp.send_message(msg)
    else:
        log_message = "[EMAIL DISABLED] - Logging swipe event for delinquent member %s" % (stripe_info['stripe_id'],)
        app.logger.info(log_message)

    # Send an alert email about a valid door access event


def send_door_access_alert_email(sub_id=None):
    stripe_info = identity.stripe.get_realtime_stripe_info(sub_id)
    member = get_member(stripe_info['stripe_id'])

    email_body_data = (
        member['full_name'],
        stripe_info['stripe_subscription_description'],
        stripe_info['stripe_last_payment_status'],
    )

    email_subject = "[DOOR ACCESS ALERT] - %s swiped in" % (member['full_name'],)
    email_body = """
    The following member swiped in:

    Name:
    %s
    
    Stripe Subscription:
    %s
    
    Last Payment Status:
    %s

    """ % email_body_data

    if config.SMTP_SEND_EMAIL:
        app.logger.info("[DOOR ACCESS ALERT] - %s swiped in" % (member['full_name'],))
        msg = EmailMessage()
        msg["to"] = config.SMTP_ALERT_TO
        msg["from"] = config.SMTP_ALERT_FROM
        msg["Subject"] = email_subject
        msg.set_content(email_body)
        with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT) as smtp:
            smtp.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
            smtp.send_message(msg)
    else:
        log_message = "[EMAIL DISABLED] - Logging swipe event for valid member %s" % (stripe_info['stripe_id'],)
        app.logger.info(log_message)


# Send alert email about a rfid token swiping in
# but is not assigned to a member in the system
def send_na_stripe_id_alert_email(rfid_id_token_hex=None):
    if config.SMTP_SEND_EMAIL:
        app.logger.info("Sending alert email regarding a delinquent door swipe")

        email_subject = "[UNASSIGNED RFID ALERT] - The token %s is being used to swipe in but is not attached to a member" % (
            rfid_id_token_hex,)
        email_body = "NO STRIPE INFORMATION IS AVAILABLE FOR RFID TOKEN %s" % (rfid_id_token_hex,)

        msg = EmailMessage()
        msg["to"] = config.SMTP_ALERT_TO
        msg["from"] = config.SMTP_ALERT_FROM
        msg["Subject"] = email_subject
        msg.set_content(email_body)
        with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT) as smtp:
            smtp.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
            smtp.send_message(msg)
    else:
        log_message = "[EMAIL DISABLED] - The token %s is being used to swipe in but is not attached to a member" % (
            rfid_id_token_hex,)
        app.logger.info(log_message)


# Returns True if user has an RFID token in the access control system
def member_has_authorized_rfid(stripe_id=None):
    try:
        db = get_db()
        cur = db.cursor()
        stmt = "select count(*) from rfid_tokens where stripe_id = %s"
        cur.execute(stmt, (stripe_id,))
        entry = cur.fetchone()

        if entry[0] > 0:
            return True
        else:
            return False
    except:
        return False


# Get a member's discord nickname for displaying on Kiosk
def get_member_discord_nickname(discord_username=None):

    if discord_username == "None" or discord_username == "":
        return "No Discord Username"

    # member is still using old discord name
    if "#" in discord_username:
        (username, discriminator) = discord_username.split("#")
        encoded_name = urllib.parse.quote(username)
    else:
        encoded_name = urllib.parse.quote(discord_username)

    GUILD_ID = app.config['DISCORD_GUILD_ID']
    TOKEN = app.config['DISCORD_BOT_TOKEN']

    headers={'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'}
    url = f'https://discord.com/api/guilds/{GUILD_ID}/members/search?limit=1&query={encoded_name}'
    results = requests.get(url,headers=headers)

    if len(results.json()) > 0:
        user = results.json()[0]
        if user['nick'] == None:
            if user['user']['global_name'] == None:
                return user['user']['username']
            else:
                return user['user']['global_name']
        else:
            return user['nick']
    else:
        return "No Discord Username"
    

# Convert a given member's discord username 
# (either with or without the #discriminator)
# into their 18 digit discord id
def get_member_discord_id(discord_username=None):

    if discord_username == "None" or discord_username == "":
        return "000000000000000000"

    if "#" in discord_username:
        (username, discriminator) = discord_username.split("#")
        encoded_name = urllib.parse.quote(username)
    else:
        encoded_name = urllib.parse.quote(discord_username)

    GUILD_ID = app.config['DISCORD_GUILD_ID']
    TOKEN = app.config['DISCORD_BOT_TOKEN']

    url = f'https://discord.com/api/v10/guilds/{GUILD_ID}/members/search?limit=10&query={encoded_name}'
    result = requests.get(url, headers={'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'})

    if result.json() != []:
        return result.json()[0]['user']['id']
    else:
        return "000000000000000000"

# Remove a discord role from a member
def unassign_discord_role(role_id=None, discord_id=None):
    GUILD_ID = app.config['DISCORD_GUILD_ID']
    TOKEN = app.config['DISCORD_BOT_TOKEN']
    app.logger.info("[DISCORD] - unassigning role %s to user %s" % (role_id, discord_id))
    url = f'https://discord.com/api/v10/guilds/{GUILD_ID}/members/{discord_id}/roles/{role_id}'
    result = requests.delete(url, headers={'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'})
    return result


# Assign a discord role to a member
def assign_discord_role(role_id=None, discord_id=None):
    GUILD_ID = app.config['DISCORD_GUILD_ID']
    TOKEN = app.config['DISCORD_BOT_TOKEN']
    app.logger.info("[DISCORD] - assigning role %s to user %s" % (role_id, discord_id))
    url = f'https://discord.com/api/v10/guilds/{GUILD_ID}/members/{discord_id}/roles/{role_id}'
    result = requests.put(url, headers={'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'})
    return result


# Manual process to remove all Vetted and Paid discord roles
# from ALL users
def m_remove_discord_roles():
    GUILD_ID = app.config['DISCORD_GUILD_ID']
    TOKEN = app.config['DISCORD_BOT_TOKEN']

    url = f'https://discord.com/api/v10/guilds/{GUILD_ID}/members?limit=999'
    result = requests.get(url, headers={'Authorization': f'Bot {TOKEN}', 'Content-Type': 'application/json'})

    for y in result.json():
        unassign_discord_role(role_id=app.config["DISCORD_ROLE_PAID_MEMBER"], discord_id=y['user']['id'])

        # Don't remove VegasVader 
        if y['user']['id'] != "494679297215430657":
            unassign_discord_role(role_id=app.config["DISCORD_ROLE_VETTED_MEMBER"], discord_id=y['user']['id'])


# Manual process to add Vetted and Paid discord roles
# to correct users
def m_add_all_discord_roles():
    with app.app_context():
        db = get_db()
        cur = db.cursor()

        # Get discord handles for Vetted Members
        stmt = 'select discord_handle from members where IS_VETTED = "VETTED" and discord_handle IS NOT NULL'
        cur.execute(stmt)
        for member in cur.fetchall():
            discord_id = get_member_discord_id(member[0])
            assign_discord_role(app.config["DISCORD_ROLE_VETTED_MEMBER"], discord_id)
            time.sleep(5)

        # Get discord handles for ACTIVE Members with valid Subscription Plans
        stmt = 'select m.discord_handle, m.stripe_id, sc.subscription_description from members m, stripe_cache sc ' \
               'where m.stripe_id = sc.stripe_id AND m.member_status = "ACTIVE" and m.discord_handle IS NOT NULL '
        cur.execute(stmt)
        for member in cur.fetchall():
            discord_id = get_member_discord_id(member[0])
            assign_discord_role(app.config["DISCORD_ROLE_PAID_MEMBER"], discord_id)
            time.sleep(5)


# Convert a given stripe_id to its current subscription_id
def get_subscription_id_from_stripe_cache(stripe_id=None):
    db = get_db()
    cur = db.cursor()
    sql_stmt = "select subscription_id from stripe_cache where stripe_id = %s"
    cur.execute(sql_stmt, (stripe_id,))

    return cur.fetchall()[0][0]


# Manually insert a new RFID token into the system
def insert_new_rfid_token_record(eb_id=None, rfid_token_hex=None, rfid_token_comment="PRIMARY"):
    db = get_db()
    cur = db.cursor()
    sql_stmt = "insert into rfid_tokens (eb_id,rfid_token_hex,rfid_token_comment,eb_status) values (%s,%s,%s,%s)"
    cur.execute(sql_stmt, (eb_id, rfid_token_hex, rfid_token_comment, "ACTIVE"))
    db.commit()


# Attach a RFID token to a member
def assign_rfid_token(eb_id=None, stripe_id=None):
    db = get_db()
    cur = db.cursor()
    sql_stmt = "update rfid_tokens set stripe_id = %s, status = 'ASSIGNED' where eb_id = %s"
    cur.execute(sql_stmt, (stripe_id, eb_id))
    db.commit()


# Detach a RFID token from a member
def unassign_rfid_token(eb_id):
    db = get_db()
    cur = db.cursor()
    sql_stmt = "update rfid_tokens set stripe_id = NULL, status = 'UNASSIGNED' where eb_id = %s"
    cur.execute(sql_stmt, (eb_id,))
    db.commit()


# Get a list of unassigned tokens
def get_unassigned_rfid_tokens():
    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)
    sql_stmt = 'select eb_id, rfid_token_hex, created_on, eb_status from rfid_tokens where status = "UNASSIGNED" order by eb_id'
    cur.execute(sql_stmt)
    return cur.fetchall()

# Get a list of assigned tokens
def get_assigned_rfid_tokens():
    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)
    sql_stmt = 'select r.eb_id, r.rfid_token_hex, r.rfid_token_comment, r.created_on, r.eb_status, r.status, m.full_name, m.stripe_id from rfid_tokens r, members m where r.stripe_id = m.stripe_id order by r.eb_id'
    cur.execute(sql_stmt)
    return cur.fetchall()

# Get all the RFID Tokens in the system
def get_all_rfid_tokens():
    tokens = {}
    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)
    sql = """select r.rfid_token_hex,r.eb_id, r.eb_status, sc.full_name, r.status, r.stripe_id 
        from rfid_tokens r, stripe_cache sc where r.stripe_id = sc.stripe_id order 
        by r.eb_id, sc.full_name"""
    
    cur.execute(sql)
    return(cur.fetchall())

# Get the attributes for a given token
def get_rfid_token_attributes(rfid_token_hex=None):
    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)
    sql_stmt = 'select * from rfid_tokens where rfid_token_hex = %s'
    cur.execute(sql_stmt, (rfid_token_hex,))
    return cur.fetchone()


# Update RFID Token Attributes
def update_rfid_token_attributes(request=None):
    eb_status = request.form.get("eb_status")
    system_status = request.form.get("system_status")
    rfid_token_comment = request.form.get("rfid_token_comment")
    rfid_token_hex = request.form.get("rfid_token_hex")
    eb_id = request.form.get("eb_id")

    if eb_status == "INACTIVE":
        eb_id = None

    if eb_id == "None":
        eb_id = None

    db = get_db()
    cur = db.cursor()
    sql_stmt = 'update rfid_tokens set eb_status = %s, status = %s, rfid_token_comment = %s, eb_id = %s where ' \
               'rfid_token_hex = %s '
    cur.execute(sql_stmt, (eb_status, system_status, rfid_token_comment, eb_id, rfid_token_hex))

    db.commit()


# Get a list of users to assign a RFID (need to be VETTED and ACTIVE)
def get_members_for_rfid_association():
    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)
    sql_stmt = "select m.stripe_id, sc.full_name, sc.email, m.is_vetted from members m, stripe_cache sc where " \
               "m.stripe_id = sc.stripe_id and m.member_status = 'ACTIVE' and is_vetted = 'VETTED'"
    cur.execute(sql_stmt)
    return cur.fetchall()


# Return the list of members who need onboarding
def get_members_to_onboard():
    entries_x = []

    db = get_db()
    cur = db.cursor()

    sql_stmt = """
        SELECT
            stripe_id, 
            created_on, 
            email, 
            full_name,
            last_payment_status,
            subscription_description,
            subscription_status
        FROM 
            stripe_cache 
        WHERE
            stripe_id 
        NOT IN
            (SELECT stripe_id FROM members) 
        ORDER BY 
            subscription_description, full_name asc
    """
    cur.execute(sql_stmt)
    rows = cur.fetchall()

    for row in rows:

        entry_dict = dict(
            stripe_id=row[0],
            stripe_email=row[2],
            drupal_legal_name=row[3],
            stripe_last_payment_status=row[4],
            stripe_subscription_description=row[5],
            stripe_subscription_status=row[6])

        entries_x.append(entry_dict)

    return entries_x


# Get a list of on-boarded, INACTIVE members
def get_inactive_members():
    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)
    sql_stmt = """
            SELECT 
            m.stripe_id,
            m.full_name,
            m.is_vetted,
            s.subscription_id,
            s.subscription_description,
            s.last_payment_status
        FROM 
            members m
        LEFT JOIN
            stripe_cache s on s.stripe_id = m.stripe_id
        WHERE
            m.member_status = "INACTIVE"
        ORDER BY
            s.subscription_description desc
    """

    cur.execute(sql_stmt)
    members = cur.fetchall()

    return members


# Fetch the rfid_token(s) for a user
def get_member_rfid_tokens(stripe_id=None):
    db = get_db()
    cur = db.cursor()
    sql_stmt = "select rfid_token_hex from rfid_tokens where stripe_id = %s"
    cur.execute(sql_stmt, (stripe_id,))

    rfid_tokens = []

    for entry in cur.fetchall():
        rfid_tokens.append(entry[0])

    return ", ".join(rfid_tokens)


# Insert a newly on-boarded member into the system
def insert_new_member(stripe_id=None, r=None):

    insert_data = (
        stripe_id,
        'ACTIVE',
        r.form.get('full_name'),
        r.form.get('discord_username'),
        r.form.get('mobile'),
        r.form.get('emergency_contact_name'),
        r.form.get('emergency_contact_mobile'),
        r.form.get('is_vetted', 'NOT VETTED'),
        r.form.get('locker_num')
    )

    db = connect_db()
    cur = db.cursor()
    cur.execute(
        'insert into members (stripe_id, member_status, full_name, discord_username, mobile,'
        'emergency_contact_name, emergency_contact_mobile, is_vetted, locker_num)'
        'values (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        insert_data)
    db.commit()
    db.close()
    
    if app.config["DISCORD_MANAGE_ROLES"] and r.form.get('discord_username') != None:

        discord_id = get_member_discord_id(r.form.get('discord_username'))
        pm = app.config["DISCORD_ROLE_PAID_MEMBER"]
        vm = app.config["DISCORD_ROLE_VETTED_MEMBER"]

        # Add Paid Member Role
        assign_discord_role(pm,discord_id)

        # Add Vetted Member Role if the member is vetted
        if r.form.get('is_vetted') == "VETTED":
            assign_discord_role(vm,discord_id)

    return True


def get_new_member(stripe_id=None):
        db = connect_db()
        cur = db.cursor(MySQLdb.cursors.DictCursor)
        sql_stmt = 'select stripe_id, email, full_name, last_payment_status, subscription_description, ' \
                'subscription_status, discord_username from stripe_cache where stripe_id = %s '
        cur.execute(sql_stmt, (stripe_id,))
        member = cur.fetchall()[0]

        return member

# Fetch a member 'object'
def get_member(stripe_id=None):

    member = {}
    subscription_id = get_subscription_id_from_stripe_cache(stripe_id)

    db = get_db()
    cur = db.cursor()
    if config.STRIPE_FETCH_REALTIME_UPDATES:
        app.logger.info("[STRIPE] - updating real-time stripe information for %s" % (stripe_id,))
        stripe_info = identity.stripe.get_realtime_stripe_info(subscription_id)

        member["stripe_status"] = stripe_info['stripe_subscription_status'].upper()
        member['stripe_plan'] = stripe_info['stripe_subscription_description'].upper()
        member['stripe_email'] = stripe_info['stripe_email']

        sql_stmt = 'update stripe_cache set last_payment_status = %s, subscription_status = %s WHERE ' \
                   'stripe_id = %s '
        cur.execute(sql_stmt,
                    (stripe_info['stripe_last_payment_status'], stripe_info['stripe_subscription_status'], stripe_id))
        db.commit()
    else:
        app.logger.info('STRIPE_FETCH_REALTIME_UPDATES set to false, user Stripe status not updated.')

    sql_stmt = """
            SELECT 
                m.stripe_id,
                m.member_status,
                m.is_vetted,
                m.created_on,
                m.changed_on,
                m.locker_num,
                m.led_color,
                m.mobile,
                m.emergency_contact_name,
                m.emergency_contact_mobile,
                sc.full_name,
                sc.email,
                sc.subscription_status,
                sc.last_payment_status,
                sc.discord_username
            FROM
                members m,
                stripe_cache sc
            WHERE
                m.stripe_id = sc.stripe_id and
                sc.stripe_id = %s
            """
    
    cur = db.cursor(MySQLdb.cursors.DictCursor)
    cur.execute(sql_stmt, (stripe_id,))
    entries = cur.fetchall()
    entry = entries[0]
    
    member.update(entry)

    member['rfid_tokens'] = get_member_rfid_tokens(stripe_id)
    member["stripe_subscription_id"] = subscription_id
    member["door_access"] = member_has_authorized_rfid(stripe_id)
    member["kiosk_username"] = get_member_discord_nickname(member["discord_username"])
    
    return member


# Update an existing member 'object'
def update_member(request=None):
    db = connect_db()
    cur = db.cursor()

    stripe_id = request.form.get('stripe_id')

    update_data = (
        request.form.get('member_status'),
        request.form.get('is_vetted', 'NOT VETTED'),
        request.form.get('mobile'),
        request.form.get('emergency_contact_name'),
        request.form.get('emergency_contact_mobile'),
        request.form.get('locker_num'),
        request.form.get('led_color'),
        stripe_id
    )

    sql_stmt = 'update members set member_status=%s,is_vetted=%s,mobile=%s,' \
               'emergency_contact_name=%s,emergency_contact_mobile=%s,locker_num=%s,' \
               'led_color=%s where stripe_id=%s'

    try:
        x = cur.execute(sql_stmt, update_data)
    except Exception as e:
        print(e)

    db.commit()
    db.close()

    if app.config["DISCORD_MANAGE_ROLES"] and request.form.get('discord_username') != "":

        discord_id = get_member_discord_id(request.form.get('discord_username'))
        pm = app.config["DISCORD_ROLE_PAID_MEMBER"]
        vm = app.config["DISCORD_ROLE_VETTED_MEMBER"]

        # Add Paid Member Role
        assign_discord_role(pm,discord_id)

        # Add Vetted Member Role if the member is vetted
        if request.form.get('is_vetted') == "VETTED":
            assign_discord_role(vm,discord_id)
        else:
            unassign_discord_role(vm,discord_id)


# Push log event into database
def insert_log_event(request=None):
    rfid_token_hex = request.form['badge']
    swipe_status = request.form['result']

    if swipe_status == "granted":
        event_type = "ACCESS_GRANT"
    elif swipe_status == "denied":
        event_type = "ACCESS_DENY"
    else:
        # be defensive, only granted or denied will be processed, all others rejected
        app.logger.info('insert_log_event() received invalid event type. Got "' + swipe_status +
                        '", expecting "granted" or "denied"')
        quit()

    # Default log values
    stripe_id = "NA"
    rfid_token_comment = "NONE"
    member = {
        'name': 'NA', 
        'handle': 'unknown ' + swipe_status, 
        'color': 'red', 
        'event_type': event_type
    }

    db = get_db()
    cur = db.cursor()

    sql_stmt = "select stripe_id, rfid_token_comment, eb_id from rfid_tokens where rfid_token_hex = %s"
    cur.execute(sql_stmt, (rfid_token_hex,))
    entry = cur.fetchone()
    
    if entry != None:
        stripe_id = entry[0]
        rfid_token_comment = entry[1]

        sql_stmt = "select sc.full_name, sc.discord_username from stripe_cache sc where sc.stripe_id = %s"
        cur.execute(sql_stmt, (stripe_id,))
        member_tmp = cur.fetchone()

        if len(member_tmp) > 0:
            color = 'yellow'
            
            member['name'] = member_tmp[0]
            member['handle'] = get_member_discord_nickname(member_tmp[1])
            member['color'] = color
            member['badge'] = rfid_token_hex

    post_alert(member)

    sql_stmt = 'insert into event_log (stripe_id, rfid_token_hex, event_type, rfid_token_comment) values (%s,%s,%s,%s)'
    cur.execute(sql_stmt, (stripe_id, rfid_token_hex, event_type, rfid_token_comment))
    db.commit()

    if stripe_id == 'NA':
        # Send alert email about a rfid token swiping in but is not assigned to a member in the system
        send_na_stripe_id_alert_email(rfid_token_hex)
    else:
        sub_id = get_subscription_id_from_stripe_cache(stripe_id)

        if config.STRIPE_FETCH_REALTIME_UPDATES:
            if identity.stripe.member_is_in_good_standing(sub_id):
                # Send alert email about a member in good standing
                send_door_access_alert_email(sub_id)
            else:
                # Send alert email about a member swiping in but is not in good standing
                send_payment_alert_email(sub_id)
        else:
            app.logger.info('STRIPE_FETCH_REALTIME_UPDATES set to false, no door alert emails sent.')


def post_alert(data):
    if hasattr(config, 'ALERT_URLS'):
        for url in config.ALERT_URLS:
            try:
                http_result = requests.post(config.ALERT_URLS[url], data=data, verify=False)
                app.logger.info('Success posted to' + str(url) + ' at "' + str(config.ALERT_URLS[url]) +
                                '", got response: ' + str(http_result))
            except Exception as e:
                app.logger.info("ERROR: POST to " + str(url) + " Error was: " + str(e))
    else:
        app.logger.info('post_alert() called, but no URLs declared in ALERT_URLS in config.')


# Get latest n rows from the event log (default is 100)
def get_event_log(n=100):
    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)
    sql_stmt = f'''
        select 
            event_log.event_id,
            event_log.stripe_id,
            event_log.rfid_token_hex,
            event_log.created_on,
            event_log.event_type,
            members.full_name,
            event_log.rfid_token_comment
        from 
            event_log
        LEFT JOIN members
        ON
            event_log.stripe_id = members.stripe_id
        ORDER BY 
            event_log.event_id desc
        LIMIT {n}'''
    
    cur.execute(sql_stmt)
    return cur.fetchall()


# Get public membership statistics
def get_public_stats():
    stats = {
        'total_membership': {
            'count': 0,
            'sql': 'select count(*) from stripe_cache'
        },
        'total_free': {
            'count': 0,
            'sql': 'select count(*) from stripe_cache where subscription_description = "Free Membership"'
        },
        'total_paused': {
            'count': 0,
            'sql': 'select count(*) from stripe_cache where subscription_description = "Paused Membership"'
        },
        'total_need_onboarding': {
            'count': 0,
            'sql': 'select count(*) FROM stripe_cache WHERE subscription_description <> "Paused Membership" and '
                   'stripe_id NOT IN (SELECT stripe_id FROM members) '
        },
        'total_vetted': {
            'count': 0,
            'sql': 'SELECT COUNT(*) FROM stripe_cache WHERE subscription_description <> "Paused Membership" AND stripe_id IN (SELECT stripe_id FROM members WHERE IS_VETTED = "VETTED" AND member_status = "ACTIVE");'
        },
        'total_not_vetted': {
            'count': 0,
            'sql': 'SELECT COUNT(*) FROM stripe_cache WHERE subscription_description <> "Paused Membership" AND stripe_id IN (SELECT stripe_id FROM members WHERE IS_VETTED = "NOT VETTED" AND member_status = "ACTIVE");'
        },
        'total_door_access': {
            'count': 0,
            'sql': 'select count(*) from members'
        }
    }

    db = get_db()
    cur = db.cursor()

    for key in stats:
        cur.execute(stats[key]['sql'])
        stats[key]['count'] = cur.fetchall()[0][0]

    return stats


# Build the /admin view
def get_admin_view():
    db = get_db()
    cur = db.cursor(MySQLdb.cursors.DictCursor)
    stmt = """  
        SELECT 
            m.stripe_id,
            s.subscription_id,
            s.full_name,
            m.is_vetted,
            s.email,
            s.subscription_status,
            s.subscription_description,
            s.last_payment_status,
            s.discord_username,
            s.coupon
        FROM 
            members m
        JOIN
            stripe_cache s on s.stripe_id = m.stripe_id
        WHERE
            m.member_status = "ACTIVE"
        AND
            m.stripe_id = s.stripe_id
        ORDER BY
            s.subscription_description, m.full_name
    """
    cur.execute(stmt)
    members = cur.fetchall()
  
    ret_members = []

    for m in members:
        m['has_rfid'] = member_has_authorized_rfid(m['stripe_id']) 
        ret_members.append(m)

    return ret_members


# Decorator for Required Auth
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('logged_in') == False or session.get('logged_in') == None:
            return redirect(url_for("show_index"))
        return f(*args, **kwargs)

    return decorated_function

# Onboarding process - this attempts to pre-populate some fields
# when setting up a new user.
@app.route('/member/new/<stripe_id>', methods=['GET',])
@login_required
def show_onboard_new_member(stripe_id):
    app.logger.info("User %s is onboarding member %s" % (session['email'], stripe_id)) 
    return render_template('new_member.html', member=get_new_member(stripe_id))

# Onboarding process - this attempts to pre-populate some fields
# when setting up a new user.
@app.route('/member/new/<stripe_id>', methods=['POST',])
@login_required
def onboard_new_member(stripe_id):
    insert_new_member(stripe_id, request)
    app.logger.info("User %s successfully on-boarded member %s" % (session['email'], stripe_id))
    return redirect(url_for("show_admin_onboard"))


# Show member details
@app.route('/member/<stripe_id>')
@login_required
def show_member(stripe_id):
    return render_template('show_member.html', member=get_member(stripe_id))


# Edit member details
@app.route('/member/<stripe_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_member_details(stripe_id):
    if request.method == "GET":
        user = get_member(stripe_id)
        app.logger.info("User %s is editing member %s " % (session['email'], stripe_id))
        return render_template('edit_member.html', member=user)

    if request.method == "POST":
        update_member(request)
        app.logger.info("User %s updated member %s" % (session['email'], stripe_id))
        return redirect(url_for("show_admin", _scheme='https', _external=True))


# Get member badge photo
@app.route('/member/<stripe_id>/files/photo.jpg')
@login_required
def show_member_photo(stripe_id):
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("select badge_photo from members where stripe_id = %s", (stripe_id,))
        photo = cur.fetchone()[0]
        response = make_response(photo)
        response.headers['Content-Description'] = 'Badge Photo'
        response.headers['Content-Type'] = 'image/jpeg'
        response.headers['Content-Disposition'] = 'inline'
    except Exception as e:
        with open("./identity/static/images/syn_shop_badge_logo.png", mode='rb') as file:
            photo = file.read()
            response = make_response(photo)
            response.headers['Content-Description'] = 'Badge Photo'
            response.headers['Content-Type'] = 'image/jpeg'
            response.headers['Content-Disposition'] = 'inline'

    return response


# Door Access Event Webhook
@app.route('/logevent', methods=['POST'])
def show_event_log():
    insert_log_event(request)
    return jsonify({"status": 200})


# Landing Page Routes
@app.route('/')
def show_index():
    if session.get('logged_in') == False or session.get('logged_in') == None:
        return render_template('index.html', stats=get_public_stats())
    else:
        return redirect(url_for('show_admin'))


@app.route("/callback", methods=["GET", "POST"])
def auth0_callback():
    try:
        token = oauth.auth0.authorize_access_token()
        session["user"] = token
        email = token['userinfo']['email']

        if is_admin(email):
            app.logger.info(f'CB - {email} is classified as an admin, redirecting to /admin...')
            session['logged_in'] = True
            session['email'] = email
            return redirect(url_for("show_admin"))
        else:
            app.logger.info(f'CB - {email} IS NOT classified as an admin, redirecting to /...')
            session['logged_in'] = False
            print(session)
            return redirect(url_for("show_index"))

    except OAuthError as e:
        app.logger.info(e)
        return render_template("index.html")


# API for public stats, JSON
@app.route('/api/public_stats')
def api_public_stats():
    statsClean = {}
    for k, v in get_public_stats().items():
        statsClean[k] = v['count']
    return jsonify(statsClean)


@app.route('/login', methods=['GET', 'POST'])
def show_login():
    redirect_uri=url_for("auth0_callback", _external=True)
    return oauth.auth0.authorize_redirect(redirect_uri)


@app.route('/logout')
def show_logout():
    session.pop('logged_in', False)
    session.pop('email', False)
    return redirect(url_for('show_index'))


@app.route('/admin')
@login_required
def show_admin():
    e = get_admin_view()
    el = get_event_log(n=5)
    us = get_public_stats()
    return render_template('admin.html', entries=e, el=el, us=us)


@app.route('/admin/onboard')
@login_required
def show_admin_onboard():

    m = get_members_to_onboard()
    s = get_public_stats()
    scr = get_kv_item('stripe_cache_rebuild')
    return render_template('onboard.html',members=m, stats=s, stripe_cache_rebuild=scr)


@app.route('/admin/dooraccess', methods=['GET'])
@login_required
def show_door_access_get():
    u = get_unassigned_rfid_tokens()
    a = get_assigned_rfid_tokens()
    return render_template('door_access.html', unassigned=u, assigned=a)


@app.route('/admin/dooraccess/assign', methods=['GET'])
@login_required
def show_door_access_assign_get():
    eb_id = request.args.get('eb_id')
    rfid_token_hex = request.args.get('rfid_token_hex')
    return render_template('door_access_assign.html', entries=get_members_for_rfid_association(),e=eb_id, r=rfid_token_hex) 


@app.route('/admin/dooraccess/assign', methods=['POST'])
@login_required
def show_door_access_assign_post():
    stripe_id = request.form.get('stripe_id')
    eb_id = request.form.get('eb_id')
    assign_rfid_token(eb_id=eb_id, stripe_id=stripe_id)
    return redirect(url_for('show_door_access_get'))


@app.route('/admin/dooraccess/newtoken', methods=['GET'])
@login_required
def show_door_access_new_token():
    return render_template("door_access_new_token.html")


@app.route('/admin/dooraccess/newtoken', methods=['POST'])
@login_required
def show_door_access_new_token_post():
    insert_new_rfid_token_record(eb_id=request.form['eb_id'], rfid_token_hex=request.form['rfid_token_hex'],
                                 rfid_token_comment=request.form['rfid_token_comment'])
    return redirect(url_for('show_door_access_get'))


@app.route('/admin/dooraccess/tokenattributes/edit', methods=['GET'])
@login_required
def show_door_access_token_attributes_get():
    rfid_token_hex = request.args.get('rfid_token_hex')
    return render_template('door_access_modify_attributes.html', e=get_rfid_token_attributes(rfid_token_hex))


@app.route('/admin/dooraccess/tokenattributes/edit', methods=['POST'])
@login_required
def show_door_access_token_attributes_post():
    update_rfid_token_attributes(request)
    return redirect(url_for('show_door_access_get'))


@app.route('/admin/dooraccess/tokenattributes/transfer', methods=['POST'])
@login_required
def show_door_access_token_unassign():
    unassign_rfid_token(request.form['eb_id'])
    return redirect(url_for('show_door_access_get'))

@app.route('/admin/eventlog', methods=['GET'])
@login_required
def show_eventlog_landing():
    return render_template('event_log.html', entries=get_event_log())


@app.route('/admin/reactivate', methods=['GET'])
@login_required
def show_reactivate_member():
    return render_template('reactivate.html', inactive_members=get_inactive_members())
