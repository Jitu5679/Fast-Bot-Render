import os
import re
import asyncio
import subprocess
import logging
import threading
import base64
import ssl
import time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import subprocess
logger = logging.getLogger(__name__)

# ==================== CONFIG ====================
API_ID = 1888747
API_HASH = "0d707e8ae15254b1453c614bf3026c32"
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8834527785:AAHRKC83GdyVErpwplApSNQELko0hHKiQKw')
ADMIN_CHAT_ID = 5136226069

os.makedirs("downloads", exist_ok=True)

# ==================== CLIENTS ====================
bot = telebot.TeleBot(BOT_TOKEN)
# Pyrogram removed, using Telethon now

user_states = {}

# ==================== PYROGRAM BACKGROUND LOOP ====================
# Pyrogram runs in its own asyncio loop in a daemon thread.
# It starts ONCE and stays connected forever.
# We upload files by submitting coroutines to this loop.

import asyncio
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
import time

_bg_loop = asyncio.new_event_loop()
_tele_ready = threading.Event()

# Use Telethon instead of Pyrogram
API_ID = 1888747
API_HASH = "0d707e8ae15254b1453c614bf3026c32"
tele_client = TelegramClient('bot_telethon_session', API_ID, API_HASH)

async def _start_telethon():
    await tele_client.start(bot_token=BOT_TOKEN)
    logger.info("✅ Telethon MTProto client started and ready!")

def _bg_loop_thread():
    asyncio.set_event_loop(_bg_loop)
    _bg_loop.run_until_complete(_start_telethon())
    _tele_ready.set()
    _bg_loop.run_forever()

threading.Thread(target=_bg_loop_thread, daemon=True).start()

async def _telethon_upload_with_progress(chat_id, file_path, caption):
    start_time = time.time()
    last_update_time = [time.time()]
    
    prog_msg = await tele_client.send_message(chat_id, f"⬆️ Uploading: {caption}\nProgress: 0%")
    
    async def progress(current, total):
        now = time.time()
        if now - last_update_time[0] > 3.0:
            last_update_time[0] = now
            perc = current * 100 / total
            elapsed = now - start_time
            speed = current / elapsed if elapsed > 0 else 0
            speed_mb = speed / (1024 * 1024)
            eta = (total - current) / speed if speed > 0 else 0
            
            bar_len = 10
            filled = int(bar_len * current / total)
            bar = "🟩" * filled + "⬜" * (bar_len - filled)
            
            text = (
                f"╭──⌯═════𝐔𝐩𝐥𝐨𝐚𝐝𝐢𝐧𝐠══════⌯──╮\n"
                f"├⚡ {bar}\n"
                f"├⚙️ Progress ➤ {perc:.1f}%\n"
                f"├🚀 Speed ➤ {speed_mb:.1f} MB/s\n"
                f"├🧲 Size ➤ {total/(1024*1024):.1f} MB\n"
                f"├🕑 ETA ➤ {int(eta)}s\n"
                f"╰─═══✨🦋Bot🦋✨═══─╯"
            )
            # Create a task to edit the message so we don't block chunk uploading
            import asyncio
            async def do_edit():
                try:
                    await tele_client.edit_message(chat_id, prog_msg.id, text)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        pass
            asyncio.create_task(do_edit())

    try:
        is_video = file_path.lower().endswith('.mp4') or file_path.lower().endswith('.mkv')
        dur = 0
        thumb_path = None
        attributes = []
        
        if is_video:
            # Try to extract duration
            try:
                import subprocess
                res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path], capture_output=True, text=True, timeout=10)
                dur = int(float(res.stdout.strip()))
            except Exception:
                dur = 0
                
            attributes.append(DocumentAttributeVideo(duration=dur, w=1280, h=720, supports_streaming=True))
            
            # Extract thumbnail
            thumb_path = f"{file_path}.jpg"
            try:
                import os
                subprocess.run(["ffmpeg", "-y", "-i", file_path, "-ss", "00:00:10", "-vframes", "1", thumb_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
                if not os.path.exists(thumb_path):
                    thumb_path = None
            except Exception:
                thumb_path = None
                
        # Use FastTelethon to upload
        import fast_telethon
        logger.info(f"Uploading via fast_telethon: {file_path}")
        uploaded_file = await fast_telethon.upload_file(tele_client, file_path, progress_callback=progress)
        
        doc = await tele_client.send_file(
            chat_id, 
            uploaded_file, 
            caption=caption,
            thumb=thumb_path,
            attributes=attributes if attributes else None,
            supports_streaming=True if is_video else False
        )
            
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
            
    except Exception as e:
        logger.error(f"Telethon upload error: {e}")
        raise e
    
    try:
        await tele_client.delete_messages(chat_id, [prog_msg.id])
    except Exception:
        pass
        
    return doc

def telethon_upload(chat_id, file_path, caption=""):
    """Upload a file via Telethon MTProto (up to 2GB). Blocks the calling thread until done."""
    if not _tele_ready.wait(timeout=60):
        raise RuntimeError("Telethon client failed to start within 60s")
    future = asyncio.run_coroutine_threadsafe(
        _telethon_upload_with_progress(chat_id, file_path, caption),
        _bg_loop
    )
    return future.result(timeout=1800)  # 30 min max for very large files


# ==================== CRYPTO HELPERS ====================
APPX_KEY = '638udh3829162018'
APPX_IV = b'fedcba9876543210'

MKV_EBML_HEADER = bytes([
    0x1a, 0x45, 0xdf, 0xa3, 0x9b, 0x42, 0x86, 0x81, 0x01, 0x42, 0xf7, 0x81, 0x01,
    0x42, 0xf2, 0x81, 0x04, 0x42, 0xf3, 0x81, 0x08, 0x42, 0x82, 0x88,
    0x6d, 0x61, 0x74, 0x72, 0x6f, 0x73, 0x6b, 0x61,
])

def decrypt_appx_link(encrypted_path):
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    try:
        parts = encrypted_path.split(':')
        ct = base64.b64decode(parts[0])
        iv = base64.b64decode(parts[1]) if len(parts) > 1 else APPX_IV
        cipher = AES.new(APPX_KEY.encode(), AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), AES.block_size).decode('utf-8')
    except Exception:
        return ""

def download_encrypted_mkv(url, out_path):
    """Download encrypted MKV and fix the header. Uses cloudscraper to bypass 403."""
    import cloudscraper
    
    scraper = cloudscraper.create_scraper(browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    })
    
    headers = {
        'Referer': 'https://player.classx.co.in/',
        'Origin': 'https://player.classx.co.in'
    }
    
    r = scraper.get(url, headers=headers, timeout=180, stream=True)
    r.raise_for_status()
    
    raw = r.content
    fixed = raw if len(raw) < 32 else (MKV_EBML_HEADER + raw[32:])
    
    with open(out_path, 'wb') as f:
        f.write(fixed)
        
    return out_path


