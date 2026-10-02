CREATE TABLE chargeback (
    id               TEXT           PRIMARY KEY,
    auth_id          TEXT           NOT NULL,
    merchant_id      TEXT           NOT NULL,
    network          TEXT           NOT NULL,
    disputed_amount  NUMERIC(18, 3) NOT NULL,
    currency         CHAR(3)        NOT NULL,
    reason_code      TEXT           NOT NULL,
    category         TEXT           NOT NULL,
    opened_at        TIMESTAMPTZ    NOT NULL,
    outcome          TEXT,
    recovered_amount NUMERIC(18, 3),
    resolved_at      TIMESTAMPTZ
);

CREATE INDEX chargeback_open ON chargeback (opened_at) WHERE outcome IS NULL;
CREATE INDEX chargeback_auth ON chargeback (auth_id);
