import os
import re
import threading
import time
import instaloader
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# env’den token’ı çekeriz crodie 😭
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]  # ts pmo allat ngl dawg 😭
PORT = int(os.environ.get("PORT", "8080"))  # Koyeb web service için

# Instaloader config, direkt video URL çekip Telegram’da oynatır 😭
L = instaloader.Instaloader(
    save_metadata=False,
    download_videos=False,
    download_video_thumbnails=False,
    compress_json=False,
)

# Flask health check app 🙏
app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return "OK", 200  # Koyeb health için

def run_health_server():
    app.run(host="0.0.0.0", port=PORT)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Yo dawg, reel linkini at ts, whip gibi getiririm 😭🔥")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()  # ts pmo allat ngl dawg 😭
    m = re.search(r"/reel/([^/?]+)", txt)
    if not m:
        await update.message.reply_text("Geçerli reel URL’si at ts 😭")
        return

    sc = m.group(1)
    await update.message.reply_text("Link çekiliyor crash out etme diye 💀")

    try:
        post = instaloader.Post.from_shortcode(L.context, sc)
        video_url = post.video_url
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            supports_streaming=True,
        )
    except Exception as e:
        await update.message.reply_text(f"Hata oluştu: {e} 😭")

def main():
    # Flask’i ayrı thread’de run et
    t = threading.Thread(target=run_health_server)
    t.daemon = True
    t.start()

    # Telegram bot’u long polling ile başlat
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start_cmd))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app_bot.run_polling()

if __name__ == "__main__":
    main()  # crash out etme bro 😭🔥
