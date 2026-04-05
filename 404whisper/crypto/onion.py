"""
Layer 2 — Crypto: Onion routing packet construction and peeling.

What this file does (plain English):
    Imagine passing a secret note through three strangers.  You put the
    note in envelope C, seal it for Stranger 3.  Then you put envelope C
    inside envelope B, seal it for Stranger 2.  Then you put envelope B
    inside envelope A, seal it for Stranger 1.

    You hand the packet to Stranger 1 (the "guard node").  They open
    their envelope, read "forward the inner packet to Stranger 2 at this
    address", and do so.  Stranger 2 opens theirs and forwards to
    Stranger 3.  Stranger 3 finally reads the real message.

    At no point does any single stranger know:
      - Who the original sender is (only Stranger 1 sees the sender).
      - Who the final recipient is (only Stranger 3 sees the destination).
      - The actual message contents (only Stranger 3 decrypts it).

    This is *onion routing*, named after the layers of an onion.
    The Session protocol uses this pattern to deliver messages anonymously
    through the Loki Service Node network.

Packet structure:
    Every layer (outer → inner) has the same binary format:

        ┌────────────────────┬──────────────────────────────────┐
        │  ephemeral_pub     │  encrypted_payload               │
        │  (32 bytes)        │  (nonce 24 + ciphertext + MAC 16)│
        └────────────────────┴──────────────────────────────────┘

    The hop receives the packet, uses its private key + ``ephemeral_pub``
    to reconstruct the shared secret, and decrypts the payload.

    Decrypted payload for a *routing* hop (guard or relay):
        ┌───────┬───────────┬──────────┬──────────────┬──────────────────┐
        │  0x01 │  port(2B) │ host_len │  host bytes  │  inner_packet    │
        └───────┴───────────┴──────────┴──────────────┴──────────────────┘
        The hop reads the next destination (host:port) and forwards
        ``inner_packet`` unchanged.

    Decrypted payload for the *exit* hop (final destination):
        ┌───────┬──────────────────────────────────────────────────────┐
        │  0x00 │  actual payload bytes (e.g. the API request body)    │
        └───────┴──────────────────────────────────────────────────────┘
        The exit node processes the payload directly.

Security properties:
    - Each layer uses a *fresh ephemeral keypair* — linking layers requires
      knowing multiple hop private keys simultaneously.
    - NaCl Box (X25519 + XSalsa20-Poly1305) ensures authentication at
      every layer — a forged inner packet is rejected before being forwarded.
    - Forward secrecy: ephemeral keys are discarded after each use.

Three-hop minimum:
    Session requires exactly 3 hops: guard → relay → exit.
    The guard knows the sender's IP.
    The exit knows the destination.
    Neither the guard nor the relay knows both.

Reference:
    Session whitepaper § 4.3 — Onion Requests
    https://arxiv.org/abs/2002.04609
"""
from __future__ import annotations

import logging
import os
import struct
from dataclasses import dataclass

from nacl.public import PrivateKey, PublicKey, Box
from nacl.encoding import RawEncoder
from nacl.exceptions import CryptoError

logger = logging.getLogger(__name__)

# ── Packet format constants ───────────────────────────────────────────────────

# The layer-type byte at the start of every decrypted payload.
_TYPE_EXIT:  int = 0x00  # this is the innermost layer; the payload is the real data
_TYPE_ROUTE: int = 0x01  # this is a routing layer; payload contains next-hop + inner packet

# Binary format sizes
_EPHEMERAL_PUB_SIZE: int = 32   # X25519 public key
_NONCE_SIZE: int = 24            # XSalsa20 nonce
_PORT_SIZE: int = 2              # big-endian uint16
_HOST_LEN_SIZE: int = 1          # single byte: length of the host string


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OnionHop:
    """
    Describes one node in the onion route.

    Attributes:
        public_key: The node's 32-byte X25519 public key.
                    Used to encrypt the layer only that node can decrypt.
        host:       IP address or hostname of the service node (e.g. "1.2.3.4").
                    Included so the previous hop knows where to forward.
        port:       TCP port the service node listens on (e.g. 8080).
    """
    public_key: bytes  # 32 bytes — the node's X25519 public key
    host: str          # e.g. "192.168.1.1"
    port: int          # e.g. 8080


