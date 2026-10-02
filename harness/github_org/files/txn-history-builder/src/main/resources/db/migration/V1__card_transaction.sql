CREATE TABLE card_transaction (
    auth_id          TEXT           PRIMARY KEY,
    card_token       TEXT           NOT NULL,
    merchant_id      TEXT           NOT NULL,
    amount           NUMERIC(18, 3) NOT NULL,
    currency         CHAR(3)        NOT NULL,
    status           TEXT           NOT NULL DEFAULT 'PENDING',
    authorised_at    TIMESTAMPTZ    NOT NULL,
    source_partition INT            NOT NULL,
    source_offset    BIGINT         NOT NULL,
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- The apps always ask for one card, newest first.
CREATE INDEX card_transaction_card_time ON card_transaction (card_token, authorised_at DESC);
