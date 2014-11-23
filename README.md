Setup
===
1. To run the system, you'll need to create a identity/config.py file with the following values:

    #
    # Some of these values are encrypted.  Please use the ./crypto/crypto.py
    # command line utility to generate the encrypted values.
    #

    ENCRYPTED_STRIPE_TOKEN = 'encrypted-token'
    ENCRYPTED_DATABASE_PASSWORD = 'encrypted-password'

    DATABASE_USER = 'root'
    DATABASE_HOST = 'localhost'
    DATABASE_PORT = 3306
    DATABASE_SCHEMA = "shopidentifyer"

    STRIPE_CACHE_REFRESH_MINUTES=60

2. Setup a python virtual environment and pip install the requirements.txt file

    $ mkvirtualenv ShopIdentifyer
    $ workon ShopIdentifyer
    $ cd ShopIdentifyer
    $ pip install -r requirements.txt

The Serial Remote
===
In addtion to the Flask web application, there is an out of process deamon that listens for incoming
RFID swipes on the serial port, and then pushes them into the system.

The deamon is located in ./serial_remote/serial_listener.py and can be started as follows:

    $ python serial_remote/serial_listener.py start

Please note that this assumes you have already set up a virtualenv with the requirements.txt satisfied.
