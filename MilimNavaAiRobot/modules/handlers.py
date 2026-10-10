# ══════════════════════════════════════════════════════════════════
#   HANDLERS — semua command & message handler (ala SaitamaRobot,
#   module-level decorators, auto-loaded via __main__)
# ══════════════════════════════════════════════════════════════════

import re
import random
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
from MilimNavaAiRobot.modules.helpers import (normalize_output,
                                              should_respond, now_str,
                                              humanize_delta, AntiSpam,
                                              Batcher, Thinker, TypingLoop, strip_meta_prefix)
from MilimNavaAiRobot.modules.media import read_media
from MilimNavaAiRobot.modules import web_search as WS
from MilimNavaAiRobot.modules import long_term_memory as LTM
from MilimNavaAiRobot.modules import persona as PR
from MilimNavaAiRobot.modules import smart_tools as ST
from MilimNavaAiRobot.modules import smart_enhance as SE
from MilimNavaAiRobot.modules import media_gen as MG
from MilimNavaAiRobot.modules import agent as AG
from MilimNavaAiRobot.modules import lang as LG
from MilimNavaAiRobot.modules import group_stats as GS
from MilimNavaAiRobot.modules import anime as AN
from MilimNavaAiRobot.modules import catchup as CU
from MilimNavaAiRobot.modules import human_touch as HT
from MilimNavaAiRobot.modules import lifedata as LD
from MilimNavaAiRobot.modules import sticker_reply as SR
from MilimNavaAiRobot.modules import cross_chat as CC
from MilimNavaAiRobot.modules import brainbox as BB
from MilimNavaAiRobot.modules import reasoning as RS
from MilimNavaAiRobot.modules import deep_brain as DB2
from MilimNavaAiRobot.modules import media_transcript as MT2

log = logging.getLogger("milim.handlers")

_handled = {}   # message_id -> True (command sudah diproses)
antispam = AntiSpam()
batcher = Batcher()
_last_seen = {}     # chat_id -> ts (anti spam revive, fitur 18)


def mark_active(chat_id: int):
    _last_seen[chat_id] = time.time()


# ══════════════════════════════════════════════════════════════════
# AI CORE
# ══════════════════════════════════════════════════════════════════

