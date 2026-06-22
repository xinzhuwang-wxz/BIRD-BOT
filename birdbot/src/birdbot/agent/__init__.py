"""BirdBot agent layer — a thin facade over the nanobot AgentLoop.

The facade wraps ``AgentLoop.from_config`` + ``process_direct`` and deliberately does
*not* reuse ``Nanobot.run`` (whose per-call ``_extra_hooks`` swap is unsafe under
multi-tenant concurrency). Hooks are wired at construction time instead.
"""
