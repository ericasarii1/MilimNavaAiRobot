# ══════════════════════════════════════════════════════════════════
#   HUMAN TOUCH — 3 kemampuan biar makin layaknya manusia:
#   1. TANYA BALIK: pertanyaan ambigu → minta klarifikasi, bukan ngawur
#   2. GAYA ADAPTIF: gaya jawab menyesuaikan lawan bicara (dari riwayat)
#   3. SELF-HONESTY: nggak yakin → akui, jangan ngarang
#   Semua di-inject ke system prompt (kemampuan, bukan command).
# ══════════════════════════════════════════════════════════════════

import re
import time
import logging

log = logging.getLogger("milim.human")

# ── 1. deteksi pertanyaan ambigu ──────────────────────────────────
# Referensi kosong ("itu", "dia", "yang tadi", dsb) tanpa konteks jelas
AMBIG_RE = re.compile(
    r"^\s*(?:(?:itu|ini|dia|ni|yang mana|gimana|gmn|kenapa|knp|kok bisa|"
    r"terus|apa lagi|yang tadi|tadi yang|yang itu|kenapa sih|btw itu|"
    r"apa solusinya|gimana dong|terus cara)\b[\s\w?!.]{0,25}?)"
    r"[\s?.!]*$", re.IGNORECASE)
TOO_SHORT_Q = re.compile(r"^[^\w]*(\w{1,4})[^\w]*\?$")

# konteks balasan (reply chain) bikin ambigu jadi jelas → tidak perlu klarifikasi


def is_ambiguous(text: str, has_reply_context: bool = False,
                 history_len: int = 0) -> bool:
    """Pertanyaan terlalu pendek/kurang referensi → perlu klarifikasi."""
    if not text or has_reply_context:
        return False
    t = text.strip()
    if AMBIG_RE.match(t):
        # ambigu hanya kalau riwayat belum jelas (pendek)
        return history_len < 4
    # pertanyaan < 4 kata yang sepenuhnya tanpa konteks topik
    words = re.findall(r"\w+", t)
    if t.endswith("?") and len(words) <= 3 and history_len < 2:
        return True
    return False


CLARIFY_RULE = (
    "\n\nATURAN MENYAMPAIKAN KEBINGUNGAN (kemampuan manusiawi):\n"
    "- Kalau pertanyaan user ambigu, terlalu singkat, atau referensinya "
    "tidak jelas (contoh: cuma \"itu gimana?\", \"kenapa sih?\" tanpa "
    "topik), JANGAN mengarang jawaban. Tanyakan balik dengan santai dan "
    "singkat, contoh: \"maksudnya yang mana nih? 🤔\" atau \"konteksnya "
    "soal apa nih?\". Maksimal 1 kalimat tanya balik."
    "\n- Kalau user sudah memberi konteks (riwayat chat atau reply), "
    "jawab langsung tanpa nanya balik.")


# ── 2. gaya adaptif per lawan bicara ─────────────────────────────
FORMAL_HINTS = re.compile(
    r"\b(selamat pagi|selamat siang|selamat sore|selamat malam|"
    r"mohon|terima kasih|makasih banyak|silakan|permisi|"
    r"tolong bantu|bapak|ibu|kak|mas|mbak)\b", re.IGNORECASE)
GASKEUN_HINTS = re.compile(
    r"\b(wkwk|anjir|anjrit|gila|njir|gas|gaskeun|aser|lu|lo|gue|"
    r"bang|bre|bro|wtf|ngakak|cok|tai|bgst)\b", re.IGNORECASE)


def style_of_speaker(group_history: list, name: str) -> str:
    """Analisis gaya bicara user dari riwayat → instruksi gaya jawaban."""
    if not name:
        return ""
    msgs = [x.get("content", "") for x in group_history[-30:]
            if x.get("speaker") == name and x.get("role") == "user"]
    if len(msgs) < 3:
        return ""
    blob = " ".join(msgs).lower()
    n_gask = len(GASKEUN_HINTS.findall(blob))
    n_formal = len(FORMAL_HINTS.findall(blob))
    avg_len = sum(len(m) for m in msgs) / len(msgs)
    hints = []
    if n_gask >= 3 and n_gask > n_formal:
        hints.append("santai banget, boleh ngegas dan bercanda")
    elif n_formal >= 2 and n_formal > n_gask:
        hints.append("cenderung sopan — jawab lebih halus, kurangi bahasa gaul")
    if avg_len > 120:
        hints.append("suka cerita panjang — jawab boleh lebih runtut & detail")
    elif avg_len < 25:
        hints.append("pendek-pendek — jawab singkat padat, jangan bertele")
    if not hints:
        return ""
    return (f"\n\nGAYA LAWAN BICARA '{name}' (dari pola chatnya): "
            + "; ".join(hints) + ". Sesuaikan gaya jawabanmu dengan ini.")


# ── 3. self-honesty ───────────────────────────────────────────────
HONESTY_RULE = (
    "\n\nKEJUJURAN DIRI (wajib):\n"
    "- Kalau tidak yakin atau tidak tahu jawaban pasti, AKUI saja: "
    "\"gue kurang tau soal itu\" / \"gue nggak yakin, jangan diambil "
    "mentah-mentah\". JANGAN PERNAH mengarang fakta, angka, tanggal, "
    "atau nama kalau tidak ada di konteks/data yang diberikan.\n"
    "- Lebih dihargai bilang \"nggak tau\" daripada ngarang.\n"
    "- Kalau datanya mungkin sudah basi (harga, jadwal, berita), "
    "sebutkan bahwa perlu dicek ulang.")


def build_human_rules(has_reply_context: bool = False,
                      history_len: int = 0) -> str:
    """Rules tanya-balik + kejujuran (selalu on)."""
    txt = CLARIFY_RULE + HONESTY_RULE
    if is_ambiguous("", has_reply_context, history_len):
        return txt  # (dipakai hanya sebagai rule; deteksi dipanggil terpisah)
    return txt
