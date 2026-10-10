# ══════════════════════════════════════════════════════════════════
#   REASONING — "mikir dulu sebelum jawab" ala model reasoning:
#   Pass 1 (tersembunyi): LLM menulis alur pikirannya — pecah masalah,
#     cek sudut pandang, uji hipotesis, cari celah.
#   Pass 2: jawab final dengan gaya percakapan, REASONING TIDAK DITAMPILKAN
#     ke user (hanya memperkuat kualitas).
#   Trigger otomatis untuk pertanyaan yang butuh mikir: logika, matematika
#   cerita, keputusan, perbandingan, debugging, dsb. Bukan command.
# ══════════════════════════════════════════════════════════════════

import re
import logging

log = logging.getLogger("milim.reasoning")

# pertanyaan yang butuh reasoning sungguhan
NEEDS_RE = re.compile(
    r"(kenapa|bagaimana cara|mengapa|jelaskan kenapa|logika|hitung|"
    r"berapa hasil|jika|kalau|seandainya|bandingkan|lebih baik|pilih "
    r"mana|solusi|sebab-akibat|penyebab|analisis|kesimpulan|"
    r"step by step|cara kerja|alasan|tebak|puzzle|teka-teki)",
    re.IGNORECASE)
# kalimat pendek santai tak perlu reasoning
TOO_SIMPLE = re.compile(
    r"^(halo|hai|hi|pagi|siang|sore|malam|oke|sip|makasih|thanks|wkwk|"
    r"assalamualaikum|p|tes|test|halo kak)[\s!.]*$", re.IGNORECASE)


def worth_reasoning(text: str) -> bool:
    """Selalu reasoning untuk pesan yang ada isinya; lewati panggilan
    nama/greeting/obrolan kosong agar tidak muncul scratchpad tak perlu."""
    t = (text or "").strip()
    if not t:
        return False
    if TOO_SIMPLE.match(t):
        return False
    # "lim", "lim lim lim", "milim nava" tanpa isi → tak perlu mikir
    low = t.lower()
    words = re.findall(r"[a-zA-Z]+", low)
    if words and all(w in {"lim", "milim", "nava", "lilim", "limlim",
                           "milm", "lik", "min"} for w in words):
        return False
    if len(t) < 15 and "?" not in t:
        return False
    return True


def needs_reasoning(text: str) -> bool:
    if not text or len(text) < 20 or TOO_SIMPLE.match(text.strip()):
        return False
    if NEEDS_RE.search(text):
        return True
    # pertanyaan panjang bertingkat (>= 2 klausa tanya)
    return text.count("?") >= 2 and len(text) > 80


REASONING_INSTRUCTION = (
    "THINK FIRST before answering. Write your private scratchpad in ENGLISH "
    "ONLY — even though the user speaks Indonesian and your final answer "
    "will be in Indonesian, THIS TEXT MUST BE FULLY IN ENGLISH. Plain text "
    "only: NO emoji, NO markdown, NO bullet lists, NO headings, NO code "
    "blocks. Keep it SHORT (2-4 sentences) and talk ONLY about your "
    "APPROACH: what the user really wants, the angle/persona to use, what "
    "to avoid. HARD RULES: NEVER retype, quote or restate the user's "
    "message; NEVER write or draft the answer itself (no titles, no list "
    "items, no example sentences that would appear in the reply); do NOT "
    "comment on the user's behavior; do NOT mention limits or batches; do "
    "NOT mention metadata, timestamps, message ids or internal formats. "
    "GOOD example: 'User asks who I am chatting with; answer casually as "
    "Milim, keep it short and light.' BAD example (never do this): "
    "'Wkwkwk spam 3x lagi, nih gue kasih: 1. JJK S3, 2. Chainsaw Man'. "
    "If the message is trivial, one short English sentence is enough.")


def final_instruction(reasoning: str) -> str:
    """Instruksi pass-2: jawab final dengan modal reasoning."""
    return (
        "\n\nCATATAN PIKIRANMU (rahasia — JANGAN dikutip atau diungkap "
        "ke user, jangan menyebut bahwa kamu punya catatan ini):\n"
        + reasoning[:1500] +
        "\n\nTUGAS SEKARANG: tulis jawaban FINAL untuk user dengan gaya "
        "percakapan sesuai kepribadianmu (lihat system prompt). Ambil "
        "kesimpulan terbaik dari analisis di atas. Jangan menampilkan "
        "proses berpikir, jangan menyebut 'analisis internal', jangan "
        "pakai format laporan — cukup jawaban yang tajam dan nyambung. "
        "Boleh singkat, yang penting benar.")


