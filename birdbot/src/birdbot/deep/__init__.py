"""Deep stage (S8): behavior understanding + local-rarity Story.

Advanced asynchronously by the Workflow Runtime (#5, re-entrant/crash-resumable). A
multimodal LLM — routed via the Model Router (#6) — receives only 3-8 curated frames +
structured evidence (never the raw video) and produces behavior / rarity narrative /
Story. The result is persisted and a callback is enqueued in the same transaction via the
transactional outbox (#5).

Note: the deep stage is a fixed-control-flow workflow with a single structured LLM call per
step — AgentRuntime's autonomous tool-selection is NOT used here; the LLM is a simple injected
StoryLLM port (governed by the LLMGateway). Hard contracts (output schema / location
precision) live in this code, NOT in the Skill (Skills have no enforcement power).
"""
