import os
import re
import asyncio
import tempfile
import json
import aiohttp
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Ortam Değişkenleri ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN") # YENİ: Apify token'ı alıyoruz

# --- API Bilgileri ---
APIFY_BASE_URL = "https://api.apify.com/v2/acts/gusost~instagram-reels-downloader/run-sync-get-dataset-items"
COBALT_API_URL = "https://api.cobalt.tools/api/json"

# --- Bot Kurulumu ---
bot_app = ApplicationBuilder().token(TOKEN).build()
last_request_time = 0
REQUEST_DELAY = 2

async def normalize_instagram_url(url):
    """URL'yi standart Instagram reel formatına çevirir."""
    match = re.search(r'(?:instagram\.com/(?:p|reel|tv)/)([A-Za-z0-9_-]+)', url)
    return f"https://www.instagram.com/reel/{match.group(1)}/" if match else None

async def download_with_apify(url: str):
    """Apify API ile video indirmeyi dener (API Token ile)."""
    if not APIFY_API_TOKEN:
        print("HATA: APIFY_API_TOKEN ortam değişkeni ayarlanmamış.")
        return None, "Apify servisi yapılandırılmamış (token eksik)."

    print(f"Trying to download with Apify: {url}")
    full_api_url = f"{APIFY_BASE_URL}?token={APIFY_API_TOKEN}"
    payload = {"links": [url]}
    timeout = aiohttp.ClientTimeout(total=90)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(full_api_url, json=payload) as response:
                print(f"Apify response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        medias = data[0].get("medias")
                        if medias and medias[0].get("url"):
                            print("Apify successful, got download URL.")
                            return medias[0]["url"], None
                    return None, "Apify'dan geçerli bir video linki alınamadı."
                else:
                    return None, f"Apify servisi {response.status} hatası döndü."
    except Exception as e:
        print(f"Apify Error: {e}")
        return None, "Apify servisinde beklenmedik bir hata oluştu."

async def download_with_cobalt(url: str):
    """Cobalt.tools API ile video indirmeyi dener (Yedek)."""
    print(f"Falling back to Cobalt: {url}")
    payload = {"url": url, "vQuality": "720"}
    timeout = aiohttp.ClientTimeout(total=45)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(COBALT_API_URL, json=payload) as response:
                if response.status == 200 and (data := await response.json()).get("status") == "success":
                    print("Cobalt fallback successful.")
                    return data.get("url"), None
    except Exception as e:
        print(f"Cobalt Error: {e}")
    return None, "Yedek servis (Cobalt) de başarısız oldu."

async def download_video_from_url(video_url: str, output_path: str):
    """Son video dosyasını URL'den indirir."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                if response.status == 200:
                    with open(output_path, 'wb') as f:
                        f.write(await response.read())
                    return True, None
                return False, f"Son video indirilemedi (HTTP {response.status})."
    except Exception as e:
        return False, f"Video indirme hatası: {e}"

async def download_instagram_video(url: str):
    """Ana indirme yöneticisi."""
    video_url, error = await download_with_apify(url)
    if not video_url:
        video_url, error = await download_with_cobalt(url)
    if not video_url:
        return None, error

    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
        temp_path = tmp.name
    
    success, dl_error = await download_video_from_url(video_url, temp_path)
    if success and os.path.getsize(temp_path) > 1000:
        return temp_path, None
    else:
        if os.path.exists(temp_path): os.unlink(temp_path)
        return None, dl_error or "İndirilen dosya geçersiz."

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mesajları işler ve indirme sürecini başlatır."""
    global last_request_time
    if time.time() - last_request_time < REQUEST_DELAY: return
    last_request_time = time.time()

    normalized_url = await normalize_instagram_url(update.message.text.strip())
    if not normalized_url:
        await update.message.reply_text("❌ Lütfen geçerli bir Instagram linki gönderin.")
        return

    progress_msg = await update.message.reply_text("🔄 Video indiriliyor, lütfen bekleyin...")
    
    try:
        video_path, error = await download_instagram_video(normalized_url)
        if video_path:
            await progress_msg.edit_text("📤 Video gönderiliyor...")
            caption = f"🤖 @{context.bot.username} ile indirildi."
            with open(video_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id, video=video_file, caption=caption, supports_streaming=True
                )
            await progress_msg.delete()
            os.unlink(video_path)
        else:
            await progress_msg.edit_text(f"❌ İndirme başarısız.\n\nSebep: {error}")
    except Exception as e:
        await progress_msg.edit_text(f"❌ Kritik hata: {e}")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Stabil Instagram Video İndirici (v4.1)\n\nBota bir Instagram linki gönderin, gerisini o halleder.")

# Handler'ları ve FastAPI uygulamasını ayarla
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot v4.1 (Apify with Token) started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
