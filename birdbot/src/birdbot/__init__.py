"""BirdBot application layer — cloud AI observation atop the vendored nanobot kernel.

BirdBot is the independent application package; the kernel lives in ``nanobot/`` as a
controlled vendor fork (ADR-0001). Domain code stays here and never lands inside
``nanobot/agent/tools/``; it extends the kernel through documented seams
(entry_points tools, hooks, config) rather than by editing the kernel.
"""