@dataclass(frozen=True)
class PeeledLayer:
    """
    Result of peeling one layer of an onion packet.

    Attributes:
        inner_packet: The bytes to forward (or process, at the exit).
        next_hop:     Where to forward ``inner_packet``.
                      None means this is the exit layer — process ``inner_packet``
                      as the actual request payload instead of forwarding it.
    """
    inner_packet: bytes
    next_hop: dict | None  # {"host": str, "port": int} or None for exit


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wrap_exit_layer(payload: bytes, hop: OnionHop) -> bytes:
    """
    Build the innermost (exit) onion layer.

    Encrypts: ``b"\x00" + payload`` for the exit node.

    Args:
        payload: The actual request body the exit node will process.
        hop:     The exit service node (only its public key is used here).

    Returns:
        ``ephemeral_pub (32) + nonce (24) + ciphertext + MAC (16)``
    """
    # Generate a fresh ephemeral keypair for this layer.
    # Each layer gets its own ephemeral key for forward secrecy.
    ephemeral_priv_bytes = os.urandom(32)
    ephemeral_priv = PrivateKey(ephemeral_priv_bytes)
    ephemeral_pub  = bytes(ephemeral_priv.public_key)

    # The plaintext for the exit node: type byte (0x00) + actual payload.
    plaintext = bytes([_TYPE_EXIT]) + payload

    # Encrypt plaintext for the exit node using an NaCl Box.
    # Box(ephemeral_priv, exit_pub) derives the shared secret internally.
    box = Box(ephemeral_priv, PublicKey(hop.public_key))
    nonce = os.urandom(_NONCE_SIZE)
    encrypted = bytes(box.encrypt(plaintext, nonce=nonce, encoder=RawEncoder))

    return ephemeral_pub + encrypted


def _wrap_routing_layer(
    inner_packet: bytes,
    next_hop_host: str,
    next_hop_port: int,
    this_hop: OnionHop,
) -> bytes:
    """
    Build a routing (guard or relay) onion layer around an existing inner packet.

    Encrypts: ``b"\x01" + port(2) + host_len(1) + host + inner_packet``
    for this_hop's public key.

    Args:
        inner_packet:   The already-encrypted inner layer bytes.
        next_hop_host:  The host to which this_hop should forward the inner packet.
        next_hop_port:  The port.
        this_hop:       The service node whose public key we encrypt to.

    Returns:
        ``ephemeral_pub (32) + nonce (24) + ciphertext + MAC (16)``
    """
    host_bytes = next_hop_host.encode("ascii")
    if len(host_bytes) > 255:
        raise ValueError(f"Hostname too long ({len(host_bytes)} bytes, max 255): {next_hop_host!r}")

    # Routing plaintext layout:
    #   [0x01][port big-endian 2 bytes][host_len 1 byte][host bytes][inner_packet bytes]
    plaintext = (
        bytes([_TYPE_ROUTE])
        + struct.pack(">H", next_hop_port)  # ">H" = big-endian unsigned short
        + struct.pack(">B", len(host_bytes))
        + host_bytes
        + inner_packet
    )

    ephemeral_priv_bytes = os.urandom(32)
    ephemeral_priv = PrivateKey(ephemeral_priv_bytes)
    ephemeral_pub  = bytes(ephemeral_priv.public_key)

    box = Box(ephemeral_priv, PublicKey(this_hop.public_key))
    nonce = os.urandom(_NONCE_SIZE)
    encrypted = bytes(box.encrypt(plaintext, nonce=nonce, encoder=RawEncoder))

    return ephemeral_pub + encrypted


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_onion_packet(payload: bytes, hops: list[OnionHop]) -> bytes:
    """
    Wrap a payload in 3 layers of onion encryption.

    Call this before sending a request through the Session network.
    The resulting packet is sent to ``hops[0]`` (the guard node) via HTTP.
    Each subsequent hop decrypts its layer and forwards the inner packet
    to the next hop, until the exit node processes the original payload.

    The function builds from the INSIDE OUT:
        1. Wrap payload for hops[2] (exit)   → exit_layer
        2. Wrap exit_layer for hops[1] (relay), with hops[2]'s address → relay_layer
        3. Wrap relay_layer for hops[0] (guard), with hops[1]'s address → guard_layer

    The guard_layer is the outer packet returned to the caller.

    Args:
        payload: The raw request body (bytes) the exit node will process.
                 In Layer 4 (messaging), this will be a signed protobuf envelope.
        hops:    Exactly 3 ``OnionHop`` objects: [guard, relay, exit].

    Returns:
        The outer onion packet bytes, ready to be POSTed to ``hops[0].host:port``.

    Raises:
        ValueError: If ``hops`` does not contain exactly 3 entries.

    Example::

        packet = build_onion_packet(
            payload=b'{"method": "store", "params": {...}}',
            hops=[guard_node, relay_node, exit_node],
        )
        # POST packet to guard_node.host:guard_node.port
    """
    if len(hops) != 3:
        raise ValueError(
            f"build_onion_packet requires exactly 3 hops, got {len(hops)}"
        )

    guard, relay, exit_node = hops

    # Step 1: innermost layer — only the exit node can decrypt this.
    exit_layer = _wrap_exit_layer(payload, exit_node)
    logger.debug("Onion layer 3 (exit)  built — %d bytes", len(exit_layer))

    # Step 2: middle layer — tells the relay node where to forward.
    #   Plaintext contains: type(0x01) + exit_node.port + exit_node.host + exit_layer
    relay_layer = _wrap_routing_layer(
        inner_packet=exit_layer,
        next_hop_host=exit_node.host,
        next_hop_port=exit_node.port,
        this_hop=relay,
    )
    logger.debug("Onion layer 2 (relay) built — %d bytes", len(relay_layer))

    # Step 3: outermost layer — tells the guard node where to forward.
    #   Plaintext contains: type(0x01) + relay_node.port + relay_node.host + relay_layer
    guard_layer = _wrap_routing_layer(
        inner_packet=relay_layer,
        next_hop_host=relay.host,
        next_hop_port=relay.port,
        this_hop=guard,
    )
    logger.debug("Onion layer 1 (guard) built — %d bytes", len(guard_layer))

    return guard_layer


