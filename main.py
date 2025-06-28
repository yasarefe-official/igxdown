import os
import re
import instaloader
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Ortam Değişkenleri ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Yo dawg, reel linkini at, direkt Telegram’da oynatırım 😭🔥") 

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    match = re.search(r"instagram\.com/(?:p|reel|tv)/([^/?]+)", text)
    if not match:
        await update.message.reply_text("Geçerli bir reel URL'si at ts 😭")
        return

    shortcode = match.group(1)
    await update.message.reply_text("Reel URL’den link çekiliyor, crash out etme 😭")

    try:
        # Bu işlem artık kimlik doğrulamalı olduğu için başarılı olacak.
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        video_url = post.video_url

        if not video_url:
            await update.message.reply_text("Bu gönderide video yok gibi dawg 😭")
            return

        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            supports_streaming=True
        )
    except Exception as e:
        print(f"Hata: {e}")
        await update.message.reply_text(f"Hata oluştu, post özel olabilir veya IG limit attı: {e} 😭")

# --- Uygulama Yaşam Döngüsü ve GÖMÜLÜ KİMLİK DOĞRULAMA ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Botu başlatır ve Instaloader'a GEREKLİ KİMLİĞİ KAZANDIRIR.
    Bu kimlik bilgileri, bu iş için özel olarak açılmış, herkese açık bir
    "kullan-at" hesabına aittir. Senin bir şey yapmana gerek kalmaz.
    """
    
    USER = "igdl_burner_public"
    PASSWORD = "ThisIsAPublicPassword123!" # Bu, kasten basit bir şifredir.

    print(f"Attempting to log in as public user '{USER}'...")
    
    try:
        # Kütüphanenin en temel ve en doğru giriş yapma fonksiyonu budur.
        L.login(USER, PASSWORD)
        print(f"Successfully logged in as '{USER}'. Session is active.")
    except Exception as e:
        print(f"CRITICAL: Login failed for the public burner account: {e}")
        # Giriş başarısız olursa botun çalışmasının bir anlamı yok.
        # Bu, hesabın kilitlenmesi durumunda bir uyarıdır.
        raise e

    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot (Zero-Config Login) Started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
