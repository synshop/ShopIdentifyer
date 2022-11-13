from .crypto import SettingsUtil, CryptoUtil
import base64, logging, time, bcrypt, io, datetime, json, smtplib
from PIL import Image as PILImage
from PIL import ImageFilter, ImageEnhance
from functools import wraps
from email.message import EmailMessage
import requests, urllib

try:
    import identity.config as config
except Exception as e:
    config_error = """
        You need to create/install a <project-home>/identity/config.py file and populate it with some values.
        Please see https://github.com/synshop/ShopIdentifyer/blob/master/README.md for more information."""
    app.logger.info(e)
    quit()

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# TODO: Move to svglib
# TODO: Look at using CursorDictRowsMixIn for db operations

# from svgwrite.image import Image
# from svgwrite.shapes import Rect
import MySQLdb as mysql

from flask import Flask, request, g, flash
from flask import redirect,  make_response
from flask import render_template, jsonify
from flask import session, escape, url_for
from flask import send_file

RUN_MODE = 'development'

ENCRYPTION_KEY = SettingsUtil.EncryptionKey.get(RUN_MODE == 'development')

app = Flask(__name__)

app.secret_key = CryptoUtil.decrypt(config.ENCRYPTED_SESSION_KEY,ENCRYPTION_KEY)

# Encrypted Configuration
app.config['STRIPE_TOKEN'] = CryptoUtil.decrypt(config.ENCRYPTED_STRIPE_TOKEN, ENCRYPTION_KEY)
app.config['DATABASE_PASSWORD'] = CryptoUtil.decrypt(config.ENCRYPTED_DATABASE_PASSWORD, ENCRYPTION_KEY)
app.config['STRIPE_CACHE_REFRESH_CRON'] = config.STRIPE_CACHE_REFRESH_CRON
app.config['STRIPE_CACHE_REFRESH_REACHBACK_MIN'] = config.STRIPE_CACHE_REFRESH_REACHBACK_MIN
app.config['STRIPE_CACHE_REBUILD_CRON'] = config.STRIPE_CACHE_REBUILD_CRON
app.config['STRIPE_CACHE_DEACTIVATE_CRON'] = config.STRIPE_CACHE_DEACTIVATE_CRON
app.config['SMTP_USERNAME'] = CryptoUtil.decrypt(config.ENCRYPTED_SMTP_USERNAME,ENCRYPTION_KEY)
app.config['SMTP_PASSWORD'] = CryptoUtil.decrypt(config.ENCRYPTED_SMTP_PASSWORD,ENCRYPTION_KEY)
app.config['DISCORD_BOT_TOKEN'] = CryptoUtil.decrypt(config.ENCRYPTED_DISCORD_BOT_TOKEN,ENCRYPTION_KEY)

# Plaintext Configuration
app.config['SMTP_SERVER'] = config.SMTP_SERVER
app.config['SMTP_PORT'] = config.SMTP_PORT

app.config["DISCORD_MANAGE_ROLES"] = config.DISCORD_MANAGE_ROLES
app.config['DISCORD_GUILD_ID'] = config.DISCORD_GUILD_ID
app.config['DISCORD_ROLE_PAID_MEMBER'] = config.DISCORD_ROLE_PAID_MEMBER
app.config['DISCORD_ROLE_VETTED_MEMBER'] = config.DISCORD_ROLE_VETTED_MEMBER

app.config['LOG_FILE'] = config.LOG_FILE
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=12)

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
import identity.stripe

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
# Currently it runs every ~15 minutes and grabs
# the last 15 minutes of data
@s1.scheduled_job(CronTrigger.from_crontab(app.config['STRIPE_CACHE_REFRESH_CRON']))
def refresh_stripe_cache():

    app.logger.info("refreshing stripe cache")
    member_array = identity.stripe.get_stripe_customers(incremental=True)

    with app.app_context():
        db = get_db()

        for member in member_array:
            cur = db.cursor()

            cur.execute("insert ignore into stripe_cache values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",\
            (member['stripe_id'], member['stripe_created_on'], member['stripe_email'], \
             member['stripe_description'], member['stripe_last_payment_status'],\
             member['stripe_subscription_id'], member['stripe_subscription_product'],\
             member['stripe_subscription_status'], member['stripe_subscription_created_on']))

        db.commit()

    app.logger.info("finished refreshing stripe cache")

