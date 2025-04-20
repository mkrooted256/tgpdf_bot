import subprocess
import logging
import requests
import os
import time
from telegram.ext import Application, Updater, CommandHandler, MessageHandler, filters as Filters, ConversationHandler, PicklePersistence
from telegram import Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode

import shutil
import multiprocessing
from multiprocessing import Process
import pathlib
import pymupdf
from PIL import Image, ImageOps

from constants import *


S = StringSupplier()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

token = None
if "BOT_TOKEN" in os.environ:
    token = os.environ.get("BOT_TOKEN", None)
elif os.path.exists('token.txt'):
    try:
        with open('token.txt') as f:
            token = f.read().strip()
    except OSError as e:
        logger.error("found token.txt but cannot read.")
if token is None:
    logger.fatal("Can't get API token. Aborting.")
    exit()

# V2. Always pymupdf. If pdf is too large, try again with lower quality several times.

def clear_user_cache(uid):
    try:
        shutil.rmtree(f'cache/{uid}')
    except OSError as err:
        logger.error(f'u{uid} while cancel: Something gone wrong while deleting cache.\n'+str(err))

def __pymupdf_compile_pdf(images, filename, quality):
    doc = pymupdf.open()
    for img_path in images:
        image = Image.open(img_path)
        if quality != 'high':
            img_path = img_path + '.small.jpg'
            image.save(img_path, 'jpeg', quality=75)
        doc.insert_file(img_path)
    doc.save(filename)

async def compile_pdf(update, context):
    # start using original image quality. lower quality until success.
    qs = ['high', 'mid']
    for quality in qs:
        await update.message.reply_text(S(f'tg_info_start_compiling_{quality}'), reply_markup=ReplyKeyboardRemove())
        
        uid = update.message.from_user.id
        ustr = str(uid)
        if update.message.from_user.username:
            ustr += f"(t.me/{update.message.from_user.username})"
        
        images = context.user_data['images'] # [f'cache/{uid}-{i}' for i in range(im_n)]
        pdfname = f'cache/{uid}/out.pdf'
        pdf_converter = 'pymupdf'
        
        logger.info(f'u{ustr} compiling {len(images)} photos, Q={quality}, {pdf_converter} -> {pdfname}:')

        try:
            # todo use background jobs in the python tg library
            p = Process(target=__pymupdf_compile_pdf, args=(images, pdfname, quality))
            t0 = time.perf_counter()
            p.start()
            p.join(timeout=40.0)
            if p.is_alive():
                # timeout
                p.terminate()
                await update.message.reply_text(S('tg_err_timeout'))
                logger.error("u{ustr} compiler: too long.")
                return
            
            t = time.perf_counter() - t0
            fsize = os.stat(pdfname).st_size
            fsize_h = fsize/1000000
            logger.info(f'u{ustr} compilation ended in {t:.2}s, {fsize_h}MB')

            if p.exitcode != 0:
                await update.message.reply_text(S('tg_err_unknown_error'))
                logger.error(f'u{ustr} returncode != 0, unknown error.')
                return
            if fsize >= MAX_PDFSIZE:
                # too big. notify user and try lower quality
                await update.message.reply_text(S('tg_warn_quality_too_high'))
                logger.info(f"pdf {pdfname} too large: {fsize_h}MB. Trying lower quality")
                continue
            
            # seems to be ok. upload and send pdf
            logger.info("uploading "+pdfname)
            await update.message.reply_document(
                document=open(pdfname, 'rb'),
                filename=context.user_data['filename'] + '.pdf'
            )
            await update.message.reply_text(S('tg_info_pdf_success'))
            logger.info(f'done uploading')
            return
            

        except Exception as err:
            await update.message.reply_text(S('tg_err_bot'))
            logger.error("Exception!!!:\n" + str(err))
    
    # lowest quality is still too big
    await update.message.reply_text(S('tg_err_pdf_too_big'))
    logger.info(f"pdf {pdfname} too large: {fsize_h}MB. End.")


# --------------------------
def newpdf(user, quick=False):
    """Start new PDF"""
    ustr = str(user.id)
    if user.username:
        ustr += f"(t.me/{user.username})"
    q = "quick " if quick else ""
    logger.info(f"u{ustr} New {q}pdf")

