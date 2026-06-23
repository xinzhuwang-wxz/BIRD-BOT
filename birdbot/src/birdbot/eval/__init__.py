"""Story / Nature Chat quality evaluation (G3): real feeder scenarios + a regression gate.

Two layers: deterministic checks (no key, CI-regressable — schema completeness, rarity
language, species grounding, region grounding against S13's deterministic region) and an
optional LLM-as-judge hook (semantic quality; needs a key, so it's injected, not required).
The deterministic gate is what guards against regressions on every change.
"""
