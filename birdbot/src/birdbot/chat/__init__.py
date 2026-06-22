"""Open interaction layer (Nature Chat) — spike.

Unlike the deterministic main line (Workflow), this is where the LLM autonomously decides
which tools to call across multiple turns to answer open-ended questions ("is it a
regular?"). This is the layer where nanobot's agent loop earns its keep; the tools here
are nanobot Tools the loop can orchestrate. MVP spike: stub data, focused on exercising
the agent loop rather than the data sources.
"""
