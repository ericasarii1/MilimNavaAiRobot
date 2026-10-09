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
#   KONFIGURASI — isi di sini, tanpa .env
# ══════════════════════════════════════════════════════════════════

class Config:
    # REQUIRED — dari https://my.telegram.org dan @BotFather
    API_ID = 123456              # integer
    API_HASH = "isi_api_hash"
    TOKEN = "isi_bot_token"
    OWNER_ID = 8907450541        # user id owner (bisa clear database)

    # DATABASE — MongoDB Atlas / Redis / PostgreSQL (boleh salah satu,
    # barengan, atau kosongkan URI lain; minimal 1)
    MONGODB_URI = ""             # ex: mongodb+srv://user:pass@cluster/
    MONGODB_DB = "milim"
    REDIS_URL = ""               # ex: redis://default:pass@host:6379
    POSTGRES_DSN = ""            # ex: postgresql://user:pass@host/db

    # LLM PROVIDERS — urutan = prioritas fallback; keys bisa unlimited
    # style: openai (OpenRouter/Groq/DeepSeek/dll) | gemini | anthropic
    PROVIDERS = [
        {
            "name": "openrouter",
            "keys": ["sk-or-v1-xxxxxxxx"],
            "model": "google/gemini-2.0-flash-001",
            "base_url": "https://openrouter.ai/api/v1/chat/completions",
            "style": "openai",
        },
    ]

    # BEHAVIOUR
    TZ_OFFSET = 7                # WIB
    MAX_CONTEXT_MSGS = 30        # riwayat personal per user
    GROUP_THREAD_LIMIT = 40      # thread grup utuh
    BATCH_WINDOW = 3.0           # detik tunggu batch merge spam
    ANTISPAM_BURST = 8           # maks pesan per window
    ANTISPAM_WINDOW = 60
    ANTISPAM_MIN_INTERVAL = 1.2  # jeda minimal antar pesan per user
    PROVIDER_RPM = 55            # rate limit per provider per menit
    KEY_COOLDOWN_RATE = 300      # detik key istirahat saat limit
    KEY_COOLDOWN_AUTH = 86400    # key invalid → ditinggal sehari
    KEY_COOLDOWN_ERR = 60
    PROVIDER_COOLDOWN = 300
    REQUEST_TIMEOUT = 120
    LOG_LEVEL = "INFO"


import re as _re

NAMES_RE = _re.compile(r"\b(milim\s*nava|milim|limlim|lilim|lim|nava|mili)\b", _re.IGNORECASE)
CMD_RE = _re.compile(r"^\s*(milim\s*nava|milim|limlim|lilim|lim|nava|mili)\s+(.+)$",
                     _re.IGNORECASE | _re.DOTALL)

C = Config

# ══════════════════════════════════════════════════════════════════
#   SINGLETONS — db, llm, memory, state, app
# ══════════════════════════════════════════════════════════════════

from MilimNavaAiRobot.modules.database import Database    # noqa: E402
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
