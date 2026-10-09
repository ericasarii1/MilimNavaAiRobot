# ══════════════════════════════════════════════════════════════════
#   LIFEDATA — data praktis harian sebagai KEMAMPUAN (bukan command):
#   1. KURS: "kurs dollar", "1 usd berapa rupiah" (open.er-api.com)
#   2. CRYPTO: "harga bitcoin" (Coinbase spot, gratis tanpa key)
#   3. JADWAL SHOLAT: "jadwal sholat jakarta" (api.myquran.com)
#   Hasil di-inject ke konteks saat pertanyaan terdeteksi → jawaban
#   berisi angka real-time, bukan tebakan.
# ══════════════════════════════════════════════════════════════════

import re
import time
import logging

import aiohttp

log = logging.getLogger("milim.lifedata")

CACHE = {}
CACHE_TTL = 900  # 15 menit

KOTA_CACHE = None

# ── deteksi ───────────────────────────────────────────────────────
KURS_RE = re.compile(
    r"\b(kurs|dollar|dolar|usd|rupiah|idr|euro|eur|sgd|yen|jpy|"
    r"riyal|sar|won|krw|yuan|cny|ringgit|myr)\b", re.IGNORECASE)
CRYPTO_RE = re.compile(
    r"\b(bitcoin|btc|ethereum|eth|crypto|kripto|solana|sol\b|bnb|"
    r"xrp|doge|usdt|tether|satoshi)\b", re.IGNORECASE)
SHOLAT_RE = re.compile(
    r"\b(jadwal\s*sholat|jadwal\s*salat|jadwal\s*solat|waktu\s*sholat|"
    r"imsak|adzan|azan|maghrib|subuh|isya|ashar|dzuhur|dhuhur|terbit)\b",
    re.IGNORECASE)


def detect(text: str) -> list:
    """Return jenis data yang dibutuhkan: ['kurs','crypto','sholat']."""
    out = []
    if text:
        if KURS_RE.search(text):
            out.append("kurs")
        if CRYPTO_RE.search(text):
            out.append("crypto")
        if SHOLAT_RE.search(text):
            out.append("sholat")
    return out


# ── kurs ──────────────────────────────────────────────────────────
# kode umum → nama ramah
NAMA = {"USD": "Dolar AS", "EUR": "Euro", "SGD": "Dolar Singapura",
        "JPY": "Yen Jepang", "SAR": "Riyal Saudi", "KRW": "Won Korea",
        "CNY": "Yuan China", "MYR": "Ringgit Malaysia",
        "AED": "Dirham UE", "AUD": "Dolar Australia", "GBP": "Pound Inggris"}
WANTED = ["USD", "EUR", "SGD", "JPY", "SAR", "KRW", "CNY", "MYR", "AUD"]


async def _kurs() -> str:
    hit = CACHE.get("kurs")
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    try:
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)) as ses:
            async with ses.get("https://open.er-api.com/v6/latest/USD") as r:
                if r.status != 200:
                    return ""
                d = await r.json()
    except Exception as e:
        log.debug(f"kurs err: {e}")
        return ""
    rates = d.get("rates") or {}
    idr = rates.get("IDR")
    if not idr:
        return ""
    lines = [f"- 1 USD = Rp {idr:,.0f}".replace(",", ".")]
    for code in WANTED[1:]:
        v = rates.get(code)
        if v:
            # nilai mata uang itu dulu → rupiah
            rp = idr / v
            lines.append(f"- 1 {NAMA.get(code, code)} = Rp {rp:,.0f}"
                         .replace(",", "."))
    out = ("DATA KURS HARI INI (real-time):\n" + "\n".join(lines))
    CACHE["kurs"] = (time.time(), out)
    return out


# ── crypto ────────────────────────────────────────────────────────
COINS = {"BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana",
         "DOGE": "Dogecoin", "XRP": "XRP"}


