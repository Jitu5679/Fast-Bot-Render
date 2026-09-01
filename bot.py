"""
Fast-Bot-Render - Auto OTP Login + Classplus/Concept RNA Extractor
"""
import os
import re
import asyncio
import aiohttp
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Render Web Port Binding
class SimpleServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Live & Running!")

def run_port():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleServer)
    server.serve_forever()

threading.Thread(target=run_port, daemon=True).start()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Config
API_ID = int(os.environ.get("API_ID", "1888747"))
API_HASH = os.environ.get("API_HASH", "0d707e8ae15254b1453c614bf3026c32")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8834527785:AAHRKC83GdyVErpwplApSNQELko0hHKiQKw")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "5136226069"))

os.makedirs("downloads", exist_ok=True)
bot = telebot.TeleBot(BOT_TOKEN)
user_states = {}

HEADERS = {
    "User-Agent": "Mobile-Android",
    "Accept": "application/json, text/plain, */*",
    "region": "IN"
}

@bot.message_handler(commands=["start"])
def send_welcome(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("📱 Concept RNA (Direct OTP Login) 📱", callback_data="cp_otp_mode")
    )
    bot.reply_to(
        message,
        f"👋 **Namaste {message.from_user.first_name}!**\n\nNeeche button par click karke direct course extract karein:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data == "cp_otp_mode":
        user_states[chat_id] = {"step": "ASK_PHONE", "org_code": "nbhom", "course_id": "756679"}
        bot.send_message(
            chat_id,
            "📱 **Apna 10-digit Mobile Number bhejein** (jis par Concept RNA account hai):",
            parse_mode="Markdown"
        )

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id, {})
    step = state.get("step")

    if step == "ASK_PHONE":
        phone = message.text.strip().replace("+91", "").replace(" ", "")
        if not re.match(r'^\d{10}$', phone):
            bot.reply_to(message, "❌ Kripya 10 digit ka valid mobile number bhejein.")
            return

        state["phone"] = phone
        state["step"] = "WAITING_OTP"
        status_msg = bot.reply_to(message, "⏳ OTP bheja ja raha hai...")

        threading.Thread(target=send_otp_task, args=(chat_id, status_msg.message_id, phone, state["org_code"])).start()

    elif step == "WAITING_OTP":
        otp = message.text.strip()
        session_id = state.get("session_id")
        org_code = state.get("org_code", "nbhom")
        course_id = state.get("course_id", "756679")
        phone = state.get("phone")

        status_msg = bot.reply_to(message, "⏳ OTP verify kiya ja raha hai...")
        threading.Thread(target=verify_otp_and_extract_task, args=(chat_id, status_msg.message_id, org_code, course_id, phone, otp, session_id)).start()

def send_otp_task(chat_id, msg_id, phone, org_code):
    asyncio.run(send_otp_async(chat_id, msg_id, phone, org_code))

async def send_otp_async(chat_id, msg_id, phone, org_code):
    url = "https://api.classplusapp.com/v2/otp/generate"
    payload = {"mobile": phone, "orgCode": org_code}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=HEADERS, timeout=15) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 200 and data.get("status") == "success":
                    session_id = data.get("data", {}).get("sessionId")
                    user_states[chat_id]["session_id"] = session_id
                    bot.edit_message_text("✅ OTP aapke number par bhej diya gaya hai!\n\n🔢 **OTP yahan send karein:**", chat_id, msg_id)
                else:
                    msg = data.get("message", "OTP request fail ho gaya.")
                    bot.edit_message_text(f"❌ Error: {msg}", chat_id, msg_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Connection error: {e}", chat_id, msg_id)

def verify_otp_and_extract_task(chat_id, msg_id, org_code, course_id, phone, otp, session_id):
    asyncio.run(verify_and_extract_async(chat_id, msg_id, org_code, course_id, phone, otp, session_id))

async def verify_and_extract_async(chat_id, msg_id, org_code, course_id, phone, otp, session_id):
    url = "https://api.classplusapp.com/v2/users/verify"
    payload = {
        "mobile": phone,
        "otp": otp,
        "sessionId": session_id,
        "orgCode": org_code
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=HEADERS, timeout=15) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200 or data.get("status") != "success":
                    msg = data.get("message", "Galat OTP ya verification failed.")
                    bot.edit_message_text(f"❌ Error: {msg}", chat_id, msg_id)
                    return

                token = data.get("data", {}).get("token")
        except Exception as e:
            bot.edit_message_text(f"❌ Login error: {e}", chat_id, msg_id)
            return

        # Token milte hi direct extraction start
        bot.edit_message_text("✅ Login successful! Course scanning start ho chuki hai...", chat_id, msg_id)
        
        auth_headers = {
            "x-access-token": token,
            "User-Agent": "Mobile-Android",
            "accept": "application/json",
            "region": "IN"
        }

        extracted_items = []
        queue = [(0, "Root")]
        visited_folders = set()

        while queue:
            current_folder_id, path = queue.pop(0)
            if current_folder_id in visited_folders:
                continue
            visited_folders.add(current_folder_id)

            content_url = f"https://api.classplusapp.com/v2/course/content/get?courseId={course_id}&folderId={current_folder_id}"
            try:
                async with session.get(content_url, headers=auth_headers, timeout=15) as c_resp:
                    if c_resp.status == 200:
                        c_data = await c_resp.json(content_type=None)
                        contents = c_data.get("data", {}).get("courseContent", [])
                        for item in contents:
                            item_type = item.get("contentType")
                            item_name = item.get("name", "Untitled")

                            if item_type == 1:
                                sub_id = item.get("id")
                                queue.append((sub_id, f"{path} > {item_name}"))
                            elif item_type == 2:
                                v_url = item.get("url") or item.get("streamUrl") or item.get("videoUrl", "")
                                extracted_items.append(f"📹 {item_name} : {v_url}")
                            elif item_type == 3:
                                d_url = item.get("url") or item.get("documentUrl", "")
                                extracted_items.append(f"📄 {item_name} : {d_url}")
            except Exception as err:
                logger.error(f"Folder fetch error: {err}")

        if not extracted_items:
            bot.edit_message_text("❌ Course khali mila ya content access nahi hua.", chat_id, msg_id)
            return

        file_path = f"downloads/ConceptRNA_{course_id}.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"--- Concept RNA Extracted Batch ({course_id}) ---\n\n")
            for line in extracted_items:
                f.write(line + "\n")

        bot.edit_message_text(f"✅ Extraction complete! Total {len(extracted_items)} files mili hain.", chat_id, msg_id)
        with open(file_path, "rb") as doc:
            bot.send_document(chat_id, doc, caption=f"📚 **Course ID:** `{course_id}`\n✨ **Total Files:** {len(extracted_items)}")

if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True)
