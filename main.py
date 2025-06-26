import os
import re
import asyncio
import tempfile
import json
import random
from contextlib import asynccontextmanager
import aiohttp
import time
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Ortam değişkenlerinden alınacak bilgiler
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# Telegram bot uygulaması
bot_app = ApplicationBuilder().token(TOKEN).build()

# İstek limitleyici
last_request_time = 0
REQUEST_DELAY = 2  # saniye

# --- YENİ VE STABİL YÖNTEM: Apify API ---
APIFY_API_URL = "https://api.apify.com/v2/acts/gusost~instagram-reels-downloader/run-sync-get-dataset-items"

# --- YEDEK YÖNTEM: Cobalt.tools ---
COBALT_INSTANCES = [
    "https://api.cobalt.tools",
    "https://co.wuk.sh",
]

async def normalize_instagram_url(url):
    """Instagram URL'ini standart bir formata getirir."""
    try:
        match = re.search(r'(?:instagram\.com/(?:p|reel|tv)/)([A-Za-z0-9_-]+)', url)
        if match:
            post_id = match.group(1)
            return f"https://www.instagram.com/reel/{post_id}/"
        return None
    except Exception as e:
        print(f"URL normalize error: {e}")
        return None

async def download_with_apify(url):
    """Apify API ile video indirmeyi dener."""
    print(f"Trying to download with Apify: {url}")
    payload = {"links": [url]}
    headers = {"Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=90)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(APIFY_API_URL, json=payload, headers=headers) as response:
                print(f"Apify response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        item = data[0]
                        if not item.get("error"):
                            medias = item.get("medias")
                            if medias and medias[0].get("url"):
                                print("Apify successful, got download URL.")
                                return medias[0]["url"], None
                    return None, "Apify response did not contain a valid video URL."
                else:
                    return None, f"Apify service returned HTTP {response.status}"
    except Exception as e:
        print(f"An error occurred during Apify download: {e}")
        return None, "An unexpected error occurred with the Apify service."

async def download_with_cobalt(url):
    """Cobalt.tools API ile video indirmeyi dener (Yedek)."""
    print(f"Falling back to Cobalt to download: {url}")
    payload = {"url": url, "vQuality": "720"}
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=45)

    for instance in COBALT_INSTANCES:
        try:
            api_endpoint = f"{instance}/api/json"
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(api_endpoint, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "success":
                            print(f"Cobalt fallback successful on {instance}")
                            return data.get("url"), None
        except Exception as e:
            print(f"Cobalt instance {instance} failed: {e}")
    return None, "All fallback services (Cobalt) also failed."

async def download_video_from_url(video_url, output_path):
    """Verilen URL'den videoyu dosyaya indirir."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(video_url) as response:
                if response.status == 200:
                    total_size = 0
                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(16384):
                            f.write(chunk)
                            total_size += len(chunk)
                            if total_size > 50 * 1024 * 1024:
                                return False, "File is larger than 50MB."
                    return True, None
                else:
                    return False, f"HTTP {response.status} error on final download."
    except Exception as e:
        return False, f"Final video download error: {e}"

async def download_instagram_video(url):
    """Ana indirme fonksiyonu. Önce Apify, sonra Cobalt'ı dener."""
    video_url, error = await download_with_apify(url)

    if not video_url:
        print(f"Apify failed with error: {error}. Trying fallback.")
        video_url, error = await download_with_cobalt(url)

    if not video_url:
        return None, error

    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
        temp_path = temp_file.name
    
    success, dl_error = await download_video_from_url(video_url, temp_path)
    
    if success and os.path.getsize(temp_path) > 1000:
        return temp_path, None
    else:
        if os.path.exists(temp_path): os.unlink(temp_path)
        return None, dl_error or "Download failed or file is empty."

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gelen mesajları işler ve video indirmeyi başlatır."""
    global last_request_time
    if time.time() - last_request_time < REQUEST_DELAY:
        return
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
                    chat_id=update.effective_chat.id,
                    video=video_file,
                    caption=caption,
                    supports_streaming=True
                )
            await progress_msg.delete()
            os.unlink(video_path)
        else:
            await progress_msg.edit_text(f"❌ İndirme başarısız.\n\nHata: {error}")
    except Exception as e:
        await progress_msg.edit_text(f"❌ Beklenmedik bir hata oluştu: {e}")

# Diğer komutlar (start, help) ve FastAPI/Webhook kurulumu
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Stabil Instagram Video İndirici (v4.0)\n\nApify ve Cobalt kullanan bu bota bir Instagram linki gönderin.")

bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not TOKEN or not WEBHOOK_URL:
        raise ValueError("TELEGRAM_BOT_TOKEN ve WEBHOOK_URL ortam değişkenleri ayarlanmalı.")
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot v4.0 (Apify) started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health(): return {"status": "ok", "version": "4.0"}

@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
