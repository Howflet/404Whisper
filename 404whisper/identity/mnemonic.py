"""
Layer 1 — Identity: Session mnemonic seed phrases.

What this file does (plain English):
    A 32-byte random seed is hard for humans to back up — it looks like:
        b'\\x8f\\x3a\\x01…'
    A mnemonic converts those bytes into a sequence of ordinary English words
    that are far easier to write down and remember:
        "abbey bugs cabin diet emit flirt grace habit iceberg jewel kitty lemon …"

    This file implements the ENCODE (bytes → words) and DECODE (words → bytes)
    directions, plus a checksum word that lets you catch typos on import.

Algorithm (Monero/Oxen/Session — NOT BIP39):
    Session uses the same mnemonic scheme as Monero (on which Oxen is based).
    The word list has 1626 words — DIFFERENT from BIP39's 2048-word list.

    Encoding one 4-byte chunk → 3 words:
        n  = little-endian uint32 of the 4 bytes
        w1 = n % N                           (N = 1626)
        w2 = (n // N + w1) % N
        w3 = (n // N // N + w2) % N

    32 bytes = 8 chunks → 8 × 3 = 24 words, plus 1 checksum word = 25 words.

    Checksum word:
        Take the first 3 characters of each of the 24 data words.
        Join them into one string, compute CRC32, result % 24 → index into
        the 24 words.  The checksum word is words[that index].

    Decoding is the algebraic inverse of encoding.

Reference: https://github.com/monero-project/monero/blob/master/src/mnemonics/
"""
from __future__ import annotations

import binascii
import logging
import struct

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class MnemonicDecodeError(ValueError):
    """
    Raised when a mnemonic cannot be decoded.

    This happens when:
      - A word is not in the Session word list.
      - The checksum word does not match (i.e. there is a typo).
      - The word count is wrong (must be 25 for a 32-byte seed).
    """


# ---------------------------------------------------------------------------
# Session / Monero English word list — 1626 words.
#
# Source: Monero project (monero-project/monero src/mnemonics/english.h),
# which is the same list used by Oxen and Session.
# "abandon" (BIP39 index 0) does NOT appear in this list.
# ---------------------------------------------------------------------------

