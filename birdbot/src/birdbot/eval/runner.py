"""Eval runner (G3): run scenarios through a Story function + deterministic checks.

``story_fn`` is injected (real LLM via build_story_prompt + GatewayStoryLLM, or a recorded /
synthetic double), so the runner works both in CI (deterministic, no key) and against a live
model. An optional ``judge`` adds semantic LLM-as-judge scoring on top of the deterministic
gate (needs a key — hence injected, never required).
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from birdbot.eval.checks import check_story
from birdbot.eval.scenarios import EvalScenario


@dataclass(frozen=True, slots=True)
class EvalResult:
    scenario: str
    issues: list[str]
    judge: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return not self.issues


async def run_eval(
    scenarios: Sequence[EvalScenario],
    story_fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    *,
    judge: Callable[[dict[str, Any], EvalScenario], Awaitable[dict[str, Any]]] | None = None,
) -> list[EvalResult]:
    results: list[EvalResult] = []
    for scenario in scenarios:
        story = await story_fn(scenario.snapshot)
        issues = check_story(story, scenario)
        judged = await judge(story, scenario) if judge is not None else None
        results.append(EvalResult(scenario.name, issues, judged))
    return results


def pass_rate(results: Sequence[EvalResult]) -> float:
    return sum(r.passed for r in results) / len(results) if results else 0.0
