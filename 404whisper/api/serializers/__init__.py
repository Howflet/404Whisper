"""
api/serializers/ — Response serialisation helpers.

Serialisers convert raw DB dicts (snake_case) to API response dicts (camelCase).
They also apply vibe-specific masking rules (e.g. CONFESSIONAL anonymisation).

  messages.py → serialise_message()
"""
