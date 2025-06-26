import os
import re
import asyncio
import tempfile
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
APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN") # Apify token'ınız

# --- API Bilgileri ---
APIFY_BASE_URL = "https://api.apify.com/v2/acts/gusost~instagram-reels-downloader/run-sync-get-dataset-items"

# --- Bot Kurulumu ---
bot_app = ApplicationBuilder().token(TOKEN).build()
last_request_time = 0
REQUEST_DELAY = 2

async def normalize_instagram_url(url: str):
    """URL'yi standart Instagram reel formatına çevirir."""
    match = re.search(r'(?:instagram\.com/(?:p|reel|tv)/)([A-Za-z0-9_-]+)', url)
    return f"https://www.instagram.com/reel/{match.group(1)}/" if match else None

async def download_with_apify(url: str):
    """Apify API ile video indirmeyi dener."""
    if not APIFY_API_TOKEN:
        print("CRITICAL: APIFY_API_TOKEN is not set in environment variables.")
        return None, "Bot sahibi Apify API anahtarını yapılandırmamış."

    print(f"Starting download with Apify for: {url}")
    full_api_url = f"{APIFY_BASE_URL}?token={APIFY_API_TOKEN}"
    payload = {"links": [url]}
    # Timeout süresi, Apify'ın yavaş çalışabilme ihtimaline karşı artırıldı.
    timeout = aiohttp.ClientTimeout(total=150)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(full_api_url, json=payload) as response:
                print(f"Apify response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        item = data[0]
                        if item.get("error"):
                            return None, f"Apify videoyu işlerken bir hata buldu: {item['error']}"
                        medias = item.get("medias")
                        if medias and medias[0].get("url"):
                            print("Apify successful, got download URL.")
                            return medias[0]["url"], None
                    return None, "Apify'dan gelen yanıtta video linki bulunamadı. Lütfen linki kontrol edin."
                else:
                    error_text = await response.text()
                    return None, f"Apify servisi {response.status} hatası döndü. Token'ınızı veya hesap durumunuzu kontrol edin. Detay: {error_text[:200]}"
    except asyncio.TimeoutError:
         return None, "Apify servisinden yanıt alınamadı (zaman aşımı). Lütfen birkaç dakika sonra tekrar deneyin."
    except Exception as e:
        print(f"A critical error occurred in download_with_apify: {e}")
        return None, "Apify servisinde beklenmedik bir hata oluştu."

async def download_video_from_url(video_url: str, output_path: str):
    """Son video dosyasını URL'den indirir."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                if response.status == 200:
                    with open(output_path, 'wb') as f:
                        f.write(await response.read())
                    # Dosya boyutunu kontrol et
                    if os.path.getsize(output_path) < 1000: # 1KB'den küçükse hatalıdır
                        return False, "İndirilen dosya bozuk veya boş."
                    return True, None
                return False, f"Son video indirilemedi (Sunucu hatası: {response.status})."
    except Exception as e:
        return False, f"Video indirme sırasında bir ağ hatası oluştu: {e}"

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mesajları işler ve SADECE Apify kullanarak indirme sürecini başlatır."""
    global last_request_time
    if time.time() - last_request_time < REQUEST_DELAY: return
    last_request_time = time.time()

    normalized_url = await normalize_instagram_url(update.message.text.strip())
    if not normalized_url:
        await update.message.reply_text("❌ Lütfen geçerli bir Instagram video/reel linki gönderin.")
        return

    progress_msg = await update.message.reply_text("🔄 Video indiriliyor, lütfen bekleyin...")
    
    video_url, error = await download_with_apify(normalized_url)

    if error:
        # Eğer Apify'dan hata geldiyse, doğrudan o hatayı göster.
        await progress_msg.edit_text(f"❌ İndirme başarısız.\n\nSebep: {error}")
        return

    try:
        # Apify link verdiyse videoyu indir ve gönder
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            video_path = tmp.name
        
        success, dl_error = await download_video_from_url(video_url, video_path)

        if success:
            await progress_msg.edit_text("📤 Video gönderiliyor...")
            caption = f"🤖 @{context.bot.username} ile indirildi."
            with open(video_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id, video=video_file, caption=caption, supports_streaming=True
                )
            await progress_msg.delete()
        else:
            await progress_msg.edit_text(f"❌ İndirme başarısız.\n\nSebep: {dl_error}")
    
    except Exception as e:
        await progress_msg.edit_text(f"❌ Kritik bir hata oluştu: {e}")
    finally:
        # Geçici dosyayı her durumda sil
        if 'video_path' in locals() and os.path.exists(video_path):
            os.unlink(video_path)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Stabil Instagram Video İndirici v4.2 (Apify-Only)\n\nBota bir Instagram linki gönderin, gerisini o halleder.")

# Handler'ları ve FastAPI uygulamasını ayarla
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot v4.2 (Apify-Only with Token) started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
