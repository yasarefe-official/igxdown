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

# --- GÜVENİLİR VE ÜCRETSİZ API BİLGİSİ ---
# iGram.io sitesinin kullandığı dahili API. Anahtar gerektirmez.
DOWNLOADER_API_URL = "https://v3.igdownloader.app/api/ajaxSearch"

# --- Bot Kurulumu ---
bot_app = ApplicationBuilder().token(TOKEN).build()
last_request_time = 0
REQUEST_DELAY = 2

async def download_instagram_video(url: str):
    """
    iGram'in dahili API'sini kullanarak Instagram videosu indirme linkini alır.
    Bu yöntem anahtarsız, ücretsiz ve stabildir.
    """
    print(f"Starting download process for: {url}")
    # API'ye gönderilecek form verisi
    payload = {
        'q': url,
        't': 'media'
    }
    # Tarayıcıyı taklit eden başlık bilgileri
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
        'Origin': 'https://igram.io',
        'Referer': 'https://igram.io/'
    }
    timeout = aiohttp.ClientTimeout(total=60)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(DOWNLOADER_API_URL, data=payload, headers=headers) as response:
                print(f"Downloader API response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "ok":
                        # API, içinde indirme linki olan bir HTML metni döndürüyor.
                        html_content = data.get("data", "")
                        # HTML içerisinden gerçek video linkini Regex ile çekiyoruz.
                        match = re.search(r'href="([^"]+)" class="abutton is-success is-fullwidth"', html_content)
                        if match:
                            video_link = match.group(1)
                            print("Successfully extracted video download link.")
                            return video_link, None
                    return None, "Video linki alınamadı. Link özel veya geçersiz olabilir."
                else:
                    return None, f"İndirme servisi {response.status} hatası verdi. Lütfen daha sonra tekrar deneyin."
    except asyncio.TimeoutError:
         return None, "İndirme servisinden yanıt alınamadı (zaman aşımı)."
    except Exception as e:
        print(f"A critical error occurred in downloader: {e}")
        return None, "Beklenmedik bir hata oluştu."

async def download_file_to_temp(video_url: str):
    """Verilen URL'den videoyu geçici bir dosyaya indirir."""
    video_path = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url) as response:
                if response.status == 200:
                    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                        video_path = tmp.name
                        tmp.write(await response.read())
                    if os.path.getsize(video_path) > 1000:
                        return video_path, None
                    else:
                        os.unlink(video_path)
                        return None, "İndirilen dosya bozuk veya boş."
                return None, f"Video dosyası indirilemedi (Sunucu: {response.status})."
    except Exception as e:
        if video_path and os.path.exists(video_path): os.unlink(video_path)
        return None, f"Video indirme sırasında ağ hatası: {e}"

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gelen mesajları işler ve indirme sürecini başlatır."""
    global last_request_time
    if time.time() - last_request_time < REQUEST_DELAY: return
    last_request_time = time.time()

    url = update.message.text.strip()
    if not "instagram.com" in url:
        await update.message.reply_text("❌ Lütfen geçerli bir Instagram linki gönderin.")
        return

    progress_msg = await update.message.reply_text("🔄 Video indiriliyor, lütfen bekleyin...")
    
    video_url, error = await download_instagram_video(url)

    if error:
        await progress_msg.edit_text(f"❌ İndirme başarısız.\n\nSebep: {error}")
        return

    video_path, error = await download_file_to_temp(video_url)
    
    if error:
        await progress_msg.edit_text(f"❌ İndirme başarısız.\n\nSebep: {error}")
        return

    try:
        await progress_msg.edit_text("📤 Video gönderiliyor...")
        caption = f"🤖 @{context.bot.username} ile indirildi."
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=update.effective_chat.id, video=video_file, caption=caption, supports_streaming=True
            )
        await progress_msg.delete()
    except Exception as e:
        await progress_msg.edit_text(f"❌ Video gönderilirken bir hata oluştu: {e}")
    finally:
        if os.path.exists(video_path):
            os.unlink(video_path)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Instagram Video İndirici v5.0 (Stabil API)\n\nBota bir Instagram linki gönderin, gerisini o halleder.")

# Handler'ları ve FastAPI uygulamasını ayarla
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot v5.0 (Stable Internal API) started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
