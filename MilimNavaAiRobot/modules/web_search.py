# ══════════════════════════════════════════════════════════════════
#   WEB SEARCH — info real-time: Google News RSS + Wikipedia + wttr.in
#   Dipicu otomatis saat pertanyaan butuh info terkini; hasil disuntik
#   ke system prompt sebelum LLM menjawab. Tanpa API key.
# ══════════════════════════════════════════════════════════════════

import re
import time
import html
import logging
import xml.etree.ElementTree as ET

import aiohttp

log = logging.getLogger("milim.websearch")

SEARCH_TRIGGERS = re.compile(
    r"\b(hari ini|kemarin|sekarang|terbaru|terkini|kabar|berita|cuaca|hujan|"
    r"panas|suhu|harga|skor|hasil pertandingan|jadwal|menang|pilpres|pemilu|"
    r"kurs|viral|tren|trending|gosip|rank|ranking|what.s the (weather|news)|"
    r"latest|today|current|news)\b", re.IGNORECASE)
NEGATIVE = re.compile(r"\b(matematika|hitung|kode|code|cerita|puisi|terjemah)\b",
                      re.IGNORECASE)
CACHE = {}
CACHE_TTL = 600
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"


def needs_search(text: str) -> bool:
    return bool(SEARCH_TRIGGERS.search(text)) and not NEGATIVE.search(text)


def _cache_get(key):
    hit = CACHE.get(key)
    return hit[1] if hit and time.time() - hit[0] < CACHE_TTL else None


def _cache_set(key, val):
    CACHE[key] = (time.time(), val)


async def _get(url, timeout=15):
    try:
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)) as ses:
            async with ses.get(url, headers={"User-Agent": UA}) as resp:
                if resp.status == 200:
                    return await resp.text()
                log.debug(f"GET {url} -> {resp.status}")
    except Exception as e:
        log.debug(f"GET {url} err: {e}")
    return None


async def _news(query: str, limit: int = 4) -> str:
    import urllib.parse
    full = ("https://news.google.com/rss/search?q=" +
            urllib.parse.quote(query) + "&hl=id&gl=ID&ceid=ID:id")
    body = await _get(full)
    if not body:
        return ""
    try:
        root = ET.fromstring(body)
        out = []
        for item in root.iter("item")[:limit] if False else                 list(root.iter("item"))[:limit]:
            title = html.unescape((item.findtext("title") or "").strip())
            pub = item.findtext("pubDate") or ""
            src = ""
            se = item.find("source")
            if se is not None and se.text:
                src = se.text.strip()
            line = f"- {title}"
            if src:
                line += f" [{src}]"
            if pub:
                line += f" ({pub[:16]})"
            out.append(line)
        return "\n".join(out)
    except Exception as e:
        log.debug(f"news parse err: {e}")
        return ""


async def _weather(place: str) -> str:
    try:
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)) as ses:
            async with ses.get(
                    f"https://wttr.in/{place}",
                    params={"format": "%l: %c %t (feels %f) humidity %h"},
                    headers={"User-Agent": "curl/8.0"}) as resp:
                if resp.status == 200:
                    return (await resp.text()).strip()
    except Exception as e:
        log.debug(f"weather err: {e}")
    return ""


async def _wiki(query: str, lang="id") -> str:
    import urllib.parse
    url = (f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/" +
           urllib.parse.quote(query.replace(" ", "_")))
    body = await _get(url, timeout=10)
    if not body:
        return ""
    try:
        import json
        d = json.loads(body)
        if d.get("type") == "standard":
            return (d.get("title", "") + ": " +
                    d.get("extract", ""))[:400]
    except Exception:
        pass
    return ""


async def web_search(query: str, limit: int = 4) -> str:
    """Gabungan berita + cuaca (bila relevan) + wiki → teks atau ''. """
    key = query.lower().strip()
    hit = _cache_get(key)
    if hit is not None:
        return hit

    parts = []

    if re.search(r"\b(cuaca|hujan|panas|suhu|weather)\b", query, re.I):
        place = "Jakarta"
        for city in ["Jakarta", "Bandung", "Surabaya", "Medan", "Semarang",
                     "Yogyakarta", "Makassar", "Denpasar"]:
            if re.search(city, query, re.I):
                place = city
                break
        w = await _weather(place)
        if w:
            parts.append("CUACA " + w)

    q = re.sub(r"(berita|terbaru|terkini|kabar|hari ini|news)", " ",
               query, flags=re.I).strip() or query
    news = await _news(q, limit)
    if news:
        parts.append("BERITA TERKINI:\n" + news)

    wiki = await _wiki(q)
    if wiki:
        parts.append("WIKIPEDIA:\n" + wiki)

    result = "\n\n".join(parts)
    if result:
        _cache_set(key, result)
    return result


async def maybe_search_and_inject(user_text: str) -> str:
    if not needs_search(user_text):
        return ""
    results = await web_search(user_text)
    if not results:
        return ""
    return ("\n\nHASIL PENCARIAN WEB REAL-TIME (jawab berdasarkan info ini; "
            "sebut sumber bila relevan):\n" + results)
