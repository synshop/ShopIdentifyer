DROP DATABASE shopidentifyer;

create database shopidentifyer;

create table shopidentifyer.members (

  badge_id int NOT NULL PRIMARY KEY AUTO_INCREMENT,
  badge_serial varchar(255) NOT NULL UNIQUE,
  badge_status ENUM('ACTIVE', 'INACTIVE','LOST','BROKEN') NOT NULL DEFAULT "ACTIVE",
  created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  changed_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  full_name varchar(255),
  nick_name varchar(255),
  drupal_name varchar(255),
  primary_email varchar(255),
  stripe_email varchar(255),
  meetup_email varchar(255),
  mobile varchar(25),
  emergency_contact_name varchar(255),
  emergency_contact_mobile varchar(25),
  is_vetted tinyint(1) NOT NULL DEFAULT 0,
  liability_waiver longblob,
  vetted_membership_form longblob,
  badge_photo longblob

);

create table shopidentifyer.event_log (

  event_id int NOT NULL PRIMARY KEY AUTO_INCREMENT,
  badge_id int NOT NULL,
  created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  event_type ENUM('BADGE_SWIPE','MANUAL_SWIPE','ACCESS_ATTEMPT','ACCESS_GRANT','ACCESS_DENY') DEFAULT 'BADGE_SWIPE',
  event_message varchar(255)

);

create table shopidentifyer.message_queue (
  message varchar(255)
);

create table shopidentifyer.stripe_cache (
  stripe_id varchar(255),
  stripe_email varchar(255),
  subscription varchar(255)
);
