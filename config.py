# ══════════════════════════════════════════════════════════════════
#   MILIM NAVA — Konfigurasi (tanpa .env, isi langsung di sini)
# ══════════════════════════════════════════════════════════════════

import re

# ── Telegram (urutan: Api Id, Api Hash, Bot Token, Owner Id) ──────
API_ID = 12345678                                # ← ganti: my.telegram.org
API_HASH = "abcdef0123456789abcdef0123456789"    # ← ganti: my.telegram.org
BOT_TOKEN = "123456:ABC-DEF..."                  # ← ganti: @BotFather
OWNER_ID = 123456789                             # ← ganti: user id kamu

# ── Database (urutan: Mongodb → Redis → Postgres) ─────────────────
# Minimal satu aktif; bisa semua sekaligus (write-through + fallback).
MONGODB_URI = "mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
MONGODB_DB = "milim_nava"
REDIS_URL = "redis://default:pass@host:6379/0"
POSTGRES_DSN = "postgresql://user:pass@host:5432/milim"

# ── Multi-Provider API keys (multi-key per provider, fallback) ────
# style: "openai" (kompatibel OpenAI/Groq/DeepSeek/dll), "gemini", "anthropic"
# Semua bisa jalan barengan, satu saja, atau sebagai fallback antar provider.
PROVIDERS = [
    {
        "name": "OpenRouter",
        "keys": [
            "sk-or-v1-XXXXXXXXXXXXXXXXXXXXXXXX",
            # "sk-or-v1-YYYYYYYYYYYYYYYYYYYYYYYY",
        ],
        "model": "openai/gpt-4o-mini",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "style": "openai",
    },
    {
        "name": "Google Gemini",
        "keys": ["AIzaXXXXXXXXXXXXXXXXXXXXXXXX"],
        "model": "gemini-2.0-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "style": "gemini",
    },
    {
        "name": "Groq",
        "keys": ["gsk_XXXXXXXXXXXXXXXXXXXXXXXX"],
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "style": "openai",
    },
    {
        "name": "DeepSeek",
        "keys": ["sk-XXXXXXXXXXXXXXXXXXXXXXXX"],
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "style": "openai",
    },
    {
        "name": "OpenAI",
        "keys": ["sk-XXXXXXXXXXXXXXXXXXXXXXXX"],
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "style": "openai",
    },
    {
        "name": "Anthropic Claude",
        "keys": ["sk-ant-XXXXXXXXXXXXXXXXXXXX"],
        "model": "claude-3-5-haiku-20241022",
        "base_url": "https://api.anthropic.com/v1/messages",
        "style": "anthropic",
    },
    # Tambah provider lain tinggal copy blok di atas:
    # Qwen, Mistral, Cohere, xAI/Grok, Cerebras, SambaNova, NVIDIA NIM,
    # Cloudflare AI, HuggingFace, Together, Fireworks, DeepInfra, Replicate,
    # AI21, Nebius, Chutes, OVHcloud, Perplexity, Vercel Gateway, Z.ai/GLM,
    # GitHub Models, Ollama (http://localhost:11434/v1/...), Bedrock, Kimi,
    # MiniMax, SiliconFlow, Novita, Hyperbolic, FriendliAI, Lepton, Modal,
    # Baseten, Anyscale.
]

# ── Nama-nama bot ─────────────────────────────────────────────────
NAMES = ["milim", "lim", "limlim", "lilim", "nava", "milim nava", "mili"]
NAMES_RE = re.compile(r"\b(milim\s*nava|milim|limlim|lilim|lim|nava|mili)\b", re.IGNORECASE)
CMD_RE = re.compile(r"^\s*(milim\s*nava|milim|limlim|lilim|lim|nava|mili)\s+(.+)$",
                    re.IGNORECASE | re.DOTALL)

# ── Batasan / antispam ────────────────────────────────────────────
ANTISPAM_MIN_INTERVAL = 2.0
ANTISPAM_BURST = 5
ANTISPAM_WINDOW = 60.0
REQUEST_TIMEOUT = 120
MAX_CONTEXT_MSGS = 30
GROUP_THREAD_LIMIT = 40
BATCH_WINDOW = 1.2          # detik gabung pesan spam
PROVIDER_RPM = 55           # aman di bawah limit umum
KEY_COOLDOWN_RATE = 300     # detik cooldown key kena limit
KEY_COOLDOWN_AUTH = 3600    # detik cooldown key invalid
KEY_COOLDOWN_ERR = 60       # detik cooldown key error umum
PROVIDER_COOLDOWN = 60      # detik cooldown provider habis semua key-nya mati

# ── Lain-lain ─────────────────────────────────────────────────────
TZ_OFFSET = 7               # WIB
LOG_LEVEL = "INFO"
