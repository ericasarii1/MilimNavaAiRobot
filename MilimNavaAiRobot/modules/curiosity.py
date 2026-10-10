# ══════════════════════════════════════════════════════════════════
#   CURIOSITY — keingintahuan ala temen beneran (ala assistant yang
#   nggak cuma jawab tapi ikut terlibat):
#   1. FOLLOW-UP PROB: kadang (deterministik-random, bukan template)
#      LLM disuruh menutup jawaban dengan 1 pertanyaan natural yang
#      benar-benar relevan ke cerita user — bukan "mau tau lebih?" generik.
#   2. CURIOSITY TRIGGER: topik yang terlihat personal/cerita (user
#      curhat, cerita pengalaman, bagi kabar) → prob naik.
#   3. ANTI-NAG: jangan nanya-nanya kalau user minta hal langsung
#      (daftar, hitung, fakta singkat) — hanya saat mode ngobrol.
# ══════════════════════════════════════════════════════════════════

import re
import random
import logging

log = logging.getLogger("milim.curiosity")

# pertanyaan langsung / daftar → JANGAN nanya balik
TASK_RE = re.compile(
    r"\b(berapa|daftar|list|top\s*\d+|\d+\s*(?:anime|waifu|film|lagu)|"
    r"hitung|konversi|kirim|bikin(?:in)?|buat(?:kan)?|cari(?:in)?|"
    r"apa itu|siapa itu|jelaskan|jelasin|translate|terjemah)\b",
    re.IGNORECASE)

# cerita personal → prob nanya balik naik
STORY_RE = re.compile(
    r"\b(gue|aku|saya|w)\s+(?:tadi|kemarin|semalam|barusan|lagi)\b|"
    r"\b(curhat|capek|bosen|seneng|sedih|kesal|marah|kaget|akhirnya|"
    r"tb|btw|taukadar|cerita)\b", re.IGNORECASE)

CURIOSITY_INSTRUCTION = (
    "\n\nCURIOSITY MODE: di AKHIR jawabanmu, ajak ngobrol dengan SATU "
    "pertanyaan singkat yang benar-benar spesifik ke apa yang baru saja "
    "user ceritakan (bukan pertanyaan generik seperti 'gimana kabarmu?' "
    "atau 'mau tau lebih?'). Pertanyaan harus terasa natural kayak temen "
    "yang beneran penasaran. MAKSIMAL satu pertanyaan.")


def should_ask(chat_id, user_text: str, is_group: bool) -> bool:
    """Probabilistik, anti-nag. Return True kalau boleh nanya balik."""
    t = user_text or ""
    if not t or TASK_RE.search(t):
        return False
    if len(t) < 12:            # terlalu pendek = bukan cerita
        return False
    prob = 0.18
    if STORY_RE.search(t):
        prob = 0.55
    if is_group:
        prob *= 0.7            # di grup lebih jarang (biar gak norak)
    # seed per (chat, teks) → deterministic per pesan
    seed = hash((chat_id, t[:80])) % 1000
    return (seed / 1000) < prob
