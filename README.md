Be sure to create a identity-config.py file with the following:

#
# Some of these values are encrypted.  Please use the./crypto/crypto.py
# command line utility to generate the encrypted values.
#

ENCRYPTED_STRIPE_TOKEN = 'encrypted-token'
ENCRYPTED_DATABASE_PASSWORD = 'encrypted-password'

DATABASE_USER = 'root'
DATABASE_HOST = 'localhost'
DATABASE_PORT = 3306
DATABASE_SCHEMA = "shopidentifyer"

SERIAL_DEVICE = '/dev/tty.usbserial-A800509r'
SERIAL_BAUD_RATE = 9600

MESSAGE_QUEUE="http://localhost:5000/queue/message"