async def think(llm, user_text: str, system: str, msgs: list):
    """Jalankan 2-pass reasoning. Return (jawaban_final, reasoning) atau
    (None, None) jika gagal (caller jatuh ke jalur jawab biasa)."""
    try:
        r_msgs = list(msgs) + [
            {"role": "user", "content": user_text + "\n\n" + REASONING_INSTRUCTION}]
        reasoning = await llm.chat(r_msgs)
        if not reasoning or len(reasoning) < 60:
            log.warning(f"reasoning terlalu pendek/kosong: {len(reasoning or '')} char")
            return None, None
        f_msgs = list(msgs) + [
            {"role": "user", "content": user_text + final_instruction(reasoning)}]
        answer = await llm.chat(f_msgs)
        if not answer:
            return None, None
        return answer, reasoning
    except Exception as e:
        log.warning(f"reasoning err: {e}")
        return None, None


def reasoning_duplicates_answer(reasoning: str, answer: str) -> bool:
    """True kalau scratchpad isinya cuma duplikat/parafrase jawaban —
    tampilkan berarti dobel, lebih baik disembunyikan."""
    def _words(t: str) -> set:
        return {w for w in re.findall(r"[a-z0-9]{4,}", (t or "").lower())
                if w not in {"yang", "dengan", "untuk", "adalah", "tapi",
                             "juga", "sudah", "gak", "nggak", "banget",
                             "kayak", "gitu", "aja", "bisa", "harus", "saya",
                             "gue", "lo", "wkwk", "wkwkwk", "makes", "this"}}
    ra, aa = _words(reasoning), _words(answer)
    if not ra or not aa:
        return False
    inter = len(ra & aa) / max(1, len(ra | aa))
    contained = sum(1 for w in ra if w in aa) / max(1, len(ra))
    return inter >= 0.35 or contained >= 0.7


MAX_REASON_SHOW = 350

# buang sisa heading/bullet meta kalau model bandel
_META_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[\*_`]*\s*)?"
    r"(scratchpad|analisis|fakta|hipotesis|observasi|kesimpulan sementara|"
    r"catatan|status|rencana|langkah-langkah|thought|thinking|analysis)"
    r"\b[^\n]*[:\u2014-].*$", re.IGNORECASE | re.MULTILINE)


def clean_reasoning(r: str) -> str:
    return _META_LINE.sub("", r).strip(" \n\t-*_")


# kata/penanda khas Indonesia — kalau reasoning banyak ini, berarti bukan Inggris
_ID_MARKERS = (
    "yang", "dengan", "untuk", "adalah", "tapi", "juga", "sudah", "gue",
    "nggak", "gak", "banget", "kayak", "gitu", "aja", "bisa", "harus",
    "saya", "dan", "atau", "ini", "itu", "aku", "kamu", "nanti", "biar",
    "jawab", "balas", "user minta", "soalnya", "malah", "udah",
)

# frasa struktural khas Indonesia yang sering bocor sebagai "rencana jawaban"
_ID_PLAN = re.compile(
    r"(gue\s+(harus|mau|akan)|aku\s+(harus|mau)|user\s+(minta|pengen|bertanya)|"
    r"jawab\s+(santai|dengan|pakai)|balas\s+(santai|dengan)|"
    r"pakai\s+gaya|tanpa\s+(nyebut|sebut)|hindari\s)", re.IGNORECASE)


def _looks_indonesian(r: str) -> bool:
    """True kalau teks reasoning lebih mirip Bahasa Indonesia daripada Inggris."""
    low = " " + r.lower() + " "
    hits = sum(1 for w in _ID_MARKERS if re.search(rf"\b{w}", low))
    return hits >= 2 or bool(_ID_PLAN.search(r))


def _strip_nonascii(r: str) -> str:
    """Buang semua karakter non-ASCII (emoji, unicode box, dsb) — teks polos."""
    return "".join(ch for ch in r if 32 <= ord(ch) < 127 or ch in "\n\r\t")


def format_answer(answer: str, reasoning: str) -> str:
    """Jawaban + blok Reasoning (markdown backtick, isi English polos)."""
    if not reasoning:
        return answer
    r = clean_reasoning(reasoning.strip())
    r = _strip_nonascii(r) if r else ""
    # reasoning harus English & bukan salinan jawaban — kalau tidak, sembunyikan
    if not r or len(r) < 30 or _looks_indonesian(r) or reasoning_duplicates_answer(r, answer):
        return answer
    return f"☁️ **Reasoning:**\n```\n{r}\n```\n\n{answer}"
