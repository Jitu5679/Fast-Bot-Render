"""
Fast-Bot-Render - Full Classplus/Concept RNA + PW/Appx Auto Extractor
"""
import os
import re
import json
import asyncio
import aiohttp
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Web Server for Render Port Binding
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

@bot.message_handler(commands=["start"])
def send_welcome(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("📘 Classplus / Concept RNA 📘", callback_data="cp_mode"),
        InlineKeyboardButton("🚀 Physics Wallah / Other 🚀", callback_data="pw_mode")
    )
    bot.reply_to(
        message,
        f"👋 **Namaste {message.from_user.first_name}!**\n\nCourse extract karne ke liye neeche platform chunein:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data == "cp_mode":
        user_states[chat_id] = {"step": "CP_ORG"}
        bot.send_message(chat_id, "🏢 **Step 1:** Apna **Org Code** bhejein (jaise `nbhom`):", parse_mode="Markdown")
    elif call.data == "pw_mode":
        bot.send_message(chat_id, "🔑 PW Batch link ya Token bhejein.")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id, {})
    step = state.get("step")

    if step == "CP_ORG":
        state["org_code"] = message.text.strip().lower()
        state["step"] = "CP_COURSE_ID"
        bot.send_message(chat_id, "🆔 **Step 2:** Apna **Course ID** bhejein (jaise `756679`):", parse_mode="Markdown")
    
    elif step == "CP_COURSE_ID":
        raw_text = message.text.strip()
        match = re.search(r'\d+', raw_text)
        course_id = match.group(0) if match else raw_text
        state["course_id"] = course_id
        state["step"] = "CP_TOKEN"
        bot.send_message(
            chat_id,
            "🔑 **Step 3:** Apna **User/Access Token** bhejein:\n*(Mobile app / Web se nikala hua Bearer token)*",
            parse_mode="Markdown"
        )
    
    elif step == "CP_TOKEN":
        token = message.text.strip().replace("Bearer ", "")
        org_code = state.get("org_code", "nbhom")
        course_id = state.get("course_id", "756679")
        
        status_msg = bot.send_message(chat_id, "⏳ Course content scan aur extract kiya ja raha hai...")
        user_states.pop(chat_id, None)

        threading.Thread(target=run_async_extractor, args=(chat_id, status_msg.message_id, org_code, course_id, token)).start()

def run_async_extractor(chat_id, msg_id, org_code, course_id, token):
    asyncio.run(extract_classplus_course(chat_id, msg_id, org_code, course_id, token))

async def fetch_folder_contents(session, headers, course_id, folder_id=0):
    url = f"https://api.classplusapp.com/v2/course/content/get?courseId={course_id}&folderId={folder_id}"
    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                return data.get("data", {}).get("courseContent", [])
    except Exception as e:
        logger.error(f"Error fetching folder {folder_id}: {e}")
    return []

async def extract_classplus_course(chat_id, msg_id, org_code, course_id, token):
    headers = {
        "x-access-token": token,
        "User-Agent": "Mobile-Android",
        "accept": "application/json",
        "region": "IN"
    }

    extracted_items = []
    
    async with aiohttp.ClientSession() as session:
        # Check Token Validity
        async with session.get(f"https://api.classplusapp.com/v2/orgs/{org_code}", headers=headers) as resp:
            if resp.status != 200:
                bot.edit_message_text("❌ Org Code verification failed.", chat_id, msg_id)
                return

        queue = [(0, "Root")]
        visited_folders = set()

        while queue:
            current_folder_id, path = queue.pop(0)
            if current_folder_id in visited_folders:
                continue
            visited_folders.add(current_folder_id)

            contents = await fetch_folder_contents(session, headers, course_id, current_folder_id)
            for item in contents:
                item_type = item.get("contentType")
                item_name = item.get("name", "Untitled")

                if item_type == 1:  # Sub-folder
                    sub_id = item.get("id")
                    queue.append((sub_id, f"{path} > {item_name}"))
                elif item_type == 2:  # Video
                    url = item.get("url") or item.get("streamUrl") or item.get("videoUrl", "")
                    extracted_items.append(f"📹 {item_name} : {url}")
                elif item_type == 3:  # PDF Document
                    url = item.get("url") or item.get("documentUrl", "")
                    extracted_items.append(f"📄 {item_name} : {url}")

    if not extracted_items:
        bot.edit_message_text("❌ Koi content extract nahi ho paya. Token expire ya Course ID galat ho sakti hai.", chat_id, msg_id)
        return

    # Save to TXT file
    file_path = f"downloads/ConceptRNA_{course_id}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"--- Concept RNA Extracted Course ({course_id}) ---\n\n")
        for line in extracted_items:
            f.write(line + "\n")

    bot.edit_message_text(f"✅ Extraction complete! Total {len(extracted_items)} items mile.", chat_id, msg_id)
    with open(file_path, "rb") as doc:
        bot.send_document(chat_id, doc, caption=f"📚 **Course ID:** `{course_id}`\n✨ **Total Files:** {len(extracted_items)}")

if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True)
    
