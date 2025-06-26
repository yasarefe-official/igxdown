import os
import re
import instaloader
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Environment Variables ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
# The correct session details from your cookie file
IG_USER_ID = os.environ.get("IG_USER_ID")
IG_SESSIONID = os.environ.get("IG_SESSIONID")
IG_CSRFTOKEN = os.environ.get("IG_CSRFTOKEN")

# --- Instaloader Setup ---
L = instaloader.Instaloader(
    save_metadata=False,
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    compress_json=False,
)

# --- Bot and FastAPI Setup ---
bot_app = ApplicationBuilder().token(TOKEN).build()
app = FastAPI()

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome. Please provide an Instagram Post/Reel URL.")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    match = re.search(r"instagram\.com/(?:p|reel|tv)/([^/?]+)", text)
    if not match:
        await update.message.reply_text("Invalid URL. Please send a valid Instagram post link.")
        return

    shortcode = match.group(1)
    progress_msg = await update.message.reply_text("Processing your request, please wait...")

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        video_url = post.video_url

        if not video_url:
            await progress_msg.edit_text("A video could not be found in this post.")
            return

        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            caption="Video downloaded successfully.",
            supports_streaming=True
        )
        await progress_msg.delete()

    except Exception as e:
        print(f"An error occurred: {e}")
        await progress_msg.edit_text("Failed to process the request. The post may be private or an error occurred.")

# --- Application Startup and Authentication ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes the bot and authenticates the Instaloader session."""
    if not all([IG_USER_ID, IG_SESSIONID, IG_CSRFTOKEN]):
        raise ValueError("CRITICAL: One or more Instagram session variables are not set!")

    try:
        # This is the CORRECT way to load an existing session.
        # We manually construct the session dictionary that Instaloader expects.
        L.context.load_session(
            username=None,  # Username is not needed when loading a session
            session_data={
                "ds_user_id": IG_USER_ID,
                "sessionid": IG_SESSIONID,
                "csrftoken": IG_CSRFTOKEN,
            }
        )
        print("Instaloader session successfully authenticated using session details.")
        
        await bot_app.initialize()
        webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
        await bot_app.bot.set_webhook(url=webhook_url)
        await bot_app.start()
        print(f"🚀 Bot (Correct Instaloader Auth) started! Webhook: {webhook_url}")
        
        yield # The application is now running

    finally:
        # This will run when the application is shutting down
        print("Application is shutting down.")
        if bot_app.is_running:
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
