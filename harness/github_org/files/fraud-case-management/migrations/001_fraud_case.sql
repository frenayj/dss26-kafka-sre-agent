CREATE TABLE fraud_case (
    case_id            UUID           PRIMARY KEY,
    customer_id        TEXT           NOT NULL,
    card_token         TEXT           NOT NULL,
    trigger            TEXT           NOT NULL,
    priority           TEXT           NOT NULL,
    triggering_auth_id TEXT           UNIQUE,
    status             TEXT           NOT NULL,
    assigned_to        TEXT,
    outcome            TEXT,
    actions_taken      TEXT[]         NOT NULL DEFAULT '{}',
    loss_amount        NUMERIC(18, 3),
    currency           CHAR(3),
    opened_at          TIMESTAMPTZ    NOT NULL,
    resolved_at        TIMESTAMPTZ
);

CREATE INDEX fraud_case_queue ON fraud_case (priority, opened_at) WHERE status = 'OPEN';