async def _crypto() -> str:
    hit = CACHE.get("crypto")
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    lines = []
    async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)) as ses:
        for code, nama in COINS.items():
            try:
                async with ses.get(
                        f"https://api.coinbase.com/v2/prices/{code}-IDR/spot") as r:
                    if r.status != 200:
                        continue
                    d = await r.json()
                    amt = float(d["data"]["amount"])
                    lines.append(f"- {nama}: Rp {amt:,.0f}".replace(",", "."))
            except Exception:
                continue
    if not lines:
        return ""
    out = "HARGA CRYPTO (real-time ke Rupiah):\n" + "\n".join(lines)
    CACHE["crypto"] = (time.time(), out)
    return out


# ── jadwal sholat ─────────────────────────────────────────────────
KOTA_TERKENAL = {"jakarta": "1301"}  # sisanya dicari via API daftar kota


async def _kota_id(nama_kota: str) -> str:
    """Cari ID kota via API daftar kota (cache penuh)."""
    global KOTA_CACHE
    q = nama_kota.lower().strip()
    if q in KOTA_TERKENAL:
        return KOTA_TERKENAL[q]
    if not KOTA_CACHE:
        try:
            async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=15)) as ses:
                async with ses.get(
                        "https://api.myquran.com/v2/sholat/kota/semua") as r:
                    if r.status != 200:
                        return ""
                    d = await r.json()
            KOTA_CACHE = [(x["lokasi"].lower(), str(x["id"]))
                          for x in d.get("data", [])]
        except Exception:
            return ""
    hits = [(lokasi, kid) for lokasi, kid in KOTA_CACHE if q in lokasi]
    if not hits:
        return ""
    # prioritas "KOTA X" di atas "KAB. X"
    hits.sort(key=lambda x: (0 if x[0].startswith("kota") else 1, len(x[0])))
    return hits[0][1]


async def _sholat(text: str) -> str:
    # kota dari teks (kata setelah 'sholat/solat/salat' atau nama kota umum)
    m = re.search(r"(?:sholat|salat|solat)\s+(?:di\s+)?([a-z\s]{3,25})",
                  text, re.IGNORECASE)
    kota_q = (m.group(1).strip() if m else "") or "jakarta"
    kota_q = re.sub(r"[^a-z\s]", "", kota_q.lower()).strip()
    kid = await _kota_id(kota_q) or "1301"
    today = time.strftime("%Y-%m-%d")
    try:
        async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)) as ses:
            async with ses.get(
                    f"https://api.myquran.com/v2/sholat/jadwal/{kid}/{today}") as r:
                if r.status != 200:
                    return ""
                d = await r.json()
    except Exception as e:
        log.debug(f"sholat err: {e}")
        return ""
    j = (d.get("data", {}) or {}).get("jadwal", {})
    lokasi = (d.get("data", {}) or {}).get("lokasi", kota_q)
    if not j:
        return ""
    out = (
        f"JADWAL SHOLAT {lokasi.upper()} hari ini ({j.get('tanggal','')}):\n"
        f"- Imsak: {j.get('imsak','-')} | Subuh: {j.get('subuh','-')}\n"
        f"- Terbit: {j.get('terbit','-')} | Dzuhur: {j.get('dzuhur','-')}\n"
        f"- Ashar: {j.get('ashar','-')} | Maghrib: {j.get('maghrib','-')}\n"
        f"- Isya: {j.get('isya','-')}")
    return out


async def maybe_inject(text: str) -> str:
    """Teks user → data real-time yang relevan (boleh >1 sekaligus)."""
    kinds = detect(text)
    if not kinds:
        return ""
    parts = []
    if "kurs" in kinds:
        k = await _kurs()
        if k:
            parts.append(k)
    if "crypto" in kinds:
        c = await _crypto()
        if c:
            parts.append(c)
    if "sholat" in kinds:
        s = await _sholat(text)
        if s:
            parts.append(s)
    if not parts:
        return ""
    return ("\n\nDATA REAL-TIME (pakai angka ini apa adanya, jangan "
            "mengarang):\n" + "\n\n".join(parts))