async def ai_respond(client, message: Message, user_text: str,
                     media_b64=None, media_desc="") -> str:
    chat, user = message.chat, message.from_user
    ai_respond._reasoning = None
    st = await state.get(chat.id)
    conv = st["conv"]

    system = (P.PROMPTS[conv].format(owner_id=C.OWNER_ID) +
              f"\n\nINFORMASI WAKTU SAAT INI: {now_str()}." +
              f"\nUSER ID Telegram penanya: {user.id}. Nama: {user.first_name}." +
              f"\n\nIDENTITAS LAWAN BICARA — PENTING:\n"
              f"- Yang sedang bertanya ke kamu adalah {user.first_name} "
              f"(ID {user.id}). SELALU jawab kepada {user.first_name}.\n"
              f"- Di utas reply / riwayat grup, tiap pesan punya penulis "
              f"berbeda. JANGAN tertukar: kalau {user.first_name} me-reply "
              f"pesan orang lain, itu hanya KONTEKS — penulis pesan itu "
              f"BUKAN yang sedang ngobrol denganmu.\n"
              f"- Alamatkan jawaban sesuai pertanyaan {user.first_name}, "
              f"jangan seakan-akan penulis pesan yang di-reply yang bertanya." +
              "\n\nFORMAT OUTPUT — WAJIB:\n"
              "- Riwayat chat di context diberi tanda seperti (pesan dari X, 5 menit lalu) — itu HANYA metadata utkmu, JANGAN PERNAH menyalin/mengulang format itu di jawaban.\n"
              "- Jawaban langsung isi saja, tanpa prefiks nama/waktu/penanda apa pun.")

    # persona tambahan (dari owner)
    system += PR.persona_prompt(await PR.get_persona())

    # memori jangka panjang
    system += LTM.ltm_prompt(await LTM.get_ltm(chat.id, user.id))

    # sejarah grup (deep brain 1)
    if chat.type != enums.ChatType.PRIVATE:
        try:
            system += DB2.archive_prompt(await DB2.get_archive(chat.id))
        except Exception as e:
            log.debug(f"arch prompt err: {e}")

    # konteks kesenjangan (deep brain 4)
    try:
        _lasth = await memory.get(chat.id, user.id, limit=6)
        fu = await DB2.followup_context(chat.id, user.id, _lasth or [])
        if fu:
            system += fu
    except Exception as e:
        log.debug(f"followup ctx err: {e}")

    # mode perencanaan (deep brain 2)
    if DB2.needs_planning(user_text or ""):
        system += DB2.PLAN_ADDON

    msgs = [{"role": "system", "content": system}]

    # thread grup utuh (fitur 33)
    # PENTING: tag [nama, waktu] hanyalah metadata riwayat — WAJIB
    # diinstruksikan agar tidak pernah disalin ke jawaban.
    if chat.type != enums.ChatType.PRIVATE:
        ghist = await memory.get_group(chat.id)
        for g in ghist:
            who = g.get("speaker", "?")
            ts = humanize_delta(time.time() - g.get("ts", time.time()))
            msgs.append({"role": g.get("role", "user"),
                         "content": f"(pesan dari {who}, {ts}) {g['content']}"})
        # statistik grup sebagai pengetahuan (bukan command — AI selalu tau)
        try:
            stats = GS.build_stats(ghist)
            if stats:
                system += stats
        except Exception as e:
            log.debug(f"gstats err: {e}")

        # anime/manga lookup: data AniList utk topik anime (kemampuan)
        try:
            anime_ctx = await AN.maybe_inject(user_text or "")
            if anime_ctx:
                system += anime_ctx
        except Exception as e:
            log.debug(f"anime err: {e}")

        # brainbox: zona waktu/konversi satuan/analisis kode (kemampuan)
        try:
            bb = BB.maybe_inject(user_text or "")
            if bb:
                system += bb
        except Exception as e:
            log.debug(f"brainbox err: {e}")

        # lifedata: kurs/crypto/jadwal sholat real-time (kemampuan)
        try:
            ld = await LD.maybe_inject(user_text or "")
            if ld:
                system += ld
        except Exception as e:
            log.debug(f"lifedata err: {e}")

        # catch-up: pesan yang lewat saat user tidak aktif (kemampuan)
        try:
            if CU.detect_catchup(user_text or ""):
                cu = CU.build_catchup(ghist, user.first_name)
                if cu:
                    system += cu
        except Exception as e:
            log.debug(f"catchup err: {e}")

        # gaya adaptif per lawan bicara (kemampuan manusiawi)
        try:
            style = HT.style_of_speaker(ghist, user.first_name)
            if style:
                system += style
        except Exception as e:
            log.debug(f"style err: {e}")

    # cross-chat versi aman (hanya DM): "siapa bahas gue di grup?"
    if chat.type == enums.ChatType.PRIVATE and CC.is_cross_question(user_text or ""):
        try:
            import json as _json
            raw = await db.get(f"user_groups:{user.id}")
            arr = _json.loads(raw) if raw else []
            cc = await CC.collect(user_text or "", user.first_name, arr)
            if cc:
                system += cc
        except Exception as e:
            log.debug(f"crosschat err: {e}")

    # riwayat personal user (fitur 7, 22)
    for h in await memory.get(chat.id, user.id):
        age = humanize_delta(time.time() - h.get("ts", time.time()))
        content = h["content"] if age == "baru saja" else f"(info waktu: dikirim {age}) {h['content']}"
        msgs.append({"role": h["role"], "content": content})

    final_text = user_text
    if media_desc:
        final_text = f"{user_text}\n\n{media_desc}" if user_text else media_desc

    # transcript audio/video yang di-reply + minta rangkuman (deep brain 4b)
    try:
        replied_msg = message.reply_to_message
        if replied_msg and (replied_msg.audio or replied_msg.video) \
                and MT2.wants_transcript(user_text or ""):
            tr = await MT2.transcript_media(client, replied_msg, llm)
            if tr:
                system += ("\n\nTRANSKRIP MEDIA YANG DI-REPLY (rangkum "
                           "berdasarkan ini):\n" + tr[:4000])
            else:
                system += ("\n\nCATATAN: user minta isi audio/video "
                           "yang di-reply, tapi transkripsi sedang tidak "
                           "tersedia. Sampaikan dengan jujur dan santai.")
    except Exception as e:
        log.debug(f"mtranscript err: {e}")

    # konteks pesan yang di-reply (fitur reply)
    try:
        replied = message.reply_to_message
        if replied:
            who = replied.from_user.first_name if replied.from_user else "seseorang"
            _rhandle = ""
            if replied.from_user and replied.from_user.username:
                _rhandle = f" (@{replied.from_user.username}, ID {replied.from_user.id})"
            rtxt = (replied.text or replied.caption or "").strip()
            if rtxt:
                final_text = (f"{final_text}\n\n"
                              f"(USER SEDANG MEMBALAS pesan dari {who}{_rhandle}: "
                              f"\"{rtxt[:300]}\")")
    except Exception:
        pass

    # IDENTITAS ASLI user yang di-mention: resolve via API supaya LLM tidak
    # mengarang username/ID. Inject nama+username+ID sebenarnya.
    try:
        _idents = []
        _seen = set()
        _ents = (message.entities or []) + (message.caption_entities or [])
        for _e in _ents:
            _u = getattr(_e, "user", None)
            if _u and _u.id not in _seen:
                _seen.add(_u.id)
                _h = f"@{_u.username}" if _u.username else "(tanpa username)"
                _idents.append(f"{_u.first_name} {_h} ID={_u.id}")
        if _idents:
            final_text = (f"{final_text}\n\n(USER MENTION user berikut — "
                          f"ini identitas ASLI dari Telegram, pakai PERSIS ini "
                          f"kalau mau men-tag: " + "; ".join(_idents) + ")")
    except Exception as e:
        log.debug(f"mention resolve err: {e}")

    # web search real-time untuk pertanyaan yang butuh info terkini
    if user_text:
        try:
            search_ctx = await WS.maybe_search_and_inject(user_text)
            if search_ctx:
                system += search_ctx
        except Exception as e:
            log.debug(f"websearch inject err: {e}")

    # link reader: baca isi halaman yang di-share
    link_ctx = ""
    if user_text:
        try:
            link_ctx = await ST.maybe_read_links(user_text)
            if link_ctx:
                system += link_ctx
        except Exception as e:
            log.debug(f"link read err: {e}")

    # reply chain: utas diskusi utuh (fitur reply berantai)
    try:
        chain = await SE.get_reply_chain(message)
        if chain:
            system += chain
    except Exception as e:
        log.debug(f"reply chain err: {e}")

    # kalkulator presisi
    if user_text:
        try:
            calc = ST.try_calculate(user_text)
            if calc:
                system += ("\n\n" + calc + "\nGunakan angka ini apa adanya, "
                           "jangan hitung ulang sendiri.")
        except Exception as e:
            log.debug(f"calc err: {e}")

    # confidence: jangan ngawur (fitur 3)
    if user_text and len(user_text) > 40:
        system += SE.CONFIDENT_ADDON

    # mood-aware tone (fitur 5)
    if user_text:
        mood = AG.detect_mood(user_text)
        if mood:
            system += AG.mood_tone_addon(mood)
        ai_respond._mood = mood

    # bahasa user (fitur lang)
    if user_text:
        system += LG.language_addon(LG.detect_language(user_text))


    # feedback/koreksi diri (fitur 6)
    if getattr(ai_respond, "_needs_clarify", False):
        system += SE.CLARIFY_INSTRUCTION

    # manifest tools utk agentic mode (agar AI tahu bisa pakai JSON tool)
    if user_text and len(user_text) > 25 and not media_b64:
        system += AG.TOOL_MANIFEST

    msgs[0] = {"role": "system", "content": system}
    msgs.append({"role": "user", "content": final_text or "(media tanpa teks)"})

    # deep think utk pertanyaan kompleks — jangan return awal: tetap lewat
    # alur bawah supaya blok reasoning tampil. Deep think hanya ganti sumber
    # jawaban via flag.
    _deep = False
    try:
        if user_text and ST.is_deep_question(user_text) and st.get("chatbot") != "off":
            _deep = True
    except Exception as e:
        log.debug(f"deep think err: {e}")

    # agentic loop: AI pilih tool sendiri (search/hitung/baca) utk
    # pertanyaan yang butuh eksplorasi; sisanya jawaban langsung
    use_agent = bool(user_text) and len(user_text) > 25 and \
        st.get("chatbot") != "off" and not media_b64
    # reasoning 2-pass (mikir dulu ala model reasoning) — SELALU (semua teks),
    # lalu jawaban final via agentic tool / chat biasa
    # reasoning 2-pass TETAP HIDUP (pass tersembunyi utk kualitas) — tanpa
    # tampilan blok apa pun, seperti perilaku original awal
    ai_respond._reasoning = None
    _pre_answer = None
    if (bool(user_text) or media_desc) and st.get("chatbot") != "off":
        _rt = user_text or (f"(user mengirim media: {media_desc[:200]})"
                            if media_desc else "(media)")
        try:
            _pre_answer, _reasoning = await RS.think(llm, _rt, system, msgs)
            ai_respond._reasoning = _reasoning
        except Exception as e:
            log.debug(f"reasoning err: {e}")
            ai_respond._reasoning = None
    if _deep:
        try:
            answer = await ST.deep_think_answer(llm, msgs)
        except Exception as e:
            log.debug(f"deep think err: {e}")
            answer = None
        if not answer:
            answer = _pre_answer or await llm.chat(msgs, image_b64=media_b64)
    elif use_agent:
        try:
            answer = await AG.agentic_chat(llm, msgs)
        except Exception as e:
            log.debug(f"agent err: {e}")
            answer = _pre_answer or await llm.chat(msgs, image_b64=media_b64)
    else:
        answer = _pre_answer or await llm.chat(msgs, image_b64=media_b64)

    # fact-check otomatis (fitur 1) — hanya utk jawaban panjang berklaim
    try:
        ctx_all = (search_ctx if 'search_ctx' in dir() else "") + link_ctx
        if user_text and len(user_text) > 60 and len(answer) > 150:
            answer = await SE.verify_answer(llm, user_text, answer, ctx_all)
    except Exception as e:
        log.debug(f"factcheck err: {e}")

    # sumber (fitur 2)
    try:
        ctx_all = (search_ctx if 'search_ctx' in dir() else "") + link_ctx
        footer = SE.sources_footer(ctx_all)
        if footer:
            answer += footer
    except Exception as e:
        log.debug(f"sumber err: {e}")

    return answer


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
        await state.set(chat_id, chatbot="on", speaking=True)
        await message.reply_text(P.chatbot_switch_text("on", st["conv"]), quote=True)
    elif cmd in ("chatbot off", "chatbot mati"):
        await state.set(chat_id, chatbot="off")
        await message.reply_text(P.chatbot_switch_text("off", st["conv"]), quote=True)
    elif cmd in ("chatbot smart", "chatbot pintar"):
        await state.set(chat_id, chatbot="smart", speaking=True)
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

