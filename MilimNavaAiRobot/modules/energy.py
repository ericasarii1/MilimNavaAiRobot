# ══════════════════════════════════════════════════════════════════
#   ENERGY — penyesuaian energi/panjang jawaban dengan pesan user
#   (ala assistant yang "niru napas" lawan bicaranya):
#   - User nulis pendek/pada point → jawaban pendek, tanpa basa-basi.
#   - User nulis panjang/bersemangat → boleh panjang & berapi.
#   - User LOW-ENERGY (bete, capes) → jawaban lebih pelan & empati,
#     guyon dikurangi.
# ══════════════════════════════════════════════════════════════════

import re

LOW_RE = re.compile(
    r"\b(bete|btw capek|capes|lelah|pengen nyerah|nyerah|sedih|nangis|"
    r"down|stress|pusing|sakit|gagal|nyesek|kehilangan)\b", re.IGNORECASE)
HIGH_RE = re.compile(r"(wkwk|awok|😂|🔥|😱|gila|keren bgt|parah sih|wow|gokil)",
                     re.IGNORECASE)


def instruction(user_text: str) -> str:
    """Return instruksi penyesuaian energi (atau '')."""
    t = user_text or ""
    if LOW_RE.search(t):
        return ("\n\nENERGI JAWAB: user terlihat sedang low-energy/sedih. "
                "Turunkan volume guyon, jawab lebih pelan & empati, "
                "prioritaskan dukungan daripada candaan. Jangan paksa "
                "menghibur dengan lelucon.")
    words = len(t.split())
    if HIGH_RE.search(t) or words >= 40:
        return ("\n\nENERGI JAWAB: user bersemangat/banyak bicara — boleh "
                "jawab panjang, hidup, dan playful.")
    if words <= 4:
        return ("\n\nENERGI JAWAB: user nulis super pendek — jawab SANGAT "
                "singkat (1-2 kalimat), tanpa perumpamaan & tanpa daftar.")
    if words <= 10:
        return ("\n\nENERGI JAWAB: user nulis singkat — jawab ringkas, "
                "maksimal 2-3 kalimat.")
    return ""
