# ══════════════════════════════════════════════════════════════════
#   FACTLAB — verifikasi fakta & logika sebagai KEMAMPUAN (bukan command):
#   1. SELF-CHECK: sebelum jawaban terkirim, klaim angka/tanggal/nama
#      diperiksa konsistensi (kalau LLM menyebut hal bertentangan di
#      dalam satu jawaban → minta versi perbaikan).
#   2. LOGIC TRAP: deteksi pertanyaan jebakan/paradoks/false premise
#      ("kenapa semua anjing bisa terbang?") → instruksi khusus supaya
#      tidak mengiyakan premis salah.
#   3. NUMBER SENSE: sanity-check angka ekstrem di jawaban (populasi,
#      tahun, jarak) → tandai ke LLM utk dikoreksi.
# ══════════════════════════════════════════════════════════════════

import re
import logging

log = logging.getLogger("milim.factlab")

# ── false premise / jebakan ──────────────────────────────────────
TRAP_RE = re.compile(
    r"\bkenapa\b.{0,60}\b(semua|semuanya|setiap|tiap)\b|"
    r"\bmengapa\b.{0,60}\b(semua|semuanya|setiap|tiap)\b|"
    r"\bkenapa\b.{0,40}\b(bisa terbang|tidak pernah|selalu|gak pernah|"
    r"nggak pernah|ga pernah)\b|"
    r"\bapakah benar\b|\bkata orang\b.{0,40}\b(kenapa|mengapa)\b",
    re.IGNORECASE)

TRAP_INSTRUCTION = (
    "\n\nPERINGATAN PREMIS: pertanyaan user kemungkinan mengandung premis "
    "yang salah/jebakan. JANGAN langsung mengiyakan — cek dulu apakah "
    "premisnya benar. Kalau salah, tolak dengan santai dan jelaskan "
    "fakta yang benar sebelum menjawab maksud aslinya.")


def is_trap_question(text: str) -> bool:
    return bool(TRAP_RE.search(text or ""))


# ── number sanity check ──────────────────────────────────────────
NUM_RE = re.compile(r"\b(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(%|juta|miliar|"
                    r"triliun|ribu|km|kilometer|tahun)?", re.IGNORECASE)

# rentang wajar untuk klaim umum (heuristik longgar)
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")


def extreme_numbers(answer: str) -> list:
    """Temukan angka yang mencurigakan (bisa jadi halusinasi)."""
    flags = []
    if not answer:
        return flags
    # tahun di masa depan
    import datetime
    this_year = datetime.date.today().year
    for m in _YEAR_RE.finditer(answer):
        if int(m.group(1)) > this_year + 1:
            flags.append(f"tahun {m.group(1)} > tahun sekarang ({this_year})")
    # persentase > 100
    for m in re.finditer(r"\b(\d{2,4})\s*(?:%|persen)\b", answer, re.I):
        if int(m.group(1)) > 100:
            flags.append(f"persentase {m.group(1)}% > 100%")
    return list(set(flags))[:4]


VERIFY_INSTRUCTION = (
    "\n\nKOREKSI ANGKA: jawaban drafmu memuat angka yang mencurigakan: "
    "{flags}. Perbaiki atau hapus klaim tersebut — jangan menebak angka. "
    "Tulis ulang jawaban final yang sudah dibersihkan.")


async def verify_numbers(llm, question: str, answer: str) -> str:
    """Kalau ada angka mencurigakan → minta LLM perbaiki. Return final."""
    flags = extreme_numbers(answer)
    if not flags:
        return answer
    try:
        fixed = await llm.chat([
            {"role": "user",
             "content": f"PERTANYAAN ASLI:\n{question[:500]}\n\nDRAF JAWABAN:\n"
                        f"{answer[:3000]}\n\n"
                        + VERIFY_INSTRUCTION.format(flags="; ".join(flags))}])
        if fixed and len(fixed) > 30:
            return fixed
    except Exception as e:
        log.debug(f"verify_numbers err: {e}")
    return answer
