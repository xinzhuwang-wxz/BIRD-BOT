"""Static demo data: the bird catalog, the regional rarity tables, the device fleet, and
the named sighting scenarios the simulator can fire.

Everything is keyed by scientific name so it lines up across the recognition candidates,
the rarity frequency tables, and the catalog cards. The regional frequency tables feed the
fake ContextSource so the *real* BirdContextService computes genuine rarity labels
(common/seasonal/rare) and exercises its source-mode + compliance interception.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Species:
    scientific: str
    common: str
    emoji: str
    color: str  # card gradient seed
    genus: str
    family: str
    order: str

    def taxon(self) -> dict[str, str]:
        return {"species": self.scientific, "genus": self.genus,
                "family": self.family, "order": self.order}

    def public(self) -> dict[str, str]:
        return {"scientific": self.scientific, "common": self.common,
                "emoji": self.emoji, "color": self.color}


# --- catalog ---------------------------------------------------------------
CATALOG: dict[str, Species] = {s.scientific: s for s in [
    Species("Cardinalis cardinalis", "Northern Cardinal", "🐦", "#c0392b",
            "Cardinalis", "Cardinalidae", "Passeriformes"),
    Species("Haemorhous mexicanus", "House Finch", "🐤", "#e67e22",
            "Haemorhous", "Fringillidae", "Passeriformes"),
    Species("Spinus tristis", "American Goldfinch", "🟡", "#f1c40f",
            "Spinus", "Fringillidae", "Passeriformes"),
    Species("Cyanocitta cristata", "Blue Jay", "🐦‍⬛", "#2980b9",
            "Cyanocitta", "Corvidae", "Passeriformes"),
    Species("Poecile atricapillus", "Black-capped Chickadee", "🐧", "#34495e",
            "Poecile", "Paridae", "Passeriformes"),
    Species("Junco hyemalis", "Dark-eyed Junco", "⚫", "#7f8c8d",
            "Junco", "Passerellidae", "Passeriformes"),
    Species("Selasphorus rufus", "Rufous Hummingbird", "🦟", "#16a085",
            "Selasphorus", "Trochilidae", "Apodiformes"),
    Species("Passerina ciris", "Painted Bunting", "🌈", "#8e44ad",
            "Passerina", "Cardinalidae", "Passeriformes"),
    # EU yard
    Species("Cyanistes caeruleus", "Eurasian Blue Tit", "🐦", "#2471a3",
            "Cyanistes", "Paridae", "Passeriformes"),
    Species("Erithacus rubecula", "European Robin", "🐦", "#cb4335",
            "Erithacus", "Muscicapidae", "Passeriformes"),
    Species("Coccothraustes coccothraustes", "Hawfinch", "🦜", "#6c3483",
            "Coccothraustes", "Fringillidae", "Passeriformes"),
]}


# --- regional rarity tables (feed the fake ContextSource) -------------------
# Frequency = local P(occurrence). The real rarity_label() maps:
#   >= 0.20 common · >= 0.02 seasonal · else rare.
_US_WEST = {
    "Cardinalis cardinalis": 0.42, "Haemorhous mexicanus": 0.40,
    "Spinus tristis": 0.12, "Cyanocitta cristata": 0.30,
    "Poecile atricapillus": 0.26, "Junco hyemalis": 0.09,
    "Selasphorus rufus": 0.05, "Passerina ciris": 0.008,
}
_US_EAST = {
    "Cardinalis cardinalis": 0.50, "Haemorhous mexicanus": 0.33,
    "Spinus tristis": 0.18, "Cyanocitta cristata": 0.38,
    "Poecile atricapillus": 0.22, "Junco hyemalis": 0.15,
    "Passerina ciris": 0.012,
}
_EU_DE = {
    "Cyanistes caeruleus": 0.52, "Erithacus rubecula": 0.35,
    "Coccothraustes coccothraustes": 0.011,
}

REGION_FREQUENCIES: dict[str, dict[str, float]] = {
    "US-CA": _US_WEST, "US-WA": _US_WEST, "US-NY": _US_EAST,
    "US": _US_WEST, "EU": _EU_DE, "DE": _EU_DE,
}


def frequencies_for(region: str) -> dict[str, float]:
    return REGION_FREQUENCIES.get(region, _US_WEST)


# --- device fleet ----------------------------------------------------------
@dataclass(frozen=True)
class Device:
    tenant_id: str
    device_id: str
    user_id: str
    label: str          # human name of the feeder
    place: str          # where it lives
    region: str         # eBird region code the platform supplies
    scenarios: list[str] = field(default_factory=list)


FLEET: list[Device] = [
    Device("acme-feeders", "feeder-garden-01", "user-amy",
           "Amy's Garden Feeder", "Palo Alto, CA backyard", "US-CA",
           ["clear-cardinal", "two-finches", "blurry-visitor", "rare-bunting", "hummingbird"]),
    Device("acme-feeders", "feeder-lake-02", "user-ben",
           "Ben's Lakeside Feeder", "Ithaca, NY dock", "US-NY",
           ["clear-cardinal", "two-finches", "blurry-visitor"]),
    Device("birdco-eu", "feeder-berlin-01", "user-lena",
           "Lena's Balkon-Futterstelle", "Berlin, DE balcony", "EU",
           ["blue-tit", "robin-eu", "rare-hawfinch"]),
]

DEVICES_BY_ID: dict[str, Device] = {d.device_id: d for d in FLEET}


# --- sighting scenarios ----------------------------------------------------
# Each scenario produces a synthetic on-device Top-K + a frame-quality profile. The Top-K
# shapes the *real* fast-stage decision (accept / rollup / escalate); the frame profile
# shapes the *real* best-frame pick. behavior_hint nudges the (fake, schema-valid) story.
@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    truth: str                       # scientific name of the "real" bird
    top_k: list[tuple[str, float]]   # on-device candidates (label, raw score)
    frames: list[tuple[float, float, float]]  # (aesthetic, sharpness, motion_blur) per frame
    behavior_hint: str
    expect: str                      # narration aid: what the fast stage should decide


SCENARIOS: dict[str, Scenario] = {s.key: s for s in [
    Scenario(
        "clear-cardinal", "A confident Northern Cardinal",
        "Cardinalis cardinalis",
        [("Cardinalis cardinalis", 5.4), ("Haemorhous mexicanus", 1.1), ("Spinus tristis", 0.6)],
        [(0.62, 0.71, 0.18), (0.88, 0.83, 0.06), (0.55, 0.60, 0.30)],
        "feeding at the platform, occasionally vigilant", "accept",
    ),
    Scenario(
        "two-finches", "Two finches too close to call",
        "Haemorhous mexicanus",
        [("Spinus tristis", 2.95), ("Haemorhous mexicanus", 2.85), ("Cardinalis cardinalis", 0.4)],
        [(0.70, 0.64, 0.20), (0.74, 0.69, 0.15)],
        "perched and cracking seeds",
        "rollup to family Fringillidae (too close even after the local-frequency rerank)",
    ),
    Scenario(
        "blurry-visitor", "A low-confidence blurry visitor",
        "Poecile atricapillus",
        [("Poecile atricapillus", 1.6), ("Junco hyemalis", 1.2), ("Spinus tristis", 0.9)],
        [(0.30, 0.28, 0.72), (0.41, 0.35, 0.58)],
        "darting in and out, hard to see", "escalate (below accept threshold)",
    ),
    Scenario(
        "rare-bunting", "A rare Painted Bunting!",
        "Passerina ciris",
        [("Passerina ciris", 4.9), ("Cardinalis cardinalis", 0.8)],
        [(0.93, 0.90, 0.04), (0.71, 0.66, 0.12)],
        "showing off vivid plumage at the feeder", "accept (locally rare — the highlight)",
    ),
    Scenario(
        "hummingbird", "A Rufous Hummingbird at the nectar",
        "Selasphorus rufus",
        [("Selasphorus rufus", 4.2), ("Spinus tristis", 0.5)],
        [(0.80, 0.58, 0.40), (0.84, 0.62, 0.33)],
        "hovering at the nectar port", "accept (seasonal visitor)",
    ),
    Scenario(
        "blue-tit", "A Eurasian Blue Tit on the balcony",
        "Cyanistes caeruleus",
        [("Cyanistes caeruleus", 5.0), ("Erithacus rubecula", 0.7)],
        [(0.85, 0.80, 0.08)],
        "acrobatic on the seed ball", "accept",
    ),
    Scenario(
        "robin-eu", "A European Robin",
        "Erithacus rubecula",
        [("Erithacus rubecula", 4.6), ("Cyanistes caeruleus", 0.9)],
        [(0.78, 0.74, 0.12)],
        "standing watchful, red breast puffed", "accept",
    ),
    Scenario(
        "rare-hawfinch", "A rare Hawfinch",
        "Coccothraustes coccothraustes",
        [("Coccothraustes coccothraustes", 4.7), ("Cyanistes caeruleus", 0.6)],
        [(0.90, 0.88, 0.05)],
        "cracking a cherry stone with that huge bill", "accept (locally rare)",
    ),
]}


def device_public(d: Device) -> dict:
    return {"tenant_id": d.tenant_id, "device_id": d.device_id, "user_id": d.user_id,
            "label": d.label, "place": d.place, "region": d.region, "scenarios": d.scenarios}


def scenario_public(s: Scenario) -> dict:
    return {"key": s.key, "title": s.title, "truth": s.truth,
            "common": CATALOG[s.truth].common if s.truth in CATALOG else s.truth,
            "expect": s.expect, "behavior_hint": s.behavior_hint}
