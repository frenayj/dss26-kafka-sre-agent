-- Inputs and result of the interchange calculation. Region and card presence
-- come from the presentment; the defaults cover everything ingested so far.
ALTER TABLE clearing_record
    ADD COLUMN region       TEXT    NOT NULL DEFAULT 'INTRA_EEA',
    ADD COLUMN card_present BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN fee_total    NUMERIC(18, 3);
