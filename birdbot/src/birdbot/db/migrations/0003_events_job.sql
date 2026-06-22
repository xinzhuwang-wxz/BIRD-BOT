-- 0003_events_job: extend events for the ingress job lifecycle (#4).
-- The identity triple (tenant_id already present + device_id + event_id) forms the
-- idempotency key; job_id is the public handle returned to the IoT platform; status
-- tracks the fast-stage lifecycle (queued -> ...).
ALTER TABLE events
    ADD COLUMN IF NOT EXISTS event_id  text,
    ADD COLUMN IF NOT EXISTS device_id text,
    ADD COLUMN IF NOT EXISTS user_id   text,
    ADD COLUMN IF NOT EXISTS job_id    uuid NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS status    text NOT NULL DEFAULT 'queued';

-- Idempotency: at most one row per (tenant, device, event). The key is scoped within
-- the tenant, and RLS keeps ON CONFLICT visible only within the current tenant.
CREATE UNIQUE INDEX IF NOT EXISTS events_idempotency_idx
    ON events (tenant_id, device_id, event_id);
