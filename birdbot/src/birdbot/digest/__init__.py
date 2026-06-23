"""Daily digest (S9): aggregate the day's events per user/device and deliver via outbox.

Cron is only the trigger (ADR-0002); aggregation/state live in Postgres. The self-hosted
CronService (ADR-0013) fires the trigger once DailyDigestScheduler wires on_job + start().
"""
