from flask import Flask
from crypto import SettingsUtil, CryptoUtil
import config

from identity.services import stripe

RUN_MODE = 'development'

ENCRYPTION_KEY = SettingsUtil.EncryptionKey.get(RUN_MODE == 'development')

app = Flask(__name__)
app.config['DEBUG'] = True

app.config['STRIPE_TOKEN'] = CryptoUtil.decrypt(config.STRIPE_TOKEN, ENCRYPTION_KEY)

app.config['DATBASE_URL'] = config.STRIPE_TOKEN
app.config['DATBASE_USER'] = config.DATABASE_USER
# app.config['DATBASE_PASSWORD'] = CryptoUtil.decrypt(config.DATABASE_PASSWORD, ENCRYPTION_KEY)


s_view = stripe.API.as_view('stripe_api')
app.add_url_rule('/schedules/', view_func=s_view, methods=['GET','POST','DELETE','PUT'])
app.add_url_rule('/schedules/<day>', view_func=s_view, methods=['GET'])