# ==================== KEYBOARD ====================
def get_platform_keyboard():
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("Adda247", callback_data="plat_adda247"),
        InlineKeyboardButton("AppX", callback_data="plat_appx"),
        InlineKeyboardButton("ClassPlus", callback_data="plat_classplus")
    )
    kb.row(
        InlineKeyboardButton("Graphy", callback_data="plat_graphy"),
        InlineKeyboardButton("IAS Hub", callback_data="plat_iashub"),
        InlineKeyboardButton("Khan GS", callback_data="plat_khangs")
    )
    kb.row(
        InlineKeyboardButton("LeanPrep", callback_data="plat_leanprep"),
        InlineKeyboardButton("OliveBoard", callback_data="plat_oliveboard"),
        InlineKeyboardButton("Physics Wallah", callback_data="plat_pw")
    )
    kb.row(
        InlineKeyboardButton("StudyIQ", callback_data="plat_studyiq"),
        InlineKeyboardButton("Tarun Grover", callback_data="plat_tarun"),
        InlineKeyboardButton("TestBook", callback_data="plat_testbook")
    )
    kb.row(
        InlineKeyboardButton("TopRankers", callback_data="plat_toprankers"),
        InlineKeyboardButton("Utkarsh", callback_data="plat_utkarsh"),
        InlineKeyboardButton("Law Prep", callback_data="plat_lawprep")
    )
    kb.row(
        InlineKeyboardButton("Virtuous", callback_data="plat_virtuous"),
        InlineKeyboardButton("TLS", callback_data="plat_tls")
    )
    kb.row(InlineKeyboardButton("Bot Plans", callback_data="bot_plans"))
    kb.row(InlineKeyboardButton("Without ID", callback_data="without_id"))
    kb.row(InlineKeyboardButton("Developer", callback_data="developer"))
    return kb


# ==================== TELEBOT HANDLERS ====================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "⚡ **Select Platform**\n\nChoose an option below",
        reply_markup=get_platform_keyboard(),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('plat_'))
