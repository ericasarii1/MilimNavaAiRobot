# ══════════════════════════════════════════════════════════════════
#   ANIME — lookup anime/manga via AniList GraphQL (gratis, tanpa key)
#   Kemampuan (bukan command):
#   1. Tool agentic: {"tool":"anime","query":"..."} — AI panggil sendiri
#   2. Auto-inject bila pertanyaan soal anime/manga → jawaban akurat
# ══════════════════════════════════════════════════════════════════

import re
import time
import logging

import aiohttp

log = logging.getLogger("milim.anime")

GQL_URL = "https://graphql.anilist.co"
CACHE = {}
CACHE_TTL = 3600

ANIME_TRIGGER = re.compile(
    r"\b(anime|manga|donghua|manhwa|manhua|season\s*\d|episode|opening|"
    r"ending|waifu|husbando|isekai|shounen|shoujo|mecha|slice of life|"
    r"studio|mappa|ufotable|kyoto animation|jujutsu|frieren|one piece|"
    r"naruto|bleach|demon slayer|kimetsu|chainsaw|attack on titan|shingeki)\b",
    re.IGNORECASE)
NEGATIVE = re.compile(r"\b(cerita|puisi|kode|code)\b", re.IGNORECASE)


def is_anime_question(text: str) -> bool:
    return bool(text) and bool(ANIME_TRIGGER.search(text)) \
        and not NEGATIVE.search(text)


QUERY = """
query ($search: String, $type: MediaType) {
  Page(perPage: 3) {
    media(search: $search, type: $type, sort: SEARCH_MATCH) {
      title { romaji english native }
      type format
      status
      episodes chapters
      duration
      averageScore
      genres
      description(asHtml: false)
      startDate { year }
      studios(isMain: true) { nodes { name } }
    }
  }
}"""


async def lookup(query: str, mtype: str = "ANIME") -> str:
    """Search AniList → teks ringkas. Return '' kalau gagal."""
    key = (mtype, query.lower().strip())
    hit = CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20)) as ses:
            async with ses.post(GQL_URL, json={
                    "query": QUERY,
                    "variables": {"search": query, "type": mtype}},
                    headers={"User-Agent": "MilimNavaBot/1.0"}) as resp:
                if resp.status != 200:
                    log.debug(f"anilist {resp.status}")
                    return ""
                d = await resp.json()
    except Exception as e:
        log.debug(f"anilist err: {e}")
        return ""

    out = []
    for m in (d.get("data", {}).get("Page", {}).get("media") or [])[:3]:
        t = (m.get("title") or {})
        title = t.get("romaji") or t.get("english") or "?"
        bits = []
        if m.get("averageScore"):
            bits.append(f"skor {m['averageScore']}%")
        if m.get("episodes"):
            bits.append(f"{m['episodes']} episode")
        if m.get("chapters"):
            bits.append(f"{m['chapters']} chapter")
        if m.get("startDate", {}).get("year"):
            bits.append(f"({m['startDate']['year']})")
        studios = ", ".join(s["name"] for s in
                            (m.get("studios", {}).get("nodes") or [])[:2])
        if studios:
            bits.append(f"studio {studios}")
        desc = re.sub(r"<[^>]+>", "", m.get("description") or "")
        desc = desc.replace("&quot;", '"').strip()[:220]
        out.append(f"- **{title}** ({m.get('format','')}, "
                   f"{', '.join(bits)})\n  {desc}")
    result = "\n".join(out)
    if result:
        CACHE[key] = (time.time(), result)
    return result

# ── bersihkan pertanyaan → kata kunci judul ──
NOISE = re.compile(
    r"\b(milim|lim|nava|dong|ya|please|tolong|itu|berapa|kapan|apa|apakah|"
    r"anime|manga|donghua|manhwa|manhua|episode|season|nya|yang|dan|atau|"
    r"itu|ini|sih|deh|nih|gak|nggak|tidak|udah|sudah|lagi|ada|rekomendasi|"
    r"rekomendasiin|kasih|info|tentang|soal|cerita|bagus|keren|gimana|"
    r"kenapa|siapa|dimana|di mana|rilis|tayang|skor|rating|bagaimana|kok)\b",
    re.IGNORECASE)


def extract_query(text: str) -> str:
    """Ambil inti judul dari kalimat pertanyaan."""
    t = re.sub(r"[?!.,]", " ", text or "")
    t = NOISE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or (text or "").strip()


async def maybe_inject(user_text: str) -> str:
    """Pertanyaan anime/manga → inject data AniList ke konteks."""
    if not is_anime_question(user_text):
        return ""
    q = extract_query(user_text) or user_text
    mtype = "MANGA" if re.search(r"\b(manga|manhwa|manhua)\b",
                                 user_text, re.I) else "ANIME"
    data = await lookup(q, mtype)
    if not data:
        data = await lookup(user_text, mtype)   # fallback: query mentah
    if not data:
        return ""
    return ("\n\nDATA ANILIST (sumber akurat — jawab berdasarkan ini, "
            "jangan mengarang angka/episode):\n" + data)
