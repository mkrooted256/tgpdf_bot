import subprocess
import logging
import requests
import os
import time
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, PicklePersistence
from telegram import ParseMode, Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove

from constants import *

S = StringSupplier()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

token = None

if "BOT_TOKEN" in os.environ:
    token = os.environ.get("BOT_TOKEN", None)
else:
    logger.fatal("Can't get API token. Aborting.")
    exit()

def pdfcmd(files, pdfname, type=MAGICK, quality=DEFAULT_QUALITY):
    # if type == MAGICK:
    #     return MAGICK_BIN + ' ' + ' '.join(files) + f' -auto-orient -quality {quality} {pdfname}'
    # elif type == IMG2PDF:
    #     return 'img2pdf ' + ' '.join(files) + ' -o ' + pdfname
    # else:
    #     raise NotImplementedError()
    return 'img2pdf ' + ' '.join(files) + ' -o ' + pdfname


def compile_pdf(update, context):
    def handle_compiler_error(message):
        if 'exhausted' in str(message):
            logger.error("compiler error. resources exhausted.")
            if context.user_data['largefiles']:
                update.message.reply_text(S('tg_err_too_big_largefiles'), parse_mode=ParseMode.HTML)
            else:                
                update.message.reply_text(S('tg_err_too_big'))
            return True
        return False


    update.message.reply_text(S('tg_info_start_compiling'), reply_markup=ReplyKeyboardRemove())
    quality = context.user_data['quality'] if 'quality' in context.user_data else DEFAULT_QUALITY
    
    uid = update.message.from_user.id
    ustr = str(uid)
    if update.message.from_user.username:
        ustr += f"(t.me/{update.message.from_user.username})"
        

    images = context.user_data['images'] # [f'cache/{uid}-{i}' for i in range(im_n)]
    pdfname = f'cache/{uid}.pdf'

    # magick is better for large. otherwise pdf is too large
    pdf_converter = MAGICK if context.user_data['largefiles'] else IMG2PDF 
    
    args = pdfcmd(images, pdfname, pdf_converter, quality)
    logger.info(f'u{ustr} compiling {len(images)} photos, {pdf_converter} -> {pdfname}:')
    try:
        t = time.time()
        result = subprocess.run(args, shell=True, capture_output=True, check=True, timeout=40)
        t = round(time.time() - t, 2)
        fsize = os.stat(pdfname).st_size
        fsize_h = fsize/1000000
        logger.info(f'u{ustr} compilation ended in {t}s, {fsize_h}MB')

        if result.returncode==0:
            
            if fsize >= MAX_PDFSIZE:
                if context.user_data['largefiles']:
                    update.message.reply_text(S('tg_err_pdf_too_big_largefiles'), parse_mode=ParseMode.HTML)
                else:
                    update.message.reply_text(S('tg_err_pdf_too_big'), parse_mode=ParseMode.HTML)

                logger.error(f"{pdfname} too large: {fsize_h}MB")
            else:
                logger.info("uploading "+pdfname)
                update.message.reply_document(
                    document=open(pdfname, 'rb'),
                    filename=context.user_data['filename'] + '.pdf'
                )
                update.message.reply_text(S('tg_info_pdf_success'))
                logger.info(f'done uploading')
            os.remove(pdfname)
        else:
            logger.exception(f'but returncode != 0')
            update.message.reply_text(S('tg_err_unknown_error'))

        for i in images:
            os.remove(i)
    except subprocess.TimeoutExpired as err:
        update.message.reply_text(S('tg_err_timeout'), parse_mode=ParseMode.HTML)
        logger.error("compiler error. too long: " + err.cmd + "\n>>>" + err.output + "<<<")
    except subprocess.CalledProcessError as err:
        if not handle_compiler_error(err.stderr):
            update.message.reply_text(S('tg_err_bot'))
        logger.error("compiler error. code not 0.\n    cmd>>>%s<<<\n    stdout>>> %s <<<\n    stderr>>> %s <<<", err.cmd, err.stdout, err.stderr)
    except Exception as err:
        update.message.reply_text(S('tg_err_bot'))
        logger.error("Exception!!!:\n" + str(err))

# --------------------------
def newpdf(user, quick=False):
    """Start new PDF"""
    ustr = str(user.id)
    if user.username:
        ustr += f"(t.me/{user.username})"
    q = "quick " if quick else ""
    logger.info(f"u{ustr} New {q}pdf")

