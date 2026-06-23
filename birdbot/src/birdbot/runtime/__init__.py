"""Self-hosted agent runtime (ADR-0013): replaces nanobot's AgentLoop.

A thin LLM -> tool_calls -> execute -> loop, backed by LiteLLM. Tools are duck-typed
(name / description / parameters / async execute) so this layer has no nanobot dependency
(the vendored kernel was removed — ADR-0013).
"""
