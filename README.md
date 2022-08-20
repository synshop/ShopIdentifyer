Introduction
===
Over the past several years, the [SYN Shop hacker/makerspace](https://www.synshop.org) has grown to where the management of validating membership when entering the shop is no longer a first-name basis and was in need of something more robust and automated.

Setup (Development)
===

1. Requirements
  * Python 3.10.x
  * virtualenv 
  * MySQL 
  * USB / Serial RFID Reader (see below)

2. Set up a [python virtual environment](http://docs.python-guide.org/en/latest/dev/virtualenvs/) and [virtualenvwrapper](http://docs.python-guide.org/en/latest/dev/virtualenvs/#virtualenvwrapper), clone or download the source for ShopIdentifyer and pip install the requirements.txt file included:

        $ git clone git@github.com:synshop/ShopIdentifyer.git
        $ python3 -m venv ShopIdentifyer/.venv/
        $ source ./ShopIdentifyer/bin/activate
        $ cd ShopIdentifyer
        $ pip install -r requirements.txt
        $ ./localserver.py (starts a local Flask instance on port 8000)

3. Additionally, the system needs a ./identity/config.py file with the following properties:

        ENCRYPTED_STRIPE_TOKEN = 'encrypted-token'
        ENCRYPTED_DATABASE_PASSWORD = 'encrypted-password'
        ENCRYPTED_MAIL_USERNAME = 'encrypted-mail-username'
        ENCRYPTED_MAIL_PASSWORD = 'encrypted-mail-password'

        ENCRYPTED_SESSION_KEY = 'session-key-salt'
        ENCRYPTED_ADMIN_PASSPHRASE = "encrypted-admin-password"

        DATABASE_USER = 'root'
        DATABASE_HOST = 'localhost'
        DATABASE_PORT = 3306
        DATABASE_SCHEMA = "shopidentifyer"

        SCHEDULER_ENABLED = False

        STRIPE_CACHE_REFRESH_MINUTES = 60
        STRIPE_CACHE_REFRESH_MINUTES = 13
        STRIPE_CACHE_REBUILD_MINUTES = 1440
        STRIPE_CACHE_REFRESH_REACHBACK_MIN = 15

        MAIL_SERVER = 'localhost'
        MAIL_PORT = 22
        MAIL_USE_TLS = True
        MAIL_USE_SSL = False
        MAIL_DEBUG = True

        ACCESS_CONTROL_HOSTNAME = 'localhost'
        ACCESS_CONTROL_SSH_PORT = 22

To get started, cp the `config.dist.py` file to `config.py` in the identify folder. Edit it to have the specific values for your environment.

Please note that <em style="background-color:#FFD700">all of the properties starting with `ENCRYPTED_` are encrypted.  When the web server starts up, it will prompt you for a single decryption password.</em>  This is the same password that you will use to encrypt the properties using the tool in ./identity/crypto/crypt.py.  The instructions for use are pretty straightforward:

    $ python crypt.py

    Usage: crypt.py encrypt
           crypt.py decrypt

In order for the decryption to work, you need to use the same password to encrypt all of the 6 values. Here's an example of encrypting the string "foo"

    $ python identity/crypto/crypt.py encrypt
    Please enter the encryption key:
    Please enter the plaintext you wish to encrypt:
    Encrypted Value: +uBiga/44gMDfr6UXFllIA==

So, if you wanted `foo` to be the value for the `ENCRYPTED_DATABASE_PASSWORD` you would define it like this in `config.py`:

    ENCRYPTED_DATABASE_PASSWORD = '+uBiga/44gMDfr6UXFllIA=='

Again, you need to use the same password for each of the 6 encrypted strings in your config file.

Starting, Stopping and Debugging
================================
In a dev  environment, you'll need to run this to start the app:

    $ ./localserver.py

This will start a local Flask 

In a production environment, you'll need to launch the application using Gunicorn:

    $ ./start_gunicorn.sh

When you run this command, you'll some output similar to this:

    ./start_gunicorn.sh  
    Please enter the startup password and press [enter]:

    Showing application status:
    mrjones   9389  0.2  0.0  17352  2280 pts/9    S+   22:07   0:00 /bin/bash ./start_gunicorn.sh
    mrjones   9411  0.0  0.1  50584 11848 ?        R    22:07   0:00 /home/mrjones/Envs/ShopIdentifyer/bin/python /home/mrjones/Envs/ShopIdentifyer/bin/gunicorn --bind 127.0.0.1:8000 -D --log-file /tmp/gunicorn.log runserver:app
    mrjones   9413  0.0  0.0  15936   936 pts/9    S+   22:07   0:00 grep -i gunicorn

And if you need to look at the log to see why something isn't working, the logs are in `/tmp/gunicorn.log`    

If you need to stop it, us kill

    $ kill $(ps aux | grep 'gunicorn' | awk '{print $2}')

Ubuntu Quick Setup
==================
	$ apt-get install python3-dev python3.10-venv \
                      mysql-server build-essential \
                      libmysqlclient-dev git gh nginx \
                      libffi-dev

