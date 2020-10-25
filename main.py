import subprocess
import logging
import os
import time
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, PicklePersistence
from telegram import ParseMode

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

# States
FILENAME, CONTENT, QUICK_FILENAME = range(3)

# pdf converter
DEFAULT_QUALITY = 100
MAGICK_BIN = 'convert'
MAGICK, IMG2PDF = range(2)
MAX_IMG_N = 100
MAX_FILENAME_LEN = 60

def pdfcmd(files, pdfname, type=MAGICK, quality=DEFAULT_QUALITY):
    if type == MAGICK:
        return MAGICK_BIN + ' ' + ' '.join(files) + f' -auto-orient -quality {quality} {pdfname}'
    elif type == IMG2PDF:
        return 'img2pdf ' + ' '.join(files) + ' -o ' + pdfname
    else:
        raise NotImplementedError()
pdf_converter = IMG2PDF


def compile_pdf(update, context):
    update.message.reply_text('compiling...\n' 'it can take up to several minutes')
    quality = context.user_data['quality'] if 'quality' in context.user_data else DEFAULT_QUALITY
    uid = update.message.from_user.id
    im_n = context.user_data['images']
    images = [f'cache/{uid}-{i}.jpg' for i in range(im_n)]
    pdfname = f'cache/{uid}.pdf'
    args = pdfcmd(images, pdfname, pdf_converter, quality)
    logger.info(f'compiling {im_n} photos into the {pdfname}:')
    try:
        t = time.time()
        result = subprocess.run(args, shell=True, capture_output=True, check=True, timeout=40)
        t = round(time.time() - t, 2)
        logger.info(f'compilation success in {t}s. uploading...')
        if result.returncode==0:
            update.message.reply_document(
                document=open(pdfname, 'rb'),
                filename=context.user_data['filename'] + '.pdf'
            )
            os.remove(pdfname)
            update.message.reply_text('here is your pdf')
            logger.info(f'done uploading')
        else:
            update.message.reply_text('unknown error. try again later.')
            logger.exception(f'returncode != 0')

        for i in images:
            os.remove(i)
    except subprocess.TimeoutExpired as err:
        update.message.reply_text('pdf compilation took too long. try adding less photos or using compression instead of jpg files.')
        logger.error("compiler error. too long: " + err.cmd + "\n>>>" + err.output + "<<<")
    except OSError as err:
        update.message.reply_text('bot error. try again later.')
        logger.error("compiler error:\n" + str(err))

# --------------------------
def newpdf(user, quick=False):
    """Start new PDF"""
    ustr = str(user.id)
    if user.username:
        ustr += f"(t.me/{user.username})"
    q = "quick " if quick else ""
    logger.info(f"New {q}pdf u{ustr}")

def newpdf_handler(update, context):
    user = update.message.from_user
    newpdf(user)
    update.message.reply_text(f"New PDF. Enter document name", parse_mode=ParseMode.HTML)
    return FILENAME

def invalid_filename(update, context):
    """Prompt one more time"""
    update.message.reply_text(
        "Invalid name. Please, use only <code>a-z, A-Z, 0-9, _, .</code> and space characters. Try again or send /cancel",
        parse_mode=ParseMode.HTML)
    return FILENAME

def filename_input(update, context):
    context.user_data['filename'] = update.message.text.strip().split('\n')[0].rstrip()[:MAX_FILENAME_LEN]
    
    if 'quick' in context.user_data:
        compile_pdf(update, context)
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data['images'] = 0
    update.message.reply_text(
        f'Got it. Now send content of your pdf - photos or *.jpg files. '
        'When you are ready to compile pdf, send /compile. Send /cancel to cancel.\n'
        # '<i>Note: pdf pages will have the same orientation as original images. Therefore you need to rotate them before sending</i>'
        ,parse_mode=ParseMode.HTML
    )
    return CONTENT

