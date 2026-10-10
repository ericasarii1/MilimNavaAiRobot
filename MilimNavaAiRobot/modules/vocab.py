# ══════════════════════════════════════════════════════════════════
#   VOCAB — variasi bahasa / anti-kliché (ala assistant yang gak
#   ngulang kalimat): melacak frasa yang kelewat sering muncul di
#   jawaban bot → instruksi ke LLM untuk menghindarinya.
#   (Pelengkap anti-repeat smart_enhance yang hanya cek jawaban utuh.)
# ══════════════════════════════════════════════════════════════════

import re
import json
import time
import logging

log = logging.getLogger("milim.vocab")

try:
    from MilimNavaAiRobot import db
except Exception:
    db = None

KEY = "ct:vocab:{chat}"
MAX_PHRASES = 120

# frasa kliché yang dihitung
KLICHE_RE = re.compile(
    r"\b(no debat|gas lah|gaskeun|lah kok|moment|vibes?|healing|"
    r"tunggal(?!a)|best(?:ie)?|literally|auto|coret)\b", re.IGNORECASE)
# kumpulkan bigram/trigram paling sering dari jawaban sendiri
WORD_RE = re.compile(r"[a-zA-Z]{4,}")


async def track(chat_id: int, answer_plain: str):
    """Catat frekuensi frasa kliché + kata dari jawaban bot."""
    if db is None or not answer_plain:
        return
    try:
        counts = {}
        raw = await db.get(KEY.format(chat=chat_id))
        counts = json.loads(raw) if raw else {}
        for m in KLICHE_RE.finditer(answer_plain):
            w = m.group(0).lower()
            counts[w] = counts.get(w, 0) + 1
        words = [w.lower() for w in WORD_RE.findall(answer_plain)]
        for w in set(words):
            if words.count(w) >= 2 and len(w) >= 6:
                counts[w] = counts.get(w, 0) + 1
        # potong: simpan top terpakai
        if len(counts) > MAX_PHRASES:
            counts = dict(sorted(counts.items(), key=lambda kv: -kv[1])[:MAX_PHRASES])
        await db.set(KEY.format(chat=chat_id), json.dumps(counts))
    except Exception as e:
        log.debug(f"vocab track err: {e}")


async def overused(chat_id: int) -> list:
    """Frasa yang terlalu sering dipakai (>=4x)."""
    if db is None:
        return []
    try:
        raw = await db.get(KEY.format(chat=chat_id))
        counts = json.loads(raw) if raw else {}
        return [w for w, c in counts.items() if c >= 4]
    except Exception:
        return []


async def instruction(chat_id: int) -> str:
    over = await overused(chat_id)
    if not over:
        return ""
    return ("\n\nVARIASI BAHASA: frasa/kata berikut sudah kamu pakai "
            "terlalu sering — HINDARI di jawaban ini atau ganti dengan "
            "ekspresi lain: " + ", ".join(over[:12]) + ".")