async def _error_reply(message, conv: str):
    """Pesan error: di-generate LLM sesuai mode (anti-template), fallback bank."""
    formal = conv == "formal"
    gaya = ("santai/gaul pakai gue/lo, singkat" if not formal
            else "formal/sopan pakai saya/Anda, singkat")
    try:
        out = await llm.chat([
            {"role": "system", "content":
                f"Kamu bot Telegram. Layanan AI-mu sedang gagal merespons "
                f"(gangguan sesaat). Buat SATU kalimat pendek (maks 15 kata) "
                f"yg minta user coba lagi sebentar lagi. Gaya: {gaya}. Maks 1 "
                f"emoji. HANYA kalimatnya."},
            {"role": "user", "content": "buat sekarang"}])
        out = (out or "").strip().strip('"')
        if 4 < len(out) < 150:
            await message.reply_text(out, quote=True)
            return
    except Exception as e:
        log.debug(f"err text gen err: {e}")
    bank = (["Sebentar ya, sistem lagi agak gangguan. Coba lagi deh bentar lagi.",
             "Waduh, otak gue lagi tersendat. Coba ulang dalam semenit ya."]
            if not formal else
            ["Mohon maaf, layanan sedang mengalami gangguan. Silakan coba lagi nanti.",
             "Terjadi kesalahan teknis sesaat. Mohon ulangi beberapa saat lagi."])
    await message.reply_text(random.choice(bank), quote=True)


