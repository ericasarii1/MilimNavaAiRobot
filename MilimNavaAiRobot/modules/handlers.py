# ══════════════════════════════════════════════════════════════════
#   HANDLERS — semua command & message handler (ala SaitamaRobot,
#   module-level decorators, auto-loaded via __main__)
# ══════════════════════════════════════════════════════════════════

import re
import time
import asyncio
import logging
import traceback

from pyrogram import filters, enums
from pyrogram.types import Message, ChatMemberUpdated
from pyrogram.errors import FloodWait

from MilimNavaAiRobot import C, app, db, llm, memory, state, NAMES_RE, CMD_RE
from MilimNavaAiRobot.modules import prompts as P
from MilimNavaAiRobot.modules.ai import LLMError
from MilimNavaAiRobot.modules.helpers import (should_respond, now_str,
                                              humanize_delta, AntiSpam,
                                              Batcher, Thinker)
from MilimNavaAiRobot.modules.media import read_media

log = logging.getLogger("milim.handlers")

_handled = {}   # message_id -> True (command sudah diproses)
antispam = AntiSpam()
batcher = Batcher()
_last_seen = {}     # chat_id -> ts (anti spam revive, fitur 18)


def mark_active(chat_id: int):
    _last_seen[chat_id] = time.time()


def was_idle(chat_id: int, threshold_min: int = 30) -> bool:
    return (time.time() - _last_seen.get(chat_id, 0)) > threshold_min * 60


# ══════════════════════════════════════════════════════════════════
# AI CORE
# ══════════════════════════════════════════════════════════════════

async def ai_respond(client, message: Message, user_text: str,
                     media_b64=None, media_desc="") -> str:
    chat, user = message.chat, message.from_user
    st = await state.get(chat.id)
    conv = st["conv"]

    system = (P.PROMPTS[conv].format(owner_id=C.OWNER_ID) +
              f"\n\nINFORMASI WAKTU SAAT INI: {now_str()}." +
              f"\nUSER ID Telegram penanya: {user.id}. Nama: {user.first_name}.")

    msgs = [{"role": "system", "content": system}]

    # thread grup utuh (fitur 33)
    if chat.type != enums.ChatType.PRIVATE:
        for g in await memory.get_group(chat.id):
            who = g.get("speaker", "?")
            ts = humanize_delta(time.time() - g.get("ts", time.time()))
            msgs.append({"role": g.get("role", "user"),
                         "content": f"[{who}, {ts}]: {g['content']}"})

    # riwayat personal user (fitur 7, 22)
    for h in await memory.get(chat.id, user.id):
        age = humanize_delta(time.time() - h.get("ts", time.time()))
        content = h["content"] if age == "baru saja" else f"{h['content']} ({age})"
        msgs.append({"role": h["role"], "content": content})

    final_text = user_text
    if media_desc:
        final_text = f"{user_text}\n\n{media_desc}" if user_text else media_desc
    msgs.append({"role": "user", "content": final_text or "(media tanpa teks)"})

    return await llm.chat(msgs, image_b64=media_b64)


# ══════════════════════════════════════════════════════════════════
# /start & /help (fitur 24, 17)
# ══════════════════════════════════════════════════════════════════

@app.on_message(filters.command(["start", "help"]) & filters.private)
async def cmd_start(client, message: Message):
    st = await state.get(message.chat.id)
    await message.reply_text(P.START_TEXT.format(status=P.status_text(st)),
                             quote=True)
    mark_active(message.chat.id)


@app.on_message(filters.command(["status"]))
async def cmd_status(client, message: Message):
    st = await state.get(message.chat.id)
    await message.reply_text(P.status_text(st), quote=True)


# ══════════════════════════════════════════════════════════════════
# COMMAND HANDLER tanpa '/' (fitur 3, 4, 13)
# ══════════════════════════════════════════════════════════════════

