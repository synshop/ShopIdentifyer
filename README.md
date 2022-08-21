## Introduction
Over the past several years, the [SYN Shop hacker/makerspace](https://www.synshop.org) has grown to where validating membership when entering the shop is no longer a first-name basis.  The space was in need of something more robust and automated.  This system integrates with the shop's payment processor (Stripe) and manages user contact information and payment / subscription status.  It also tracks liability waivers and various other documents related to shop operation.

## Setup (Development)

1. Requirements
    * Python 3.10.x
    * virtualenv 
    * MySQL
    * NGINX

2. Set up a [python virtual environment](http://docs.python-guide.org/en/latest/dev/virtualenvs/), clone or download the source for ShopIdentifyer and pip install the requirements.txt file included:

        $ git clone git@github.com:synshop/ShopIdentifyer.git
        $ python3 -m venv ShopIdentifyer/.venv/
        $ source ./ShopIdentifyer/bin/activate
        $ cd ShopIdentifyer
        $ pip install -r requirements.txt
        $ ./localserver.py (starts a local Flask instance on port 8000)

3. Additionally, the system needs a `./identity/config.py` file with the following properties:

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

To get started, copy the `config.dist.py` file to `config.py` in the `identify` folder. Modify it to have the specific values for your environment.

Please note that all of the properties starting with `ENCRYPTED_` are encrypted.  When the application starts up, it will prompt you for a single decryption password.  This is the same password that you will use to encrypt the properties using the cli tool `./identity/crypto/crypt.py`.  The instructions for use are pretty straightforward:

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

## Setup (Production)

### NGINX Configuration
You'll need to set up SSL/TLS to do development, since all the Flask routes are designed to use SSL.  The development instance is already configured to use an ad-hoc SSL generation mechanism when you start the application using `./localserver.py`, but there is more work involved to set a production instance that uses Gunicorn.  You'll need to set up a HTTP server (we choose NGINX) to terminate the SSL requests and proxy them to the Gunicorn container.  There is a very basic NGINX configuration in `nginx/default` that you should be able to use out of the box or without many changes.  You will need to provide a SSL certificate but there are many solutions available on the internet.

### Starting, Stopping and Debugging

In a production environment, you'll need to launch the application using Gunicorn:

    $ ./start_gunicorn.sh

When you run this command, you'll some output similar to this:

    ./start_gunicorn.sh  
    Please enter the startup password and press [enter]:

    Showing application status:
    mrjones   9389  0.2  0.0  17352  2280 pts/9    S+   22:07   0:00 /bin/bash ./start_gunicorn.sh
    mrjones   9411  0.0  0.1  50584 11848 ?        R    22:07   0:00 /home/mrjones/Envs/ShopIdentifyer/bin/python /home/mrjones/Envs/ShopIdentifyer/bin/gunicorn --bind 127.0.0.1:8000 -D --log-file /tmp/gunicorn.log runserver:app
    mrjones   9413  0.0  0.0  15936   936 pts/9    S+   22:07   0:00 grep -i gunicorn

If you need to look at the log to see why something isn't working, the logs are in `/tmp/gunicorn.log`    

### Ubuntu Quick Setup

	$ apt-get install python3-dev python3.10-venv \
                      mysql-server build-essential \
                      libmysqlclient-dev git gh nginx \
                      libffi-dev