@s1.scheduled_job(CronTrigger.from_crontab(app.config['STRIPE_CACHE_REBUILD_CRON']))
def rebuild_stripe_cache():

    app.logger.info("nightly stripe cache rebuild")

    member_array = identity.stripe.get_stripe_customers()

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

# Archive (set m.status to INACTIVE) for members w/o a subscription
# and send a nightly email report
@s1.scheduled_job(CronTrigger.from_crontab(app.config['STRIPE_CACHE_DEACTIVATE_CRON']))
def archive_members_no_sub():
    with app.app_context():
        
        app.logger.info("[ARCHIVE MEMBERS] - Starting archiving process...")
        db = get_db()
        cur = db.cursor()
        sql_stmt = 'select stripe_id, full_name, discord_handle, created_on from members where stripe_id not in (select stripe_id from stripe_cache) and member_status = "ACTIVE"'
        cur.execute(sql_stmt)
        members = cur.fetchall()

        if len(members) != 0:
        
            for member in members:
                send_member_deactivation_email(member)

                # Remove Vetted and Paid Member Discord Roles if member has a discord handle
                if member[2] != None and app.config["DISCORD_MANAGE_ROLES"]:
                    app.logger.info("[ARCHIVE MEMBERS] - Removing Discord Roles for " + member[0])
                    discord_id = get_member_discord_id(member[2])
                    unassign_discord_role(app.config['DISCORD_ROLE_PAID_MEMBER'], discord_id)
                    unassign_discord_role(app.config['DISCORD_ROLE_VETTED_MEMBER'], discord_id)
    
            # Do the deactivation
            sql_stmt = 'update members set member_status = "INACTIVE", is_vetted = "NOT VETTED" where stripe_id not in (select stripe_id from stripe_cache)'
            cur.execute(sql_stmt)
            db.commit()
        else:
            app.logger.info("[ARCHIVE MEMBERS] - No members need archiving.")

if config.SCHEDULER_ENABLED == True:
    s1.start()

# End cron tasks

# Decorator for Required Auth
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('logged_in') == None:
            return redirect(url_for("show_login"))
        return f(*args, **kwargs)
    return decorated_function

# Allow admin users to change their passwords
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
            app.logger.info(e)
            passwords_match = False

        return passwords_match

# Send a nightly report 
def send_member_deactivation_email(member):

    has_tokens = member_has_authorized_rfid(member[0])

    email_subject = "[ARCHIVING MEMBER] - %s no longer has a Stripe subscription" % (member[1],)
    email_body = """
    
    Name:
    %s
    
    Discord Handle:
    %s
    
    Account Created On:
    %s

    Has RFID Token(s)
    %s

    """  % (member[1],member[2],member[3], has_tokens)

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
        log_message = "[ARCHIVING MEMBERS][EMAIL DISABLED] - Deactivating %s in the system, Has RFIDs = %s" % (member[0], has_tokens)
        app.logger.info(log_message)

