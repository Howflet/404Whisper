"""
api/services/ — Application-level business logic.

Services encode the rules described in DATA_CONTRACT and CONTEXT.md.
They are pure Python (no HTTP, no DB) so they're easy to unit-test.

  vibes.py  → vibe classification, permission checks, cooldown helpers
"""
