import os
import re
import aiohttp
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Ortam Değişkenleri ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# --- GÜVENİLİR VE ÜCRETSİZ API BİLGİSİ ---
DOWNLOADER_API_URL = "https://v3.igdownloader.app/api/ajaxSearch"

# --- Bot ve FastAPI Kurulumu ---
bot_app = ApplicationBuilder().token(TOKEN).build()
app = FastAPI()

async def get_download_link(url: str):
    """
    iGram'in dahili API'sini kullanarak Instagram videosu indirme linkini alır.
    """
    payload = {'q': url, 't': 'media'}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
        'Origin': 'https://igram.io',
        'Referer': 'https://igram.io/'
    }
    
    # <<< BU SATIR DÜZELTİLDİ >>>
    # Hata mesajının tam olarak belirttiği gibi, timeout parametresi
    # basit bir sayı değil, bir ClientTimeout nesnesi olmalıdır.
    timeout_config = aiohttp.ClientTimeout(total=60)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.post(DOWNLOADER_API_URL, data=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "ok":
                        match = re.search(r'href="([^"]+)" class="abutton is-success is-fullwidth"', data.get("data", ""))
                        if match:
                            return match.group(1), None
                    return None, "Video linki alınamadı. Link özel veya geçersiz olabilir."
                else:
                    return None, f"İndirme servisi yanıt vermiyor (Hata: {response.status})."
    except Exception as e:
        print(f"API hatası: {e}")
        return None, "Beklenmedik bir hata oluştu."

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome. Send an Instagram link to download the video.")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "instagram.com" not in url:
        await update.message.reply_text("Please provide a valid Instagram link.")
        return

    progress_msg = await update.message.reply_text("Processing...")
    
    video_url, error = await get_download_link(url)

    if error:
        await progress_msg.edit_text(f"Failed to download.\nReason: {error}")
        return

    try:
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            caption="Video downloaded successfully.",
            supports_streaming=True
        )
        await progress_msg.delete()
    except Exception as e:
        print(f"Telegram'a gönderme hatası: {e}")
        await progress_msg.edit_text("An error occurred while sending the video to Telegram.")

# --- Uygulama Yaşam Döngüsü ve Webhook ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot (Simple & Final, Corrected) started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
