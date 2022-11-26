ENCRYPTED_STRIPE_TOKEN = 'encrypted-token'
ENCRYPTED_DATABASE_PASSWORD = 'encrypted-database-password'
ENCRYPTED_MAIL_USERNAME = 'encrypted-mail-user'
ENCRYPTED_MAIL_PASSWORD = 'encrypted-mail-pass'

ENCRYPTED_DISCORD_BOT_TOKEN = 'encrypted-discord-token'
DISCORD_MANAGE_ROLES = False
DISCORD_GUILD_ID = 'example-value-here'
DISCORD_ROLE_PAID_MEMBER = 'example-value-here'
DISCORD_ROLE_VETTED_MEMBER = 'example-value-here'

ENCRYPTED_SESSION_KEY = 'encrypted-session'
ENCRYPTED_ADMIN_PASSPHRASE = "encrypted-admin-pass"

ENCRYPTED_SMTP_USERNAME = 'encrypted-smtp-user'
ENCRYPTED_SMTP_PASSWORD = 'encrypted-smtp-pass'
SMTP_SERVER = 'example.com'
SMTP_PORT = 465
SMTP_SEND_EMAIL = False
SMTP_ALERT_TO = "foo@example.org"
SMTP_ALERT_FROM = "smang@example.org"

DATABASE_USER = 'synshop'
DATABASE_HOST = 'localhost'
DATABASE_PORT = 3306
DATABASE_SCHEMA = "shopidentifyer"

LOG_FILE = "/tmp/gunicorn.log"

SCHEDULER_ENABLED = False

STRIPE_CACHE_REFRESH_MINUTES = 60
STRIPE_CACHE_REBUILD_MINUTES = 1440
STRIPE_CACHE_REBUILD_CRON = '46 23 * * *'
STRIPE_CACHE_REFRESH_CRON = '15 * * * *'
STRIPE_CACHE_REFRESH_REACHBACK_MIN = 15
STRIPE_CACHE_DEACTIVATE_CRON = '55 23 * * *'
STRIPE_FETCH_REALTIME_UPDATES = False  # False means no emails sent during swipes

MAIL_SERVER = 'localhost'
MAIL_PORT = 22
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_DEBUG = True

ACCESS_CONTROL_HOSTNAME = 'localhost'
ACCESS_CONTROL_SSH_PORT = 22

ALERT_URLS = {  # leave as an empty object if you don't want to send any POSTs
    'kiosk': 'http://10.0.40.219/member_fobbing/',
    'blinkenlights': 'https://10.0.40.10'
}