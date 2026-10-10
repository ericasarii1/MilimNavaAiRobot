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
    "SINGKAT (2-3 baris), fokus ke CARA MENJAWAB: apa inti pertanyaannya, "
    "sudut pandang apa yang dipakai, apa yang perlu dihindari. "
    "ATURAN KERAS: JANGAN menulis isi jawaban, JANGAN membuat daftar/"
    "rekomendasi/contoh yang akan jadi isi jawaban, JANGAN mengulang atau "
    "memparafrase pesan user, JANGAN pakai judul/heading, JANGAN "
    "mengomentari perilaku user. Contoh bentuk yang benar: 'pertanyaannya "
    "soal rekomendasi, gue harus hindari judul yang udah disebut, kasih 4-5 "
    "judul beda genre'. Contoh yang SALAH: 'wkwk spam lagi, oke ini "
    "tambahannya: 1. JJK S3...'. Kalau pertanyaannya gampang dan gak butuh "
    "pikir panjang, tulis satu kalimat pendek saja.")


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


def format_answer(answer: str, reasoning: str) -> str:
    """Jawaban + blok 💭 Reasoning (markdown, quote >). Tanpa HTML."""
    if not reasoning:
        return answer
    r = clean_reasoning(reasoning.strip())
    if not r:
        return answer
    if len(r) > MAX_REASON_SHOW:
        r = r[:MAX_REASON_SHOW].rsplit(" ", 1)[0] + " …"
    r = r.replace("```", "")
    # blok kode dgn tombol "Salin Kode" ala Telegram
    q = f"```\n{r}\n```"
    head = f"💭 **Reasoning:**\n{q}\n\n"
    # jaga total tetap muat 1 pesan Telegram (4096)
    budget = 3950 - len(head)
    if len(answer) > budget > 0:
        answer = answer[:budget].rsplit(".", 1)[0].rsplit("\n", 1)[0] + "…"
    return head + answer
