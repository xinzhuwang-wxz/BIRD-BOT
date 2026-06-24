"""DemoEngine — the one live backend behind all three faces.

It wires the **real** BirdBot components and drives them with the offline fakes:

  fast stage   real run_fast_stage + Calibrator + FrameScorer, with the real
               geo/temporal reranker (context/rerank.py) actually injected — the
               "implemented but unwired" gap from the feature inventory, shown working.
  rarity       real BirdContextService over fake sources, with real source-mode +
               commercial interception (ADR-0005) surfaced through the alert sink.
  story        real GatewayStoryLLM + build_story_prompt + STORY_SCHEMA gate, every call
               through the real LLMGateway (quota -> route -> telemetry -> cost, ADR-0014).
  chat         the real NatureChatHandler + AgentRuntime + tools, over a fake DB so device
               history is genuine.

Postgres/outbox/workflow are bypassed (in-memory event log + inline deep stage); that is
the only place the production main-line differs. See demo/README.md.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from birdbot.chat.handler import NatureChatHandler
from birdbot.context.models import SourceMode
from birdbot.context.rerank import make_geo_temporal_reranker
from birdbot.context.service import BirdContextService
from birdbot.deep.llm import build_story_llm
from birdbot.deep.story import STORY_SCHEMA, build_story_prompt
from birdbot.ingress.schema import BirdEvent, CoarseLocation, SpeciesCandidate
from birdbot.observability.alerts import SOURCE_SWITCH, Alert
from birdbot.observability.telemetry import cost_by_tenant
from birdbot.recognition.adapter import RecognitionAdapter
from birdbot.recognition.fast_stage import run_fast_stage
from birdbot.recognition.types import FrameFeatures, ScoredCandidate
from birdbot.router.registry import Capability, CapabilityRegistry, ModelEntry
from birdbot.router.router import ModelRouter
from birdbot.runtime.gateway import LLMGateway

from demo.bus import Broadcaster
from demo.fakes import (
    STORY_BRIEF,
    AsyncQuota,
    BroadcastAlertSink,
    BroadcastTelemetrySink,
    FakeCompletion,
    FakeContextSource,
    FakeDB,
)
from demo.scenarios import (
    CATALOG,
    DEVICES_BY_ID,
    FLEET,
    SCENARIOS,
    device_public,
    scenario_public,
)

_CAPS = frozenset({Capability.VISION, Capability.STRUCTURED_OUTPUT,
                   Capability.FUNCTION_CALLING, Capability.PROMPT_CACHING})

# The capability registry the router resolves against. Two backends for one logical model
# (fallback order) + an EU-resident route, so the console's routing table shows real
# residency/compliance/pricing — and the deep-reasoning call really gets governed.
_REGISTRY = CapabilityRegistry([
    ModelEntry("deep-reasoning", "anthropic", "claude-sonnet-demo", _CAPS,
               200_000, 3.0, "US", frozenset({"dpf"})),
    ModelEntry("deep-reasoning", "openai", "gpt-vision-demo", _CAPS,
               128_000, 5.0, "US", frozenset({"dpf"})),
    ModelEntry("deep-reasoning-eu", "mistral", "mistral-large-eu", _CAPS,
               128_000, 2.5, "EU", frozenset()),
])


def _softmax(xs: list[float]) -> list[float]:
    ceiling = max(xs)
    exps = [math.exp(x - ceiling) for x in xs]
    total = sum(exps) or 1.0
    return [e / total for e in exps]


class DemoEngine:
    def __init__(self) -> None:
        self.bus = Broadcaster()
        self.telemetry = BroadcastTelemetrySink(self.bus.publish)
        self.alerts = BroadcastAlertSink(self.bus.publish)
        self.quota = AsyncQuota()
        self.completion = FakeCompletion()

        self.gateway = LLMGateway(
            router=ModelRouter(_REGISTRY), telemetry=self.telemetry,
            alerts=self.alerts, quota=self.quota, completion=self.completion,
        )
        # Region-aware deep-stage routing: EU/UK traffic resolves to an EU-resident model,
        # everything else to the US (DPF) one — so the console's data-flow region is honest.
        self.story_llm_us = build_story_llm(gateway=self.gateway)
        self.story_llm_eu = build_story_llm(gateway=self.gateway, logical_model="deep-reasoning-eu")

        sources = {name: FakeContextSource(name)
                   for name in ("ebird", "inaturalist", "taxonomy")}
        self.context = BirdContextService(sources=sources, observer=self._on_context)

        self._events: list[dict] = []                       # in-memory event log
        self._observations: dict[tuple[str, str], list[dict]] = {}
        self.feed: list[dict] = []                          # global newest-first feed

        self.chat_handler = NatureChatHandler(
            gateway=self.gateway, alerts=self.alerts,
            db=FakeDB(self._count_visits), context_service=self.context,
        )

    # --- context observer: surface source-mode + compliance interception ---
    def _on_context(self, diag: dict[str, Any]) -> None:
        self.bus.publish({"type": "context", "diag": diag})
        if diag.get("blocked") or diag.get("degraded"):
            # eBird/iNat intercepted pre-license, or a source switch — never silent.
            self.alerts.emit(Alert(SOURCE_SWITCH, diag))

    # --- device history (powers the chat tool + the "seen N times" line) ---
    def _count_visits(self, tenant_id: str, device_id: str, species: str) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        return sum(
            1 for e in self._events
            if e["tenant_id"] == tenant_id and e["device_id"] == device_id
            and e["species"] == species and e["ts"] >= cutoff
        )

    # --- the whole pipeline for one simulated sighting ---------------------
    async def ingest_event(self, spec: dict[str, Any]) -> dict[str, Any]:
        device = DEVICES_BY_ID.get(spec.get("device_id", ""))
        if device is None:
            raise ValueError(f"unknown device {spec.get('device_id')!r}")
        scenario = SCENARIOS.get(spec.get("scenario", ""))
        if scenario is None:
            raise ValueError(f"unknown scenario {spec.get('scenario')!r}")

        region = spec.get("region") or device.region
        mode = SourceMode(spec.get("source_mode", "auto"))
        licensed = bool(spec.get("ebird_licensed", False))  # ADR-0005: false pre-license
        commercial = not licensed  # commercial use of unlicensed sources is intercepted

        event_id = f"evt-{uuid.uuid4().hex[:10]}"
        probs = _softmax([s for _, s in scenario.top_k])
        media = [f"frame://{device.device_id}/{event_id}/{i}"
                 for i in range(len(scenario.frames))]

        # A real, schema-valid BirdEvent — exactly what an IoT platform would POST.
        event = BirdEvent(
            tenant_id=device.tenant_id, user_id=device.user_id, device_id=device.device_id,
            event_id=event_id, media=media,
            top_k=[SpeciesCandidate(label=lbl, score=round(p, 4))
                   for (lbl, _), p in zip(scenario.top_k, probs)],
            location=CoarseLocation(region=region),
        )
        self.bus.publish({"type": "pipeline", "stage": "ingest", "event_id": event_id,
                          "device_id": device.device_id, "event": event.model_dump()})

        # --- fast stage (real), with the real geo/temporal reranker injected ---
        ctx = await self.context.get_context(
            region=region, date=_today(), mode=mode, commercial=commercial)
        candidates = [
            ScoredCandidate(lbl, p, CATALOG[lbl].taxon() if lbl in CATALOG else None)
            for (lbl, _), p in zip(scenario.top_k, probs)
        ]
        frames = [FrameFeatures(frame_id=media[i], aesthetic=a, sharpness=s, motion_blur=m)
                  for i, (a, s, m) in enumerate(scenario.frames)]
        adapter = RecognitionAdapter(reranker=make_geo_temporal_reranker(ctx))
        fast = run_fast_stage(raw_candidates=candidates, frames=frames, adapter=adapter)

        top = fast.candidates[0]
        identity = self._identity(fast, top)
        rarity = ctx.labels.get(top.label)
        rarity_str = rarity.value if rarity is not None else "unknown"
        species_info = CATALOG.get(top.label)
        visits_30d = self._count_visits(device.tenant_id, device.device_id, top.label)

        self.bus.publish({"type": "pipeline", "stage": "recognition", "event_id": event_id,
                          "decision": fast.decision.action, "reason": fast.decision.reason,
                          "confidence": round(fast.confidence, 3), "identity": identity,
                          "best_frame": fast.best_frame.frame_id if fast.best_frame else None})

        # --- deep stage (real gateway + story + schema gate) ---
        snapshot = {
            "candidates": [(c.label, round(c.score, 3)) for c in fast.candidates[:3]],
            "rarity": {top.label: rarity_str},
            "region": region,
            "evidence": {"decision": fast.decision.action, "confidence": round(fast.confidence, 3)},
            "attribution": ctx.attribution,
        }
        STORY_BRIEF.set({
            "common": species_info.common if species_info else top.label,
            "scientific": top.label, "decision": fast.decision.action,
            "rarity": rarity_str, "region": region,
            "behavior_hint": scenario.behavior_hint, "visits_30d": visits_30d,
            "attribution": ctx.attribution,
        })
        story_llm = self.story_llm_eu if region in ("EU", "UK") else self.story_llm_us
        story = await story_llm.generate(
            prompt=build_story_prompt(snapshot),
            frames=[fast.best_frame.frame_id] if fast.best_frame else [],
            envelope=event.envelope, region=region,
        )
        story_ok = all(k in story for k in STORY_SCHEMA["required"])
        if not story_ok:  # the real workflow rejects off-contract stories — surface, don't ship
            self.alerts.emit(Alert("degraded", {"stage": "story", "reason": "schema_violation"}))

        # --- record the finished observation ---
        now = datetime.now(timezone.utc)
        self._events.append({
            "tenant_id": device.tenant_id, "device_id": device.device_id,
            "species": top.label, "ts": now,
        })
        obs = {
            "id": event_id, "ts": now.isoformat(),
            "tenant_id": device.tenant_id, "device_id": device.device_id,
            "user_id": device.user_id, "device_label": device.label, "place": device.place,
            "region": region,
            "species": species_info.public() if species_info else {"scientific": top.label,
                                                                    "common": top.label,
                                                                    "emoji": "🐦", "color": "#888"},
            "identity": identity, "confidence": round(fast.confidence, 3),
            "decision": fast.decision.action, "decision_reason": fast.decision.reason,
            "rollup_to": fast.decision.rollup_to,
            "rarity": rarity_str, "source": ctx.source, "attribution": ctx.attribution,
            "source_degraded": ctx.degraded, "source_diagnostics": ctx.diagnostics,
            "best_frame": fast.best_frame.frame_id if fast.best_frame else None,
            "frame_count": len(frames), "visits_30d": visits_30d,
            "behavior": story.get("behavior", ""),
            "rarity_narrative": story.get("rarity_narrative", ""),
            "story": story.get("story", ""),
            "story_ok": story_ok,
        }
        self._observations.setdefault((device.tenant_id, device.device_id), []).append(obs)
        self.feed.insert(0, obs)
        self.bus.publish({"type": "observation", "observation": obs})
        return obs

    def _identity(self, fast: Any, top: ScoredCandidate) -> str:
        info = CATALOG.get(top.label)
        common = info.common if info else top.label
        if fast.decision.action == "rollup" and fast.decision.rollup_to:
            return f"{fast.decision.rollup_to} (reported at family level)"
        if fast.decision.action == "escalate":
            return f"likely {common} — flagged for a closer look"
        return common

    # --- chat (real handler) ----------------------------------------------
    async def chat(self, spec: dict[str, Any]) -> str:
        device = DEVICES_BY_ID.get(spec.get("device_id", ""))
        if device is None:
            raise ValueError(f"unknown device {spec.get('device_id')!r}")
        region = spec.get("region") or device.region
        return await self.chat_handler.handle(
            envelope=BirdEvent(
                tenant_id=device.tenant_id, user_id=device.user_id,
                device_id=device.device_id, event_id="chat", location=CoarseLocation(region=region),
            ).envelope,
            prompt=spec["prompt"], region=region,
        )

    # --- reads for the UIs -------------------------------------------------
    def observations(self, tenant_id: str, device_id: str) -> list[dict]:
        items = self._observations.get((tenant_id, device_id), [])
        return list(reversed(items))  # newest first

    def digest(self, tenant_id: str, device_id: str) -> dict[str, Any]:
        items = self._observations.get((tenant_id, device_id), [])
        today = _today()
        todays = [o for o in items if o["ts"].startswith(today)]
        if not todays:
            return {"date": today, "device_id": device_id, "count": 0,
                    "summary": "No visits logged yet today — the feeder is quiet so far."}
        species = {}
        for o in todays:
            species[o["species"]["common"]] = species.get(o["species"]["common"], 0) + 1
        rank = {"rare": 0, "seasonal": 1, "common": 2, "unknown": 3}
        rarest = min(todays, key=lambda o: rank.get(o["rarity"], 3))
        best = max(todays, key=lambda o: o.get("frame_count", 0))
        headline = rarest["species"]["common"]
        rare_note = (f"The highlight was a {headline}"
                     + (f", locally {rarest['rarity']}!" if rarest["rarity"] in ("rare", "seasonal")
                        else "."))
        return {
            "date": today, "device_id": device_id, "count": len(todays),
            "distinct_species": len(species), "by_species": species,
            "rarest": {"common": headline, "rarity": rarest["rarity"]},
            "best_frame": best["best_frame"],
            "summary": f"{len(todays)} visits from {len(species)} species today. {rare_note}",
        }

    # --- ops console feeds -------------------------------------------------
    def metrics(self) -> dict[str, Any]:
        recs = self.telemetry.records
        calls = len(recs)
        by_provider: dict[str, int] = {}
        by_region: dict[str, int] = {}
        for r in recs:
            by_provider[r.provider] = by_provider.get(r.provider, 0) + 1
            reg = r.data_flow_region or "—"
            by_region[reg] = by_region.get(reg, 0) + 1
        alert_kinds: dict[str, int] = {}
        for a in self.alerts.alerts:
            alert_kinds[a.kind] = alert_kinds.get(a.kind, 0) + 1
        tenants = {r.tenant_id for r in recs}
        return {
            "calls": calls,
            "tokens": sum(r.tokens for r in recs),
            "cost_usd": round(sum(r.cost_usd for r in recs), 6),
            "avg_latency_ms": round(sum(r.latency_ms for r in recs) / calls, 1) if calls else 0.0,
            "degraded": sum(1 for r in recs if r.degraded),
            "by_provider": by_provider, "by_region": by_region,
            "cost_by_tenant": {k: round(v, 6) for k, v in cost_by_tenant(recs).items()},
            "alerts": alert_kinds, "alert_total": len(self.alerts.alerts),
            "quota_acquired": self.quota.acquired, "quota_rejected": self.quota.rejected,
            "tenants_active": len(tenants), "devices_active": len({(o["tenant_id"], o["device_id"]) for o in self.feed}),
            "observations": len(self.feed),
        }

    def routing_table(self) -> list[dict]:
        return _registry_entries()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _registry_entries() -> list[dict]:
    rows = []
    for logical in ("deep-reasoning", "deep-reasoning-eu"):
        for i, e in enumerate(_REGISTRY.entries_for(logical)):
            rows.append({
                "logical_name": e.logical_name, "order": i, "backend": e.backend,
                "model": e.model, "residency": e.residency_region,
                "compliance_tags": sorted(e.compliance_tags),
                "pricing_per_mtok": e.pricing_per_mtok,
                "capabilities": sorted(c.value for c in e.capabilities),
            })
    return rows


def fleet_public() -> list[dict]:
    return [device_public(d) for d in FLEET]


def scenarios_public() -> list[dict]:
    return [scenario_public(s) for s in SCENARIOS.values()]
