# ══════════════════════════════════════════════════════════════════
#   LANG - deteksi bahasa otomatis → jawab dalam bahasa user
#   Dipakai di ai_respond: suntik instruksi bahasa ke system prompt.
#   Deteksi berbasis skrip (aksara) + kata kunci umum, tanpa library.
# ══════════════════════════════════════════════════════════════════

import re

LANG_RULES = [
    ("Jepang", re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")),
    ("Korea", re.compile(r"[\uac00-\ud7af]")),
    ("Arab", re.compile(r"[\u0600-\u06ff]")),
    ("Rusia", re.compile(r"[\u0400-\u04ff]")),
    ("Mandarin", re.compile(r"[\u4e00-\u9fff]")),
]

# kata umum bahasa Inggris (beda dari Indonesia)
EN_WORDS = re.compile(
    r"\b(the|is|are|you|what|how|why|when|where|and|with|this|that|have|"
    r"please|thanks|thank you|hello|hi|good|very|can|will|about|from|"
    r"make|want|need|know|think)\b", re.I)
# kata umum bahasa Indonesia
ID_WORDS = re.compile(
    r"\b(gue|lo|kamu|apa|kenapa|gimana|bagaimana|yang|dan|dengan|ini|itu|"
    r"udah|sudah|nggak|tidak|banget|deh|dong|sih|nih|aja|saja|mau|pengen|"
    r"tau|tahu|bisa|nanti|sekarang|kita|saya|aku)\b", re.I)


def detect_language(text: str) -> str | None:
    """Return nama bahasa, atau None kalau Indonesia/netral/tak yakin."""
    if not text or len(text) < 3:
        return None
    for name, pat in LANG_RULES:
        if pat.search(text):
            return name
    en = len(EN_WORDS.findall(text))
    idn = len(ID_WORDS.findall(text))
    if en >= 2 and en > idn * 2:
        return "Inggris"
    # kata Inggris murni tanpa konteks Indonesia
    if en >= 1 and idn == 0 and re.fullmatch(
            r"[A-Za-z0-9\s\?\!\.,']+", text):
        return "Inggris"
    return None


def language_addon(lang: str | None) -> str:
    if not lang:
        return ""
    return (f"\n\nBAHASA: user menulis dalam bahasa {lang}. Jawab dalam "
            f"bahasa {lang} yang natural (tetap pakai kepribadianmu, "
            f"adaptasikan gaya santai ke bahasa {lang}).")
