"""Unit tests for post-call structured-output validation + failure classification.

Three fallback classes are distinguished (generic / context_window / content_policy),
plus schema-invalid output (ADR-0007 acceptance)."""
from __future__ import annotations

from birdbot.router.validate import (
    FailureClass,
    classify_failure,
    fallback_action,
    validate_structured_output,
)

_SCHEMA = {
    "type": "object",
    "properties": {"species": {"type": "string"}},
    "required": ["species"],
}


def test_valid_structured_output_passes():
    assert validate_structured_output({"species": "robin"}, _SCHEMA) == []


def test_invalid_structured_output_reports_errors():
    assert validate_structured_output({}, _SCHEMA)  # missing required field


def test_classify_context_window():
    assert classify_failure("Error: maximum context length exceeded") is FailureClass.CONTEXT_WINDOW


def test_classify_content_policy():
    assert classify_failure("response blocked by content policy") is FailureClass.CONTENT_POLICY


def test_classify_generic():
    assert classify_failure("503 service unavailable") is FailureClass.GENERIC


def test_fallback_action_per_class():
    assert fallback_action(FailureClass.CONTEXT_WINDOW) == "shrink_context"
    assert fallback_action(FailureClass.CONTENT_POLICY) == "reject"
    assert fallback_action(FailureClass.SCHEMA) == "retry_next"
    assert fallback_action(FailureClass.GENERIC) == "retry_next"