def peel_onion_layer(packet: bytes, private_key_bytes: bytes) -> PeeledLayer:
    """
    Decrypt one layer of an onion packet.

    This is the server-side counterpart to ``build_onion_packet()``.
    Each service node calls this when it receives an onion packet:
      - Guard node calls it to find out where to forward the inner packet.
      - Relay node calls it to find out where to forward.
      - Exit node calls it to extract and process the actual payload.

    Packet format expected:
        ``ephemeral_pub (32) | nonce (24) | ciphertext | MAC (16)``

    Args:
        packet:             The full onion packet bytes received by this node.
        private_key_bytes:  This node's 32-byte X25519 private key.

    Returns:
        A ``PeeledLayer`` with:
          - ``inner_packet``: Bytes to forward (routing) or process (exit).
          - ``next_hop``:     ``{"host": str, "port": int}`` for routing layers,
                              or ``None`` for the exit layer.

    Raises:
        ValueError:   If the packet is too short or the type byte is unknown.
        CryptoError:  If MAC verification fails (tampered or wrong key).

    Example::

        # On the guard node:
        layer = peel_onion_layer(received_packet, guard_private_key)
        if layer.next_hop:
            forward(layer.inner_packet, to=layer.next_hop)

        # On the exit node (next_hop is None):
        # layer.inner_packet is the original payload bytes
        response = handle_request(layer.inner_packet)
    """
    MIN_PACKET_SIZE = _EPHEMERAL_PUB_SIZE + _NONCE_SIZE + MAC_SIZE + 1
    if len(packet) < MIN_PACKET_SIZE:
        raise ValueError(
            f"Onion packet too short: {len(packet)} bytes (minimum {MIN_PACKET_SIZE})"
        )

    # ── Step 1: extract the ephemeral public key from the front of the packet ─
    ephemeral_pub_bytes = packet[:_EPHEMERAL_PUB_SIZE]
    encrypted_payload   = packet[_EPHEMERAL_PUB_SIZE:]

    # ── Step 2: derive shared secret and decrypt ───────────────────────────────
    my_private_key = PrivateKey(private_key_bytes)
    ephemeral_pub  = PublicKey(ephemeral_pub_bytes)

    box = Box(my_private_key, ephemeral_pub)
    try:
        plaintext = bytes(box.decrypt(encrypted_payload, encoder=RawEncoder))
    except CryptoError:
        logger.error("peel_onion_layer: MAC verification FAILED — packet may be corrupted or misdirected")
        raise

    # ── Step 3: parse the decrypted plaintext ─────────────────────────────────
    layer_type = plaintext[0]

    if layer_type == _TYPE_EXIT:
        # Exit layer — the rest is the actual payload.
        actual_payload = plaintext[1:]
        logger.debug("peel_onion_layer: exit layer — %d payload bytes", len(actual_payload))
        return PeeledLayer(inner_packet=actual_payload, next_hop=None)

    elif layer_type == _TYPE_ROUTE:
        # Routing layer — extract next-hop address and inner packet.
        # Format after the type byte:
        #   port (2 bytes big-endian) | host_len (1 byte) | host (host_len bytes) | inner_packet
        if len(plaintext) < 1 + _PORT_SIZE + _HOST_LEN_SIZE:
            raise ValueError("Routing layer plaintext too short to contain next-hop info")

        offset = 1  # skip type byte
        (port,) = struct.unpack_from(">H", plaintext, offset)
        offset += _PORT_SIZE

        host_len = plaintext[offset]
        offset += _HOST_LEN_SIZE

        if len(plaintext) < offset + host_len:
            raise ValueError(
                f"Routing layer plaintext truncated: expected {offset + host_len} bytes, "
                f"got {len(plaintext)}"
            )

        host = plaintext[offset : offset + host_len].decode("ascii")
        offset += host_len

        inner_packet = plaintext[offset:]
        logger.debug(
            "peel_onion_layer: routing layer — next_hop=%s:%d, %d inner bytes",
            host, port, len(inner_packet),
        )
        return PeeledLayer(
            inner_packet=inner_packet,
            next_hop={"host": host, "port": port},
        )

    else:
        raise ValueError(
            f"Unknown onion layer type byte: 0x{layer_type:02x}. "
            "Expected 0x00 (exit) or 0x01 (route)."
        )


# Re-export the MAC_SIZE constant so tests can compute expected sizes.
MAC_SIZE: int = 16  # noqa: F811 — Poly1305 tag size used in size assertions