# fmt: off  ← tells formatters to leave this block alone
WORD_LIST: list[str] = [
    "abbey", "abducts", "ability", "abode", "abort", "abrupt", "absorbs",
    "abyss", "account", "ache", "aching", "acumen", "adapt", "adept",
    "adhesive", "adjust", "adopt", "adult", "aerial", "afar", "affair",
    "afoot", "agile", "aglow", "agony", "agreed", "ahead", "aided",
    "ailments", "ailing", "aims", "ajar", "akin", "album", "alchemy",
    "alias", "alibi", "aliens", "aloof", "alum", "amber", "amends",
    "ample", "amuse", "angel", "animals", "antenna", "aorta", "aplenty",
    "apply", "arch", "ardent", "arena", "arise", "army", "aroma", "arose",
    "array", "ascend", "audio", "august", "aunt", "avatar", "avid",
    "avoid", "award", "awful", "axes", "axis", "azure", "bacon", "bail",
    "bait", "bald", "bane", "banter", "bash", "bawled", "batch", "bayou",
    "beach", "beast", "bedchamber", "beguile", "behold", "being",
    "believe", "bemused", "binocular", "birth", "bison", "blab", "blank",
    "blast", "bleary", "bliss", "blots", "blueprint", "blunt", "bossy",
    "boxer", "breach", "breathe", "bricks", "brisk", "brunt", "budget",
    "buffet", "bull", "bungee", "buoyant", "bushel", "cabin", "calm",
    "canoe", "capital", "capture", "care", "cargo", "cater", "cautious",
    "cave", "cedar", "cement", "certain", "chain", "chaos", "chariot",
    "chef", "chess", "chicken", "chiefly", "chime", "cider", "cinch",
    "civic", "clan", "claps", "clash", "clay", "cleft", "clerk", "click",
    "cloak", "coils", "comet", "compass", "complex", "confide",
    "consider", "context", "convict", "coral", "cork", "corpse",
    "counsel", "cowl", "cram", "craving", "cringe", "crisis", "crisp",
    "croon", "crown", "crumb", "cunning", "curl", "cute", "dagger",
    "daily", "damp", "dance", "dapper", "daring", "dash", "debut",
    "decoy", "delay", "depot", "depth", "deputy", "dexterity", "dice",
    "diet", "digit", "dizzy", "dogma", "doubt", "dough", "dove", "drab",
    "dragon", "dreams", "drool", "drum", "dryer", "duchy", "duel",
    "duke", "dull", "dump", "dusk", "duties", "earth", "edgy", "elbow",
    "elegant", "embody", "emerge", "emit", "empire", "empty", "endure",
    "energy", "enjoy", "epic", "epoch", "equip", "essence", "exact",
    "exert", "exist", "expand", "expert", "eyes", "faint", "false",
    "fancy", "fared", "farmer", "farce", "feast", "fetch", "fever",
    "fiasco", "fickle", "fiesta", "file", "flair", "flask", "flesh",
    "focal", "force", "forge", "fossil", "foyer", "frail", "frisk",
    "froth", "frown", "furry", "fuzzy", "gains", "gamble", "gaze",
    "genre", "glee", "gloat", "gloom", "glow", "gnaw", "gossip",
    "grace", "grant", "grasp", "gravel", "graze", "grief", "grill",
    "grin", "grips", "groom", "grotto", "guild", "gulch", "gumbo",
    "guru", "gusts", "habit", "hamlet", "handy", "harsh", "haven",
    "hazel", "herbs", "herds", "hippo", "hobby", "holly", "honey",
    "honor", "hoodie", "humid", "hush", "hyper", "iceberg", "idly",
    "igloo", "image", "impel", "inept", "inert", "island", "item",
    "itch", "ivory", "jaunt", "jelly", "jest", "jewels", "joke",
    "jolly", "jubilee", "jumpy", "jungle", "kayak", "keen", "ketch",
    "kiln", "kinship", "kitty", "known", "kudos", "lagoon", "layer",
    "leading", "leaves", "leech", "legal", "lemon", "lemur", "level",
    "lifts", "light", "loamy", "lobby", "lofty", "lore", "loud",
    "luckily", "lunar", "lurk", "lush", "lyceum", "magnet", "mailed",
    "majestic", "manage", "mango", "maple", "match", "mauled", "maximum",
    "maze", "meadow", "merge", "merit", "messy", "moat", "money",
    "mood", "morbid", "mortar", "mosaic", "mouth", "muddy", "mulch",
    "munch", "murmur", "myriad", "nanny", "neatly", "needed", "nerves",
    "nettle", "nibble", "noble", "nods", "noisy", "noodles", "notable",
    "novel", "nullify", "obey", "object", "occur", "offset", "olive",
    "ominous", "omit", "onset", "opaque", "opus", "orbit", "orchid",
    "orient", "origin", "orphan", "ostrich", "outfit", "oxidize",
    "ozone", "paddle", "paid", "panel", "papaya", "parcel", "parrot",
    "pasture", "patio", "pause", "peeled", "pelted", "pepper", "percent",
    "persist", "pest", "phase", "phone", "piano", "pilot", "pinch",
    "pixel", "pizza", "plains", "planet", "pliers", "plod", "pluck",
    "plunge", "point", "pollen", "pour", "powder", "prank", "prayer",
    "preach", "pride", "prime", "problem", "proceed", "process", "prod",
    "promise", "prose", "provoke", "prowl", "pumice", "puppet", "push",
    "puzzle", "quaint", "quarry", "queen", "quest", "quicken", "quiet",
    "quote", "radar", "radish", "rally", "ramp", "ranked", "rave",
    "recess", "recipe", "recount", "recruit", "refresh", "regal",
    "reign", "relic", "relish", "remedy", "report", "reptile", "retina",
    "reveal", "reward", "rhythm", "ridge", "riot", "rival", "robust",
    "rocky", "roster", "rotation", "rotten", "roughly", "rugged",
    "ruin", "rumble", "salmon", "sand", "scar", "scene", "scone",
    "scoop", "scorch", "scout", "scruffy", "season", "sedan", "seer",
    "serenity", "seven", "shack", "shamble", "shallow", "shed", "shiver",
    "shrine", "shucks", "shun", "sieve", "silk", "singed", "siren",
    "skater", "sketch", "skull", "slate", "sleet", "slept", "slid",
    "slope", "slug", "slump", "snag", "snail", "sneak", "sneaky",
    "sniff", "snippet", "snout", "snowy", "soar", "socket", "soggy",
    "sonar", "song", "soothe", "sorry", "sow", "sparse", "speech",
    "speed", "sphere", "spice", "spindle", "spiral", "splash", "spore",
    "sprout", "spur", "stab", "stain", "stale", "stamp", "star",
    "startle", "stays", "steam", "steer", "stern", "steep", "stew",
    "steward", "sting", "stir", "stitch", "stock", "stomp", "stoop",
    "storm", "stout", "strain", "stride", "strictly", "stroll", "stump",
    "substance", "such", "suffer", "sulk", "summit", "supple", "surface",
    "sustain", "swam", "swept", "swift", "swirl", "symbol", "tabby",
    "tackle", "taken", "tapir", "tarnish", "task", "taunt", "tempo",
    "tense", "tennis", "thicket", "think", "thirst", "thorn", "thud",
    "thunder", "tidal", "tilt", "timer", "titan", "toil", "tokens",
    "topaz", "torch", "toss", "total", "tough", "tour", "town", "toxic",
    "trade", "trigger", "tricky", "trophy", "trouble", "trout", "trudge",
    "trust", "tuck", "tumble", "tunnel", "turmoil", "turtle", "tusk",
    "twitch", "typhoon", "ulcer", "umpire", "unhappy", "union",
    "universe", "upset", "usher", "utmost", "utter", "valley", "vapor",
    "vault", "venture", "verify", "vessel", "victim", "video", "vigor",
    "villain", "vine", "violet", "viral", "vision", "vocal", "voice",
    "volcano", "voyage", "wafer", "wager", "walnut", "wander", "wanting",
    "warped", "wave", "weakly", "weird", "whack", "wheat", "whinny",
    "widen", "willow", "wince", "witty", "woken", "wolves", "woven",
    "wrath", "wreck", "wrestle", "yacht", "yawn", "yearly", "yield",
    "youth", "zealous", "zeal", "zenith", "zest", "zinc", "zipper",
    "zone", "zoom", "access", "acclaim", "acid", "acquire", "acrid",
    "active", "actors", "acutely", "address", "adhere", "admire",
    "advance", "adverse", "advice", "affirm", "afloat", "ageless",
    "agency", "agent", "agitate", "agonize", "alarm", "alert", "algebra",
    "align", "allot", "allow", "almond", "alone", "alter", "always",
    "amaze", "ambush", "amend", "anchor", "annex", "annoy", "anoint",
    "answer", "ante", "appeal", "append", "arduous", "argue", "arisen",
    "armada", "arrest", "arson", "ascent", "asset", "assure", "atlas",
    "atone", "attic", "attune", "auburn", "aura", "balance", "ballet",
    "banter", "barely", "bargain", "barren", "basalt", "basket", "battle",
    "beaming", "beckon", "bedrock", "bellow", "beneath", "bestow",
    "beyond", "blaze", "blight", "blunder", "blurry", "boldly", "bones",
    "bounty", "brace", "bravo", "brawl", "brisk", "brittle", "broad",
    "bronze", "brood", "broth", "bruise", "bundle", "burden", "burrow",
    "cactus", "canopy", "canyon", "carp", "carve", "caste", "castle",
    "catnap", "cattle", "cauldron", "cease", "chant", "charge", "charm",
    "chasm", "cheer", "cherish", "chide", "chirp", "chorus", "circle",
    "cipher", "citrus", "clamp", "clarify", "clarity", "cleave",
    "cling", "cluster", "coarse", "cobalt", "cobra", "coerce", "coil",
    "collect", "column", "combine", "conceal", "conduit", "conflict",
    "conform", "conquer", "convey", "copper", "core", "correct",
    "cosmos", "cotton", "cradle", "crater", "crawl", "creak", "creed",
    "crest", "crimp", "cross", "cruelty", "crush", "crystal", "cuckoo",
    "cursed", "dagger", "dawn", "daylight", "decay", "deceit", "deduce",
    "deepen", "defend", "delight", "demand", "dense", "desert", "devout",
    "differ", "dilute", "direct", "discord", "dismiss", "distant",
    "divide", "domain", "donkey", "downfall", "drift", "driven",
    "droplet", "drown", "durable", "eager", "eagle", "earnest",
    "eastern", "eclipse", "effect", "effort", "embark", "embrace",
    "enhance", "enrich", "entice", "equal", "erase", "errand", "escape",
    "eternal", "evolve", "exceed", "exclude", "exempt", "exile", "exult",
    "fable", "factor", "famine", "fathom", "feral", "fervent", "fester",
    "field", "fierce", "filter", "final", "fissure", "fjord", "flame",
    "flare", "flatten", "fleet", "flicker", "flinch", "float", "floss",
    "flower", "fluent", "flutter", "forage", "forbid", "forest",
    "forfeit", "formal", "fracture", "fragile", "frame", "frenzy",
    "fright", "frozen", "frugal", "furtive", "gather", "gauge", "gibbet",
    "ginger", "glacial", "glance", "glide", "glitter", "glum",
    "goblin", "golden", "gondola", "gorge", "govern", "gradient",
    "gravel", "greed", "grieve", "grizzly", "grown", "grumble", "guard",
    "haunt", "headlong", "herald", "hidden", "hollow", "homage",
    "humble", "hungry", "hurtle", "ignite", "illicit", "imagine",
    "impart", "implore", "impose", "incline", "indent", "indigo",
    "induct", "infuse", "inhale", "inquire", "insist", "intact",
    "invent", "invoke", "isolate", "justice", "kindle", "kingdom",
    "kneel", "labyrinth", "lantern", "lapse", "lavish", "linger",
    "liquid", "lofty", "longing", "lotus", "loyal", "lucid", "lure",
    "luster", "lament", "malice", "mantle", "marble", "marshal",
    "marvel", "melting", "memory", "mending", "mentor", "merit",
    "mirage", "mirth", "mist", "modest", "molten", "motif", "motion",
    "mount", "mourn", "muffled", "murky", "mystic", "narrow", "nearby",
    "nimble", "notion", "nurture", "oblique", "observant", "obvious",
    "ocean", "offered", "olive", "onward", "oracle", "ordeal", "outline",
    "outpace", "outrun", "overcome", "overlap", "palm", "parch",
    "pardon", "patience", "peaceful", "phoenix", "pilgrim", "pioneer",
    "placid", "plateau", "plunder", "polished", "portal", "potent",
    "practice", "prelude", "prestige", "prism", "pursue", "quarrel",
    "radiant", "random", "recall", "reclaim", "redeem", "refine",
    "refuge", "remain", "renew", "repel", "rescue", "resilient",
    "resolve", "restore", "retreat", "revive", "riddle", "ripple",
    "ritual", "roam", "robust", "rogue", "rotate", "rustle", "sacred",
    "salvage", "scatter", "scorch", "scoundrel", "sculptor", "seldom",
    "sentinel", "seraph", "serene", "shadow", "shatter", "shelter",
    "shimmer", "signal", "silence", "silver", "simple", "sincere",
    "sinister", "sliver", "smolder", "somber", "sorcerer", "sorrow",
    "sought", "solemn", "sparkle", "spiral", "splendor", "stalwart",
    "sterling", "strive", "strong", "struggle", "sublime", "sunken",
    "sunder", "surge", "survive", "swear", "tender", "terrify",
    "thankful", "thorough", "thrive", "token", "totem", "tranquil",
    "treasure", "tremble", "triumph", "turquoise", "twilight", "unbind",
    "unearth", "unique", "unravel", "unsung", "untamed", "urge",
    "valiant", "vanish", "verdict", "vibrant", "vigilant", "virtue",
    "vision", "vivid", "wander", "warmth", "weave", "wholesome",
    "wield", "wisdom", "worthy", "yearn",
]
# fmt: on

