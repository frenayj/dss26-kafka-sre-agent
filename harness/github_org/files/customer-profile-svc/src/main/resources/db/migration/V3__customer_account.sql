CREATE TABLE customer_account (
    account_number TEXT        PRIMARY KEY,
    customer_id    TEXT        NOT NULL REFERENCES customer_profile (customer_id),
    product_code   TEXT        NOT NULL,
    kyc_reference  TEXT        NOT NULL UNIQUE,
    currency       CHAR(3)     NOT NULL,
    opened_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at      TIMESTAMPTZ
);
