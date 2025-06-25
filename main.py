import os
import re
import instaloader
import asyncio

from fastapi import FastAPI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ENV’lerden al
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PORT = int(os.environ.get("PORT", "8080"))

# Instaloader (sadece video_url çekmek için)
L = instaloader.Instaloader(
    save_metadata=False,
    download_videos=False,
    download_video_thumbnails=False,
    compress_json=False,
)

# Telegram bot application
bot_app = ApplicationBuilder().token(TOKEN).build()

# Handlers
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Yo dawg, reel linkini at ts, direkt getiririm.")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    m = re.search(r"/reel/([^/?]+)", txt)
    if not m:
        await update.message.reply_text("Geçerli reel URL’si at ts.")
        return

    sc = m.group(1)
    await update.message.reply_text("Link çekiliyor…")

    try:
        post = instaloader.Post.from_shortcode(L.context, sc)
        video_url = post.video_url
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            supports_streaming=True,
        )
    except Exception as e:
        await update.message.reply_text(f"Hata: {e}")

# Kayıt et
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# FastAPI app
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    # Telegram bot’u başlat
    await bot_app.initialize()
    # polling’i background task olarak ata
    asyncio.create_task(bot_app.updater.start_polling())

@app.get("/")
async def health():
    return {"status": "ok"}

# uvicorn ile run edilince burayı kullanacak
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
