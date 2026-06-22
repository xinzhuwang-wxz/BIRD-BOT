"""Test-support utilities for BirdBot (record/replay LLM transport, etc.).

These let real end-to-end tests run in CI without a real key or network access — record
provider responses once, replay them forever (S14).
"""
