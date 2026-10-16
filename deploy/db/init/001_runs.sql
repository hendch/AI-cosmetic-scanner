-- Run history: one row per workflow execution (scan, ingest or evaluate).
CREATE TABLE IF NOT EXISTS runs (
    id          BIGSERIAL PRIMARY KEY,
    request_id  TEXT        NOT NULL,
    status      TEXT        NOT NULL,
    action      TEXT        NOT NULL,
    origin      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    result      JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_request_id_idx ON runs (request_id);
CREATE INDEX IF NOT EXISTS runs_status_idx     ON runs (status);
CREATE INDEX IF NOT EXISTS runs_created_at_idx ON runs (created_at DESC);
