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
    "THINK FIRST before answering. Write your short scratchpad in ENGLISH "
    "(like a reasoning model does), plain text: NO emoji, NO markdown, NO "
    "bullets, NO headings, NO code blocks. Keep it SHORT (2-4 sentences) "
    "and talk only about your APPROACH: what the user really wants, the "
    "angle/persona to use, what to avoid. HARD RULES: NEVER retype, quote "
    "or restate the user's message; NEVER count or mention how many "
    "times the user repeated messages; NEVER write or draft the answer itself "
    "(no titles, no list items, no sentences that would appear in the "
    "reply); do NOT comment on the user's behavior; do NOT mention limits, "
    "batches, metadata or internal formats. GOOD: 'User asks who I am "
    "chatting with; answer casually as Milim, keep it short.' BAD: 'wkwkwk "
    "spam lagi, ini tambahannya: 1. JJK S3, 2. Chainsaw Man'. If the "
    "message is trivial, one short sentence is enough.")


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
        reasoning = ""
        for _try in range(2):          # retry sekali kalau hasilnya kosong/pendek
            r_msgs = list(msgs) + [
                {"role": "user",
                 "content": user_text + "\n\n" + REASONING_INSTRUCTION}]
            reasoning = (await llm.chat(r_msgs)) or ""
            if len(reasoning.strip()) >= 15:
                break
        if len(reasoning.strip()) < 15:
            log.warning(f"reasoning kosong: {len(reasoning)} char")
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
    return inter >= 0.3 or contained >= 0.6


MAX_REASON_SHOW = 350

# buang sisa heading/bullet meta kalau model bandel
_META_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[\*_`]*\s*)?"
    r"(scratchpad|analisis|fakta|hipotesis|observasi|kesimpulan sementara|"
    r"catatan|status|rencana|langkah-langkah|thought|thinking|analysis)"
    r"\b[^\n]*[:\u2014-].*$", re.IGNORECASE | re.MULTILINE)


def clean_reasoning(r: str) -> str:
    return _META_LINE.sub("", r).strip(" \n\t-*_")


def _strip_nonascii(r: str) -> str:
    """Buang semua karakter non-ASCII (emoji, unicode box, dsb) — teks polos."""
    return "".join(ch for ch in r if 32 <= ord(ch) < 127 or ch in "\n\r\t")


_BLOCK_RE = re.compile(
    r"☁️\s*\*\*Reasoning:\*\*\s*```.*?```\s*", re.DOTALL)


def strip_block(text: str) -> str:
    """Buang blok reasoning dari teks (dipakai sebelum simpan ke memori
    supaya model tidak meniru pola reasoning-dalam-reasoning)."""
    if not text:
        return text
    return _BLOCK_RE.sub("", text).strip()


def format_answer(answer: str, reasoning: str) -> str:
    """Jawaban + blok ☁️ Reasoning (markdown backtick, isi polos)."""
    if not reasoning:
        return answer
    r = clean_reasoning(reasoning.strip())
    if not r:
        return answer
    r = r.replace("```", "")
    r = _strip_nonascii(r)
    if not r:
        return answer
    return f"☁️ **Reasoning:**\n```\n{r}\n```\n\n{answer}"
