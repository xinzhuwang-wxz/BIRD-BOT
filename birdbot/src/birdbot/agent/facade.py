"""BirdBotAgent — a thin, multi-tenant-safe facade over the nanobot AgentLoop.

Wraps ``AgentLoop.from_config`` + ``process_direct``. Unlike ``Nanobot.run`` it never
swaps ``loop._extra_hooks`` per call: that mutation interleaves under multi-tenant
concurrency, so hooks are wired once at construction instead. Per-turn tenant scoping
rides on the explicit ``session_key`` and a per-call ``tools`` registry.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nanobot.agent.hook import AgentHook
    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.tools.registry import ToolRegistry
    from nanobot.bus.events import OutboundMessage


class BirdBotAgent:
    """Thin facade driving the kernel agent loop for one BirdBot turn."""

    def __init__(self, loop: AgentLoop) -> None:
        self._loop = loop

    @classmethod
    def from_config(
        cls,
        config_path: str | Path | None = None,
        *,
        workspace: str | Path | None = None,
        hooks: list[AgentHook] | None = None,
    ) -> BirdBotAgent:
        """Build a facade from a config file, wiring ``hooks`` at construction.

        Args:
            config_path: Path to ``config.json``; defaults to the kernel's default path.
            workspace: Optional override of the workspace directory from config.
            hooks: Lifecycle hooks attached to the loop once, at construction time
                (NOT swapped per call as ``Nanobot.run`` does).
        """
        from nanobot.agent.loop import AgentLoop
        from nanobot.config.loader import load_config, resolve_config_env_vars
        from nanobot.providers.image_generation import image_gen_provider_configs

        resolved: Path | None = None
        if config_path is not None:
            resolved = Path(config_path).expanduser().resolve()
            if not resolved.exists():
                raise FileNotFoundError(f"Config not found: {resolved}")

        config = resolve_config_env_vars(load_config(resolved))
        if workspace is not None:
            config.agents.defaults.workspace = str(
                Path(workspace).expanduser().resolve()
            )

        loop = AgentLoop.from_config(
            config,
            hooks=hooks,
            image_generation_provider_configs=image_gen_provider_configs(config),
        )
        return cls(loop)

    async def process(
        self,
        content: str,
        *,
        session_key: str,
        media: list[str] | None = None,
        tools: ToolRegistry | None = None,
        ephemeral: bool = False,
    ) -> OutboundMessage | None:
        """Run one agent turn via the kernel's ``process_direct`` (never ``Nanobot.run``).

        Args:
            content: The user/event content for this turn.
            session_key: Tenant-scoped conversation key, e.g.
                ``tenant:{tid}:user:{uid}:device:{did}``.
            media: Optional media references passed through to the loop.
            tools: Optional per-turn tool registry (used for per-stage / tenant-scoped
                tool sets); falls back to the loop's default registry when omitted.
            ephemeral: When True, the turn is not persisted to session history.
        """
        return await self._loop.process_direct(
            content,
            session_key=session_key,
            media=media,
            tools=tools,
            ephemeral=ephemeral,
        )
