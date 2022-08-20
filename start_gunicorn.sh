#!/bin/bash

echo -n "Please enter the startup password and press [enter]: ";
stty -echo
read key;
stty echo

if [ -e /opt/ShopIdentifyer ];
then
	cd /opt/ShopIdentifyer;
fi

export ENCRYPTION_KEY=${key};
gunicorn --bind 127.0.0.1:8000 -D --log-file /tmp/gunicorn.log --pid /tmp/gunicorn.pid runserver:app
export ENCRYPTION_KEY=;

echo "Showing application status: ";
ps aux | grep -i gunicorn;

echo;
echo "Errors are being written to /tmp/gunicorn.log";
