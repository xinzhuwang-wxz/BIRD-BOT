"""Privacy layer (ADR-0007 + 方案 §3/§9): location precision degradation, a unified
output/log redaction layer (location + sensitive species + PII), retention TTLs with an
expiry purge, and DSAR cascade delete/export by tenant/user/device.

Location is degraded BEFORE it is persisted or crosses a border (data minimization).
"""
