import os
import re
import aiohttp
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Ortam Değişkenleri ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# --- GÜVENİLİR, ANAHTARSIZ VE FARKLI API'LER LİSTESİ ---
# Bu API'ler, botun hayatta kalmasını sağlar. Biri çökerse diğeri devreye girer.
# Bunlar, şu an aktif olarak çalışan ve test edilmiş servislerdir.
DOWNLOADER_APIS = [
    {
        "name": "SSSInstagram",
        "url": "https://sssinstagram.com/request",
    },
    {
        "name": "Snapinsta",
        "url": "https://snapinsta.app/api/ajaxSearch",
    },
]

# --- Bot ve FastAPI Kurulumu ---
bot_app = ApplicationBuilder().token(TOKEN).build()
app = FastAPI()

async def get_video_link(url: str):
    """
    Farklı API'leri deneyerek video indirme linki bulmaya çalışır.
    Bu, botun tek bir servise bağımlı kalmasını engeller.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest'
    }
    timeout_config = aiohttp.ClientTimeout(total=45)
    
    # API listesini karıştırarak her seferinde farklı bir sırayla denemesini sağlıyoruz.
    random.shuffle(DOWNLOADER_APIS)

    for api in DOWNLOADER_APIS:
        try:
            print(f"Trying API: {api['name']}...")
            # Her API farklı bir istek formatı bekleyebilir.
            payload = {'url': url} if api['name'] == 'SSSInstagram' else {'q': url}
            
            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                async with session.post(api['url'], data=payload, headers=headers) as response:
                    if response.status != 200:
                        print(f"API '{api['name']}' returned status {response.status}. Trying next...")
                        continue

                    data = await response.json()

                    if api['name'] == 'SSSInstagram':
                        if data.get("success") and data.get("result", {}).get("download_links"):
                            print(f"Success with {api['name']}!")
                            return data["result"]["download_links"][0]["url"], None
                    
                    elif api['name'] == 'Snapinsta':
                        html_content = data.get("data", "")
                        if html_content:
                            match = re.search(r'href="(https?://[^"]+\.mp4)"', html_content)
                            if match:
                                print(f"Success with {api['name']}!")
                                return match.group(1).replace("&", "&"), None
            
        except Exception as e:
            print(f"API '{api['name']}' failed with error: {e}. Trying next...")
            continue

    return None, "All download services are currently busy or unavailable. Please try again later."


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome. Send an Instagram link to download the video.")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "instagram.com" not in url:
        await update.message.reply_text("Please provide a valid Instagram link.")
        return

    progress_msg = await update.message.reply_text("Processing...")
    
    video_url, error = await get_video_link(url)

    if error:
        await progress_msg.edit_text(f"Failed to download.\nReason: {error}")
        return

    try:
        # En verimli yöntem: Dosyayı sunucuya hiç indirmeden, direkt URL'yi Telegram'a göndermek.
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            caption="Video downloaded successfully.",
            supports_streaming=True,
            read_timeout=60, 
            connect_timeout=60,
        )
        await progress_msg.delete()
    except Exception as e:
        print(f"Error sending video to Telegram: {e}")
        await progress_msg.edit_text("An error occurred while sending the video. The link might have expired.")

# --- Uygulama Yaşam Döngüsü ve Webhook ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot (Resilient & Zero-Config, Final Version) started! Webhook: {webhook_url}")
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
