#!/bin/bash

# Ubuntu 14.04.01
if [ -e /etc/bash_completion.d/virtualenvwrapper ]
then
	source /etc/bash_completion.d/virtualenvwrapper;
	workon ShopIdentifyer;
fi

# OS X
if [ -e /usr/local/bin/virtualenvwrapper.sh ]
then
	source /usr/local/bin/virtualenvwrapper.sh
    workon ShopIndentifyer;
fi

echo -n "Please enter the startup password and press [enter]: ";
stty -echo
read key;
stty echo

if [ -e /opt/ShopIdentifyer ]
then
	cd /opt/ShopIdentifyer;
fi

export ENCRYPTION_KEY=${key};
gunicorn --bind 127.0.0.1:8000 -D --log-file /tmp/gunicorn.log runserver:app
export ENCRYPTION_KEY=;

echo "Showing application status: ";
ps aux | grep -i gunicorn;

echo;
echo "Errors are being written to /tmp/gunicorn.log";
