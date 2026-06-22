"""Deep stage (S8): behavior understanding + local-rarity Story.

Advanced asynchronously by the Workflow Runtime (#5, re-entrant/crash-resumable). A
multimodal LLM — routed via the Model Router (#6) — receives only 3-8 curated frames +
structured evidence (never the raw video) and produces behavior / rarity narrative /
Story. The result is persisted and a callback is enqueued in the same transaction via the
transactional outbox (#5).

Note (basis evaluation): the deep stage is a fixed-control-flow workflow with a single
structured LLM call per step — the kernel agent loop's autonomous tool-selection is not
exercised here, so the LLM is a simple injected StoryLLM port, not a full process_direct
agent loop. Hard contracts (tool allow-list / output schema / location precision) live in
this code, NOT in the Skill (Skills have no enforcement power — D10).
"""
