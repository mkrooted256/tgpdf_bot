import subprocess
import logging
import os
import time
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler
from telegram import ParseMode

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

# States
FILENAME, CONTENT = range(2)

# pdf converter
DEFAULT_QUALITY = 100
MAGICK_BIN = 'convert'
MAGICK, IMG2PDF = range(2)

def pdfcmd(files, pdfname, type=MAGICK, quality=DEFAULT_QUALITY):
    if type == MAGICK:
        return MAGICK_BIN + ' ' + ' '.join(files) + f' -auto-orient -quality {quality} {pdfname}'
    elif type == IMG2PDF:
        return 'img2pdf ' + ' '.join(files) + ' -o ' + pdfname
    else:
        raise NotImplementedError()
pdf_converter = IMG2PDF

# Define a few command handlers. These usually take the two arguments update and
# context. Error handlers also receive the raised TelegramError object in error.
def start(update, context):
    """Send a message when the command /start is issued."""
    update.message.reply_text('Hi!')


def help_command(update, context):
    """Send a message when the command /help is issued."""
    update.message.reply_text('Help!')


def echo(update, context):
    """Echo the user message."""
    update.message.reply_text(update.message.text)

# --------------------------
def newpdf(update, context):
    """Start new PDF"""
    update.message.reply_text("New PDF. Enter document name (`[a-zA-Z0-9_.]`)")
    return FILENAME

def invalid_filename(update, context):
    """Prompt one more time"""
    update.message.reply_text("Invalid name. Please, use only `a-z, A-Z, 0-9, _` and `.` characters. Try again or send /cancel")
    return FILENAME

def filename_input(update, context):
    """valid filename entered. proceed to content"""
    context.user_data['filename'] = update.message.text
    context.user_data['images'] = 0
    update.message.reply_text(
        f'Got it. Now send content of the <code>{update.message.text}.pdf</code> (*.jpg files without tg compression or any tg-compressed images)\n'
        'When you are ready to compile pdf, send /compile. Send /cancel to cancel.\n'
        '<i>Note: pdf pages will have the same orientation as original images. Therefore you need to rotate them before sending</i>',
        parse_mode=ParseMode.HTML
    )
    return CONTENT

def addfile(update, context):
    """input: .jpg file"""
    uid = update.message.from_user.id
    im_id = context.user_data['images']
    image = update.message.document.get_file()
    image.download(f'cache/{uid}-{im_id}.jpg')
    context.user_data['images'] += 1
    update.message.reply_text(f'image {im_id+1} - ok')
    return CONTENT

def addphoto(update, context):
    """input: tg photo"""
    uid = update.message.from_user.id
    im_id = context.user_data['images']
    image = update.message.photo[-1].get_file()
    image.download(f'cache/{uid}-{im_id}.jpg')
    context.user_data['images'] += 1
    update.message.reply_text(f'image {im_id+1} - ok')
    return CONTENT
    
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
        logger.info(f'compilation success in {t}s.')
        if result.returncode==0:
            update.message.reply_text('here is your pdf')
            update.message.reply_document(
                document=open(pdfname, 'rb'),
                filename=context.user_data['filename'] + '.pdf'
            )
            os.remove(pdfname)
        else:
            update.message.reply_text('unknown error. try again later.')

        for i in images:
            os.remove(i)
    except subprocess.CalledProcessError as err:
        update.message.reply_text('bot error. try again later.')
        logger.error("magick error: " + err.cmd + "\n>>>" + err.output + "<<<")
    except subprocess.TimeoutExpired as err:
        update.message.reply_text('pdf compilation took too long. try adding less photos or using compression instead of jpg files.')
        logger.error("magick too long: " + err.cmd + "\n>>>" + err.output + "<<<")
    except err:
        logger.error(err)

    context.user_data.clear()
    return ConversationHandler.END

def cancel(update, context):
    update.message.reply_text("Okay, aborting.")
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

def main():
    if not os.path.exists("cache"):
        os.mkdir("cache")

    token = None
    with open('token') as f:
        token = f.read()
    if (token is None):
        logger.fatal("API Token file not found. Aborting.")
        return

    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(token, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler(['start','newpdf'], newpdf)],
        states={
            FILENAME: [
                MessageHandler(Filters.regex(r'^[a-zA-Z0-9_][a-zA-Z0-9_.]*$'), filename_input),
                MessageHandler(~Filters.command, invalid_filename)
            ],
            CONTENT: [
                MessageHandler(Filters.document.jpg, addfile),
                MessageHandler(Filters.photo, addphoto),
                CommandHandler('compile', compile_pdf)
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel)
        ]
    )

    dp.add_handler(CommandHandler('quality', quality))
    dp.add_handler(conv_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()