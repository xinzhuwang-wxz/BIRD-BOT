"""BirdBot product showcase — a runnable, offline demonstration of the whole product.

Three faces over one live backend:
  * device simulator  — an IoT feeder fabricating BirdEvents (the data source)
  * end-user app       — the nature-observation experience the owner sees
  * vendor ops console — the governance/observability the operator sees

NOT production. It reuses the *real* BirdBot governance + story + recognition + rarity
components and fakes only the external IO (LLM provider, eBird/iNat HTTP, Postgres). See
``demo/README.md`` for the exact real-vs-faked boundary.
"""
