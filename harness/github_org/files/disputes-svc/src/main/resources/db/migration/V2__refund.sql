CREATE TABLE refund (
    id           TEXT           PRIMARY KEY,
    auth_id      TEXT           NOT NULL,
    card_token   TEXT           NOT NULL,
    merchant_id  TEXT           NOT NULL,
    amount       NUMERIC(18, 3) NOT NULL,
    currency     CHAR(3)        NOT NULL,
    reason       TEXT           NOT NULL,
    requested_at TIMESTAMPTZ    NOT NULL,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT now()
);
