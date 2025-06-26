import os
import re
import instaloader
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Env'den al ngl
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # Webhook URL'ini env'den al

# Instaloader config
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
    await update.message.reply_text("Yo dawg, reel linkini at ts, beni test et 🔥")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    m = re.search(r"/reel/([^/?]+)", txt)
    if not m:
        await update.message.reply_text("Geçerli reel URL'si at ts 🙏")
        return

    sc = m.group(1)
    await update.message.reply_text("Link çekiliyor… crash out etme 😂")

    try:
        post = instaloader.Post.from_shortcode(L.context, sc)
        video_url = post.video_url
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            supports_streaming=True,
        )
    except Exception as e:
        await update.message.reply_text(f"Hata: {e} 💔")

# Kayıt et
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await bot_app.initialize()
    
    # Webhook modunda çalıştır
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        print(f"Webhook set to: {WEBHOOK_URL}/webhook")
    else:
        print("WEBHOOK_URL not set, webhook not configured")
    
    await bot_app.start()
    
    yield
    
    # Shutdown
    await bot_app.stop()
    await bot_app.shutdown()

# FastAPI app
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health():
    return {"status": "ok", "message": "Bot is running"}

@app.post("/webhook")
async def webhook(request: Request):
    """Telegram webhook endpoint"""
    try:
        # JSON verisini al
        json_data = await request.json()
        
        # Update objesini oluştur
        update = Update.de_json(json_data, bot_app.bot)
        
        # Update'i işle
        await bot_app.process_update(update)
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
