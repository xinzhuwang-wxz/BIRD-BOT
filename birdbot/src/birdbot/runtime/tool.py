"""Self-hosted Tool protocol (ADR-0013 / M1): replaces nanobot's Tool + tool_parameters.

A tool exposes name / description / parameters (JSON Schema) + async execute. AgentRuntime
duck-types these; ToolRegistry collects them. No nanobot dependency. Parameter
casting/validation (nanobot's Schema) is intentionally out of scope — AgentRuntime passes
the model's parsed arguments straight to execute, as the live spike confirmed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from copy import deepcopy
from typing import Any, TypeVar

_ToolT = TypeVar("_ToolT", bound="Tool")


class Tool(ABC):
    """Agent capability the runtime can call: name + JSON-Schema params + async execute."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calls."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        ...

    @property
    def read_only(self) -> bool:
        """Whether this tool is side-effect free (advisory; parallelism is runtime policy)."""
        return False

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Run the tool; returns a string or content blocks."""
        ...

    def to_schema(self) -> dict[str, Any]:
        """OpenAI function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def tool_parameters(schema: dict[str, Any]) -> Callable[[type[_ToolT]], type[_ToolT]]:
    """Class decorator: attach JSON Schema and inject a concrete ``parameters`` property.

    Use on ``Tool`` subclasses instead of writing ``@property def parameters``. The schema
    is stored on the class and returned as a fresh deep copy on each access.
    """

    def decorator(cls: type[_ToolT]) -> type[_ToolT]:
        frozen = deepcopy(schema)

        @property
        def parameters(self: Any) -> dict[str, Any]:
            return deepcopy(frozen)

        cls.parameters = parameters  # type: ignore[assignment]

        abstract = getattr(cls, "__abstractmethods__", None)
        if abstract is not None and "parameters" in abstract:
            cls.__abstractmethods__ = frozenset(abstract - {"parameters"})  # type: ignore[misc]

        return cls

    return decorator
