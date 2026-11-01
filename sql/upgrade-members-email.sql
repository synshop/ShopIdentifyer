-- Keep Stripe-sourced contact details on members so they survive a cancelled subscription.
-- Run once against an existing database before deploying the code that uses these columns.

ALTER TABLE `shopid`.`members`
  ADD COLUMN email varchar(255) AFTER full_name,
  ADD COLUMN last_seen_in_stripe TIMESTAMP NULL DEFAULT NULL AFTER emergency_contact_mobile;

-- Backfill from the current cache. changed_on is set to itself so it isn't bumped
UPDATE `shopid`.`members` m
JOIN `shopid`.`stripe_cache` sc ON sc.stripe_id = m.stripe_id
SET
  m.email = NULLIF(sc.email, ''),
  m.last_seen_in_stripe = NOW(),
  m.changed_on = m.changed_on;
