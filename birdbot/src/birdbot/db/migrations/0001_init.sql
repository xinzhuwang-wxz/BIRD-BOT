-- 0001_init: seed business-state schema.
-- The events table is the BirdEvent full-lifecycle state landing spot (ADR-0002);
-- extended by #4 (BirdEvent v0). Every business table carries tenant_id + index so it
-- can be tenant-isolated by RLS (ADR-0004); the RLS policy itself is added in 0002.
CREATE TABLE IF NOT EXISTS events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   text        NOT NULL,
    kind        text        NOT NULL,
    payload     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS events_tenant_created_idx ON events (tenant_id, created_at);

-- Least-privilege DML for the non-owner application role. The role's lifecycle is the
-- deploy environment's responsibility (ADR-0009); the migration only grants on it.
GRANT SELECT, INSERT, UPDATE, DELETE ON events TO birdbot_app;
