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


def needs_reasoning(text: str) -> bool:
    if not text or len(text) < 20 or TOO_SIMPLE.match(text.strip()):
        return False
    if NEEDS_RE.search(text):
        return True
    # pertanyaan panjang bertingkat (>= 2 klausa tanya)
    return text.count("?") >= 2 and len(text) > 80


REASONING_INSTRUCTION = (
    "SEKARANG PIKIRKAN PERTANYAAN INI SECARA MENDALAM. Tulis alur pikiran "
    "MENTAHmu: pecah masalahnya, daftar fakta yang diketahui, hipotesis "
    "yang mungkin, uji masing-masing, tunjukkan sudut pandang yang bisa "
    "terlewat, dan kesimpulan sementara. Tulis bebas dan terstruktur — "
    "ini SCRATCHPAD internal, tidak akan ditampilkan ke user. Jangan "
    "pakai gaya percakapan di bagian ini, cukup logika.")


def final_instruction(reasoning: str) -> str:
    """Instruksi pass-2: jawab final dengan modal reasoning."""
    return (
        "\n\nHASIL ANALISIS INTERNALMU (scratchpad — JANGAN ditampilkan "
        "atau dikutip apa adanya ke user):\n" + reasoning[:3000] +
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


MAX_REASON_SHOW = 1500


def format_answer(answer: str, reasoning: str) -> str:
    """Jawaban + blok 💭 Reasoning (blockquote expandable — bisa dibuka/
    ditutup di Telegram, persis tampilan reasoning model modern)."""
    if not reasoning:
        return answer
    r = reasoning.strip()
    if len(r) > MAX_REASON_SHOW:
        r = r[:MAX_REASON_SHOW] + " …"
    r = r.replace("```", "")
    # escape HTML di KEDUA bagian agar parse_mode=HTML aman
    import html as _html
    r = _html.escape(r)
    answer = _html.escape(answer)
    return (f"💭 <b>Reasoning:</b>\n"
            f"<blockquote expandable>{r}</blockquote>\n\n{answer}")
