-- Transaction detail screen shows where and how the card was used.
-- Nullable: rows written before this migration are not backfilled.
ALTER TABLE card_transaction
    ADD COLUMN merchant_country CHAR(2),
    ADD COLUMN channel          TEXT;
