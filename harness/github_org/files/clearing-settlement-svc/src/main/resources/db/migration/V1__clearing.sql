CREATE TABLE clearing_record (
    clearing_id       TEXT           PRIMARY KEY,
    network           TEXT           NOT NULL,
    network_reference TEXT           NOT NULL,
    card_token        TEXT           NOT NULL,
    merchant_id       TEXT           NOT NULL,
    mcc               CHAR(4)        NOT NULL,
    amount            NUMERIC(18, 3) NOT NULL,
    currency          CHAR(3)        NOT NULL,
    card_product      TEXT           NOT NULL,
    status            TEXT           NOT NULL DEFAULT 'RECEIVED',
    received_at       TIMESTAMPTZ    NOT NULL
);

CREATE TABLE clearing_match (
    clearing_id TEXT PRIMARY KEY REFERENCES clearing_record (clearing_id),
    auth_id     TEXT NOT NULL UNIQUE,
    score       DOUBLE PRECISION NOT NULL,
    matched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
