CREATE TABLE card (
    card_token    TEXT        PRIMARY KEY,
    customer_id   TEXT        NOT NULL,
    product_code  TEXT        NOT NULL,
    form_factor   TEXT        NOT NULL,
    bin           CHAR(6)     NOT NULL,
    expiry_yyyymm CHAR(6)     NOT NULL,
    state         TEXT        NOT NULL,
    block_reason  TEXT,
    updated_at    TIMESTAMPTZ NOT NULL
);

CREATE INDEX card_customer ON card (customer_id);

CREATE TABLE outbox (
    id           BIGSERIAL   PRIMARY KEY,
    topic        TEXT        NOT NULL,
    event_key    TEXT        NOT NULL,
    event_type   TEXT        NOT NULL,
    payload      JSONB       NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE INDEX outbox_pending ON outbox (id) WHERE published_at IS NULL;
