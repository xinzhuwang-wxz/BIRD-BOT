"""Fast-stage recognition adapter (ADR-0008): consume the on-device Top-K and turn it
into calibrated candidates + evidence + a decision, plus a best-frame pick.

Pure domain logic — no LLM, no I/O. The recognition backend (species classifier) is a
separate layer from the LLM (ADR-0008); this package never calls an LLM. The SpeciesNet
ensemble pattern (calibrate -> geo/temporal rerank -> decide: accept/rollup/escalate)
informs the shape. Confidence is temperature-scaled before any threshold is applied.
"""