def cb_platform(call):
    platform = call.data.replace('plat_', '')
    chat_id = call.message.chat.id
    user_states[chat_id] = {'platform': platform, 'state': 'WAITING_FOR_TOKEN'}
    bot.send_message(chat_id, f"You selected **{platform.upper()}**.\n\nPlease send your authorization token/credentials.", parse_mode="Markdown")
    try: bot.answer_callback_query(call.id)
    except: pass

@bot.message_handler(func=lambda m: m.chat.id in user_states, content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    us = user_states.get(chat_id)
    if not us:
        return

    state = us.get('state')
    platform = us.get('platform')

    if state == 'WAITING_FOR_TOKEN':
        us['token'] = message.text.strip()
        us['state'] = 'WAITING_FOR_BATCH'
        bot.send_message(chat_id, "✅ Token received. Now send the batch ID.")

    elif state == 'WAITING_FOR_BATCH':
        batch_id = message.text.strip()
        bot.send_message(chat_id, f"🔄 Extracting data for batch {batch_id}...")
        token_str = us['token']
        
        try:
            if platform == 'appx':
                import appx_api
                if '*' in token_str:
                    parts = token_str.split('*')
                    if len(parts) >= 3:
                        base_url, email, password = parts[0], parts[1], parts[2]
                        bot.send_message(chat_id, "🔐 Logging into AppX...")
                        login_res = appx_api.appx_login(base_url, email, password)
                        if login_res.get('success'):
                            data_obj = login_res['data']
                            token = data_obj.get('token') or data_obj.get('auth_token')
                            user_id = data_obj.get('userid') or data_obj.get('id')
                        else:
                            raise Exception(f"Login failed: {login_res.get('error')}")
                    else:
                        raise Exception("Invalid AppX credential format. Expected: base_url*email*password")
                else:
                    # Token is direct authorization token, but we still need user_id and base_url. 
                    # Assuming format base_url*token*userid
                    parts = token_str.split('*')
                    if len(parts) == 3:
                        base_url, token, user_id = parts[0], parts[1], parts[2]
                    else:
                        raise Exception("If using direct token, format must be base_url*token*userid")

                bot.send_message(chat_id, "⏳ Fetching folders and links...")
                links = appx_api.extract_batch_links(base_url, token, user_id, batch_id, bot_instance=bot, chat_id=chat_id)
                
            elif platform == 'classplus':
                # Similar logic for Classplus would go here (dummy for now)
                raise Exception("Classplus extraction not fully implemented yet in the new flow.")
            else:
                raise Exception("Platform extraction not fully implemented yet.")
                
            if not links:
                bot.send_message(chat_id, "❌ No links found or failed to extract.")
                user_states.pop(chat_id, None)
                return

            bot.send_message(chat_id, f"🎉 Extraction complete! Generating TXT file...")
            
            # Write to TXT file and send to user
            txt_filename = f"Batch_{batch_id}_Links.txt"
            with open(txt_filename, "w", encoding="utf-8") as f:
                f.write(f"--- Extracted Links for Batch {batch_id} ---\n\n")
                for link in links:
                    f.write(f"{link}\n")
                    
            with open(txt_filename, "rb") as f:
                bot.send_document(chat_id, f, caption=f"🎉 Extraction complete! Here are all your decrypted links for Batch {batch_id}.")
                
            import os
            os.remove(txt_filename)

        except Exception as e:
            bot.send_message(chat_id, f"❌ Error during extraction: {e}")
            import traceback
            traceback.print_exc()
            
        user_states.pop(chat_id, None)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    if not message.document.file_name.endswith('.txt'):
        bot.send_message(chat_id, "⚠️ Please send a `.txt` file containing links.")
        return

    bot.send_message(chat_id, "⏳ Downloading your TXT file...")

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)

        file_path = f"downloads/{chat_id}_{int(time.time())}_{message.document.file_name}"
        with open(file_path, 'wb') as f:
            f.write(downloaded)

        bot.send_message(chat_id, "✅ TXT file received! Starting download & upload. This may take a while...")

        # Launch worker thread — all blocking I/O happens here, NOT in the asyncio loop
        t = threading.Thread(target=process_txt_worker, args=(chat_id, file_path), daemon=True)
        t.start()

    except Exception as e:
        bot.send_message(chat_id, f"❌ Failed to download TXT: {e}")


