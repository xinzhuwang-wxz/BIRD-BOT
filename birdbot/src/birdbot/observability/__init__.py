"""Observability & governance (ADR-0004 / ADR-0006): (tenant,skill,model) quota,
structured cost/data-flow telemetry, and surfaced alerts.

Day-one, not bolted on. Every LLM/tool/external-API call is recorded with full
attribution (tenant/user/device, logical->real provider, fallback chain, degradation,
data-source mode, tokens/cost/latency, data-flow region). Any degradation / circuit-break
/ quota-exhaustion is surfaced — never silent. The kernel hook default is reraise=False
(silently swallows); the BirdBot observability hook flips that.
"""
