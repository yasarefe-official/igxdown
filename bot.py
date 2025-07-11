import os
import logging
from uuid import uuid4
import shutil

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import instaloader

# --- TEMEL AYARLAR ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ORTAM DEĞİŞKENLERİ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SESSION_ID = os.getenv("INSTAGRAM_SESSIONID") # Opsiyonel, kullanıcı tarafından sağlanabilir

if not TELEGRAM_TOKEN:
    logger.critical("TELEGRAM_TOKEN ortam değişkeni eksik. Uygulama başlatılamıyor.")
    exit()

# --- TELEGRAM HANDLER'LARI ---
def start_command(update: Update, context: CallbackContext):
    user_name = update.effective_user.first_name
    update.message.reply_html(
        f"Merhaba {user_name}! 👋\n"
        "Bana bir Instagram Reel veya video linki gönder, senin için indirmeye çalışacağım.\n\n"
        "Eğer indirme işlemi başarısız olursa, özel videolar için Instagram `sessionid`'nizi ayarlamanız gerekebilir. "
        "Bu konuda daha sonra size bilgi vereceğim."
    )

def link_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    video_url = update.message.text

    if "instagram.com/" not in video_url:
        update.message.reply_text("Lütfen geçerli bir Instagram video/reel linki gönderin.")
        return

    context.bot.send_message(chat_id=user_id, text="Video talebin alındı, indirme işlemi başlatılıyor... ⏳")

    L = instaloader.Instaloader(
        download_pictures=False, download_video_thumbnails=False,
        download_geotags=False, download_comments=False,
        save_metadata=False, compress_json=False,
        max_connection_attempts=1 # Hızlı fail etmesi için
    )

    # Session ID kullanarak giriş yapmayı dene (eğer ayarlanmışsa)
    if SESSION_ID:
        try:
            logger.info(f"Sağlanan INSTAGRAM_SESSIONID ile giriş deneniyor.")
            L.context.username = "dummy_user_for_session_id_usage" # Instaloader'ın sessionid'yi kullanması için bir kullanıcı adı gerekir
            L.context.login(L.context.username, "dummy_password") # Şifre kullanılmaz ama fonksiyon çağrılmalı
            L.context.session.cookies.update({"sessionid": SESSION_ID})

            # Girişin başarılı olup olmadığını test etmek için basit bir istek
            # Bu kısım gerçek bir kullanıcı profili çekmeye çalışacağı için dikkatli olunmalı,
            # veya daha hafif bir test endpoint'i bulunmalı. Şimdilik bu adımı atlayalım
            # L.test_login()
            logger.info("INSTAGRAM_SESSIONID başarıyla yüklendi.")
        except Exception as e:
            logger.warning(f"INSTAGRAM_SESSIONID ile giriş yaparken hata oluştu: {e}. Anonim indirme denenecek.")
            # Session ID ile giriş başarısız olursa, anonim devam et
            L = instaloader.Instaloader(
                download_pictures=False, download_video_thumbnails=False,
                download_geotags=False, download_comments=False,
                save_metadata=False, compress_json=False, max_connection_attempts=1
            )
    else:
        logger.info("INSTAGRAM_SESSIONID ayarlanmamış. Anonim indirme denenecek.")

    target_dir = f"temp_{user_id}_{uuid4()}"

    try:
        logger.info(f"Video indiriliyor: {video_url}")

        # URL'den shortcode'u çıkar
        if "/p/" in video_url:
            shortcode = video_url.split("/p/")[-1].split("/")[0]
        elif "/reel/" in video_url:
            shortcode = video_url.split("/reel/")[-1].split("/")[0]
        else:
            update.message.reply_text("Link formatı anlaşılamadı. Lütfen .../p/SHORTCODE/... veya .../reel/SHORTCODE/... formatında bir link gönderin.")
            return

        post = instaloader.Post.from_shortcode(L.context, shortcode)

        if not post.is_video:
            update.message.reply_text("Bu link bir video içeriğine ait değil gibi görünüyor.")
            return

        os.makedirs(target_dir, exist_ok=True)
        L.download_post(post, target=target_dir)

        video_path = None
        for filename in os.listdir(target_dir):
            if filename.endswith('.mp4'):
                video_path = os.path.join(target_dir, filename)
                break

        if video_path:
            logger.info(f"Video başarıyla indirildi: {video_path}")
            with open(video_path, 'rb') as video_file:
                context.bot.send_video(chat_id=user_id, video=video_file, caption="İşte videon! ✅", timeout=120) # Video gönderme süresini artır
            update.message.reply_text("Video başarıyla gönderildi!")
        else:
            raise FileNotFoundError("İndirilen video dosyası sunucuda bulunamadı.")

    except instaloader.exceptions.ProfileNotExistsException:
        logger.warning(f"Profil bulunamadı veya gizli: {video_url}")
        update.message.reply_text(
            "Bu video indirilemedi. Profil gizli olabilir veya video mevcut olmayabilir. "
            "Eğer video özelse ve INSTAGRAM_SESSIONID ayarlamadıysanız, bu bir sebep olabilir."
        )
    except instaloader.exceptions.PrivateProfileNotFollowedException:
        logger.warning(f"Özel profil takip edilmiyor: {video_url}")
        update.message.reply_text(
            "Bu video indirilemedi çünkü özel bir hesaba ait ve hesap takip edilmiyor (veya geçerli bir sessionid sağlanmadı)."
        )
    except instaloader.exceptions.LoginRequiredException:
        logger.warning(f"Giriş gerektiren video: {video_url}")
        update.message.reply_text(
            "Bu videoyu indirmek için Instagram'a giriş yapmak gerekiyor. Lütfen `INSTAGRAM_SESSIONID` ortam değişkenini ayarlayın. "
            "Bu değişkeni nasıl alacağınız konusunda README dosyasını kontrol edebilirsiniz."
        )
    except instaloader.exceptions.ConnectionException as e:
        logger.error(f"Bağlantı hatası ({video_url}): {e}")
        update.message.reply_text("Instagram'a bağlanırken bir sorun oluştu. Lütfen daha sonra tekrar deneyin.")
    except Exception as e:
        logger.error(f"Genel indirme hatası ({video_url}): {e}", exc_info=True)
        update.message.reply_text(f"Video indirilirken beklenmedik bir hata oluştu. 😞\n\n<b>Hata:</b> {type(e).__name__}", parse_mode="HTML")
    finally:
        if os.path.exists(target_dir):
            try:
                shutil.rmtree(target_dir)
                logger.info(f"Geçici klasör {target_dir} temizlendi.")
            except Exception as e:
                logger.error(f"Geçici klasör {target_dir} temizlenirken hata: {e}")

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update '{update}' caused error '{context.error}'", exc_info=context.error)
    if update and update.effective_message:
        update.effective_message.reply_text("Bir hata oluştu. Geliştiriciler bilgilendirildi.")

