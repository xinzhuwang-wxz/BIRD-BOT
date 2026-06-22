-- 0004_workflow: durable step journal + transactional outbox (#5, ADR-0002).

-- Step journal for DBOS-style durable execution: a step is journaled before it runs,
-- recorded completed with its output after, and replayed (not re-executed) on restart.
CREATE TABLE IF NOT EXISTS workflow_steps (
    workflow_id text        NOT NULL,
    step_name   text        NOT NULL,
    tenant_id   text        NOT NULL,
    status      text        NOT NULL DEFAULT 'pending',  -- pending | completed | failed
    output      jsonb,
    attempts    integer     NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workflow_id, step_name)
);

-- Transactional outbox: rows are enqueued in the SAME transaction as the business
-- write, then a separate relay delivers them at-least-once. dedupe_key lets the
-- consumer dedupe redundant deliveries.
CREATE TABLE IF NOT EXISTS outbox (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    text        NOT NULL,
    topic        text        NOT NULL,
    payload      jsonb       NOT NULL,
    dedupe_key   text,
    status       text        NOT NULL DEFAULT 'pending',  -- pending | delivered
    attempts     integer     NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now(),
    delivered_at timestamptz
);
CREATE INDEX IF NOT EXISTS outbox_pending_idx ON outbox (status, id);

-- workflow_steps: business (app role) only — FORCE RLS like events (defense in depth).
ALTER TABLE workflow_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_steps FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON workflow_steps;
CREATE POLICY tenant_isolation ON workflow_steps
    USING (tenant_id = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant', true));

-- outbox: enqueue is tenant-scoped (app role, RLS-enforced), but the relay is a system
-- component that must sweep every tenant's pending rows — so ENABLE (not FORCE) RLS,
-- letting the owner/relay connection bypass it while the app role stays isolated.
ALTER TABLE outbox ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON outbox;
CREATE POLICY tenant_isolation ON outbox
    USING (tenant_id = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant', true));

GRANT SELECT, INSERT, UPDATE, DELETE ON workflow_steps TO birdbot_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON outbox TO birdbot_app;
