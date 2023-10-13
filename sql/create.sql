-- CREATE USER 'synshop'@'localhost' IDENTIFIED BY 'CHANGME';

DROP DATABASE IF EXISTS shopid;
CREATE DATABASE shopid;
GRANT ALL PRIVILEGES ON shopid.* TO 'synshop'@'localhost' WITH GRANT OPTION;

create table shopid.members (
  stripe_id varchar(255) NOT NULL PRIMARY KEY UNIQUE,
  member_status ENUM('ACTIVE','INACTIVE') NOT NULL DEFAULT "ACTIVE",
  is_vetted ENUM('VETTED','NOT VETTED') NOT NULL DEFAULT "NOT VETTED",
  full_name varchar(255),
  locker_num varchar(255),
  led_color varchar(255) DEFAULT "#000000,#000000",
  mobile varchar(25),
  emergency_contact_name varchar(255),
  emergency_contact_mobile varchar(25),
  liability_waiver longblob,
  vetted_membership_form longblob,
  badge_photo longblob,
  is_admin ENUM('Y','N') NOT NULL DEFAULT "N",
  created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  changed_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

create table shopid.stripe_cache (
  stripe_id varchar(255) unique,
  created_on varchar(255),
  email varchar(255),
  full_name text,
  discord_username varchar(25),
  last_payment_status varchar(255),
  subscription_id varchar(255),
  subscription_product varchar(255),
  subscription_status varchar(255),
  subscription_created_on varchar(255)
);

create table shopid.event_log (
  event_id int NOT NULL PRIMARY KEY AUTO_INCREMENT,
  stripe_id varchar(255) NOT NULL,
  rfid_token_hex varchar(255) NOT NULL,
  created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  event_type ENUM('DOOR_SWIPE','BADGE_SWIPE','MANUAL_SWIPE','ACCESS_ATTEMPT','ACCESS_GRANT','ACCESS_DENY','MISSING_BADGE','MISSING_ACCOUNT') DEFAULT 'BADGE_SWIPE',
  reader_id int,
  rfid_token_comment varchar(255)
);

CREATE TABLE shopid.rfid_tokens (
  eb_id int DEFAULT NULL,
  stripe_id varchar(255),
  eb_status ENUM('ACTIVE','INACTIVE') NOT NULL DEFAULT "ACTIVE",
  rfid_token_hex varchar(255) NOT NULL PRIMARY KEY,
  rfid_token_comment varchar(255),
  status ENUM('ASSIGNED','UNASSIGNED','LOST','BROKEN') NOT NULL DEFAULT "UNASSIGNED",
  created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  changed_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
