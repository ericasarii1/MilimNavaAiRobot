# ══════════════════════════════════════════════════════════════════
#   MILIM NAVA — Package init (ala SaitamaRobot)
#   Config + Database + LLM + State + Memory + Client
#   Semua modul meng-import dari sini.
# ══════════════════════════════════════════════════════════════════

import logging
import time
import asyncio

from pyrogram import Client, enums

StartTime = time.time()

# ── logging ──────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[logging.FileHandler("log.txt"), logging.StreamHandler()],
    level=logging.INFO,
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger("MilimNavaAiRobot")


# ══════════════════════════════════════════════════════════════════
#   KONFIGURASI — ala SaitamaRobot:
#   1. .env / environment variables (prioritas utama)
#   2. config.py di folder package (rename dari sample_config.py)
#   3. Default di bawah (fallback terakhir)
# ══════════════════════════════════════════════════════════════════

import os

# load .env sederhana (tanpa dependency)
_ENV = {}
try:
    from pathlib import Path as _P
    _env_file = _P(__file__).parent.parent / ".env"
    if _env_file.exists():
        for _line in _env_file.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _ENV.setdefault(_k.strip(), _v.strip())
except Exception:
    pass


def _get(name, default=None):
    return os.environ.get(name) or _ENV.get(name) or default


try:
    from MilimNavaAiRobot.config import Config as _FileConfig
    _FILE = {k: getattr(_FileConfig, k) for k in dir(_FileConfig)
             if not k.startswith("_") and k.isupper()}
except ImportError:
    _FILE = {}


def _cfg(name, default):
    v = _get(name)
    if v is not None:
        return v
    return _FILE.get(name, default)


def _cfg_int(name, default):
    try:
        return int(_cfg(name, default))
    except (TypeError, ValueError):
        return default


def _cfg_providers():
    """PROVIDERS: lightvela (env LIGHTVELA_KEY) → openrouter (env) → config.py → default."""
    providers = []

    # 1. LightVela provider (key via env LIGHTVELA_KEY) — prioritas utama
    lv_key = _get("LIGHTVELA_KEY")
    if lv_key:
        providers.append({
            "name": "lightvela",
            "keys": [k.strip() for k in lv_key.split(",") if k.strip()],
            "model": _get("LIGHTVELA_MODEL", "auto"),
            "base_url": "https://token.lightvela.ai/v1/chat/completions",
            "style": "openai",
        })

    # 2. OpenRouter
    keys_env = _get("OPENROUTER_KEYS") or _get("API_KEYS")
    if keys_env:
        keys = [k.strip() for k in keys_env.split(",") if k.strip()]
        providers.append({
            "name": "openrouter",
            "keys": keys,
            "model": _get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001"),
            "base_url": "https://openrouter.ai/api/v1/chat/completions",
            "style": "openai",
        })
    if not providers and "PROVIDERS" in _FILE:
        providers = list(_FILE["PROVIDERS"])
    if not providers:
        providers = [{
            "name": "openrouter",
            "keys": ["sk-or-v1-xxxxxxxx"],
            "model": "google/gemini-2.0-flash-001",
            "base_url": "https://openrouter.ai/api/v1/chat/completions",
            "style": "openai",
        }]
    return providers


class Config:
    # REQUIRED
    API_ID = _cfg_int("API_ID", 123456)
    API_HASH = _cfg("API_HASH", "isi_api_hash")
    TOKEN = _cfg("TOKEN", "isi_bot_token")
    OWNER_ID = _cfg_int("OWNER_ID", 8907450541)

    # DATABASE
    MONGODB_URI = _cfg("MONGODB_URI", "")
    MONGODB_DB = _cfg("MONGODB_DB", "milim")
    REDIS_URL = _cfg("REDIS_URL", "")
    POSTGRES_DSN = _cfg("POSTGRES_DSN", "")

    # LLM
    PROVIDERS = _cfg_providers()

    # BEHAVIOUR
    TZ_OFFSET = _cfg_int("TZ_OFFSET", 7)
    MAX_CONTEXT_MSGS = _cfg_int("MAX_CONTEXT_MSGS", 30)
    GROUP_THREAD_LIMIT = _cfg_int("GROUP_THREAD_LIMIT", 40)
    BATCH_WINDOW = float(_cfg("BATCH_WINDOW", 3.0))
    ANTISPAM_BURST = _cfg_int("ANTISPAM_BURST", 8)
    ANTISPAM_WINDOW = _cfg_int("ANTISPAM_WINDOW", 60)
    ANTISPAM_MIN_INTERVAL = float(_cfg("ANTISPAM_MIN_INTERVAL", 1.2))
    PROVIDER_RPM = _cfg_int("PROVIDER_RPM", 55)
    KEY_COOLDOWN_RATE = _cfg_int("KEY_COOLDOWN_RATE", 300)
    KEY_COOLDOWN_AUTH = _cfg_int("KEY_COOLDOWN_AUTH", 86400)
    KEY_COOLDOWN_ERR = _cfg_int("KEY_COOLDOWN_ERR", 60)
    PROVIDER_COOLDOWN = _cfg_int("PROVIDER_COOLDOWN", 300)
    REQUEST_TIMEOUT = _cfg_int("REQUEST_TIMEOUT", 120)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    LOG_LEVEL = _cfg("LOG_LEVEL", "INFO")


