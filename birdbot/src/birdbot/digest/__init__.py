"""Daily digest (S9): aggregate the day's events per user/device and deliver via outbox.

Cron is only the trigger (ADR-0002); aggregation/state live in Postgres. The kernel's
CronService is a dead store until the app wires on_job and calls start() (the D5 gap) —
DailyDigestScheduler does exactly that, without touching the kernel.
"""