@app.on_message(filters.group | filters.private, group=1)
async def handle_commands(client, message: Message):
    if not message.text and not message.caption:
        return
    if message.from_user and message.from_user.is_bot:
        return

    raw = (message.text or message.caption or "").strip()
    m = CMD_RE.match(raw)
    if not m:
        return
    cmd = m.group(2).strip().lower()
    chat_id = message.chat.id
    st = await state.get(chat_id)

    if cmd in ("mode formal", "formal"):
        await state.set(chat_id, conv="formal")
        await message.reply_text(P.mode_switch_text("formal"), quote=True)
    elif cmd in ("mode santai", "santai"):
        await state.set(chat_id, conv="santai")
        await message.reply_text(P.mode_switch_text("santai"), quote=True)
    elif cmd in ("chatbot on", "chatbot nyala"):
        await state.set(chat_id, chatbot="on")
        await message.reply_text(P.chatbot_switch_text("on", st["conv"]), quote=True)
    elif cmd in ("chatbot off", "chatbot mati"):
        await state.set(chat_id, chatbot="off")
        await message.reply_text(P.chatbot_switch_text("off", st["conv"]), quote=True)
    elif cmd in ("chatbot smart", "chatbot pintar"):
        await state.set(chat_id, chatbot="smart")
        await message.reply_text(P.chatbot_switch_text("smart", st["conv"]), quote=True)
    elif cmd == "diam":
        await state.set(chat_id, speaking=False)
        await message.reply_text(P.speaking_switch_text(False, st["conv"]), quote=True)
    elif cmd == "bicara":
        await state.set(chat_id, speaking=True)
        await message.reply_text(P.speaking_switch_text(True, st["conv"]), quote=True)
    elif cmd == "status":
        await message.reply_text(P.status_text(st), quote=True)
    elif cmd in ("clear database", "clear db", "hapus ingatan", "lupa semua"):
        if message.from_user.id == C.OWNER_ID:
            await db.clear_all()
            st = await state.get(chat_id)
            await message.reply_text(P.clear_done_text(st["conv"]), quote=True)
        else:
            try:
                await message.delete()
            except Exception:
                pass
    else:
        return   # bukan command → biar main handler proses
    mark_active(chat_id)
    # tandai pesan ini sudah diproses sebagai command agar
    # handle_message (group=2) mengabaikannya
    _handled[message.id] = True


# ══════════════════════════════════════════════════════════════════
# MAIN MESSAGE HANDLER (fitur 5, 6, 7, 8, 18, 21, 31, 38-41)
# ══════════════════════════════════════════════════════════════════

@app.on_message(filters.group | filters.private, group=2)
async def handle_message(client, message: Message):
    if message.id in _handled:
        return
    if not message.from_user or message.from_user.is_bot:
        return

    chat, user = message.chat, message.from_user
    text = (message.text or message.caption or "").strip()
    chat_id, user_id = chat.id, user.id
    st = await state.get(chat_id)
    is_private = chat.type == enums.ChatType.PRIVATE

    # selalu baca media + simpan memory walau mode diam (fitur 7, 8)
    media = await read_media(client, message)
    entry = text or media["desc"] or "(media)"
    if is_private:
        await memory.add(chat_id, user_id, "user", entry)
    else:
        await memory.add_group(chat_id, user.first_name, "user", entry)
        await memory.add(chat_id, user_id, "user", entry)

    respond, reason = should_respond(st, text, user_id)

    # media & smart mode (fitur 39)
    if not respond and (media["b64"] or media["desc"]) \
            and st["chatbot"] == "smart" and st["speaking"]:
        respond, reason = True, "smart-media"

    if not respond:
        return

    # antispam
    if not await antispam.check(user_id):
        return

    # batch merge spam (fitur 38)
    merged = await batcher.push(chat_id, user_id, text, media["desc"])
    if merged is False:
        return

    # anti spam revive (fitur 18)
    if was_idle(chat_id) and not is_private:
        await message.reply_text(P.revive_text(st["conv"]), quote=True)
        mark_active(chat_id)
        return

    # thinking indicator (mode smart saja — fitur 41)
    thinker = Thinker()
    think_msg = await thinker.start(client, chat_id,
                                    smart=(st["chatbot"] == "smart"))
    try:
        await client.send_chat_action(chat_id, "typing")
    except Exception:
        pass

    try:
        answer = await ai_respond(client, message, merged,
                                  media_b64=media["b64"],
                                  media_desc=media["desc"])
    except LLMError:
        await message.reply_text(P.error_text(st["conv"]), quote=True)
        await thinker.stop(client, think_msg)
        return
    except Exception as e:
        log.error(f"ai_respond err: {e}\n{traceback.format_exc()}")
        await message.reply_text(P.error_text(st["conv"]), quote=True)
        await thinker.stop(client, think_msg)
        return
    finally:
        try:
            await client.send_chat_action(chat_id, enums.ChatAction.CANCEL)
        except Exception:
            pass

    await thinker.stop(client, think_msg)

    # simpan jawaban
    if is_private:
        await memory.add(chat_id, user_id, "assistant", answer)
    else:
        await memory.add_group(chat_id, "Milim", "assistant", answer)
        await memory.add(chat_id, user_id, "assistant", answer)

    mark_active(chat_id)

    try:
        await message.reply_text(answer, quote=is_private or bool(message.reply_to_message))
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.reply_text(answer)
    except Exception as e:
        log.error(f"reply err: {e}")