import re as _re

import difflib as _difflib

_NAME_WORDS = ("milim", "nava", "lim", "lilim", "limlim", "mili")

# kata umum yang MIRIP nama tapi bukan panggilan → jangan pernah dianggap
_NOT_NAME = {
    "like", "likes", "link", "links", "klik", "kliklah", "lilin", "lima",
    "limit", "kilat", "lil", "lila", "lip", "lap", "lon", "limun", "limus",
    "naval", "nav", "lime", "lump", "lamp", "lain", "laen", "klim", "limau",
    "mil", "mile", "miles", "mill", "nail", "naskah", "nilai", "nyawa",
}


BOT_USERNAME = "MilimNavaRobot"   # @MilimNavaRobot


def _fuzzy_name_hit(text: str) -> bool:
    """Kenali nama bot walau ada typo (lik~lim, milim~milm, nawaa~nava)."""
    if not text:
        return False
    # tag mention akun bot: @MilimNavaRobot / @milimnavarobot di mana pun
    if BOT_USERNAME.lower() in text.lower():
        return True
    for w in _re.findall(r"[a-z]+", text.lower()):
        if w in _NAME_WORDS:
            return True
        if w in _NOT_NAME or len(w) < 3:
            continue
        # typo: kemiripan cukup & beda tak lebih dari 2 huruf dari nama terdekat
        for n in _NAME_WORDS:
            r = _difflib.SequenceMatcher(None, w, n).ratio()
            if r >= 0.66 and abs(len(w) - len(n)) <= 1:
                return True
    return False


NAMES_RE = _re.compile(r"\b(milim\s*nava|milim|limlim|lilim|lim|nava|mili)\b", _re.IGNORECASE)


class _FuzzyRe:
    """Drop-in untuk regex yang dipakai should_respond: search() fuzzy."""
    def search(self, text):
        if not text:
            return None
        if NAMES_RE.search(text):
            return True
        return _fuzzy_name_hit(text) or None


NAMES_MATCH_RE = _FuzzyRe()

CMD_RE = _re.compile(r"^\s*(milim\s*nava|milim|limlim|lilim|lim|nava|mili)\s+(.+)$",
                     _re.IGNORECASE | _re.DOTALL)

C = Config

# ══════════════════════════════════════════════════════════════════
#   SINGLETONS — db, llm, memory, state, app
# ══════════════════════════════════════════════════════════════════

from MilimNavaAiRobot.modules.database.db import Database   # noqa: E402
from MilimNavaAiRobot.modules.ai import LLM               # noqa: E402
from MilimNavaAiRobot.modules.memory import Memory        # noqa: E402
from MilimNavaAiRobot.modules.state import StateManager   # noqa: E402

db = Database(C.MONGODB_URI, C.MONGODB_DB, C.REDIS_URL, C.POSTGRES_DSN)
llm = LLM(C.PROVIDERS)
memory = Memory(db)
state = StateManager(db)

app = Client(
    "milim_nava",
    api_id=C.API_ID,
    api_hash=C.API_HASH,
    bot_token=C.TOKEN,
    workers=16,
    parse_mode=enums.ParseMode.MARKDOWN,
)


async def startup():
    await llm.start()
    LOGGER.info("🚀 Milim Nava bot starting…")
    LOGGER.info("   Providers : %s", [p.name for p in llm.providers])
    LOGGER.info("   DB        : %s", db.backends)
    LOGGER.info("   Owner ID  : %s", C.OWNER_ID)
    LOGGER.info("✔ Milim Nava siap menerima pesan!")
