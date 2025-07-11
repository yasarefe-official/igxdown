import os
import logging
import requests # GitHub API'sine istek göndermek için
from uuid import uuid4

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# --- TEMEL AYARLAR ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ORTAM DEĞİŞKENLERİ (Koyeb'de ayarlanacak) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_PAT = os.getenv("GITHUB_PAT") # GitHub Personal Access Token
GITHUB_OWNER = os.getenv("GITHUB_OWNER") # Örneğin, sizin GitHub kullanıcı adınız
GITHUB_REPO = os.getenv("GITHUB_REPO") # Örneğin, "instagram-bot"
# Workflow dosyasının adı veya ID'si. Genellikle dosya adı yeterlidir.
GITHUB_WORKFLOW_ID = os.getenv("GITHUB_WORKFLOW_ID", "main.yml")

# Kontroller
if not all([TELEGRAM_TOKEN, GITHUB_PAT, GITHUB_OWNER, GITHUB_REPO]):
    missing_vars = [
        var_name for var_name, var_val in {
            "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
            "GITHUB_PAT": GITHUB_PAT,
            "GITHUB_OWNER": GITHUB_OWNER,
            "GITHUB_REPO": GITHUB_REPO
        }.items() if not var_val
    ]
    logger.critical(f"Eksik ortam değişkenleri: {', '.join(missing_vars)}. Uygulama başlatılamıyor.")
    exit()

# --- TELEGRAM HANDLER'LARI ---
def start_command(update: Update, context: CallbackContext):
    user_name = update.effective_user.first_name
    update.message.reply_html(
        f"Merhaba {user_name}! 👋\n\n"
        "Instagram'dan video veya Reel indirmek için bana linkini göndermen yeterli.\n"
        "Örneğin: <code>https://www.instagram.com/p/Cxyz123.../</code>\n\n"
        "Linkinizi gönderdikten sonra videonuz hazırlanacak ve size gönderilecektir. Bu işlem biraz zaman alabilir."
    )

def trigger_github_action(instagram_url: str, chat_id: str) -> bool:
    """Belirtilen Instagram URL'si için GitHub Actions workflow'unu tetikler."""
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW_ID}/dispatches"

    headers = {
        "Authorization": f"token {GITHUB_PAT}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    data = {
        "ref": "main", # Genellikle main branch kullanılır
        "inputs": {
            "instagram_url": instagram_url,
            "chat_id": str(chat_id) # Chat ID'nin string olması önemli olabilir
        }
    }

    try:
        response = requests.post(api_url, headers=headers, json=data, timeout=10) # 10 saniye timeout
        response.raise_for_status() # HTTP 4xx veya 5xx hatalarında exception fırlatır
        logger.info(f"GitHub Actions workflow başarıyla tetiklendi. URL: {instagram_url}, Chat ID: {chat_id}. Yanıt Kodu: {response.status_code}")
        return True
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"GitHub Actions API'sine istekte HTTP hatası: {http_err}")
        logger.error(f"Yanıt içeriği: {response.text if response else 'Yanıt yok'}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"GitHub Actions API'sine istekte hata: {req_err}")
    except Exception as e:
        logger.error(f"GitHub Actions tetiklenirken beklenmedik bir hata: {e}", exc_info=True)

    return False

def link_handler(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    video_url = update.message.text

    if "instagram.com/" not in video_url:
        update.message.reply_text("Lütfen geçerli bir Instagram video/reel linki gönderin.")
        return

    # Kullanıcıya ilk geri bildirimi ver
    update.message.reply_text("İsteğiniz alındı, video indirme işlemi başlatılıyor... cessing Lütfen bekleyin. ⏳")

    # GitHub Actions'ı tetikle
    success = trigger_github_action(instagram_url=video_url, chat_id=user_id)

    if success:
        # Actions'ın tamamlanmasını burada beklemiyoruz.
        # Actions, videoyu işleyip doğrudan kullanıcıya gönderecek.
        # İsteğe bağlı olarak burada farklı bir mesaj daha gönderilebilir veya hiç gönderilmeyebilir.
        # Örneğin: "Videonuz hazırlanıyor ve hazır olduğunda size gönderilecek."
        # Şimdilik ek bir mesaj göndermeyelim, Actions'tan video gelmesini beklesin kullanıcı.
        logger.info(f"Kullanıcı {user_id} için {video_url} indirme görevi GitHub Actions'a gönderildi.")
    else:
        update.message.reply_text(" माफ करा, şu anda video indirme işlemini başlatırken bir sorun oluştu. Lütfen daha sonra tekrar deneyin.") # Hintçe özür :)

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update '{update}' caused error '{context.error}'", exc_info=context.error)
    if update and update.effective_message:
        update.effective_message.reply_text("İşlem sırasında beklenmedik bir sorun oluştu. Lütfen daha sonra tekrar deneyin.")

# --- ANA UYGULAMA FONKSİYONU ---
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.regex(r'https?://www\.instagram\.com/(p|reel)/\S+'), link_handler))
    dispatcher.add_error_handler(error_handler)

    logger.info("Bot başlatıldı ve Koyeb üzerinde çalışıyor (GitHub Actions tetikleyici modunda).")

    # Koyeb gibi platformlar genellikle web sunucusu bekler.
    # Eğer bu script doğrudan çalıştırılacaksa (worker olarak), start_polling yeterli.
    # Eğer bir web framework (FastAPI, Flask) ile bir sağlık endpoint'i vb. sunulacaksa,
    # o zaman updater.start_polling() bir thread'de çalıştırılıp ana thread web sunucusunu yönetebilir.
    # Şimdilik basit bir worker olduğunu varsayalım:
    updater.start_polling()
    updater.idle()

    logger.info("Bot polling sonlandırıldı, uygulama kapatılıyor.")

if __name__ == '__main__':
    main()
