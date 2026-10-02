CREATE TABLE customer_profile (
    customer_id     TEXT        PRIMARY KEY,
    first_name      TEXT        NOT NULL,
    last_name       TEXT        NOT NULL,
    date_of_birth   DATE,
    nationality     CHAR(2),
    email           TEXT,
    phone           TEXT,
    address         TEXT,
    marketing_email BOOLEAN     NOT NULL DEFAULT FALSE,
    marketing_sms   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    erased_at       TIMESTAMPTZ
);