# --- ANA UYGULAMA FONKSİYONU ---
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.regex(r'https?://www\.instagram\.com/(p|reel)/\S+'), link_handler))
    dispatcher.add_error_handler(error_handler)

    # Botu başlat
    updater.start_polling()
    logger.info("Bot başlatıldı ve polling modunda çalışıyor.")

    # Bot, GitHub Actions'ın timeout-minutes ayarı ile yönetileceği için
    # burada ek bir zamanlayıcıya veya döngüye gerek yoktur.
    # Polling işlemini başlatmak yeterlidir, Actions job'ı sonlandığında
    # script de sonlanacaktır.
    # Ancak, düzgün bir kapanış (shutdown) sağlamak için updater.idle() kullanılabilir.
    # Bu, SIGINT, SIGTERM gibi sinyalleri yakalayarak botun düzgün kapanmasını sağlar.
    # GitHub Actions job'ı sonlandığında SIGTERM gönderir.
    updater.idle() # Botu sinyal gelene kadar çalışır durumda tutar

    # idle() sonlandıktan sonra (örneğin bir sinyal ile), kapanış mesajı loglanabilir.
    # shutdown() fonksiyonu artık doğrudan idle() tarafından yönetildiği için burada ayrıca çağrılmaz.
    logger.info("Bot polling sonlandırıldı, uygulama kapatılıyor.")


if __name__ == '__main__':
    # Sinyal işleyicilerini (signal.signal) burada tanımlamaya gerek yok,
    # çünkü python-telegram-bot'un Updater.idle() metodu bunları zaten ele alıyor.
    main()