# ══════════════════════════════════════════════════════════════════
# GROUP EVENTS (fitur 14) — bot add / member join / member left
# ══════════════════════════════════════════════════════════════════

async def _event_respond(chat_id: int, event_desc: str):
    st = await state.get(chat_id)
    if st["chatbot"] != "on" or not st["speaking"]:
        return
    msgs = [
        {"role": "system",
         "content": P.PROMPTS[st["conv"]].format(owner_id=C.OWNER_ID) +
                    f"\n\nINFORMASI WAKTU SAAT INI: {now_str()}."},
        {"role": "user", "content": event_desc},
    ]
    try:
        answer = await llm.chat(msgs)
        await app.send_message(chat_id, answer)
    except Exception as e:
        log.debug(f"event_respond err: {e}")


@app.on_chat_member_updated()
async def on_member_event(client, update: ChatMemberUpdated):
    try:
        old, new = update.old_chat_member, update.new_chat_member
        chat_id = update.chat.id
        if not new or not new.user:
            return
        st = await state.get(chat_id)

        if new.user.is_self and (not old or old.status == "left"):
            if st["conv"] == "formal":
                desc = ("Anda baru saja ditambahkan ke sebuah grup Telegram. "
                        "Sapa anggota grup secara formal dan profesional, "
                        "perkenalkan diri sebagai Milim Nava asisten AI, dan "
                        "jelaskan singkat bahwa Anda siap membantu.")
            else:
                desc = ("Lo barusan di-add ke grup. Sapa anggota grup pake "
                        "gaya santai gaul, perkenalkan diri sebagai Milim "
                        "Nava, bilang siap bantu apa aja.")
            await _event_respond(chat_id, desc)
            return

        if not new.user.is_self and (not old or old.status in ("left", "kicked")):
            u = new.user
            name = f"{u.first_name} {u.last_name or ''}".strip()
            if st["conv"] == "formal":
                desc = (f"Seorang anggota baru bergabung ke grup: {name}. "
                        "Berikan sambutan singkat, formal, dan ramah.")
            else:
                desc = f"Ada yang baru join nih: {name}. Sambutin dia pake gaya santai dan asik!"
            await _event_respond(chat_id, desc)
            return

        if old and not old.user.is_self and new.status in ("left", "kicked"):
            u = old.user
            name = f"{u.first_name} {u.last_name or ''}".strip()
            if st["conv"] == "formal":
                desc = (f"Seorang anggota meninggalkan grup: {name}. "
                        "Berikan ucapan perpisahan singkat dan formal.")
            else:
                desc = f"Yah, ada yang keluar grup: {name}. Ucapkan selamat tinggal dengan santai."
            await _event_respond(chat_id, desc)
    except Exception as e:
        log.debug(f"member_event err: {e}")
