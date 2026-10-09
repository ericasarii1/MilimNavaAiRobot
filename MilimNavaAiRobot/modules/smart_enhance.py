# ══════════════════════════════════════════════════════════════════
#   SMART ENHANCE — biar jawaban akurat, nyambung, & tidak ngawur:
#   1. FACT-CHECK   : verifikasi konsistensi jawaban sebelum dikirim
#   2. SUMBER       : tambahkan daftar sumber dari web-search/link
#   3. CONFIDENCE   : jawaban "gue gak tau pasti" bila data kurang
#   4. ANTI-REPETISI: variasikan jawaban yang mirip sebelumnya
#   5. REPLY CHAIN  : trace utas reply ke atas utk konteks utuh
#   6. FEEDBACK     : "bukan maksud gue" → simpan preferensi ke LTM
# ══════════════════════════════════════════════════════════════════

import re
import time
import difflib
import logging

log = logging.getLogger("milim.enhance")

# ───────────────────── 2. SUMBER ─────────────────────
def extract_source_lines(context: str) -> list:
    """Ambil URL dari konteks yang diinject (web search/link reader)."""
    if not context:
        return []
    urls = re.findall(r"https?://[^\s\)\]>\"']+", context)
    out, seen = [], set()
    for u in urls:
        u = u.rstrip(".,;")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:5]


def sources_footer(context: str) -> str:
    urls = extract_source_lines(context)
    if not urls:
        return ""
    lines = "\n".join(f"• {u}" for u in urls)
    return f"\n\n📚 **Sumber:**\n{lines}"


# ──────────────── 4. ANTI-REPETISI ────────────────
_sim_cache = {}   # chat_id -> [(ts, answer)]
SIM_TTL = 3600 * 6


def _recent(chat_id):
    now = time.time()
    arr = [a for t, a in _sim_cache.get(chat_id, []) if now - t < SIM_TTL]
    _sim_cache[chat_id] = [(t, a) for t, a in _sim_cache.get(chat_id, [])
                           if now - t < SIM_TTL]
    return arr


def is_repetitive(chat_id: int, answer: str, threshold: float = 0.75) -> bool:
    a = re.sub(r"\s+", " ", (answer or "").lower()).strip()
    if len(a) < 40:
        return False
    for prev in _recent(chat_id):
        if difflib.SequenceMatcher(None, a, prev).ratio() > threshold:
            return True
    return False


def remember_answer(chat_id: int, answer: str):
    _sim_cache.setdefault(chat_id, []).append((time.time(), re.sub(
        r"\s+", " ", (answer or "").lower()).strip()))
    # jaga ukuran
    if len(_sim_cache[chat_id]) > 30:
        _sim_cache[chat_id] = _sim_cache[chat_id][-30:]


VARIATION_INSTRUCTION = (
    "\n\nPENTING: jawabanmu yang terakhir untuk chat ini mirip/identik dengan "
    "yang sebelumnya. Tulis ULANG dengan cara berbeda: kalimat, struktur, dan "
    "angle berbeda — tetap akurat, jangan mengulang frasa yang sama.")


# ──────────────── 1. FACT-CHECK ────────────────
FACTCHECK_INSTRUCTION = (
    "\n\nMODE VERIFIKASI AKTIF. Sebelum menulis jawaban final:\n"
    "- Cek setiap klaim faktual di drafmu terhadap konteks/hasil pencarian "
    "yang tersedia.\n"
    "- Klaim yang TIDAK bisa didukung data di konteks → hapus atau ubah "
    "jadi spekulasi yang ditandai jelas (\"kira-kira\", \"setahuku\").\n"
    "- Jangan mengarang angka, tanggal, nama, atau kutipan.")


async def verify_answer(llm, question: str, answer: str,
                        context: str = "") -> str:
    """Cek jawaban; return jawaban (asli / terkoreksi / disclaimer)."""
    if len(answer) < 60:
        return answer          # jawaban pendek: skip (sapaan dll)
    try:
        verdict = await llm.chat([
            {"role": "system", "content":
                "Kamu auditor ketat. Periksa jawaban AI berikut terhadap "
                "pertanyaan & konteks. Jawab HANYA salah satu:\n"
                "OK — kalau tidak ada klaim yang mencurigakan/ngawur\n"
                "FIX: <kalimat koreksi spesifik> — kalau ada klaim ngawur/"
                "kontradiktif/karangan"},
            {"role": "user", "content":
                f"PERTANYAAN: {question[:400]}\n\nKONTEKS: {context[:800]}\n\n"
                f"JAWABAN: {answer[:1200]}"}
        ], temperature=0.0)
        v = (verdict or "").strip()
        if v.upper().startswith("OK"):
            return answer
        if v.upper().startswith("FIX"):
            fixed = await llm.chat([
                {"role": "system", "content":
                    "Perbaiki jawaban berikut sesuai koreksi auditor. "
                    "Pertahankan gaya & format, ubah hanya bagian yang "
                    "bermasalah. Jangan tambahkan penjelasan proses."},
                {"role": "user", "content":
                    f"JAWABAN:\n{answer[:1200]}\n\nKOREKSI: {v[4:300]}"}
            ])
            return fixed or answer
    except Exception as e:
        log.debug(f"verify err: {e}")
    return answer


# ──────────────── 3. CONFIDENCE ────────────────
UNCERTAIN_MARKERS = re.compile(
    r"\b(gak tau|nggak tau|tidak tahu|tidak yakin|kurang yakin|"
    r"belum ada info|tidak ditemukan|tidak ada data|saya tidak "
    r"memiliki)\b", re.I)


def is_uncertain(answer: str) -> bool:
    return bool(UNCERTAIN_MARKERS.search(answer or ""))


CONFIDENT_ADDON = (
    "\n\nATURAN KEPERCAYAAN: kalau info yang dibutuhkan tidak ada di konteks "
    "dan di luar pengetahuanmu, katakan JUJUR bahwa kamu tidak tahu pasti "
    "(bisa tawarkan mencari lagi). JANGAN PERNAH mengarang jawaban.")


# ──────────────── 5. REPLY CHAIN ────────────────
async def get_reply_chain(message, depth: int = 4) -> str:
    """Trace utas reply ke atas (maks depth) → teks konteks."""
    parts = []
    msg = message
    for _ in range(depth):
        try:
            msg = msg.reply_to_message
        except Exception:
            break
        if not msg:
            break
        who = msg.from_user.first_name if msg.from_user else "?"
        txt = (msg.text or msg.caption or "").strip()
        if txt:
            parts.append(f"{who}: {txt[:250]}")
    if not parts:
        return ""
    parts.reverse()
    return ("\n\nUTAS REPLY (dari awal ke baru — ini konteks diskusi yang "
            "sedang berlangsung):\n" + "\n".join(parts))


# ──────────────── 6. FEEDBACK / KOREKSI DIRI ────────────────
CLARIFY_RE = re.compile(
    r"\b(bukan maksud|bukan gitu|salah|ngawur|kamu salah|lo salah|"
    r"maksud gue|maksudku|bukan itu|tetap salah|masih salah)\b", re.I)


def wants_correction(text: str) -> bool:
    return bool(CLARIFY_RE.search(text or "")) and len(text) < 300


CLARIFY_INSTRUCTION = (
    "\n\nCATATAN PENTING: user menandai bahwa jawabanmu sebelumnya meleset. "
    "Minta klarifikasi singkat & spesifik tentang apa yang kurang pas — "
    "JANGAN mengulang jawaban lama, JANGAN defensif. Akui dulu, lalu "
    "tanyakan satu pertanyaan klarifikasi yang tepat sasaran.")
