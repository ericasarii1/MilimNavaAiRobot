# ══════════════════════════════════════════════════════════════════
#   LLM PROVIDER LAYER — multi-provider, multi-key, sticky + fallback
#   - Sticky: selama key+model aktif, TIDAK pindah-pindah
#   - Fallback: key limit/error/invalid → key berikutnya → provider
#   - Anti-abuse: rate limit per key + cooldown progresif
#   - Mendukung: OpenAI-compatible, Gemini, Anthropic style
# ══════════════════════════════════════════════════════════════════

import time
import json
import base64
import logging
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from MilimNavaAiRobot import C

log = logging.getLogger("milim.llm")


class _RateLimit(Exception):
    pass


class _AuthError(Exception):
    pass


class LLMError(Exception):
    pass


@dataclass
class ProviderState:
    name: str
    keys: list
    model: str
    base_url: str
    style: str
    key_idx: int = 0
    dead_keys: dict = field(default_factory=dict)
    dead_until: float = 0
    rpm: list = field(default_factory=list)


class LLM:
    def __init__(self, providers: list):
        self.providers = [ProviderState(**p) for p in providers]
        self.p_idx = 0
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=C.REQUEST_TIMEOUT))

    async def close(self):
        if self.session:
            await self.session.close()

    def _rate_ok(self, p: ProviderState) -> bool:
        now = time.time()
        p.rpm = [t for t in p.rpm if now - t < 60]
        if len(p.rpm) >= C.PROVIDER_RPM:
            return False
        p.rpm.append(now)
        return True

    def _dead(self, p: ProviderState, k_idx: int) -> bool:
        return time.time() < p.dead_keys.get(k_idx, 0) or time.time() < p.dead_until

    def _mark_dead(self, p: ProviderState, k_idx: int, seconds: int):
        p.dead_keys[k_idx] = time.time() + seconds

    async def chat(self, messages: list, image_b64: Optional[str] = None) -> str:
        total = len(self.providers)
        last_err = None
        for attempt in range(total):
            p = self.providers[(self.p_idx + attempt) % total]
            if time.time() < p.dead_until:
                continue
            for k in range(len(p.keys)):
                k_idx = (p.key_idx + k) % len(p.keys)
                if self._dead(p, k_idx) or not self._rate_ok(p):
                    continue
                try:
                    result = await self._call(p, p.keys[k_idx], messages, image_b64)
                    self.p_idx = (self.p_idx + attempt) % total   # sticky
                    p.key_idx = k_idx
                    return result
                except _RateLimit as e:
                    log.warning(f"[{p.name}] key#{k_idx} limit: {e}")
                    self._mark_dead(p, k_idx, C.KEY_COOLDOWN_RATE)
                    last_err = e
                except _AuthError as e:
                    log.warning(f"[{p.name}] key#{k_idx} invalid: {e}")
                    self._mark_dead(p, k_idx, C.KEY_COOLDOWN_AUTH)
                    last_err = e
                except Exception as e:
                    log.warning(f"[{p.name}] key#{k_idx} err: {e}")
                    self._mark_dead(p, k_idx, C.KEY_COOLDOWN_ERR)
                    last_err = e
            p.dead_until = time.time() + C.PROVIDER_COOLDOWN
        raise LLMError(f"Semua API key & provider gagal: {last_err}")

    async def _call(self, p: ProviderState, key: str, messages: list, image_b64):
        if p.style == "gemini":
            return await self._call_gemini(p, key, messages, image_b64)
        if p.style == "anthropic":
            return await self._call_anthropic(p, key, messages, image_b64)
        return await self._call_openai_style(p, key, messages, image_b64)

    # ── OpenAI-compatible (OpenRouter, Groq, DeepSeek, dst) ───────
    async def _call_openai_style(self, p, key, messages, image_b64):
        msgs = messages
        if image_b64:
            msgs = list(messages)
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i]["role"] == "user":
                    msgs[i] = {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": msgs[i]["content"]},
                            {"type": "image_url",
                             "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                        ],
                    }
                    break
        payload = {"model": p.model, "messages": msgs, "temperature": 0.8}
        async with self.session.post(
            p.base_url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        ) as r:
            body = await r.json()
            if r.status == 429:
                raise _RateLimit(str(body)[:200])
            if r.status in (401, 403):
                raise _AuthError(str(body)[:200])
            if r.status >= 400:
                raise RuntimeError(f"{p.name} http {r.status}: {str(body)[:200]}")
            msg = body["choices"][0].get("message", {})
            content = msg.get("content") or ""
            if not content.strip():
                # beberapa provider taruh jawaban di reasoning_content
                content = msg.get("reasoning_content") or ""
            if not content.strip():
                raise RuntimeError(f"{p.name} balasan kosong")
            return content

    # ── Google Gemini ─────────────────────────────────────────────
    async def _call_gemini(self, p, key, messages, image_b64):
        sys_txt = " ".join(m["content"] for m in messages if m["role"] == "system")
        contents = []
        for m in messages:
            if m["role"] == "system":
                continue
            parts = [{"text": m["content"]}]
            if image_b64 and m["role"] == "user" and m is messages[-1]:
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})
            contents.append({"role": "user" if m["role"] == "user" else "model",
                             "parts": parts})
        payload = {"contents": contents,
                   "systemInstruction": {"parts": [{"text": sys_txt}]}}
        url = f"{p.base_url}/{p.model}:generateContent?key={key}"
        async with self.session.post(url, json=payload) as r:
            body = await r.json()
            if r.status == 429:
                raise _RateLimit("gemini rate limit")
            if r.status in (401, 403):
                raise _AuthError(str(body)[:200])
            if r.status >= 400:
                raise RuntimeError(f"{p.name} http {r.status}: {str(body)[:200]}")
            return body["candidates"][0]["content"]["parts"][0]["text"]

    # ── Anthropic Claude ──────────────────────────────────────────
    async def _call_anthropic(self, p, key, messages, image_b64):
        sys_txt = " ".join(m["content"] for m in messages if m["role"] == "system")
        msgs = []
        for m in messages:
            if m["role"] == "system":
                continue
            content = m["content"]
            if image_b64 and m["role"] == "user" and m is messages[-1]:
                content = [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/jpeg",
                                "data": image_b64}},
                    {"type": "text", "text": m["content"]},
                ]
            msgs.append({"role": "user" if m["role"] == "user" else "assistant",
                         "content": content})
        payload = {"model": p.model, "max_tokens": 3000, "messages": msgs,
                   "system": sys_txt}
        async with self.session.post(
            p.base_url,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            json=payload,
        ) as r:
            body = await r.json()
            if r.status == 429:
                raise _RateLimit("anthropic rate limit")
            if r.status in (401, 403):
                raise _AuthError(str(body)[:200])
            if r.status >= 400:
                raise RuntimeError(f"{p.name} http {r.status}: {str(body)[:200]}")
            return body["content"][0]["text"]


    # ── STT: transkripsi audio memakai SEMUA provider/key yang ada ──
    async def transcribe(self, audio: bytes, filename: str = "voice.ogg",
                         language: str = "id") -> str:
        """Coba endpoint /audio/transcriptions di tiap provider/key.
        Return teks atau '' kalau tak ada yang mendukung."""
        # daftar model yang umum tersedia di gateway multi-model
        models = ["whisper-large-v3", "whisper-large-v3-turbo",
                  "whisper-1", "whisper", "speech-to-text", "auto"]
        total = len(self.providers)
        for attempt in range(total):
            p = self.providers[(self.p_idx + attempt) % total]
            # endpoint transkripsi = base_url tanpa /chat/completions
            base = p.base_url.replace("/chat/completions", "") \
                .replace("/v1/chat/completions", "/v1")
            if not base.endswith("/v1") and "/v1" not in base:
                base = base.rstrip("/") + "/v1"
            url = base.rstrip("/") + "/audio/transcriptions"
            for k_idx, key in enumerate(p.keys):
                for model in models:
                    try:
                        form = aiohttp.FormData()
                        form.add_field("file", audio, filename=filename,
                                       content_type="audio/ogg")
                        form.add_field("model", model)
                        form.add_field("language", language)
                        async with self.session.post(
                                url, data=form,
                                headers={"Authorization": f"Bearer {key}"},
                                timeout=aiohttp.ClientTimeout(total=60)) as r:
                            if r.status == 200:
                                d = await r.json()
                                txt = (d.get("text") or "").strip()
                                if txt:
                                    log.info(f"STT ok via {p.name} "
                                             f"({model})")
                                    return txt
                            elif r.status in (401, 403):
                                break   # key invalid → key berikutnya
                    except Exception as e:
                        log.debug(f"stt {p.name}/{model} err: {e}")
        return ""
