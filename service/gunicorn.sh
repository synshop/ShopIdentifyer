#!/bin/bash

cd /opt/ShopIdentifyer
source ~/.bashrc
source /opt/ShopIdentifyer/activate;
gunicorn --bind 127.0.0.1:8000 --log-file /tmp/gunicorn.log --pid /tmp/gunicorn.pid identity:app

