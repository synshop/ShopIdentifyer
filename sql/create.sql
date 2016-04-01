DROP DATABASE IF EXISTS shopidentifyer;

create database shopidentifyer;

create table shopidentifyer.members (

  stripe_id varchar(255) NOT NULL PRIMARY KEY UNIQUE,
  drupal_id varchar(255),
  badge_serial varchar(255) default "N/A",
  member_status ENUM('ACTIVE','INACTIVE') NOT NULL DEFAULT "ACTIVE",
  is_vetted ENUM('YES','NO') NOT NULL DEFAULT "NO",
  full_name varchar(255),
  nick_name varchar(255),
  stripe_email varchar(255),
  meetup_email varchar(255),
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
  member_id int NOT NULL,
  created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  event_type ENUM('DOOR_SWIPE','BADGE_SWIPE','MANUAL_SWIPE','ACCESS_ATTEMPT','ACCESS_GRANT','ACCESS_DENY','MISSING_BADGE','MISSING_STRIPE') DEFAULT 'BADGE_SWIPE',
  event_message varchar(255)

);

-- ALTER TABLE shopidentifyer.event_log CHANGE event_type event_type ENUM('DOOR_SWIPE','BADGE_SWIPE','MANUAL_SWIPE','ACCESS_ATTEMPT','ACCESS_GRANT','ACCESS_DENY','MISSING_BADGE','MISSING_STRIPE');

create table shopidentifyer.event_types (
  event_id int NOT NULL PRIMARY KEY AUTO_INCREMENT,
  event_type varchar(100)
);

insert into shopidentifyer.event_types values ('DOOR_SWIPE');
insert into shopidentifyer.event_types values ('BADGE_SWIPE');
insert into shopidentifyer.event_types values ('MANUAL_SWIPE');
insert into shopidentifyer.event_types values ('ACCESS_ATTEMPT');
insert into shopidentifyer.event_types values ('ACCESS_GRANT');
insert into shopidentifyer.event_types values ('ACCESS_DENY');

create table shopidentifyer.message_queue (
  message varchar(255)
);

create table shopidentifyer.stripe_cache (
  stripe_id varchar(255),
  stripe_created_on varchar(255),
  stripe_description text,
  stripe_email varchar(255),
  subscription varchar(255)
);

ALTER TABLE shopidentifyer.stripe_cache ADD UNIQUE (stripe_id)
