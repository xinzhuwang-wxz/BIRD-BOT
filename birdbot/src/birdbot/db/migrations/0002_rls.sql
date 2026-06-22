-- 0002_rls: enforce per-tenant row-level security on events (ADR-0004 / ADR-0009).
-- Business connects as the non-owner birdbot_app role so these policies bind; FORCE
-- makes them bind even for the table owner (defense in depth). current_setting(..., true)
-- returns NULL when app.current_tenant is unset, so an unscoped connection sees zero
-- rows (fail-closed) and cannot insert.
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON events;
CREATE POLICY tenant_isolation ON events
    USING (tenant_id = current_setting('app.current_tenant', true))
    WITH CHECK (tenant_id = current_setting('app.current_tenant', true));
