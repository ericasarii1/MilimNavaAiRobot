# ══════════════════════════════════════════════════════════════════
#   SAMPLE CONFIG — template ala SaitamaRobot
#   Cara pakai (pilih salah satu):
#   1. Rename file ini jadi config.py lalu isi langsung, ATAU
#   2. Buat file .env di repo root dan isi variabelnya (prioritas)
#
#   .env contoh:
#   API_ID=123456
#   API_HASH=xxxx
#   TOKEN=123456:ABC-xxx
#   OWNER_ID=8907450541
#   MONGODB_URI=mongodb+srv://user:pass@cluster/
#   OPENROUTER_KEYS=sk-or-v1-xxx,sk-or-v1-yyy
#   OPENROUTER_MODEL=google/gemini-2.0-flash-001
# ══════════════════════════════════════════════════════════════════

import os


def get_user_list(key):
    pass


class Config(object):
    LOGGER = True

    # REQUIRED
    API_ID = 123456              # dari https://my.telegram.org
    API_HASH = "awoo"
    TOKEN = "BOT_TOKEN"          # dari @BotFather
    OWNER_ID = 8907450541        # user id owner

    # DATABASE — MongoDB / Redis / PostgreSQL (minimal 1, boleh semua)
    MONGODB_URI = ""
    MONGODB_DB = "milim"
    REDIS_URL = ""
    POSTGRES_DSN = ""

    # LLM PROVIDERS — urutan = prioritas fallback; keys unlimited
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
    MAX_CONTEXT_MSGS = 30
    GROUP_THREAD_LIMIT = 40
    BATCH_WINDOW = 3.0
    ANTISPAM_BURST = 8
    ANTISPAM_WINDOW = 60
    ANTISPAM_MIN_INTERVAL = 1.2
    PROVIDER_RPM = 55
    KEY_COOLDOWN_RATE = 300
    KEY_COOLDOWN_AUTH = 86400
    KEY_COOLDOWN_ERR = 60
    PROVIDER_COOLDOWN = 300
    REQUEST_TIMEOUT = 120
    LOG_LEVEL = "INFO"