# ==================== TXT PROCESSING WORKER (runs in its own thread) ====================
def process_txt_worker(chat_id, file_path):
    """
    Process links from a .txt file. Runs in a background thread.
    - Downloads are synchronous (subprocess / requests) — safe to block here.
    - Uploads go through pyrogram_upload() which submits to the bg_loop.
    - Status messages use Telebot (synchronous, thread-safe).
    """
    total_ok = 0
    total_err = 0

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()

        current_title = "Unknown"

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # --- Link line ---
            if line.startswith("↳ Video") or line.startswith("↳ PDF"):
                parts = line.split(": ", 1)
                if len(parts) < 2:
                    continue
                link = parts[1].strip()
                is_pdf = line.startswith("↳ PDF")

                clean = re.sub(r'[\\/*?:"<>|]', "", current_title).strip() or f"file_{total_ok}"
                out_path = None

                try:
                    if is_pdf:
                        # --- PDF ---
                        out_path = f"downloads/{clean}.pdf"
                        if not link.startswith("http"):
                            dec = decrypt_appx_link(link)
                            if dec and dec.startswith("http"):
                                link = dec
                            else:
                                bot.send_message(chat_id, f"⚠️ Skipping (encrypted): {current_title}")
                                continue

                        bot.send_message(chat_id, f"⬇️ [{total_ok+total_err+1}] PDF: {current_title}")
                        # -f flag forces curl to return error on 403/404, preventing corrupt PDF saving
                        subprocess.run(["curl", "-s", "-f", "-L", "-o", out_path, link], check=True, timeout=120)

                        # Validate: if curl downloaded an HTML error page, skip it
                        if os.path.exists(out_path):
                            if os.path.getsize(out_path) < 100:
                                os.remove(out_path)
                                raise Exception("Downloaded PDF is too small (likely corrupt).")
                            with open(out_path, 'rb') as chk:
                                head = chk.read(20)
                            if b'<' in head or b'{"error' in head:
                                os.remove(out_path)
                                raise Exception("PDF link returned error page.")

                    elif "encrypted.mkv" in link:
                        # --- Encrypted MKV ---
                        # Save as .mp4 so Telegram recognizes it as a streamable video natively
                        out_path = f"downloads/{clean}.mp4"
                        bot.send_message(chat_id, f"⬇️🔓 [{total_ok+total_err+1}] Decrypting: {current_title}")
                        out_path = download_encrypted_mkv(link, out_path)

                    else:
                        # --- Normal video (yt-dlp) ---
                        out_path = f"downloads/{clean}.mp4"
                        bot.send_message(chat_id, f"⬇️ [{total_ok+total_err+1}] Video: {current_title}")
                        subprocess.run([
                            "yt-dlp",
                            "--no-warnings",
                            "--add-header", "Referer:https://player.classx.co.in/",
                            "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                            "-o", out_path, link
                        ], check=True, timeout=600)

                    # --- Upload ---
                    if out_path and os.path.exists(out_path):
                        fsize = os.path.getsize(out_path)
                        if fsize > 0:
                            mb = fsize / (1024 * 1024)
                            bot.send_message(chat_id, f"⬆️ Uploading: {current_title} ({mb:.1f} MB)")
                            telethon_upload(chat_id, out_path, caption=f"**{current_title}**")
                            total_ok += 1
                        else:
                            bot.send_message(chat_id, f"⚠️ Empty file skipped: {current_title}")
                        os.remove(out_path)

                except Exception as e:
                    total_err += 1
                    bot.send_message(chat_id, f"❌ Error [{current_title}]: {e}")
                    logger.error(f"Error processing {current_title}: {e}", exc_info=True)
                    if out_path and os.path.exists(out_path):
                        os.remove(out_path)

            # --- Title line ---
            elif not line.startswith("---") and not line.startswith("BATCH ID") and not line.startswith("↳"):
                current_title = line

        bot.send_message(chat_id, f"✅ **All done!**\n\n📥 Uploaded: {total_ok}\n❌ Errors: {total_err}", parse_mode="Markdown")

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        bot.send_message(chat_id, f"❌ Fatal processing error:\n\n`{err[-3500:]}`", parse_mode="Markdown")
        logger.error(f"FATAL: {err}")

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# ==================== MAIN ====================
if __name__ == "__main__":
    # Wait for Telethon to be ready before accepting messages
    logger.info("Waiting for Telethon to connect...")
    _tele_ready.wait(timeout=30)

    try:
        logger.info("🤖 Bot is live! Polling for messages...")
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        import traceback, requests
        err = traceback.format_exc()
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT_ID, "text": f"❌ FATAL CRASH:\n\n`{err[-4000:]}`", "parse_mode": "Markdown"}
        )
        raise
