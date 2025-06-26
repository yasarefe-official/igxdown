import os
import asyncio
import tempfile
import yt_dlp
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Ortam Değişkenleri ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# --- Bot ve FastAPI Uygulaması ---
bot_app = ApplicationBuilder().token(TOKEN).build()
app = FastAPI()

# --------------------------------------------------------------------------- #
# BÖLÜM 1: İNDİRME MOTORU (KENDİ API'miz)                                    #
# --------------------------------------------------------------------------- #

class DownloadRequest(BaseModel):
    url: str

@app.post("/api/download")
async def api_download_video(request: DownloadRequest):
    """
    Bu endpoint, gelen Instagram URL'sini yt-dlp ile indirir
    ve sonucu doğrudan bir video dosyası olarak döndürür.
    """
    temp_dir = tempfile.mkdtemp()
    video_path = os.path.join(temp_dir, "video.mp4")

    # yt-dlp için en iyi ayarlar
    ydl_opts = {
        'outtmpl': video_path,
        'format': 'best[ext=mp4]/best',
        'quiet': True,
    }

    try:
        print(f"Downloader engine starting for: {request.url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([request.url])

        if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
            raise HTTPException(status_code=404, detail="Video could not be downloaded. It might be private or an invalid link.")

        print(f"Download successful. Serving file: {video_path}")
        # Dosyayı response olarak gönder ve gönderdikten sonra sil.
        return FileResponse(path=video_path, media_type='video/mp4', filename="video.mp4")

    except Exception as e:
        print(f"Error in downloader engine: {e}")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

# --------------------------------------------------------------------------- #
# BÖLÜM 2: TELEGRAM BOT ARAYÜZÜ                                               #
# --------------------------------------------------------------------------- #

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Send an Instagram post link to download the video.")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Kullanıcıdan linki alır ve kendi indirme motorumuza (API) istek gönderir.
    """
    url = update.message.text.strip()
    if "instagram.com" not in url:
        await update.message.reply_text("Please provide a valid Instagram link.")
        return

    progress_msg = await update.message.reply_text("Processing request...")

    # Kendi sunucumuzdaki API adresine istek atıyoruz.
    # Not: Koyeb gibi ortamlarda WEBHOOK_URL tam adresi içerir.
    api_endpoint = f"{WEBHOOK_URL.rstrip('/')}/api/download"
    payload = {"url": url}
    
    video_path = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_endpoint, json=payload, timeout=300) as response:
                if response.status == 200:
                    # İndirme motorumuz bize direkt video dosyasını verdi.
                    # Bu dosyayı geçici olarak kaydedip Telegram'a göndereceğiz.
                    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                        video_path = tmp.name
                        tmp.write(await response.read())
                    
                    await progress_msg.edit_text("Uploading video...")
                    with open(video_path, 'rb') as video_file:
                        await context.bot.send_video(
                            chat_id=update.effective_chat.id,
                            video=video_file,
                            caption="Video downloaded successfully.",
                            supports_streaming=True
                        )
                    await progress_msg.delete()
                else:
                    # İndirme motorumuz bir hata döndürdü.
                    error_data = await response.json()
                    await progress_msg.edit_text(f"Failed to download.\nReason: {error_data.get('detail', 'Unknown error')}")

    except Exception as e:
        await progress_msg.edit_text(f"A critical error occurred: {e}")
    finally:
        if video_path and os.path.exists(video_path):
            os.unlink(video_path)

# --- UYGULAMAYI BAŞLATMA ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Botun yaşam döngüsünü yönetir."""
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot v10 (Architect's Edition) started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

# FastAPI uygulamasını lifespan ile yeniden tanımlıyoruz.
app = FastAPI(lifespan=lifespan)

# /api/download endpoint'ini router'a ekliyoruz.
app.post("/api/download")(api_download_video)

# Telegram komutlarını ve webhook'u ekliyoruz.
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@app.post("/webhook")
async def webhook(request: Request):
    """Telegram'dan gelen güncellemeleri alır ve bot'a iletir."""
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
