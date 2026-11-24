-- Store the liability waiver details from Stripe customer metadata in stripe_cache and members.
-- Run once against an existing database before deploying the code that uses these columns.
-- Nothing to backfill: the next stripe_cache rebuild and members refresh fill them in

ALTER TABLE `shopid`.`stripe_cache`
  ADD COLUMN waiver_auth0_sub varchar(255),
  ADD COLUMN waiver_dob varchar(255),
  ADD COLUMN waiver_esign_consent varchar(255),
  ADD COLUMN waiver_sha256 varchar(255),
  ADD COLUMN waiver_signed_at varchar(255),
  ADD COLUMN waiver_signed_ip varchar(255),
  ADD COLUMN waiver_signed_name varchar(255),
  ADD COLUMN waiver_user_agent text,
  ADD COLUMN waiver_version varchar(255);

ALTER TABLE `shopid`.`members`
  ADD COLUMN waiver_auth0_sub varchar(255) AFTER vetting_doc,
  ADD COLUMN waiver_dob varchar(255) AFTER waiver_auth0_sub,
  ADD COLUMN waiver_esign_consent varchar(255) AFTER waiver_dob,
  ADD COLUMN waiver_sha256 varchar(255) AFTER waiver_esign_consent,
  ADD COLUMN waiver_signed_at varchar(255) AFTER waiver_sha256,
  ADD COLUMN waiver_signed_ip varchar(255) AFTER waiver_signed_at,
  ADD COLUMN waiver_signed_name varchar(255) AFTER waiver_signed_ip,
  ADD COLUMN waiver_user_agent text AFTER waiver_signed_name,
  ADD COLUMN waiver_version varchar(255) AFTER waiver_user_agent;
