import os
import re
import instaloader
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Ortam Değişkenleri ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
IG_COOKIES_CONTENT = os.environ.get("IG_COOKIES") # Koyeb'e eklediğin tüm cookie metni

# --- Instaloader Kurulumu ---
L = instaloader.Instaloader(
    save_metadata=False,
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    compress_json=False,
)

# --- Bot ve FastAPI Kurulumu ---
bot_app = ApplicationBuilder().token(TOKEN).build()
app = FastAPI()

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome. Please provide an Instagram Post/Reel URL.")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Senin orijinal, temiz kodun burada, artık kimlik doğrulamalı çalışıyor."""
    text = update.message.text.strip()
    match = re.search(r"instagram\.com/(?:p|reel|tv)/([^/?]+)", text)
    if not match:
        await update.message.reply_text("Invalid URL. Please send a valid Instagram post link.")
        return

    shortcode = match.group(1)
    progress_msg = await update.message.reply_text("Processing your request, please wait...")

    try:
        # L.context artık kimlik doğrulamalı olduğu için bu işlem başarılı olacak.
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        video_url = post.video_url

        if not video_url:
            await progress_msg.edit_text("A video could not be found in this post.")
            return

        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            caption="Video downloaded successfully.",
            supports_streaming=True
        )
        await progress_msg.delete()

    except Exception as e:
        print(f"An error occurred: {e}")
        await progress_msg.edit_text("Failed to process the request. The post may be private or an error occurred.")

# --- Handler'lar ve Uygulama Yaşam Döngüsü ---
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Botu başlatır, kimlik doğrular ve kapatır."""
    if not IG_COOKIES_CONTENT:
        raise ValueError("CRITICAL: IG_COOKIES environment variable is not set!")

    # Geçici bir dosyaya cookie'leri yazarak Instaloader'a kimlik sağlıyoruz.
    cookie_file = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt')
    try:
        cookie_file.write(IG_COOKIES_CONTENT)
        cookie_file.close() 
        print(f"Cookies loaded into temporary file: {cookie_file.name}")
        
        # Instaloader'a bu cookie dosyası ile giriş yapmasını söylüyoruz.
        L.context.load_cookies_from_file(cookie_file.name)
        print("Instaloader session authenticated using cookies.")

        await bot_app.initialize()
        webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
        await bot_app.bot.set_webhook(url=webhook_url)
        await bot_app.start()
        print(f"🚀 Bot (Instaloader with Login) started! Webhook: {webhook_url}")
        yield
    finally:
        # Uygulama kapandığında geçici dosyayı temizliyoruz.
        os.unlink(cookie_file.name)
        print("Temporary cookie file cleaned up.")
        await bot_app.stop()
        await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
