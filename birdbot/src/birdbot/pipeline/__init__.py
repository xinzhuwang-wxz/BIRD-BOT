"""Main-line orchestration (S15): wire ingress -> fast stage -> deep stage end-to-end.

Converts a BirdEvent into fast-stage inputs, runs the fast stage on the synchronous 202
path (landing a candidate/best-frame snapshot), then advances the deep stage
asynchronously via the Workflow Runtime, routing the LLM through the Model Router and
delivering the result via the transactional outbox.
"""
