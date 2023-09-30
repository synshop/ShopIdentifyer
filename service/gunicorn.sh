#!/bin/bash

cd /opt/ShopIdentifyer
source ~/.bashrc
source /opt/ShopIdentifyer/activate;
gunicorn --bind [fd42:7c97:9426:8f29:216:3eff:fe43:a5ec]:8000 --log-file /tmp/gunicorn.log --pid /tmp/gunicorn.pid identity:app

