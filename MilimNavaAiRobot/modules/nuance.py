# ══════════════════════════════════════════════════════════════════
#   NUANCE — kepekaan bahasa figuratif (ala assistant yang gak PEDE):
#   1. SARCASM: "wah bagus banget, baru sekarang dibales" → gak dijawab
#      literal. Deteksi pola sarkasme → instruksi baca antar-garis.
#   2. RHETORICAL: pertanyaan retoris ("emangnya gue peduli?")
#      → jangan dijawab kayak pertanyaan beneran.
#   3. JOKE MODE: user banyol/gesrek → boleh main balik, gak serius.
# ══════════════════════════════════════════════════════════════════

import re

SARCASM_RE = re.compile(
    r"\b(bagus banget[^.!?]*baru|wah[^.!?]*keren[^.!?]*(?:baru|baru ini)|"
    r"mantap[^.!?]*(?:banget|bet)|yes (?:dong|lah|punya)|keren deh|"
    r"oke banget sih|pintar(?:nya| sekali)[^.!?]*(?:baru|tapi))\b",
    re.IGNORECASE)
RHETORIC_RE = re.compile(
    r"\b(emangnya [^?]*peduli|apa urusan|kata siapa|geer banget|"
    r"gitu aja (?:nggak|gak) bisa)\b", re.IGNORECASE)
JOKE_RE = re.compile(r"(?:wkwk|awok|😂|🤣|lucu|gesrek|banyol|guyon|meme|memes)",
                     re.IGNORECASE)

INSTR = ("\n\nNUANCE MODE: pesan user kemungkinan SARKASME/banyol/retoris "
         "— JANGAN dijawab secara literal. Baca antar-garis: kalau dia "
         "sedang bercanda, main balik dengan nada sama. Kalau retoris, "
         "tangkap maksud tersembunyinya, jangan dijawab 'ya'/'tidak'.")


def instruction(user_text: str) -> str:
    t = user_text or ""
    hits = []
    if SARCASM_RE.search(t):
        hits.append("sarkasme")
    if RHETORIC_RE.search(t):
        hits.append("pertanyaan retoris")
    if JOKE_RE.search(t) and len(t.split()) <= 15:
        hits.append("banyol")
    if hits:
        return INSTR + f" (indikasi: {', '.join(hits)})."
    return ""
