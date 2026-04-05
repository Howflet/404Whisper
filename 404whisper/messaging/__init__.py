"""
messaging/ — Message send/receive layer (Layer 4).

This package encodes the core messaging rules and will house the full
send/receive pipeline when Layer 4 is implemented.

Currently available sub-modules:
  ttl.py    → 404 vibe message TTL and purge logic
  delay.py  → SLOW_BURN vibe delivery delay logic
  chorus.py → CHORUS vibe 30-second grouping windows

Future sub-modules (Layer 4):
  compose.py  → build + sign + encrypt outgoing message envelopes
  parse.py    → decrypt + verify + deserialise incoming envelopes
  send.py     → store locally, dispatch via network.send_onion_request()
  poll.py     → background polling loop: receive → decrypt → store → WebSocket event
"""