# Build a fast lookup dict: word → index (used in decode).
# If the list had duplicate words, the last index wins — avoid duplicates.
_WORD_INDEX: dict[str, int] = {word: i for i, word in enumerate(WORD_LIST)}

# Number of words in the list.  All modular arithmetic uses this constant.
_N: int = len(WORD_LIST)

# Number of characters taken from each word to form the checksum string.
# Must be small enough that every word is unique within its prefix.
_PREFIX_LEN: int = 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _checksum_index(words: list[str]) -> int:
    """
    Compute the index (0-23) of the checksum word within the 24 data words.

    Algorithm:
        1. Take the first _PREFIX_LEN characters of each of the 24 words.
        2. Concatenate those prefixes into one string.
        3. CRC32 of that string (encoded as UTF-8).
        4. Result modulo 24 → which word in the 24 to use as the checksum.

    Args:
        words: The 24 data words (NOT including any existing checksum word).

    Returns:
        An integer in range [0, 23].
    """
    # Join the first three letters of each word.
    # Example: ["abbey", "bacon", "cabin"] → "abbbaocab"
    prefix_str = "".join(w[:_PREFIX_LEN] for w in words)
    crc = binascii.crc32(prefix_str.encode("utf-8")) & 0xFFFF_FFFF
    return crc % 24


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def encode(seed: bytes) -> str:
    """
    Convert a 32-byte seed into a 25-word Session mnemonic phrase.

    The mnemonic is a human-readable backup of your identity seed.  Write it
    on paper and store it safely — it's everything needed to restore access.

    How the encoding works:
        - The 32 bytes are split into 8 groups of 4 bytes.
        - Each group is treated as a little-endian unsigned 32-bit integer n.
        - n maps to exactly 3 words using modular arithmetic on the word list.
        - 8 groups × 3 words = 24 data words.
        - A 25th checksum word is appended so typos can be detected on decode.

    Args:
        seed: Exactly 32 bytes.  Usually ``os.urandom(32)`` or the output of
              the key-generation step.

    Returns:
        A string of 25 lowercase words separated by spaces.

    Raises:
        ValueError: If ``seed`` is not exactly 32 bytes.

    Example::

        >>> phrase = encode(os.urandom(32))
        >>> assert len(phrase.split()) == 25
        >>> assert "abandon" not in phrase.split()  # Not BIP39!
    """
    if len(seed) != 32:
        raise ValueError(f"encode() expects exactly 32 bytes, got {len(seed)}")

    words: list[str] = []

    # Process 8 chunks of 4 bytes each.
    for i in range(8):
        chunk = seed[i * 4 : i * 4 + 4]

        # Interpret the 4 bytes as a little-endian unsigned 32-bit integer.
        # '<I' means: little-endian, unsigned int (4 bytes).
        n = struct.unpack("<I", chunk)[0]

        # Map n → three words using the Monero/Session algorithm.
        # Think of it like writing a number in base-1626 with three "digits".
        w1 = n % _N
        w2 = (n // _N + w1) % _N
        w3 = (n // _N // _N + w2) % _N

        words.extend([WORD_LIST[w1], WORD_LIST[w2], WORD_LIST[w3]])

    # Append a checksum word so that decode() can detect typos.
    checksum_idx = _checksum_index(words)
    words.append(words[checksum_idx])  # the checksum IS one of the 24 data words

    logger.debug("encode() produced %d words", len(words))
    return " ".join(words)


def decode(mnemonic: str) -> bytes:
    """
    Convert a 25-word Session mnemonic back into the original 32-byte seed.

    This is the inverse of :func:`encode`.  It also validates the checksum
    word, raising an error if any word has been changed or mistyped.

    How the decoding works:
        - Split the mnemonic into 25 words.
        - Look up each word's index in the word list (raises if unknown).
        - Verify the checksum word matches the expected position.
        - Process the 24 data words in groups of 3, inverting the encode math.
        - Each group of 3 word-indices → one 4-byte little-endian chunk.
        - Concatenate 8 chunks → the original 32-byte seed.

    Args:
        mnemonic: A space-separated string of 25 Session mnemonic words.

    Returns:
        The original 32-byte seed.

    Raises:
        MnemonicDecodeError: If any word is not in the Session word list,
            the checksum is wrong, or the word count is not 25.

    Example::

        >>> seed = os.urandom(32)
        >>> assert decode(encode(seed)) == seed
    """
    words = mnemonic.strip().lower().split()

    # ── Validate word count ───────────────────────────────────────────────
    if len(words) != 25:
        raise MnemonicDecodeError(
            f"Expected 25 words, got {len(words)}.  "
            "A Session mnemonic is always 25 words (24 data + 1 checksum)."
        )

    # ── Validate all words are in the word list ───────────────────────────
    try:
        indices = [_WORD_INDEX[w] for w in words]
    except KeyError as exc:
        raise MnemonicDecodeError(
            f"Word not found in Session word list: {exc}.  "
            "Check for typos or make sure you are using a Session seed phrase."
        ) from exc

    # ── Verify the checksum word ──────────────────────────────────────────
    data_words   = words[:24]
    checksum_word = words[24]
    expected_checksum = data_words[_checksum_index(data_words)]

    if checksum_word != expected_checksum:
        raise MnemonicDecodeError(
            f"Checksum mismatch: got '{checksum_word}', "
            f"expected '{expected_checksum}'.  One or more words may be wrong."
        )

    # ── Decode 8 groups of 3 word-indices → 32 bytes ─────────────────────
    seed_bytes = b""
    for i in range(8):
        # Each group of 3 indices is the algebraic inverse of the encoding:
        #   n1 + N*(n2 - n1) + N²*(n3 - n2)   (all modulo N)
        i1, i2, i3 = indices[i * 3], indices[i * 3 + 1], indices[i * 3 + 2]

        # Invert: recover the original 32-bit integer n.
        n = i1 + _N * ((i2 - i1) % _N) + _N * _N * ((i3 - i2) % _N)

        # Pack n back into 4 little-endian bytes.
        seed_bytes += struct.pack("<I", n)

    logger.debug("decode() recovered %d bytes", len(seed_bytes))
    return seed_bytes
