"""Deterministic, offline fakes that stand in for the only things BirdBot needs the
outside world for — an LLM provider, the eBird/iNat HTTP sources, Postgres, and Redis —
so the *real* governance / story / recognition / rarity components run end-to-end with no
keys and no services. The fakes are intentionally thin: they implement exactly the ports
the real code already depends on.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import random
from collections.abc import Callable, Mapping
from typing import Any

from birdbot.observability.alerts import Alert
from birdbot.observability.quota import QuotaKey, QuotaLimiter
from birdbot.observability.telemetry import CallRecord

from demo.scenarios import CATALOG, frequencies_for

# Per-request brief the engine hands to the fake "model" for the deep-stage story. Set
# right before story_llm.generate(); read inside FakeCompletion. contextvars keep it
# correct under concurrent requests.
STORY_BRIEF: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "story_brief", default=None
)


# --- fake eBird/iNat/taxonomy sources --------------------------------------
class FakeContextSource:
    """A ContextSource (region -> {species: frequency}). All three demo sources read the
    same regional table — the *real* BirdContextService is what gates them by source-mode
    and commercial authorization, so eBird/iNat interception is genuine, not staged."""

    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name = name
        self._fail = fail

    async def frequencies(self, *, region: str, date: str) -> Mapping[str, float]:
        await asyncio.sleep(0.01)  # pretend it's a network hop
        if self._fail:
            raise RuntimeError(f"{self.name} source unavailable")
        return dict(frequencies_for(region))


# --- async quota over the in-process limiter -------------------------------
class AsyncQuota:
    """The gateway awaits try_acquire/release; the in-memory QuotaLimiter is sync. This is
    the same shim shape the RedisQuotaLimiter exposes."""

    def __init__(self, *, rpm: int = 600, max_concurrent: int = 32) -> None:
        self._limiter = QuotaLimiter(rpm=rpm, max_concurrent=max_concurrent)
        self.acquired = 0
        self.rejected = 0

    async def try_acquire(self, key: QuotaKey) -> bool:
        ok = self._limiter.try_acquire(key)
        self.acquired += int(ok)
        self.rejected += int(not ok)
        return ok

    async def release(self, key: QuotaKey) -> None:
        self._limiter.release(key)


# --- broadcasting telemetry + alert sinks ----------------------------------
def _record_dict(c: CallRecord) -> dict:
    return {
        "tenant_id": c.tenant_id, "user_id": c.user_id, "device_id": c.device_id,
        "logical_model": c.logical_model, "provider": c.provider,
        "fallback_chain": list(c.fallback_chain), "degraded": c.degraded,
        "source_mode": c.source_mode, "tokens": c.tokens,
        "cost_usd": round(c.cost_usd, 6), "latency_ms": round(c.latency_ms, 1),
        "data_flow_region": c.data_flow_region,
    }


class BroadcastTelemetrySink:
    """Keeps the real CallRecord list (chargeback/audit) and mirrors each to the live bus."""

    def __init__(self, publish: Callable[[dict], None]) -> None:
        self.records: list[CallRecord] = []
        self._publish = publish

    def record(self, call: CallRecord) -> None:
        self.records.append(call)
        self._publish({"type": "telemetry", "record": _record_dict(call)})


class BroadcastAlertSink:
    def __init__(self, publish: Callable[[dict], None]) -> None:
        self.alerts: list[Alert] = []
        self._publish = publish

    def emit(self, alert: Alert) -> None:
        self.alerts.append(alert)
        self._publish({"type": "alert", "kind": alert.kind, "detail": alert.detail})


# --- fake DB so the REAL NatureChatHandler runs unmodified ------------------
class _Conn:
    def __init__(self, count: Callable[[str, str], int]) -> None:
        self._count = count

    async def fetchval(self, _sql: str, device_id: str, species: str) -> int:
        # The handler's query is fixed (visits of this species on this device, 30d); we
        # answer it from the in-memory event log instead of Postgres.
        return self._count(device_id, species)


class _Scope:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _Conn:
        return self._conn

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class FakeDB:
    def __init__(self, count_visits: Callable[[str, str, str], int]) -> None:
        self._count_visits = count_visits

    def tenant_scope(self, tenant_id: str) -> _Scope:
        return _Scope(_Conn(lambda dev, sp: self._count_visits(tenant_id, dev, sp)))


# --- the deterministic, offline "LLM" --------------------------------------
_BEHAVIOR = {
    "accept": "{common} is {hint}. Posture and the curated frame support a confident read.",
    "rollup": "A finch is {hint}; the top two candidates are too close to separate at the "
              "species level, so this is reported at the family level.",
    "escalate": "Something small is {hint}. The on-device read is below the confidence bar, "
                "so it is flagged for a closer second look rather than over-claimed.",
}
_RARITY_LINE = {
    "common": "For {region} this species is locally common — a regular at feeders this "
              "time of year.",
    "seasonal": "For {region} this is a seasonal visitor — present in some weeks and absent "
                "in others, which is why it feels like an event.",
    "rare": "For {region} this is genuinely rare — few recent local records, so a "
            "feeder visit is a real highlight.",
    "unknown": "Local frequency for {region} is not available right now, so rarity is left "
               "open rather than guessed.",
}


class FakeCompletion:
    """An async ``completion(model=, messages=, **kw)`` indistinguishable to the gateway
    from litellm.acompletion. Deep-stage calls (response_format=json) return a schema-valid
    story built from the per-request brief; chat calls (tools=) drive a real two-step
    tool-use loop and then answer from the tool observations."""

    def __init__(self, *, seed: int = 7) -> None:
        self._rng = random.Random(seed)
        # keyword -> scientific name, for spotting a species in free-form chat
        self._kw: list[tuple[str, str]] = []
        for sci, sp in CATALOG.items():
            for w in (sp.common.lower().split() + [sci.lower()]):
                if len(w) >= 4:
                    self._kw.append((w, sci))

    async def __call__(self, *, model: str, messages: list[dict], **kw: Any) -> dict:
        if kw.get("response_format"):
            await asyncio.sleep(self._rng.uniform(0.35, 0.9))   # deep vision call
            return self._story(model)
        if kw.get("tools") is not None:
            await asyncio.sleep(self._rng.uniform(0.15, 0.45))  # chat turn
            return self._chat(model, messages)
        await asyncio.sleep(0.1)
        return self._wrap("OK.")

    # -- deep stage --------------------------------------------------------
    def _story(self, model: str) -> dict:
        b = STORY_BRIEF.get() or {}
        common = b.get("common", "the bird")
        decision = b.get("decision", "accept")
        rarity = b.get("rarity", "unknown")
        region = b.get("region", "your area")
        hint = b.get("behavior_hint", "active at the feeder")
        visits = int(b.get("visits_30d", 0))
        attribution = b.get("attribution")

        behavior = _BEHAVIOR.get(decision, _BEHAVIOR["accept"]).format(common=common, hint=hint)
        rarity_narrative = _RARITY_LINE.get(rarity, _RARITY_LINE["unknown"]).format(region=region)
        if attribution:
            rarity_narrative += f" ({attribution})"

        seen = ("the first time it's been logged here" if visits == 0
                else f"the {_ordinal(visits + 1)} visit logged at this feeder")
        story = (
            f"A {common} dropped by — {hint}. {rarity_narrative} "
            f"This is {seen} in the last 30 days. "
            + ("The frame caught the light well; one to keep." if rarity != "rare"
               else "Worth saving the best frame — a sighting like this doesn't come often.")
        )
        payload = {"behavior": behavior, "rarity_narrative": rarity_narrative, "story": story}
        return self._wrap(json.dumps(payload))

    # -- chat --------------------------------------------------------------
    def _chat(self, model: str, messages: list[dict]) -> dict:
        observations = [m for m in messages if m.get("role") == "tool"]
        if observations:
            return self._wrap(self._answer_from_tools(messages, observations))

        user = _last_user_text(messages)
        species = self._spot_species(user)
        if species is None:
            return self._wrap(
                "I can tell you about the birds at your feeder — try asking about a "
                "specific one, like \"how often does the cardinal visit?\" or \"is the "
                "painted bunting rare here?\""
            )
        calls = [
            {"id": "call_hist", "type": "function",
             "function": {"name": "device_history", "arguments": json.dumps({"species": species})}},
            {"id": "call_rar", "type": "function",
             "function": {"name": "bird_context", "arguments": json.dumps({"species": species})}},
        ]
        return {"choices": [{"message": {"content": None, "tool_calls": calls}}],
                "usage": {"total_tokens": 180}}

    def _answer_from_tools(self, messages: list[dict], observations: list[dict]) -> str:
        visits, rarity, species = None, None, None
        for ob in observations:
            try:
                data = json.loads(ob.get("content") or "{}")
            except json.JSONDecodeError:
                continue
            if "visits_30d" in data:
                visits = int(data["visits_30d"])
            if "rarity" in data:
                rarity = data["rarity"]
        species = self._spot_species(_first_user_text(messages)) or "this species"
        common = CATALOG[species].common if species in CATALOG else species
        v = visits if visits is not None else 0
        rar = rarity or "unknown"
        seen = ("hasn't been logged here yet in the last 30 days"
                if v == 0 else f"has visited this feeder {v} time(s) in the last 30 days")
        rar_line = {
            "common": "It's a locally common bird, so expect it to keep coming back.",
            "seasonal": "It's a seasonal visitor here, so sightings come and go with the weeks.",
            "rare": "It's locally rare — a genuine highlight whenever it shows up.",
        }.get(rar, "Local rarity isn't available right now.")
        return f"The {common} {seen}. {rar_line}"

    def _spot_species(self, text: str) -> str | None:
        t = (text or "").lower()
        for kw, sci in self._kw:
            if kw in t:
                return sci
        return None

    # -- shared ------------------------------------------------------------
    def _wrap(self, content: str) -> dict:
        return {"choices": [{"message": {"content": content}}],
                "usage": {"total_tokens": 120 + len(content) // 4}}


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return _as_text(m.get("content"))
    return ""


def _first_user_text(messages: list[dict]) -> str:
    for m in messages:
        if m.get("role") == "user":
            return _as_text(m.get("content"))
    return ""


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # multimodal parts
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
