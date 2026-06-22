"""Post-call validation + failure classification for the Model Router.

Structured output is validated against its JSON schema with the standard ``jsonschema``
validator (ADR-0013: self-hosted, no kernel dependency), and provider failures are
classified so the right fallback applies: generic/schema -> retry the next entry,
context_window -> shrink the context, content_policy -> reject (no retry).
"""
from __future__ import annotations

from enum import Enum
from typing import Any

import jsonschema


class FailureClass(str, Enum):
    GENERIC = "generic"
    SCHEMA = "schema"
    CONTEXT_WINDOW = "context_window"
    CONTENT_POLICY = "content_policy"


def validate_structured_output(data: Any, schema: dict[str, Any]) -> list[str]:
    """Validate ``data`` against a JSON schema; returns error messages (empty = valid)."""
    validator = jsonschema.Draft202012Validator({**schema, "type": "object"})
    return [error.message for error in validator.iter_errors(data)]


_CONTEXT_MARKERS = ("context length", "context window", "maximum context", "too many tokens")
_POLICY_MARKERS = ("content policy", "content_policy", "safety", "blocked")


def classify_failure(error_text: str) -> FailureClass:
    low = error_text.lower()
    if any(marker in low for marker in _CONTEXT_MARKERS):
        return FailureClass.CONTEXT_WINDOW
    if any(marker in low for marker in _POLICY_MARKERS):
        return FailureClass.CONTENT_POLICY
    return FailureClass.GENERIC


_ACTIONS = {
    FailureClass.GENERIC: "retry_next",
    FailureClass.SCHEMA: "retry_next",
    FailureClass.CONTEXT_WINDOW: "shrink_context",
    FailureClass.CONTENT_POLICY: "reject",
}


def fallback_action(failure_class: FailureClass) -> str:
    return _ACTIONS[failure_class]
