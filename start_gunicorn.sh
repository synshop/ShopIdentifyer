#!/bin/bash

echo -n "Please enter the startup password and press [enter]: ";
stty -echo
read key;
stty echo

export ENCRYPTION_KEY=${key};
gunicorn --bind 127.0.0.1:8000 -D --log-file /tmp/gunicorn.log runserver:app
export ENCRYPTION_KEY=;

echo "Showing application status: ";
ps aux | grep -i gun;