def newpdf_handler(update, context):
    context.user_data['largefiles'] = False
    user = update.message.from_user
    newpdf(user)
    update.message.reply_text(S('tg_info_newpdf'), parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    return FILENAME

def filename_input(update, context):
    context.user_data['filename'] = update.message.text.strip().split('\n')[0].rstrip()[:MAX_FILENAME_LEN]
    
    if 'quick' in context.user_data:
        compile_pdf(update, context)
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data['images'] = []
    update.message.reply_text(S('tg_info_newpdf_name_accepted'), parse_mode=ParseMode.HTML)
    return CONTENT

def save_img(file, update, context):
    uid = update.message.from_user.id
    try:
        if not 'images' in context.user_data:
            # Quick way
            newpdf(update.message.from_user, True)
            context.user_data['images'] = []
            context.user_data['quick'] = True
            context.user_data['largefiles'] = False # set True after first large file
            update.message.reply_text(S('tg_info_newpdf_quick'))
        elif len(context.user_data['images']) >= MAX_IMG_N:
            update.message.reply_text(S('tg_info_max_imgs'), quote=True)
            return
        
        images = context.user_data['images']
        im_n = len(images)

        # try to get file type
        dot_index = file.file_path.rfind('.')
        if dot_index == -1:
            update.message.reply_text(S('tg_err_no_img_format').format(im_n+1), quote=True)
            return
        filetype = file.file_path[dot_index:]
        if not filetype in ['.jpg', '.jpeg', '.png', '.gif']:
            update.message.reply_text(S('tg_err_unsupported_img_format').format(im_n+1), quote=True)
            return
        filename = f'cache/{uid}-{im_n}{filetype}'
        file.download(filename)
        images.append(filename)

        update.message.reply_text(S('tg_info_img_ok').format(im_n+1), quote=True
        , reply_markup=ReplyKeyboardMarkup([["/compile 🎉"],["/cancel ❌", "/help ℹ"]]))
    except Exception as err:
        ustr = str(uid)
        if update.message.from_user.username:
            ustr += f"(t.me/{update.message.from_user.username})"
        logger.error(f"u{ustr} Error saving image: " + str(err))
        update.message.reply_text(S('tg_err_img_error').format(im_n+1), quote=True)

def addfile(update, context):
    """input: .jpg file"""
    context.user_data['largefiles'] = True
    image = update.message.document.get_file()
    save_img(image, update, context)
    return CONTENT

def addphoto(update, context):
    """input: tg photo"""
    image = update.message.photo[-1].get_file()
    save_img(image, update, context)
    return CONTENT

def compile_handler(update, context):
    # no images
    if not (context.user_data['images']):
        update.message.reply_text(S('tg_info_no_imgs'))
        return CONTENT

    if 'quick' in context.user_data:
        update.message.reply_text(S('tg_info_enter_name'))
        return FILENAME
    compile_pdf(update, context)
    context.user_data.clear()
    return ConversationHandler.END

def cancel(update, context):
    update.message.reply_text(S('tg_info_cancel'), reply_markup=ReplyKeyboardRemove())
    if 'images' in context.user_data:
        uid = update.message.from_user.id
        images = context.user_data['images']
        try:
            for i in images:
                os.remove(i)
        except OSError as err:
            ustr = str(uid)
            if update.message.from_user.username:
                ustr += f"(t.me/{update.message.from_user.username})"
            logger.error(f'u{ustr} while cancel: Something gone wrong while deleting cache.\n'+str(err))
    context.user_data.clear()
    return ConversationHandler.END

# -------------------------

def help_handler(update, context):
    update.message.reply_text(S('tg_help'), parse_mode=ParseMode.HTML)

def unknown_handler(update, context):
    update.message.reply_text(S('tg_err_unknown_cmd'), quote=True)

# -------------------------

def edit_handler(update, context):
    update.message.reply_text(S('tg_err_unimplemented'))
    # TODO

def edit_content(update, context):
    # TODO
    pass

# -------------------------

def signal_handler(signal, frame):
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage", 
        data={'chat_id': 211399446,  'text': f"@abstractpdf_bot is down with signal {signal}"}
    )

def main():
    if not os.path.exists("cache"):
        os.mkdir("cache")

    logger.info("Starting up")
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(token, use_context=True, user_sig_handler=signal_handler)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler(['start','newpdf'], newpdf_handler), # Classic way
            MessageHandler(Filters.document.jpg | Filters.document.mime_type("image/png"), addfile), # Quick ways
            MessageHandler(Filters.photo, addphoto)
        ],
        states={
            FILENAME: [
                # MessageHandler(Filters.regex(r'^[a-zA-Z0-9_][a-zA-Z0-9_.]*$'), filename_input),
                MessageHandler(Filters.text & ~Filters.command, filename_input),
                # MessageHandler(~Filters.command, invalid_filename)
            ],
            CONTENT: [
                MessageHandler(Filters.document.jpg | Filters.document.mime_type("image/png"), addfile),
                MessageHandler(Filters.photo, addphoto),
                CommandHandler('compile', compile_handler),
                #
                # MessageHandler(Filters.updates.edited_message, edit_content)
                #
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(Filters.all, unknown_handler)
        ]
    )

    # dp.add_handler(CommandHandler('quality', quality))
    dp.add_handler(CommandHandler('help', help_handler))
    dp.add_handler(conv_handler)
    dp.add_handler(MessageHandler(Filters.all, unknown_handler))

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()