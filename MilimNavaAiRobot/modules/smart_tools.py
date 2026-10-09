# ══════════════════════════════════════════════════════════════════
#   SMART TOOLS — kemampuan tambahan biar Milim super cerdas:
#   1. LINK READER   : share link → isi halaman dibaca & diinject ke AI
#   2. CALC          : ekspresi matematika dihitung presisi (bukan tebakan LLM)
#   3. DEEP THINK    : reasoning 3 tahap utk pertanyaan kompleks
#   Semua otomatis — tanpa command.
# ══════════════════════════════════════════════════════════════════

import re
import ast
import html
import time
import operator
import logging
import urllib.parse

import aiohttp
from bs4 import BeautifulSoup

log = logging.getLogger("milim.tools")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "Chrome/124.0 Safari/537.36")
UA_WIKI = ("MilimNavaBot/1.0 (https://t.me/MilimNavaRobot; "
           "contact: aleneric@nekosan.uk) aiohttp")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
LINK_CACHE = {}
CACHE_TTL = 1800

# ─────────────────────────── LINK READER ───────────────────────────
MAX_PAGE_CHARS = 4000
SKIP_HOSTS = (r"youtube\.com", r"youtu\.be", r"tiktok\.com",
              r"instagram\.com", r"facebook\.com", r"x\.com",
              r"twitter\.com")


def extract_urls(text: str) -> list:
    return URL_RE.findall(text or "")


async def read_url(url: str) -> str:
    """Download & ekstrak teks utama sebuah halaman → ringkas."""
    key = url.lower()
    hit = LINK_CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]

    if any(re.search(h, key) for h in SKIP_HOSTS):
        return ""
    try:
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20)) as ses:
            ua = UA_WIKI if "wikipedia.org" in url else UA
            async with ses.get(url, headers={"User-Agent": ua},
                               allow_redirects=True) as resp:
                if resp.status != 200:
                    return ""
                ctype = resp.headers.get("content-type", "")
                if "text/html" not in ctype and "text/plain" not in ctype:
                    return ""
                body = await resp.text(errors="ignore")
    except Exception as e:
        log.debug(f"read_url err {url}: {e}")
        return ""

    try:
        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "form", "noscript", "iframe", "svg"]):
            tag.decompose()
        # judul + paragraf
        title = soup.title.get_text(strip=True) if soup.title else ""
        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        paras = [p for p in paras if len(p) > 40]
        text = (title + "\n\n" if title else "") + "\n".join(paras)
        text = html.unescape(text)
        # pangkas
        if len(text) > MAX_PAGE_CHARS:
            text = text[:MAX_PAGE_CHARS] + "…"
        if len(text) > 80:
            LINK_CACHE[key] = (time.time(), text)
            return text
    except Exception as e:
        log.debug(f"parse err {url}: {e}")
    return ""


async def maybe_read_links(user_text: str) -> str:
    """Kalau ada link di pesan → baca isinya, return konteks."""
    urls = extract_urls(user_text)
    if not urls:
        return ""
    parts = []
    for u in urls[:2]:        # maks 2 link per pesan
        content = await read_url(u)
        if content:
            parts.append(f"ISI HALAMAN {u}:\n{content}")
    if not parts:
        return ""
    return ("\n\nKONTEKS DARI LINK YANG DIKIRIM USER (jawab berdasarkan isi "
            "halaman ini; kalau user cuma share link tanpa pertanyaan, "
            "ringkas isi halamannya):\n" + "\n\n---\n\n".join(parts))


# ─────────────────────────── CALCULATOR ───────────────────────────
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv, ast.USub: operator.neg,
        ast.UAdd: operator.pos}
_FUNCS = {"sqrt": lambda x: x ** 0.5, "abs": abs, "sin": __import__("math").sin,
          "cos": __import__("math").cos, "tan": __import__("math").tan,
          "log": __import__("math").log10, "ln": __import__("math").log,
          "round": round}
_CONSTS = {"pi": __import__("math").pi, "e": __import__("math").e}
CALC_RE = re.compile(
    r"(?<![\w.])(-?\d+(?:[.,]\d+)?)\s*([\+\-\*\/x×÷\^])\s*(-?\d+(?:[.,]\d+)?)"
    r"(?![\w%])")


