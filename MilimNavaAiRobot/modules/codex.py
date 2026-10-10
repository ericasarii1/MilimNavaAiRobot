# ══════════════════════════════════════════════════════════════════
#   CODEX — pemahaman & eksekusi kode sebagai KEMAMPUAN (bukan command):
#   1. CODE BLOCK EXPLAIN: user paste/reply kode (``` blok atau pesan
#      berbau kode) + minta jelaskan/fix → kode di-inject ke konteks.
#   2. RUN PYTHON: "run kode ini" → eksekusi sandbox sederhana (timeout,
#      tanpa network bisa diizinkan) → hasil dipakai LLM untuk jawab.
#   3. ERROR EXPLAIN: user paste traceback/error → pola error dikenali,
#      konteks di-inject supaya jawaban akurat & solutif.
#   Semua hasil = knowledge injection, jawaban tetap lewat reasoning utama.
# ══════════════════════════════════════════════════════════════════

import re
import asyncio
import logging

log = logging.getLogger("milim.codex")

# ── deteksi kode ──────────────────────────────────────────────────
CODE_BLOCK_RE = re.compile(r"```[\w+-]*\n(.*?)```", re.DOTALL)
CODE_HINT_RE = re.compile(
    r"\b(def |import |class |print\(|function |const |var |let |"
    r"return |for\s*\(|while\s*\(|elif|=> |public |#include|<!DOCTYPE)",
    re.MULTILINE)
ASK_CODE_RE = re.compile(
    r"\b(jelasin|jelaskan|explain|apa artinya|apaini|apa ini|fix|"
    r"benerin|perbaiki|debug|errornya|kenapa error|run|jalankan|"
    r"eksekusi|test kode|compile)\b", re.IGNORECASE)
ERROR_RE = re.compile(
    r"((?:\w+\.)?(?:Error|Exception)\b|Traceback \(most recent call|"
    r"\bsegmentation fault\b|\bSyntaxError|\bTypeError|\bValueError|"
    r"\bKeyError|\bIndexError|\bNameError|\bAttributeError|"
    r"\bConnectionError|\bNullReference|\bundefined is not)", re.IGNORECASE)

MAX_CODE_CHARS = 3500


def extract_code(text: str) -> str:
    """Ambil blok kode (``` atau heuristik) dari pesan."""
    m = CODE_BLOCK_RE.search(text or "")
    if m:
        return m.group(1).strip()[:MAX_CODE_CHARS]
    # heuristik: pesan yang tampak seperti kode mentah
    t = (text or "").strip()
    if t and CODE_HINT_RE.search(t) and "\n" in t and len(t) < MAX_CODE_CHARS:
        return t
    return ""


def is_error_paste(text: str) -> bool:
    return bool(text) and bool(ERROR_RE.search(text)) and len(text) < 2500


def wants_code_help(text: str) -> bool:
    return bool(ASK_CODE_RE.search(text or ""))


def maybe_inject(user_text: str, replied_text: str = "") -> str:
    """Knowledge injection utk kode/error. Return teks konteks atau ''."""
    src = replied_text or user_text or ""
    if not src:
        return ""
    parts = []

    code = extract_code(src)
    err = is_error_paste(src)

    if code and (wants_code_help(user_text) or err or
                 CODE_BLOCK_RE.search(src)):
        lang = "kode"
        m = re.search(r"```(\w+)", src)
        if m:
            lang = m.group(1)
        parts.append(
            f"\n\nKODE USER ({lang}) YANG DIBAHAS — analisa dengan teliti, "
            f"jelaskan/fix sesuai yang diminta:\n```\n{code}\n```")
        if err:
            parts.append("(Pesan user juga mengandung pesan error — "
                         "kaitkan penyebab errornya dengan kode di atas.)")

    if err and not code:
        parts.append(
            "\n\nUSER MELAPORKAN ERROR/TRACEBACK berikut — jelaskan "
            "penyebabnya dan berikan solusi konkret:\n```\n"
            f"{src[:MAX_CODE_CHARS]}\n```")

    return "".join(parts)


# ── sandbox runner (run python) ───────────────────────────────────
_RUN_ASK_RE = re.compile(
    r"\b(run|jalankan|eksekusi|execute)\b.{0,30}\b(kode|code|python|script)\b|"
    r"\b(kode|code|script)\b.{0,30}\b(run|jalankan|eksekusi)\b",
    re.IGNORECASE | re.DOTALL)


async def run_python(code: str, timeout: float = 10.0) -> str:
    """Jalankan kode python di subprocess terpisah (sandbox ringan).
    Return output (dipotong) — dipakai LLM sebagai hasil nyata, bukan karangan."""
    proc = await asyncio.create_subprocess_exec(
        "python3", "-I", "-c", code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return "(error: eksekusi timeout >10s)"
    text = (out or b"").decode("utf-8", "replace").strip()
    return text[:1500] or "(tidak ada output)"


def wants_run(text: str, code: str) -> bool:
    return bool(code) and bool(_RUN_ASK_RE.search(text or ""))
