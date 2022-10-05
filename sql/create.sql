-- CREATE USER 'synshop'@'localhost' IDENTIFIED BY 'CHANGME';

DROP DATABASE IF EXISTS shopidentifyer;
CREATE DATABASE shopidentifyer;
GRANT ALL PRIVILEGES ON shopidentifyer.* TO 'synshop'@'localhost' WITH GRANT OPTION;

create table shopidentifyer.members (
  stripe_id varchar(255) NOT NULL PRIMARY KEY UNIQUE,
  drupal_id varchar(255),
  badge_serial varchar(255) default "N/A",
  member_status ENUM('ACTIVE','INACTIVE') NOT NULL DEFAULT "ACTIVE",
  is_vetted ENUM('VETTED','NOT VETTED') NOT NULL DEFAULT "NOT VETTED",
  full_name varchar(255),
  nick_name varchar(255),
  meetup_email varchar(255),
  discord_handle varchar(255),
  locker_num varchar(255),
  led_color varchar(255) DEFAULT "#000000,#000000",
  mobile varchar(25),
  emergency_contact_name varchar(255),
  emergency_contact_mobile varchar(25),
  liability_waiver longblob,
  vetted_membership_form longblob,
  badge_photo longblob,
  created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  changed_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

create table shopidentifyer.event_log (
  event_id int NOT NULL PRIMARY KEY AUTO_INCREMENT,
  stripe_id varchar(255) NOT NULL,
  badge_hex varchar(255) NOT NULL,
  created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  event_type ENUM('DOOR_SWIPE','BADGE_SWIPE','MANUAL_SWIPE','ACCESS_ATTEMPT','ACCESS_GRANT','ACCESS_DENY','MISSING_BADGE','MISSING_ACCOUNT') DEFAULT 'BADGE_SWIPE'
);

create table shopidentifyer.stripe_cache (
  stripe_id varchar(255) unique,
  stripe_created_on varchar(255),
  stripe_email varchar(255),
  stripe_description text,
  stripe_last_payment_status varchar(255),
  stripe_subscription_id varchar(255),
  stripe_subscription_product varchar(255),
  stripe_subscription_status varchar(255),
  stripe_subscription_created_on varchar(255)
);

create table shopidentifyer.admin_users (
	stripe_id varchar(255) NOT NULL PRIMARY KEY,
  pwd varchar(2048)
);

insert into shopidentifyer.admin_users values ('cus_12VClCAS8R2pNP','$2b$12$fyqvNiP3ouafim/p.xPDDOqu6I3qXROoroPfoe/pWPb1nkzkbItJm');

CREATE TABLE shopidentifyer.rfid_tokens (
  eb_id int UNIQUE DEFAULT NULL,
  stripe_id varchar(255) NOT NULL,
  rfid_token_hex varchar(255) NOT NULL
);

CREATE TABLE shopidentifyer.electric_badger_import (
  id int UNIQUE DEFAULT NULL,
  level int DEFAULT NULL,
  badge text,
  name text,
  handle text,
  color text,
  email text,
  badge_decimal int DEFAULT NULL
);