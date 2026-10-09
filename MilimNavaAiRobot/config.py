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
    API_ID = 24714349              # dari https://my.telegram.org
    API_HASH = "54eb108eb194c40b376cc9a753bf738a"
    TOKEN = "8327682798:AAEHWxm9jWmNNqMaT8XTB9h6wE9k0oPVMaQ"          # dari @BotFather
    OWNER_ID = 8250624344        # user id owner

    # DATABASE — MongoDB / Redis / PostgreSQL (minimal 1, boleh semua)
    MONGODB_URI = "mongodb+srv://pinivo3229_db_user:b46ve3uqc75xS6GU@milimnavaaidb.bjren1z.mongodb.net"
    MONGODB_DB = "milim"
    REDIS_URL = ""
    POSTGRES_DSN = ""

    # LLM PROVIDERS — urutan = prioritas fallback; keys unlimited
    # style: openai (OpenRouter/Groq/DeepSeek/dll) | gemini | anthropic
    PROVIDERS = [
        {
            "name": "openrouter",
            "keys": ["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"],
            "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
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