def save_img(file, update, context):
    if not 'images' in context.user_data:
        # Quick way
        newpdf(update.message.from_user, True)
        context.user_data['images'] = 0
        context.user_data['quick'] = True
        update.message.reply_text('New PDF. Send /compile to finish when you are ready. Send /cancel to cancel.')
    elif context.user_data['images'] >= MAX_IMG_N:
        update.message.reply_text("Sorry, maximum image number reached.\n/compile or /cancel")
        return CONTENT
    im_id = context.user_data['images']
    uid = update.message.from_user.id
    file.download(f'cache/{uid}-{im_id}.jpg')
    update.message.reply_text(f'image {im_id+1} - ok')
    context.user_data['images'] = im_id+1
    return CONTENT

def addfile(update, context):
    """input: .jpg file"""
    image = update.message.document.get_file()
    save_img(image, update, context)
    return CONTENT

def addphoto(update, context):
    """input: tg photo"""
    image = update.message.photo[-1].get_file()
    save_img(image, update, context)
    return CONTENT

def compile_handler(update, context):
    if 'quick' in context.user_data:
        update.message.reply_text("Enter document name")
        return FILENAME
    compile_pdf(update, context)
    context.user_data.clear()
    return ConversationHandler.END

def cancel(update, context):
    update.message.reply_text("Okay, aborting.")
    if 'images' in context.user_data:
        uid = update.message.from_user.id
        im_n = context.user_data['images']
        images = [f'cache/{uid}-{i}.jpg' for i in range(im_n)]
        try:
            for i in images:
                os.remove(i)
        except OSError as err:
            logger.error(f'Cancelling u{uid}. Something gone wrong while deleting cache.\n'+str(err))
    context.user_data.clear()
    return ConversationHandler.END

def quality(update, context):
    q = context.args[0]
    try:
        q = int(q)
        if q > 100 or q < 10:
            update.message.reply_text('invalid quality. enter integer from 10 to 100')
        else:
            context.user_data['quality'] = q
            update.message.reply_text(f'jpg quality is now {q}%')
    except:
        update.message.reply_text('invalid quality. enter integer from 10 to 100')

    context.user_data.clear()
    return ConversationHandler.END
# -------------------------

def help_handler(update, context):
    update.message.reply_text(
        'I can create PDF from your images: photos (sent with telegram compression, \'as photo\') and *.jpg files (sent without compression, \'as file\').\n'
        'There are 2 ways:\n'
        '1. send /start or /newpdf, enter pdf name then send images;\n'
        '2. just send me some images, then /compile and enter pdf name.\n'
        'You can cancel operation anytime using /cancel; then you will be able to start again.\n'
        '<i>By the way, I delete all your images right after sending you PDF.</i>\n\n'
        'also pls consider donating (servers aren\'t free) - 4441114448609220',
        parse_mode=ParseMode.HTML
    )

# -------------------------

def main():
    if not os.path.exists("cache"):
        os.mkdir("cache")

    token = None
    try:
        with open('token') as f:
            token = f.read()
    except IOError as ioerr:
        logger.fatal("Can't access API token file")
        logger.fatal(ioerr)
    except:
        logger.fatal("Can't get API token. Aborting.")

    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(token, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler(['start','newpdf'], newpdf_handler), # Classic way
            MessageHandler(Filters.document.jpg, addfile), # Quick way
            MessageHandler(Filters.photo, addphoto)
        ],
        states={
            FILENAME: [
                # MessageHandler(Filters.regex(r'^[a-zA-Z0-9_][a-zA-Z0-9_.]*$'), filename_input),
                MessageHandler(Filters.text & ~Filters.command, filename_input),
                # MessageHandler(~Filters.command, invalid_filename)
            ],
            CONTENT: [
                MessageHandler(Filters.document.jpg, addfile),
                MessageHandler(Filters.photo, addphoto),
                CommandHandler('compile', compile_handler)
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel)
        ]
    )

    # dp.add_handler(CommandHandler('quality', quality))
    dp.add_handler(CommandHandler('help', help_handler))
    dp.add_handler(conv_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()