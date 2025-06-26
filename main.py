import os
import re
import asyncio
import tempfile
import aiohttp
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Environment Variables ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# --- RELIABLE & FREE DOWNLOADER API ---
# This API from SSSInstagram is simple and returns clean JSON. No keys needed.
API_ENDPOINT = "https://sssinstagram.com/request"

# --- Bot Setup ---
bot_app = ApplicationBuilder().token(TOKEN).build()

async def get_download_link(url: str):
    """
    Calls the SSSInstagram API to get a direct download link.
    This is the core of our simple, login-free solution.
    """
    print(f"Requesting download link for: {url}")
    payload = {"url": url}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
    }
    timeout = aiohttp.ClientTimeout(total=60)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(API_ENDPOINT, data=payload, headers=headers) as response:
                print(f"API Response Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    # The API returns a list of download links; we take the first one.
                    if data.get("success") and data["result"]["download_links"]:
                        video_url = data["result"]["download_links"][0]["url"]
                        print("Successfully retrieved download link.")
                        return video_url, None
                    else:
                        return None, "The API could not process this link. It may be private or invalid."
                else:
                    return None, f"The download service is currently unavailable (HTTP {response.status}). Please try again later."
    except Exception as e:
        print(f"An error occurred while calling the API: {e}")
        return None, "An unexpected error occurred. Please try again."

async def download_file(url: str, path: str):
    """Downloads the final video file from the given URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(path, 'wb') as f:
                        f.write(await response.read())
                    return True
                return False
    except Exception:
        return False

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming messages, processes the URL, and sends the video."""
    url = update.message.text.strip()
    if "instagram.com" not in url:
        await update.message.reply_text("Please provide a valid Instagram link.")
        return

    progress_msg = await update.message.reply_text("Processing your request, please wait...")

    video_url, error = await get_download_link(url)

    if error:
        await progress_msg.edit_text(f"Failed to download.\nReason: {error}")
        return

    video_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            video_path = tmp.name

        if await download_file(video_url, video_path):
            await progress_msg.edit_text("Uploading video...")
            with open(video_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=video_file,
                    caption=f"Video downloaded successfully.",
                    supports_streaming=True
                )
            await progress_msg.delete()
        else:
            await progress_msg.edit_text("Failed to download the final video file.")
    except Exception as e:
        await progress_msg.edit_text(f"An error occurred while sending the video: {e}")
    finally:
        if video_path and os.path.exists(video_path):
            os.unlink(video_path)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Send an Instagram post link to download the video.")

# --- Setup Handlers and FastAPI Application ---
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles bot startup and shutdown."""
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot v9.0 (Simple & Stable API) started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
