-- Store the signed Vetted Membership PDF on each member.
-- Run once against an existing database before deploying the code that uses this column.
-- MEDIUMBLOB holds up to 16MB (a plain BLOB is only 64KB)

ALTER TABLE `shopid`.`members`
  ADD COLUMN vetting_doc MEDIUMBLOB AFTER last_seen_in_stripe;
