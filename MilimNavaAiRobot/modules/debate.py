# ══════════════════════════════════════════════════════════════════
#   DEBATE — mode diskusi/debat (ala assistant yang punya pendirian,
#   bukan yes-man):
#   - User menyatakan opini kuat & membuka diskusi → bot boleh
#     (dengan probabilitas rendah) menyampaikan PANDANGAN BERBEDA
#     dengan argumen, tetap sopan & santai.
#   - User minta opinion bot ("menurut lo?") → JANGAN plin-plan
#     menyamai user; punya posisi sendiri.
#   - Anti-yesman: larangan keras mengiyakan semata-mata demi dipuji.
# ══════════════════════════════════════════════════════════════════

import re
import random

ASK_OP_RE = re.compile(
    r"\b(menurut lo|menurut kamu|kalo lo|kalau lo|lo pilih|kamu pilih|"
    r"setuju gak|setuju nggak|bagusan mana|pilih mana|juara|terbaik)\b",
    re.IGNORECASE)
STRONG_OP_RE = re.compile(
    r"\b(menurut gue|gue rasa|beneran|serius|no debat|paling|juara|"
    r"yang terbaik|gak ada lawan)\b", re.IGNORECASE)
SOFTEN_RE = re.compile(r"\b(maaf|sorry|kalau boleh|semoga)\b", re.IGNORECASE)

DISAGREE_INSTR = (
    "\n\nDEBATE MODE: user sedang menyatakan opini kuat. Kamu BOLEH — "
    "dan kadang PERLU — menyampaikan pandangan berbeda dengan argumen "
    "yang jelas. Tetap santai & sopan, tapi JANGAN jadi yes-man yang "
    "mengiyakan semua. Kalau kamu setuhuh setuju, tunjukkan bagian yang "
    "setuju DAN bagian yang beda.")

OWN_OPINION_INSTR = (
    "\n\nOWN OPINION: user menanyakan PENDAPATMU. Kasih jawaban yang "
    "beneran kamu pilih (dengan alasan spesifik), JANGAN cuma nimbrung "
    "nyamain pilihan user atau jawaban aman yang menyamakan semua opsi.")


def instruction(user_text: str) -> str:
    t = user_text or ""
    if ASK_OP_RE.search(t):
        return OWN_OPINION_INSTR
    if STRONG_OP_RE.search(t) and len(t.split()) >= 8:
        # probabilitas rendah biar gak selalu debat
        if random.random() < 0.35:
            return DISAGREE_INSTR
    return ""
