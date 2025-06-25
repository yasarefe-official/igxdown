import os
import re
import threading
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

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PORT = int(os.environ.get("PORT", "8080"))

L = instaloader.Instaloader(
    save_metadata=False,
    download_videos=False,
    download_video_thumbnails=False,
    compress_json=False,
)

app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return "OK", 200

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Yo dawg, reel linkini at ts, whip gibi getiririm 😭🔥")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
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

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

def main():
    from asyncio import run
    import asyncio

    # Flask thread’de run
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Telegram bot’u async olarak run et
    async def run_bot():
        app_bot = ApplicationBuilder().token(TOKEN).build()
        app_bot.add_handler(CommandHandler("start", start_cmd))
        app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
        await app_bot.run_polling()

    run(run_bot())

if __name__ == "__main__":
    main()