# Send alert email about a member swiping in
# but is not in good standing
def send_payment_alert_email(sub_id=None):
    
    stripe_info = identity.stripe.get_realtime_stripe_info(sub_id)
    member = get_member(stripe_info['stripe_id'])
    
    email_body_data = (
        member['full_name'], 
        stripe_info['stripe_subscription_product'],
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

    """  % email_body_data

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
        stripe_info['stripe_subscription_product'],
        stripe_info['stripe_last_payment_status']
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

    """  % email_body_data

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

        email_subject = "[UNASSIGNED RFID ALERT] - The token %s is being used to swipe in but is not attached to a member" % (rfid_id_token_hex,)
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
        log_message = "[EMAIL DISABLED] - The token %s is being used to swipe in but is not attached to a member" % (rfid_id_token_hex,)
        app.logger.info(log_message)

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
        else:
            return False
    except:
        return False

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

# Convert a given member's discord handle (username#discrimator) 
# into their 18 digit discord id
def get_member_discord_id(discord_handle=None):

    if discord_handle == "None" or discord_handle == "":
        return "000000000000000000"

    (username, discriminator) = discord_handle.split("#")
    encoded_name = urllib.parse.quote(username)

    GUILD_ID = app.config['DISCORD_GUILD_ID']
    TOKEN = app.config['DISCORD_BOT_TOKEN']

    url = f'https://discord.com/api/v10/guilds/{GUILD_ID}/members/search?limit=10&query={encoded_name}'
    result = requests.get(url,headers={'Authorization': f'Bot {TOKEN}','Content-Type': 'application/json'})
    return result.json()[0]['user']['id']

# Remove a discord role from a member
def unassign_discord_role(role_id=None, discord_id=None):
    GUILD_ID = app.config['DISCORD_GUILD_ID']
    TOKEN = app.config['DISCORD_BOT_TOKEN']
    app.logger.info("[DISCORD] - unassigning role %s to user %s" % (role_id, discord_id))
    url = f'https://discord.com/api/v10/guilds/{GUILD_ID}/members/{discord_id}/roles/{role_id}'
    result = requests.delete(url,headers={'Authorization': f'Bot {TOKEN}','Content-Type': 'application/json'})
    return result

# Assign a discord role to a member
def assign_discord_role(role_id=None, discord_id=None):
    GUILD_ID = app.config['DISCORD_GUILD_ID']
    TOKEN = app.config['DISCORD_BOT_TOKEN']
    app.logger.info("[DISCORD] - assigning role %s to user %s" % (role_id, discord_id))
    url = f'https://discord.com/api/v10/guilds/{GUILD_ID}/members/{discord_id}/roles/{role_id}'
    result = requests.put(url,headers={'Authorization': f'Bot {TOKEN}','Content-Type': 'application/json'})
    return result

# Manual process to remove all Vetted and Paid discord roles
# from ALL users
def m_remove_discord_roles():

    GUILD_ID = app.config['DISCORD_GUILD_ID']
    TOKEN = app.config['DISCORD_BOT_TOKEN']

    url = f'https://discord.com/api/v10/guilds/{GUILD_ID}/members?limit=999'
    result = requests.get(url,headers={'Authorization': f'Bot {TOKEN}','Content-Type': 'application/json'})

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
            assign_discord_role(app.config["DISCORD_ROLE_VETTED_MEMBER"],discord_id)
            time.sleep(5)
        
        # Get discord handles for ACTIVE Members with valid Subscription Plans
        stmt = 'select m.discord_handle, m.stripe_id, sc.stripe_subscription_product from members m, stripe_cache sc where m.stripe_id = sc.stripe_id AND m.member_status = "ACTIVE" and m.discord_handle IS NOT NULL'
        cur.execute(stmt)
        for member in cur.fetchall():
            discord_id = get_member_discord_id(member[0])
            assign_discord_role(app.config["DISCORD_ROLE_PAID_MEMBER"],discord_id)
            time.sleep(5)

# Convert a given stripe_id to its current subscription_id
def get_subscription_id_from_stripe_cache(stripe_id=None):
    db = get_db()
    cur = db.cursor()
    sql_stmt = "select stripe_subscription_id from stripe_cache where stripe_id = %s"
    cur.execute(sql_stmt, (stripe_id,))

    return cur.fetchall()[0][0]

# Mnaully insert a new RFID token into the system 
def insert_new_rfid_token_record(eb_id=None,rfid_token_hex=None,rfid_token_comment="PRIMARY"):
    db = get_db()
    cur = db.cursor()
    sql_stmt = "insert into rfid_tokens (eb_id,rfid_token_hex,rfid_token_comment,eb_status) values (%s,%s,%s,%s)"
    cur.execute(sql_stmt, (eb_id,rfid_token_hex,rfid_token_comment,"ACTIVE"))
    db.commit()

# Attach a RFID token to a member
def assign_rfid_token(eb_id=None,stripe_id=None):
    db = get_db()
    cur = db.cursor()
    sql_stmt = "update rfid_tokens set stripe_id = %s, status = 'ASSIGNED' where eb_id = %s"
    cur.execute(sql_stmt, (stripe_id,eb_id))
    db.commit()

# Detach a RFID token from a member
def unassign_rfid_token(rfid_id_token_hex=None):
    db = get_db()
    cur = db.cursor()
    sql_stmt = "update rfid_tokens set stripe_id = 'NA', status = 'UNASSIGNED', rfid_token_comment = '' where rfid_token_hex = %s"
    cur.execute(sql_stmt, (rfid_id_token_hex,))
    db.commit()

# Get a list of unassigned tokens
def get_unassigned_rfid_tokens():
    db = get_db()
    cur = db.cursor()
    sql_stmt = 'select eb_id,rfid_token_hex,created_on,eb_status from rfid_tokens where status = "UNASSIGNED"'
    cur.execute(sql_stmt)
    return cur.fetchall()

# Get all the RFID Tokens in the system
def get_all_rfid_tokens():
    db = get_db()
    cur = db.cursor()
    sql_stmt = 'select r.rfid_token_hex,r.eb_id,r.eb_status,m.full_name,r.status,r.stripe_id from rfid_tokens r, members m where r.stripe_id = m.stripe_id order by r.eb_id, m.full_name'
    cur.execute(sql_stmt)
    return cur.fetchall()

# Get the attributes for a given token
def get_rfid_token_attributes(rfid_token_hex=None):
    db = get_db()
    cur = db.cursor()
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
    sql_stmt = 'update rfid_tokens set eb_status = %s, status = %s, rfid_token_comment = %s, eb_id = %s where rfid_token_hex = %s'
    cur.execute(sql_stmt, (eb_status,system_status,rfid_token_comment,eb_id,rfid_token_hex))

    db.commit()

# NOT USED YET
def get_unassigned_rfid_tokens_from_event_log():
    db = get_db()
    cur = db.cursor()
    sql_stmt = """
        select distinct event_log.rfid_token_hex from event_log 
        where event_log.event_type = "ACCESS_GRANT" 
        and event_log.rfid_token_hex not in 
        (select rfid_tokens.rfid_token_hex from rfid_tokens 
        where rfid_tokens.status = "ASSIGNED")'
    """
    cur.execute(sql_stmt)
    return cur.fetchall()

# Get a list of users to assign a RFID (need to be VETTED and ACTIVE)
def get_members_for_rfid_association():
    db = get_db()
    cur = db.cursor()
    sql_stmt = "select m.stripe_id, m.full_name, sc.stripe_email, m.is_vetted from members m, stripe_cache sc where m.stripe_id = sc.stripe_id and member_status = 'ACTIVE' and is_vetted = 'VETTED'"
    cur.execute(sql_stmt)
    return cur.fetchall()

# Get a list of members with RFID Tokens assigned to them
def get_members_with_rfid_tokens():
    db = get_db()
    cur = db.cursor()
    sql_stmt = "select m.stripe_id, m.full_name, r.rfid_token_hex, r.rfid_token_comment from members m, rfid_tokens r where m.stripe_id = r.stripe_id order by m.full_name"
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
        ORDER BY 
            stripe_created_on desc
    """
    cur.execute(sql_stmt)
    rows = cur.fetchall()

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
        
    return entries_x

# Get a list of onboarded INACTIVE members
def get_inactive_members():
    db = get_db()
    cur = db.cursor()
    sql_stmt = """
            SELECT 
            m.stripe_id,
            s.stripe_subscription_id,
            m.full_name,
            m.is_vetted,
            s.stripe_subscription_product,
            s.stripe_subscription_status,
            s.stripe_last_payment_status
        FROM 
            members m
        LEFT JOIN
            stripe_cache s on s.stripe_id = m.stripe_id
        WHERE
            m.member_status = "INACTIVE"
        ORDER BY
            s.stripe_subscription_product desc
    """
    
    cur.execute(sql_stmt)
    members = cur.fetchall()

    ret_members = []

    for member in members:
        x = list(member)
        has_rfid = member_has_authorized_rfid(member[0])
        x.append(has_rfid)
        ret_members.append(x)
        
    return ret_members

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

# Fetch a member 'object'
def get_member(stripe_id=None):

    member = {}

    subscription_id = get_subscription_id_from_stripe_cache(stripe_id)

    # Check and update the stripe cache every time you view member details
    app.logger.info("[STRIPE] - updating real-time stripe information for %s" % (stripe_id,))
    stripe_info = identity.stripe.get_realtime_stripe_info(subscription_id)
    
    member["stripe_status"] = stripe_info['stripe_subscription_status'].upper()
    member['stripe_plan'] = stripe_info['stripe_subscription_product'].upper()
    member['stripe_email'] = stripe_info['stripe_email']

    member['rfid_tokens'] = get_member_rfid_tokens(stripe_id)

    db = get_db()
    cur = db.cursor()
    sql_stmt = 'update stripe_cache set stripe_last_payment_status = %s, stripe_subscription_status = %s WHERE stripe_id = %s'
    cur.execute(sql_stmt, (stripe_info['stripe_last_payment_status'], stripe_info['stripe_subscription_status'], stripe_id))
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
         locker_num,
         led_color 
         from members where stripe_id = %s'''

    cur.execute(sql_stmt, (stripe_info['stripe_id'],))
    entries = cur.fetchall()
    entry = entries[0]

    member["stripe_id"] = stripe_info['stripe_id']
    member["member_status"] = entry[0]
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
    member["led_color"] = entry[15]
    member["door_access"] = member_has_authorized_rfid(stripe_id)
    member["rfid_tokens"] = get_member_rfid_tokens(stripe_id)
    
    return member

# Update an existing member 'object'
def update_member(request=None):

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
        request.form.get('led_color'),
        stripe_id
    )
    
    sql_stmt = 'update members set member_status=%s,full_name=%s,nick_name=%s,meetup_email=%s,mobile=%s,emergency_contact_name=%s,emergency_contact_mobile=%s,is_vetted=%s,discord_handle=%s,locker_num=%s,led_color=%s where stripe_id=%s'
    cur.execute(sql_stmt, insert_data)

    db.commit()
    db.close()

    # Add Vetted Member Role if the member has a discord handle
    if app.config["DISCORD_MANAGE_ROLES"] and \
        request.form.get('is_vetted') == "VETTED" and \
        request.form.get('discord_handle') != None:
        assign_discord_role(app.config["DISCORD_ROLE_VETTED_MEMBER"],get_member_discord_id(request.form.get('discord_handle')))

    # Remove Vetted Member Role if the member has a discord handle
    if request.form.get('is_vetted') == "NOT VETTED" and \
        request.form.get('discord_handle') != None and app.config["DISCORD_MANAGE_ROLES"]:
        unassign_discord_role(app.config["DISCORD_ROLE_VETTED_MEMBER"],get_member_discord_id(request.form.get('discord_handle')))

    # Add Paid Member Role if the member has a discord handle
    if app.config["DISCORD_MANAGE_ROLES"] and \
        request.form.get('stripe_plan') != "Pause Membership" and \
        request.form.get('discord_handle') != None:
        assign_discord_role(app.config["DISCORD_ROLE_PAID_MEMBER"],get_member_discord_id(request.form.get('discord_handle')))

# Push log event into database
def insert_log_event(request=None):
    id = request.form['ID']
    rfid_token_hex =  request.form['badge']
    swipe_status = request.form['result']
    
    # Default log values
    stripe_id = "NA"
    rfid_token_comment = "NONE"

    db = get_db()
    cur = db.cursor()
    sql_stmt = "select stripe_id, rfid_token_comment from rfid_tokens where eb_id = %s"
    cur.execute(sql_stmt,(id,))
    entry = cur.fetchone()

    if entry:
        stripe_id = entry[0]
        rfid_token_comment = entry[1]
        
    if (swipe_status == "granted"):
        event_type = "ACCESS_GRANT"
    
    if (swipe_status == "denied"):
        event_type = "ACCESS_DENY"
    
    sql_stmt = 'insert into event_log (stripe_id, rfid_token_hex, event_type, rfid_token_comment) values (%s,%s,%s,%s)'
    cur.execute(sql_stmt,(stripe_id,rfid_token_hex,event_type,rfid_token_comment))
    db.commit()

    if stripe_id == 'NA':
        # Send alert email about a rfid token swiping in but is not assigned to a member in the system
        send_na_stripe_id_alert_email(rfid_token_hex)
    else:
        sub_id = get_subscription_id_from_stripe_cache(stripe_id)

        if identity.stripe.member_is_in_good_standing(sub_id):
            # Send alert email about a member in good standing
            send_door_access_alert_email(sub_id)
        else:
            # Send alert email about a member swiping in but is not in good standing
            send_payment_alert_email(sub_id)

# Get unbounded event logs
def get_event_log():

    db = get_db()
    cur = db.cursor()
    sql_stmt = """
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
    """
    cur.execute(sql_stmt)
    return cur.fetchall()

# Get public membership statistics for the front page
def get_public_stats():

    stats = {
        'total_membership': {
            'count':0, 
            'sql':'select count(*) from stripe_cache'
        },
        'total_paused': {
            'count':0,
            'sql': 'select count(*) from stripe_cache where stripe_subscription_product = "Pause Membership"'
        },
        'total_need_onboarding': {
            'count':0,
            'sql':'select count(*) FROM stripe_cache WHERE stripe_subscription_product <> "Pause Membership" and stripe_id NOT IN (SELECT stripe_id FROM members)'
        },
        'total_vetted': {
            'count':0,
            'sql':'select count(*) from members where IS_VETTED = "VETTED"'
        },
        'total_not_vetted': {
            'count':0,
            'sql':'select count(*) from members where IS_VETTED = "NOT VETTED"'
        },
        'total_have_waivers': {
            'count':0,
            'sql':'select count(*) from members where liability_waiver is NOT NULL'
        },
        'total_no_waivers': {
            'count':0,
            'sql':'select count(*) from members where liability_waiver is NULL'
        },
        'total_door_access': {
            'count':0,
            'sql':'select count(*) from members'
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
    cur = db.cursor()
    stmt = """  
        SELECT 
            m.stripe_id,
            s.stripe_subscription_id,
            m.full_name,
            m.is_vetted, 
            m.liability_waiver, 
            m.vetted_membership_form, 
            s.stripe_email,
            s.stripe_subscription_status,
            s.stripe_subscription_product,
            s.stripe_last_payment_status
        FROM 
            members m
        JOIN
            stripe_cache s on s.stripe_id = m.stripe_id
        WHERE
            m.member_status = "ACTIVE"
        AND
            m.stripe_id = s.stripe_id
        ORDER BY
            m.is_vetted desc
    """
    cur.execute(stmt)
    members = cur.fetchall()

    ret_members = []

    for member in members:
        x = list(member)
        has_rfid = member_has_authorized_rfid(member[0])
        x.append(has_rfid)
        ret_members.append(x)
        
    return ret_members

# Onboarding process - this attempts to pre-populate some fields 
# when setting up a new user.
@app.route('/member/new/<stripe_id>', methods=['GET','POST'])
@login_required
def show_onboard_new_member(stripe_id):
    # Get a new form, or if a POST then save the data
    if request.method == "GET":
        app.logger.info("User %s is onboarding member %s" % (session['username'],stripe_id))

        db = connect_db()
        cur = db.cursor()
        sql_stmt = 'select stripe_email, stripe_description, stripe_last_payment_status, stripe_subscription_product, stripe_subscription_status from stripe_cache where stripe_id = %s'
        cur.execute(sql_stmt, (stripe_id,))
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
            request.form.get('discord_handle'),
            request.form.get('locker_num')
        )

        db = connect_db()
        cur = db.cursor()
        cur.execute('insert into members (stripe_id,drupal_id,member_status,full_name,nick_name,meetup_email,mobile,emergency_contact_name,emergency_contact_mobile,is_vetted,liability_waiver,vetted_membership_form,badge_photo,discord_handle,locker_num) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', insert_data)
        db.commit()
        db.close()

        # Add Paid Member Role in if the member has a discord handle
        if request.form.get('discord_handle') != None and app.config["DISCORD_MANAGE_ROLES"]:
            assign_discord_role(app.config["DISCORD_ROLE_PAID_MEMBER"],get_member_discord_id(request.form.get('discord_handle')))

        # Add Vetted Member Role in if the member has a discord handle
        if request.form.get('is_vetted') == "VETTED" and request.form.get('discord_handle') != None and app.config["DISCORD_MANAGE_ROLES"]:
            assign_discord_role(app.config["DISCORD_ROLE_VETTED_MEMBER"],get_member_discord_id(request.form.get('discord_handle')))

        app.logger.info("User %s successfully onboarded member %s" % (session['username'],stripe_id))
        return redirect(url_for("show_admin_onboard",_scheme='https',_external=True))

# Show member details
@app.route('/member/<stripe_id>')
@login_required
def show_member(stripe_id):
    return render_template('show_member.html', member=get_member(stripe_id))

# Edit member details
@app.route('/member/<stripe_id>/edit', methods=['GET','POST'])
@login_required
def edit_member_details(stripe_id):

    if request.method == "GET":
        user = get_member(stripe_id)
        app.logger.info("User %s is editing member %s " % (session['username'],stripe_id))
        return render_template('edit_member.html', member=user)

    if request.method == "POST":
        update_member(request)
        app.logger.info("User %s updated member %s" % (session['username'],stripe_id))
        return redirect(url_for("show_admin",_scheme='https',_external=True))

# Get member badge photo
@app.route('/member/<stripe_id>/files/photo.jpg')
@login_required
def show_member_photo(stripe_id):
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
        with open("./identity/static/images/syn_shop_badge_logo.png", mode='rb') as file:
            photo = file.read()
        
        response = make_response(photo)
        response.headers['Content-Description'] = 'Badge Photo'
        response.headers['Content-Type'] = 'image/jpeg'
        response.headers['Content-Disposition'] = 'inline'

    return response

# Get member liability waiver
@app.route("/member/<stripe_id>/files/liability-waiver.pdf")
@login_required
def show_member_wavier(stripe_id):

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
@login_required
def show_member_vetted(stripe_id):

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

# Door Access Event Webhook
@app.route('/logevent', methods=['POST'])
def show_event_log():
    insert_log_event(request)
    return jsonify({"status":200})

# Landing Page Routes
@app.route('/')
def show_index():
    if session.get('logged_in') == None:
        return render_template('index.html',stats=get_public_stats())
    else:
        return redirect(url_for('show_admin'))

@app.route('/login', methods=['GET', 'POST'])
def show_login():

    error = ""
    r_to = request.referrer

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        url = "/admin"

        if check_password(username,password):
            session['logged_in'] = True
            session['username'] = username
            session.permanent = True
            app.logger.info("User %s logged in successfully" % (username))
            return redirect(url)
        else:
            error = 'Invalid credentials'
            app.logger.info("User %s failed login attempt" % (username))
            r_to=url

    return render_template('login.html',r_to=r_to,errors=error)

@app.route('/logout')
def show_logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash('You were logged out')
    return redirect(url_for('show_index',_scheme='https',_external=True))

@app.route('/admin')
@login_required
def show_admin():
    return render_template('admin.html', entries=get_admin_view())

@app.route('/admin/onboard')
@login_required
def show_admin_onboard():
    return render_template('onboard.html',entries=get_members_to_onboard())

@app.route('/admin/changepassword/<stripe_id>', methods=['GET','POST'])
@login_required
def show_changepassword(stripe_id):
    if request.method == "GET":
        return render_template('changepassword.html',stripe_id=stripe_id)

    if request.method == "POST":
        x = admin_change_password(stripe_id,request.form.get('password1'),)
        return redirect(url_for('show_index'))

@app.route('/admin/dooraccess', methods=['GET'])
@login_required
def show_door_access_landing():
    return render_template('door_access.html',entries=get_unassigned_rfid_tokens())

@app.route('/admin/dooraccess/newtoken', methods=['GET'])
@login_required
def show_door_access_new_token():
    return render_template('door_access_new_token.html')

@app.route('/admin/dooraccess/newtoken', methods=['POST'])
@login_required
def show_door_access_new_token_post():
    insert_new_rfid_token_record(eb_id=request.form['eb_id'],rfid_token_hex=request.form['rfid_token_hex'],rfid_token_comment=request.form['rfid_token_comment'])
    return redirect(url_for('show_door_access_landing'))

@app.route('/admin/dooraccess/assign', methods=['GET'])
@login_required
def show_door_access_assign():
    eb_id = request.args.get('eb_id')
    return render_template('door_access_assign.html',entries=get_members_for_rfid_association(),eb_id=eb_id)

@app.route('/admin/dooraccess/assign', methods=['POST'])
@login_required
def show_door_access_assign_post():
    stripe_id = request.form.get('stripe_id')
    eb_id = request.form.get('eb_id')
    assign_rfid_token(eb_id=eb_id,stripe_id=stripe_id)
    return redirect(url_for('show_door_access_landing'))

@app.route('/admin/dooraccess/unassign', methods=['GET'])
@login_required
def show_door_access_unassign():
    return render_template('door_access_unassign.html', entries=get_members_with_rfid_tokens())

@app.route('/admin/dooraccess/unassign', methods=['POST'])
@login_required
def show_door_access_unassign_post():
    rfid_token_hex = request.form.get('rfid_id_token_hex')
    unassign_rfid_token(rfid_token_hex)
    flash('RFID Token has been unassigned')
    return redirect(url_for('show_door_access_landing'))

@app.route('/admin/dooraccess/tokenattributes', methods=['GET'])
@login_required
def show_door_access_token_attributes():
    return render_template('door_access_modify_attributes.html', entries=get_all_rfid_tokens())

@app.route('/admin/dooraccess/tokenattributes/edit', methods=['GET'])
@login_required
def show_door_access_token_attributes_post():
    rfid_token_hex = request.args.get('rfid_token_hex')
    return render_template('door_access_attributes_edit.html', entry=get_rfid_token_attributes(rfid_token_hex))

@app.route('/admin/dooraccess/tokenattributes/edit', methods=['POST'])
@login_required
def show_access_attributes_edit():
    update_rfid_token_attributes(request)
    return redirect(url_for('show_door_access_landing'))

@app.route('/admin/dooraccess/scanlog', methods=['GET'])
@login_required
def show_door_access_scanlog():
    return render_template('door_access_scanlog.html')

@app.route('/admin/eventlog', methods=['GET'])
@login_required
def show_eventlog_landing():
    return render_template('event_log.html', entries=get_event_log())

@app.route('/admin/reactivate', methods=['GET'])
@login_required
def show_reactivate_member():
    return render_template('reactivate.html',inactive_members=get_inactive_members())

@app.route('/admin/reactivate', methods=['POST'])
@login_required
def show_reactivate_member_post():
    stripe_id = request.form.get('stripe_id')
    return redirect('/member/' + stripe_id + '/edit')

@app.route('/admin/discordroles', methods=['GET'])
@login_required
def show_manage_discord_roles():
    return render_template('manage_discord_roles.html', entries=None)

# Widget Testing
@app.route('/widget', methods=['GET','POST'])
def show_test_widget():
    return render_template('camera-widget.html')