def _safe_calc(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_calc(node.left),
                                   _safe_calc(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_calc(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _FUNCS and len(node.args) == 1:
        return _FUNCS[node.func.id](_safe_calc(node.args[0]))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    raise ValueError("tidak diizinkan")


def try_calculate(text: str) -> str:
    """Return 'HASIL: ...' kalau pesan berisi hitungan jelas, else ''."""
    if not text:
        return ""
    # hanya kalau terlihat seperti ekspresi matematis murni
    cleaned = (text.replace("×", "*").replace("÷", "/").replace("x", "*")
               .replace("^", "**").replace(",", "."))
    cleaned = re.sub(r"\b(berapa|hasil|hitung|kali|tambah|bagi|kurang|sama dengan|\?|=)\b",
                     " ", cleaned, flags=re.I).strip()
    if not re.fullmatch(r"[\d\s\.\+\-\*/%\(\)]*(sqrt|sin|cos|tan|log|ln|round|pi|e)?[\d\s\.\+\-\*/%\(\)]*",
                        cleaned, re.I):
        return ""
    if not CALC_RE.search(text) and "%" not in cleaned \
            and not re.search(r"(sqrt|sin|cos|tan|log|ln|round|\bpi\b)",
                              cleaned, re.I):
        return ""
    try:
        tree = ast.parse(cleaned, mode="eval")
        result = _safe_calc(tree.body)
        if isinstance(result, float):
            result = round(result, 10)
            if result == int(result):
                result = int(result)
        return f"HASIL HITUNG PASTI (cek dengan kalkulator — jangan ragu): {result}"
    except Exception:
        return ""


# ─────────────────────────── DEEP THINK ───────────────────────────
DEEP_TRIGGERS = re.compile(
    r"\b(pikir dalam|deep think|mikir dalam|pikirkan baik|pertimbangkan|"
    r"analisis mendalam|analisa mendalam|kenapa|mengapa|bagaimana cara|"
    r"sebaiknya|solusi|strategi|perbedaan|minta saran|nasihat)\b", re.I)
DEEP_SKIP = re.compile(r"^\s*(hai|halo|hi|pagi|siang|malam|test|tes)\b", re.I)


def is_deep_question(text: str) -> bool:
    if not text or len(text) < 25:
        return False
    if DEEP_SKIP.search(text):
        return False
    return bool(DEEP_TRIGGERS.search(text))


DEEP_INSTRUCTION = (
    "\n\nMODE BERPIKIR DALAM AKTIF. Prosedur WAJIB sebelum menjawab:\n"
    "1. Analisis pertanyaan: identifikasi inti masalah, asumsi tersembunyi, "
    "dan sudut pandang alternatif (pikirkan, JANGAN ditulis di jawaban).\n"
    "2. Kritik draf jawabanmu: cari kelemahan, fakta yang belum pasti, "
    "perspektif yang terlewat (pikirkan, JANGAN ditulis).\n"
    "3. Tulis HANYA jawaban final yang sudah matang — terstruktur, "
    "dengan alasan singkat tiap poin. Jangan tunjukkan proses 1-2 di atas.")


async def deep_think_answer(llm, msgs: list, max_iter: int = 1) -> str:
    """Reasoning dua lintasan: draf → kritik diri → final."""
    draft = await llm.chat(msgs + [{"role": "user", "content":
        "(Draf cepat dulu — internal, bukan jawaban final)"}])
    critique = await llm.chat([
        {"role": "system", "content":
            "Kamu pemeriksa kritis. Evaluasi draf berikut: sebutkan 2-3 "
            "kelemahan terbesar (fakta, logika, kelalaian) dalam poin "
            "singkat."},
        {"role": "user", "content": f"PERTANYAAN:\n{msgs[-1]['content'][:600]}"
         f"\n\nDRAF:\n{draft[:800]}"}])
    final = await llm.chat(msgs + [
        {"role": "assistant", "content": draft},
        {"role": "user", "content":
            f"Kritik terhadap drafmu:\n{critique[:400]}\n\n"
            "Sekarang tulis jawaban FINAL yang sudah memperbaiki semua "
            "kritik di atas. Hanya jawaban final."}])
    return final