async def newpdf_handler(update, context):
    user = update.message.from_user
    newpdf(user)
    await update.message.reply_text(S('tg_info_newpdf'), parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    return FILENAME

async def filename_input(update, context):
    context.user_data['filename'] = update.message.text.strip().split('\n')[0].rstrip()[:MAX_FILENAME_LEN]
    
    # filename provided, yes images, proceed
    if 'quick' in context.user_data:
        await compile_pdf(update, context)
        context.user_data.clear()
        return ConversationHandler.END

    # start waiting for images
    context.user_data['images'] = []
    await update.message.reply_text(S('tg_info_newpdf_name_accepted'), parse_mode=ParseMode.HTML)
    return CONTENT

async def save_img(file, update, context):
    uid = update.message.from_user.id
    try:
        if not 'images' in context.user_data:
            # Quick way
            newpdf(update.message.from_user, True)
            context.user_data['images'] = []
            context.user_data['quick'] = True
            await update.message.reply_text(S('tg_info_newpdf_quick'))
        elif len(context.user_data['images']) >= MAX_IMG_N:
            await update.message.reply_text(S('tg_info_max_imgs'), do_quote=True)
            return
        
        images = context.user_data['images']
        im_n = len(images)

        # try to get file type
        dot_index = file.file_path.rfind('.')
        if dot_index == -1:
            await update.message.reply_text(S('tg_err_no_img_format').format(im_n+1), do_quote=True)
            return
        filetype = file.file_path[dot_index:].lower()
        if not filetype in ['.jpg', '.jpeg', '.png', '.gif']:
            await update.message.reply_text(S('tg_err_unsupported_img_format').format(im_n+1), do_quote=True)
            return
        
        os.makedirs(f'cache/{uid}', exist_ok=True)
        filename = f'cache/{uid}/{im_n}{filetype}'
        
        await file.download_to_drive(filename)
        images.append(filename)

        await update.message.reply_text(S('tg_info_img_ok').format(im_n+1), do_quote=True
        , reply_markup=ReplyKeyboardMarkup([["/compile 🎉"],["/cancel ❌", "/help ℹ"]]))
    except Exception as err:
        ustr = str(uid)
        if update.message.from_user.username:
            ustr += f"(t.me/{update.message.from_user.username})"
        logger.error(f"u{ustr} Error saving image: " + str(err))
        await update.message.reply_text(S('tg_err_img_error').format(im_n+1), do_quote=True)

async def addfile(update, context):
    """input: image file"""
    image = await update.message.document.get_file()
    await save_img(image, update, context)
    return CONTENT

async def addphoto(update, context):
    """input: tg photo"""
    image = await update.message.photo[-1].get_file()
    await save_img(image, update, context)
    return CONTENT

async def compile_handler(update, context):
    # default mode, filename provided, but no images
    if not (context.user_data['images']):
        await update.message.reply_text(S('tg_info_no_imgs'))
        return CONTENT

    # yes images but need filename
    if 'quick' in context.user_data:
        await update.message.reply_text(S('tg_info_enter_name'))
        return FILENAME
    
    # filename provided, yes images, proceed
    await compile_pdf(update, context)
    clear_user_cache(update.message.from_user.id)
    context.user_data.clear()
    logger.info("u{update.message.from_user.id} - end")
    return ConversationHandler.END

async def cancel(update, context):
    await update.message.reply_text(S('tg_info_cancel'), reply_markup=ReplyKeyboardRemove())
    clear_user_cache(update.message.from_user.id)
    context.user_data.clear()
    logger.info("u{update.message.from_user.id} - cancelled")
    return ConversationHandler.END

# -------------------------

async def help_handler(update, context):
    await update.message.reply_text(S('tg_help'), parse_mode=ParseMode.HTML)

async def unknown_handler(update, context):
    await update.message.reply_text(S('tg_err_unknown_cmd'), do_quote=True)

# -------------------------

async def edit_handler(update, context):
    await update.message.reply_text(S('tg_err_unimplemented'))
    # TODO

def edit_content(update, context):
    # TODO
    pass

# -------------------------

async def post_shutdown(application:Application):
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage", 
        data={'chat_id': 211399446,  'text': f"!!! @abstractpdf_bot is down"}
    )
    
async def post_init(application:Application):
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage", 
        data={'chat_id': 211399446,  'text': f"@abstractpdf_bot is up"}
    )

def main():
    if not os.path.exists("cache"):
        os.mkdir("cache")

    logger.info("Starting up")
    """Start the bot."""

    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler(['start','newpdf'], newpdf_handler), # Classic way
            # todo add pdf handling
            MessageHandler(Filters.Document.JPG | Filters.Document.GIF | Filters.Document.MimeType("image/png"), addfile), # Quick ways
            MessageHandler(Filters.PHOTO, addphoto)
        ],
        states={
            FILENAME: [
                # MessageHandler(Filters.regex(r'^[a-zA-Z0-9_][a-zA-Z0-9_.]*$'), filename_input),
                MessageHandler(Filters.TEXT & ~Filters.COMMAND, filename_input),
                # MessageHandler(~Filters.command, invalid_filename)
            ],
            CONTENT: [
                MessageHandler(Filters.Document.JPG | Filters.Document.GIF | Filters.Document.MimeType("image/png"), addfile),
                MessageHandler(Filters.PHOTO, addphoto),
                CommandHandler('compile', compile_handler),
                #
                # MessageHandler(Filters.updates.edited_message, edit_content)
                #
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(Filters.ALL, unknown_handler)
        ]
    )

    # dp.add_handler(CommandHandler('quality', quality))
    application.add_handler(CommandHandler('help', help_handler))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(Filters.ALL, unknown_handler))

    # Start the Bot
    application.run_polling(drop_pending_updates=True)


if __name__ == '__main__':
    main()