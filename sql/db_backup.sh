#!/bin/bash

# External backups
ssh -p 2240 shop.synshop.org mysqldump -u root shopidentifyer > ~/dumps/dump-`date "+%Y-%m-%d-%H"`.sql

