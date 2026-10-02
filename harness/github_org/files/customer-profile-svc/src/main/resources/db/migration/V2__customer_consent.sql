CREATE TABLE customer_consent (
    consent_id   TEXT        PRIMARY KEY,
    customer_id  TEXT        NOT NULL REFERENCES customer_profile (customer_id),
    consent_type TEXT        NOT NULL,
    scope        TEXT        NOT NULL,
    granted_at   TIMESTAMPTZ NOT NULL,
    expires_at   TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ
);

CREATE INDEX customer_consent_customer ON customer_consent (customer_id);
