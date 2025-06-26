import os
import re
import instaloader
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Environment Variables ---
# The token will be fetched from Koyeb's environment variables.
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# --- Instaloader Configuration ---
# Clean and efficient setup to only fetch metadata without downloading any files.
L = instaloader.Instaloader(
    save_metadata=False,
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    compress_json=False,
    max_connection_attempts=1 # Fail fast on connection errors
)

# --- Bot Application Setup ---
bot_app = ApplicationBuilder().token(TOKEN).build()

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command with a professional welcome message."""
    await update.message.reply_text(
        "Welcome! Please provide a valid Instagram post or Reel URL to download the video."
    )

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes user-sent messages, extracts the video URL, and sends it back."""
    text = update.message.text.strip()
    
    # A more robust regex to capture post, reel, and tv links.
    match = re.search(r"instagram\.com/(?:p|reel|tv)/([^/?]+)", text)
    if not match:
        await update.message.reply_text("Invalid URL. Please send a valid Instagram post link.")
        return

    shortcode = match.group(1)
    progress_msg = await update.message.reply_text("Processing your request, please wait...")

    try:
        # Fetch post metadata using the shortcode.
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        # Get the direct video URL.
        video_url = post.video_url

        if not video_url:
            await progress_msg.edit_text("A video could not be found in this post. It might be an image-only post.")
            return

        # Send the video to the user via URL. Telegram handles the download and streaming.
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url, # Provide the direct URL to Telegram
            caption=f"Video downloaded successfully.\nPowered by @{context.bot.username}",
            supports_streaming=True
        )
        await progress_msg.delete()

    except Exception as e:
        error_message = str(e)
        print(f"An error occurred: {error_message}")
        
        # Provide user-friendly error messages for common issues.
        if "session" in error_message.lower() or "login" in error_message.lower() or "401" in error_message:
             await progress_msg.edit_text(
                 "Could not access the post. The account may be private or Instagram's rate limits have been reached. Please try again later."
            )
        else:
            await progress_msg.edit_text(f"An unexpected error occurred. Please try again.")

# --- Register Handlers and Set Up FastAPI ---
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles bot startup and shutdown, including setting the webhook."""
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 IGXDOWN (Professional Edition) started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def webhook(request: Request):
    """The main webhook endpoint to receive updates from Telegram."""
    try:
        update = Update.de_json(await request.json(), bot_app.bot)
        await bot_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        print(f"Error in webhook: {e}")
        return {"status": "error"}
