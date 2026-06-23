"""BirdBot — self-hosted cloud AI agent service for smart bird feeders (ADR-0013).

An independent application package, no kernel dependency (the vendored nanobot kernel was
removed; ADR-0013 supersedes ADR-0001). Agent runtime = ``birdbot.runtime.AgentRuntime`` (a
thin LLM→tool_calls→execute loop); provider gateway = LiteLLM via
``birdbot.runtime.gateway.LLMGateway``; tools = ``birdbot.runtime.tool.Tool``; structured
output validation = jsonschema.
"""
