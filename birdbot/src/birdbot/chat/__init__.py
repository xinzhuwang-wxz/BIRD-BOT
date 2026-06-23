"""Open interaction layer (Nature Chat).

Unlike the deterministic main line (Workflow), this is where the LLM autonomously decides
which tools to call across multiple turns to answer open-ended questions ("is it a
regular?"). It runs on the self-hosted ``AgentRuntime`` (ADR-0013), which orchestrates the
tool_calls returned by the LiteLLM gateway; the tools here are ``birdbot.runtime.tool.Tool``
instances. MVP uses stub data, focused on exercising the loop rather than the data sources.
"""
