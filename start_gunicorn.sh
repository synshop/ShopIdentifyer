#!/bin/bash

echo -n "Please enter the startup password and press [enter]: ";

read key;

export ENCRYPTION_KEY=${key};
gunicorn --bind 0.0.0.0:8000 -D --log-file /tmp/gunicorn.log runserver:app
export ENCRYPTION_KEY=;

echo "Showing application status: ";
ps aux | grep -i gun;
