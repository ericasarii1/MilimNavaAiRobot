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
    "SEKARANG PIKIRKAN SEBENTAR sebelum menjawab. Tulis alur pikirmu "
    "SINGKAT (paling banyak 3-4 baris pendek), pakai bahasa yang sama "
    "dengan obrolan (santai tetap santai). Fokus HANYA pada isi jawaban. "
    "ATURAN KERAS: jangan pakai judul/heading (jangan tulis 'SCRATCHPAD', "
    "'Fakta:', 'Hipotesis:', 'Analisis:'), jangan pakai bullet bernomor, "
    "jangan mengomentari perilaku/kebiasaan user, jangan menyebut fitur, "
    "tombol, atau aplikasi. Cukup inti pikiran yang mengarah ke jawaban.")


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
            return None, None
        f_msgs = list(msgs) + [
            {"role": "user", "content": user_text + final_instruction(reasoning)}]
        answer = await llm.chat(f_msgs)
        if not answer:
            return None, None
        return answer, reasoning
    except Exception as e:
        log.debug(f"reasoning err: {e}")
        return None, None


MAX_REASON_SHOW = 480

# buang sisa heading/bullet meta kalau model bandel
_META_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[\*_`]*\s*)?"
    r"(scratchpad|analisis|fakta|hipotesis|observasi|kesimpulan sementara|"
    r"catatan|status|rencana|langkah-langkah|thought|thinking|analysis)"
    r"\b[^\n]*[:\u2014-].*$", re.IGNORECASE | re.MULTILINE)


def clean_reasoning(r: str) -> str:
    return _META_LINE.sub("", r).strip(" \n\t-*_")


def format_answer(answer: str, reasoning: str) -> str:
    """Jawaban + blok 💭 Reasoning (blockquote expandable — bisa dibuka/
    ditutup di Telegram, persis tampilan reasoning model modern)."""
    if not reasoning:
        return answer
    r = clean_reasoning(reasoning.strip())
    if not r:
        return answer
    if len(r) > MAX_REASON_SHOW:
        r = r[:MAX_REASON_SHOW].rsplit(" ", 1)[0] + " …"
    r = r.replace("```", "")
    # escape HTML di KEDUA bagian agar parse_mode=HTML aman
    import html as _html
    r = _html.escape(r)
    answer = _html.escape(answer)
    return (f"💭 <b>Reasoning:</b>\n"
            f"<blockquote expandable>{r}</blockquote>\n\n{answer}")