@app.on_message(filters.group | filters.private, group=2)
async def handle_message(client, message: Message):
    if message.id in _handled:
        return
    if not message.from_user or message.from_user.is_bot:
        return
    # voice/audio: diproses modules/voice.py (group=0) — lewati di sini
    if (message.voice or message.audio) and not getattr(
            message, "_milim_voice_text", None):
        return

    chat, user = message.chat, message.from_user
    # sticker reply: catat stiker yang terlihat; kadang bales pakai stiker
    if message.sticker and message.sticker.file_id:
        try:
            SR.remember(chat_id, message.sticker.file_id)
        except Exception:
            pass

    # voice: transkrip disuntik oleh modules/voice.py
    voice_text = getattr(message, "_milim_voice_text", None)
    text = (voice_text or message.text or message.caption or "").strip()
    chat_id, user_id = chat.id, user.id
    # flag balasan suara
    _voice_reply = False
    if voice_text:
        vr = await db.get(f"voice_reply:{chat_id}")
        _voice_reply = vr == "1"
        await db.delete(f"voice_reply:{chat_id}")
    st = await state.get(chat_id)
    is_private = chat.type == enums.ChatType.PRIVATE

    # selalu baca media + simpan memory walau mode diam (fitur 7, 8)
    media = await read_media(client, message)

    # document reader: PDF/DOCX/XLSX/TXT — ekstrak isi (fitur 2)
    if message.document and AG.is_supported_doc(message):
        try:
            doctext = await AG.read_document(client, message)
            if doctext:
                media["desc"] = (media["desc"] or "") + \
                    f"\n\nISI DOKUMEN '{message.document.file_name}':\n{doctext}"
                if not media.get("b64"):
                    media["b64"] = None
        except Exception as e:
            log.debug(f"doc read err: {e}")
    entry = text or (media["desc"][:400] if media["desc"] else "") or "(media)"
    if is_private:
        await memory.add(chat_id, user_id, "user", entry)
    else:
        await memory.add_group(chat_id, user.first_name, "user", entry)
        await memory.add(chat_id, user_id, "user", entry)
        # cross-chat (aman): catat grup ini di daftar grup milik user
        try:
            raw = await db.get(f"user_groups:{user_id}")
            import json as _json
            arr = _json.loads(raw) if raw else []
            if chat_id not in arr:
                arr.append(chat_id)
                del arr[:-10]
                await db.set(f"user_groups:{user_id}", _json.dumps(arr))
        except Exception as e:
            log.debug(f"ugroups err: {e}")
        # arsip sejarah grup: rangkum berkala (deep brain 1)
        try:
            asyncio.ensure_future(DB2.bump_and_maybe_archive(
                chat_id, llm, memory))
        except Exception as e:
            log.debug(f"garch bump err: {e}")

    respond, reason = should_respond(st, text, user_id)

    # reaction pintar: kadang cukup emoji, tanpa paragraf (fitur 9)
    if not respond and st["speaking"] and st["chatbot"] == "on" \
            and not is_private:
        emo = MG.maybe_should_react(chat_id, text)
        if emo:
            await MG.send_reaction(client, message, emo)
            return

    # reply ke pesan bot = pemicu respon (mode smart & off)
    # sticker reply balik (kemampuan fun): kadang bales stiker dgn stiker
    if not respond and message.sticker and st["speaking"] \
            and st["chatbot"] in ("on", "smart") and not is_private:
        try:
            sid = SR.maybe_reply(chat_id)
            if sid:
                await message.reply_sticker(sid)
                return
        except Exception as e:
            log.debug(f"sticker reply err: {e}")

    if not respond and st["speaking"] and st["chatbot"] in ("smart", "off"):
        replied = message.reply_to_message
        if replied and replied.from_user and replied.from_user.is_bot                 and replied.from_user.id == client.me.id:
            respond, reason = True, "reply-to-bot"
        elif replied and not replied.from_user and replied.text:
            # pesan via-channel/service tanpa from_user dianggap bot
            respond, reason = True, "reply-to-bot"

    # media & smart/off mode — hanya kalau reply ke bot (fitur 39, revisi:
    # sticker/media di smart & off tidak lagi auto-dibalas)
    if not respond and (media["b64"] or media["desc"]
                        or (message.document and AG.is_supported_doc(message))) \
            and st["chatbot"] in ("smart", "off") and st["speaking"]:
        replied_m = message.reply_to_message
        if (replied_m and ((replied_m.from_user and replied_m.from_user.id == client.me.id)
                           or (not replied_m.from_user and replied_m.text))):
            respond, reason = True, "smart-media"

    if not respond:
        return


    # antispam
    if not await antispam.check(user_id):
        return

    # image generation (fitur 7)
    if is_private or st["chatbot"] in ("on",) or reason in ("named", "reply-to-bot"):
        if MG.is_image_request(text):
            handled = await MG.handle_image_request(message, text)
            if handled:
                mark_active(chat_id)
                return

    # youtube summarizer (fitur 8)
    vid = MG.extract_yt_id(text)
    if vid:
        handled = await MG.summarize_youtube(message, text, vid)
        if handled:
            mark_active(chat_id)
            return

    # feedback/koreksi diri (fitur 6): tandai supaya AI minta klarifikasi
    needs_clarify = SE.wants_correction(text)

    # kemampuan manusiawi: rule tanya-balik + kejujuran diri (selalu on)
    try:
        _reply_ctx = bool(message.reply_to_message)
        try:
            _h = (await memory.get(chat_id, user_id, limit=6) if is_private
                  else await memory.get_group(chat_id, limit=6))
            _hlen = len(_h or [])
        except Exception:
            _hlen = 0
        if HT.is_ambiguous(text or "", _reply_ctx, _hlen):
            needs_clarify = True
        system += HT.build_human_rules(_reply_ctx, _hlen)
    except Exception as e:
        log.debug(f"human rules err: {e}")

    # batch merge spam (fitur 38)
    merged = await batcher.push(chat_id, user_id, text, media["desc"])
    if merged is False:
        return

    # typing kontinu — langsung tampil begitu bot mulai memproses
    typing = await TypingLoop().start(client, chat_id)

    # thinking indicator (mode smart saja — fitur 41)
    thinker = Thinker()
    think_msg = await thinker.start(client, chat_id,
                                    smart=(st["chatbot"] == "smart"),
                                    conv=st["conv"], llm=llm)

    try:
        ai_respond._needs_clarify = needs_clarify
        answer = None
        for _attempt in range(3):
            try:
                answer = await ai_respond(client, message, merged,
                                          media_b64=media["b64"],
                                          media_desc=media["desc"])
                break
            except Exception as _e:
                log.debug(f"ai attempt {_attempt+1} gagal: {_e}")
                if _attempt < 2:
                    await asyncio.sleep(1.5 * (_attempt + 1))
        if answer is None:
            raise LLMError("semua percobaan gagal")
        # fact-verify (deep brain 3): klaim faktual dicek ke web
        try:
            answer = await DB2.verify_facts(llm, merged, answer)
        except Exception as e:
            log.debug(f"verify err: {e}")
        # tandai interaksi (deep brain 4)
        try:
            await DB2.mark_conversation(chat_id, user_id)
        except Exception as e:
            log.debug(f"mark conv err: {e}")
        # hygiene ejaan: tampal typo nama & singkatan kasar (jaga gaya)
        try:
            answer = normalize_output(
                answer, formal=(st["conv"] == "formal"))
        except Exception as e:
            log.debug(f"normalize err: {e}")
        # tampilkan reasoning sbg blok markdown (☁️ Reasoning + backtick)
        _plain = answer                     # versi tanpa blok (utk memori/konteks)
        _rp = getattr(ai_respond, "_reasoning", None)
        if _rp:
            try:
                answer = RS.format_answer(answer, _rp)
            except Exception as e:
                log.debug(f"reason fmt err: {e}")
        else:
            _plain = answer
    except LLMError:
        await _error_reply(message, st["conv"])
        await thinker.stop(client, think_msg)
        return
    except Exception as e:
        log.error(f"ai_respond err: {e}\n{traceback.format_exc()}")
        await _error_reply(message, st["conv"])
        await thinker.stop(client, think_msg)
        return
    finally:
        await typing.stop(client, chat_id)

    await thinker.stop(client, think_msg)

    # simpan jawaban TANPA blok reasoning (biar model gak niru pola dobel)
    try:
        _plain = RS.strip_block(answer) if "answer" in dir() else answer
    except Exception:
        _plain = answer
    if is_private:
        await memory.add(chat_id, user_id, "assistant", _plain)
    else:
        await memory.add_group(chat_id, "Milim", "assistant", _plain)
        await memory.add(chat_id, user_id, "assistant", _plain)

    # long-term memory: mungkin trigger ringkasan otomatis
    try:
        await LTM.bump_and_maybe_summarize(chat_id, user_id)
    except Exception as e:
        log.debug(f"ltm bump err: {e}")



    mark_active(chat_id)

    # anti-repetisi (fitur 4): kalau mirip jawaban sebelumnya → minta variasi
    try:
        if SE.is_repetitive(chat_id, answer):
            retry = await llm.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": final_text or "(media)"},
                {"role": "assistant", "content": answer},
                {"role": "user", "content":
                    "Jawabanmu di atas terlalu mirip dengan jawabanmu "
                    "sebelumnya. Tulis ulang dengan kalimat & angle BERBEDA, "
                    "tetap akurat."}])
            if retry:
                answer = retry
    except Exception as e:
        log.debug(f"anti-repeat err: {e}")
    SE.remember_answer(chat_id, answer)

    # bersihkan prefix metadata yang bocor (mis. "(1 jam yang lalu) ...")
    answer = strip_meta_prefix(answer)

    try:
        # SELALU reply (quote) ke pesan user, di grup maupun DM
        if _voice_reply:
            from MilimNavaAiRobot.modules.voice import reply_voice
            await reply_voice(message, answer,
                              formal=(st["conv"] == "formal"),
                              quote=True)
        else:
            _pm = (enums.ParseMode.MARKDOWN
                   if answer.count("```") >= 2 else None)
            # jawaban >4096 dipecah otomatis ke beberapa pesan berurutan
            if len(answer) <= 4000:
                await message.reply_text(answer, quote=True, parse_mode=_pm)
            else:
                parts, cur = [], ""
                for para in answer.split("\n\n"):
                    if cur and len(cur) + len(para) + 2 > 3800:
                        parts.append(cur); cur = para
                    else:
                        cur = (cur + "\n\n" + para) if cur else para
                if cur:
                    parts.append(cur)
                first = True
                for part in parts:
                    _p = _pm if part.count("```") >= 2 else None
                    try:
                        if first:
                            await message.reply_text(part, quote=True, parse_mode=_p)
                            first = False
                        else:
                            await message.reply_text(part, parse_mode=_p)
                            await asyncio.sleep(0.6)
                    except Exception:
                        await message.reply_text(part, quote=first)
                        first = False
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.reply_text(answer)
    except Exception as e:
        # kebanyakan: pesan >4096 (MESSAGE_TOO_LONG) → pangkas rapi, tetap 1 pesan
        log.debug(f"reply long err: {e}")
        try:
            _cut = answer[:3950].rsplit(".", 1)[0].rsplit("\n", 1)[0] + "…"
            await message.reply_text(_cut, quote=True)
        except Exception as e2:
            log.error(f"reply err: {e2}")
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
