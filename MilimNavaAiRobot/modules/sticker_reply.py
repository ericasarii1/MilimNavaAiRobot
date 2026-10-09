# ══════════════════════════════════════════════════════════════════
#   STICKER REPLY — Milim kadang bales stiker pakai stiker juga,
#   belajar dari stiker yang pernah dikirim anggota grup (kemampuan).
# ══════════════════════════════════════════════════════════════════

import time
import random
import logging

log = logging.getLogger("milim.sticker_reply")

# file_id stiker yang pernah terlihat per chat (maks 40/chat)
_SEEN = {}
LAST_REPLY = {}
COOLDOWN = 300          # jangan terlalu sering: 5 menit per chat
CHANCE = 0.30           # 30% kalau ada stikernya


def remember(chat_id: int, file_id: str):
    arr = _SEEN.setdefault(chat_id, [])
    if file_id not in arr:
        arr.append(file_id)
        del arr[:-40]


def maybe_reply(chat_id: int) -> str | None:
    """Return file_id stiker buat dibalas, atau None."""
    now = time.time()
    if now - LAST_REPLY.get(chat_id, 0) < COOLDOWN:
        return None
    arr = [f for f in _SEEN.get(chat_id, []) if f]
    if not arr or random.random() > CHANCE:
        return None
    LAST_REPLY[chat_id] = now
    return random.choice(arr)
