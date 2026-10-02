ALTER TABLE clearing_record ADD COLUMN settlement_batch_id TEXT;

-- The cut-off only ever looks at cleared, unsettled records.
CREATE INDEX clearing_record_to_settle ON clearing_record (merchant_id, currency) WHERE status = 'CLEARED';
