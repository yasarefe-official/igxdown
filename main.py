import os
import asyncio
import tempfile
import yt_dlp
import aiohttp  # <<< THIS IS THE MISSING LINE
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Environment Variables ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# --- Bot and FastAPI Application ---
bot_app = ApplicationBuilder().token(TOKEN).build()
# We define the app here, but the lifespan logic is separate
app_instance = FastAPI()


# --------------------------------------------------------------------------- #
# SECTION 1: THE DOWNLOAD ENGINE (OUR OWN API)                                #
# --------------------------------------------------------------------------- #

class DownloadRequest(BaseModel):
    url: str

@app_instance.post("/api/download")
async def api_download_video(request: DownloadRequest):
    """
    This endpoint downloads the video from the given Instagram URL using yt-dlp
    and returns the result directly as a video file.
    """
    temp_dir = tempfile.mkdtemp()
    # Define a specific output filename
    output_template = os.path.join(temp_dir, "%(id)s.%(ext)s")
    
    ydl_opts = {
        'outtmpl': output_template,
        'format': 'best[ext=mp4]/best',
        'quiet': True,
    }

    try:
        print(f"Downloader engine starting for: {request.url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(request.url, download=True)
            downloaded_file_path = ydl.prepare_filename(info_dict)

        if not os.path.exists(downloaded_file_path) or os.path.getsize(downloaded_file_path) == 0:
            raise HTTPException(status_code=404, detail="Video could not be downloaded.")

        print(f"Download successful. Serving file: {downloaded_file_path}")
        return FileResponse(path=downloaded_file_path, media_type='video/mp4', filename="video.mp4")

    except Exception as e:
        print(f"Error in downloader engine: {e}")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


# --------------------------------------------------------------------------- #
# SECTION 2: THE TELEGRAM BOT INTERFACE                                       #
# --------------------------------------------------------------------------- #

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Send an Instagram post link to download the video.")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receives the link from the user and sends a request to our own download engine.
    """
    url = update.message.text.strip()
    if "instagram.com" not in url:
        await update.message.reply_text("Please provide a valid Instagram link.")
        return

    progress_msg = await update.message.reply_text("Processing request...")

    api_endpoint = f"{WEBHOOK_URL.rstrip('/')}/api/download"
    payload = {"url": url}
    
    video_path = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_endpoint, json=payload, timeout=300) as response:
                if response.status == 200:
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
                    error_data = await response.json()
                    await progress_msg.edit_text(f"Failed to download.\nReason: {error_data.get('detail', 'Unknown error')}")

    except Exception as e:
        await progress_msg.edit_text(f"A critical error occurred: {e}")
    finally:
        if video_path and os.path.exists(video_path):
            os.unlink(video_path)

# --- APPLICATION LIFESPAN & STARTUP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages the bot's lifecycle."""
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot v10.1 (Architect's Edition) started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

# Re-assign the app with the lifespan manager
app = FastAPI(lifespan=lifespan)

# Mount the downloader engine and webhook to the final app
app.post("/api/download")(api_download_video)
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@app.post("/webhook")
async def webhook(request: Request):
    """Receives updates from Telegram and forwards them to the bot."""
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
