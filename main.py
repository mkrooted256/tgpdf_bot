import subprocess
import logging
import requests
import os
import re
import time
from datetime import datetime
from telegram.ext import Application, Updater, CommandHandler, MessageHandler, filters as Filters, ConversationHandler, PicklePersistence
from telegram import Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.error import TimedOut, NetworkError
from telegram.constants import ParseMode

import shutil
import multiprocessing
from multiprocessing import Process
import pathlib
from PIL import Image, ImageOps

import pymupdf
import img2pdf

from constants import *

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Globals
S = StringSupplier()
logger = logging.getLogger(__name__)
pool = None
statistics_file = None
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


#### PDF Compilation

def __pymupdf_compile_pdf(images, filename, quality):
    doc = pymupdf.open()
    for img_path in images:
        if quality == 'high':
            doc.insert_file(img_path)
        else:
            image = Image.open(img_path)
            img_path = img_path + '.small.jpg'
            image.save(img_path, 'jpeg', quality=80)
            doc.insert_file(img_path)
    doc.save(filename)
    doc.close()
    
def __img2pdf_compile_pdf(images, filename, quality):
    if quality == 'high':
        with open(filename,"wb") as f:
            f.write(img2pdf.convert(images))
    else:
        small_images = []
        for img_path in images:
            small_img_path = img_path + '.small.jpg'
            Image.open(img_path).save(small_img_path, 'jpeg', quality=80)
            small_images.append(small_img_path)
        with open(filename,"wb") as f:
            f.write(img2pdf.convert(small_images))


#### Utility functions

"""
user context:
'images'
'quick'
'filename'
'pdfname'
"""

def statusbar(context):
    n = len(context.user_data['images'])
    size = context.user_data['total_size']
    size_mb = size * 1e-6
    if size > MAX_PDFSIZE:
        return f"{n} / {MAX_IMG_N} imgs, (LQ!) {size_mb:.2f} / {MAX_TOTAL_IMG_SIZE/1e6:.2f} MB"
    return f"{n} / {MAX_IMG_N} imgs, {size_mb:.2f} / {MAX_PDFSIZE/1e6:.2f} MB"

def clear_user_cache(update) -> bool:
    uid = update.message.from_user.id
    try:
        # delete whole user directory
        shutil.rmtree(f'cache/{uid}')
        return True
    except OSError as err:
        logger.error(f'u{uid}: failed to delete cache. '+str(err))
        return False

async def compile_pdf(update, context, starting_quality=0) -> bool:
    # Returns True if compilation successful.
    # Notifies user on errors, but do not notify on success.
    # Does not clear cache.
    uid = update.message.from_user.id
    ustr = str(uid)
    if update.message.from_user.username:
        ustr += f"(t.me/{update.message.from_user.username})"
    
    images = context.user_data['images']

    # start using original image quality. lower quality until success.
    qs = ['high', 'mid']
    for quality in qs[starting_quality:]:
        lasttry = quality == qs[-1]
        pdf_converter = 'img2pdf'
        pdfname = f'cache/{uid}/out-{quality}.pdf'
        context.user_data['pdfname'] = pdfname

        begin = 'begin' if quality == qs[0] else 'repeat'
        logger.info(f'u{ustr} compiler: {begin} {len(images)} photos, Q={quality}, {pdf_converter} -> {pdfname}:')
        await update.message.reply_text(S(f'tg_info_start_compiling_{quality}'), reply_markup=ReplyKeyboardRemove())

        try:
            t0 = time.perf_counter()
            # .get raises a TimeoutError if timeout and any exception raised inside the worker
            res = pool.apply_async(__img2pdf_compile_pdf, args=(images, pdfname, quality)).get(COMPILATION_TIMEOUT)
            t = time.perf_counter() - t0
        except multiprocessing.TimeoutError:
            # Will retry with lower quality
            t = time.perf_counter() - t0
            logger.info(f"u{ustr} compiler: timeout, t={t:.2f}s.")
            if not lasttry:
                await update.message.reply_text(S('tg_warn_timeout_retry'))
            else:
                await update.message.reply_text(S('tg_err_timeout'))
            continue
        except OSError as e:
            # Abort and don't retry
            logger.error(f"u{ustr} compiler: OSError:", exc_info=True)
            await update.message.reply_text(S('tg_err_bot'))
            return False
        except Exception as e:
            # Abort and don't retry
            logger.error(f"u{ustr} compiler: Fuckery:", exc_info=True)
            await update.message.reply_text(S('tg_err_bot'))
            return False

        fsize = os.stat(pdfname).st_size
        fsize_h = fsize/1000000
        logger.info(f'u{ustr} compiler: success, t={t:.2f}s, s={fsize_h}MB')

        if fsize >= MAX_PDFSIZE:
            # too big. notify user and try lower quality
            logger.info(f"u{ustr} compiler: {pdfname} too big")
            if not lasttry:
                await update.message.reply_text(S('tg_warn_size_retry'))
            else:
                await update.message.reply_text(S('tg_err_pdf_too_big'))
            continue
        
        # all checks passed. pdf seems to be ok. proceed to pdf upload
        return True
    # end for quality

    # If not exited yet, then lowest quality pdf still fails. 
    # User is already notified.
    logger.info(f"u{ustr} compiler: final failure.")
    return False

# This function logs successful pdf sessions. Uses context.user_data['pdfname']
async def upload_pdf(update, context):
    uid = update.message.from_user.id
    ustr = str(uid)
    if update.message.from_user.username:
        ustr += f"(t.me/{update.message.from_user.username})"
        
    images = context.user_data['images']
    number_of_images = len(images)
    pdfname = context.user_data['pdfname']
    
    logger.info("u{ustr} upload: begin")
    await update.message.reply_text(S('tg_info_pdf_success'))
    
    try:
        t0 = time.perf_counter()
        await update.message.reply_document(
            document=open(pdfname, 'rb'),
            filename=context.user_data['filename'] + '.pdf',
            # read_timeout=15.0,
            write_timeout=30.0,
            # connect_timeout=5.0
        )
        t = time.perf_counter() - t0
        logger.info(f'u{ustr} upload: done, t={t:.2f}s')
        statistics_file.write(f"{datetime.now().strftime("%Y-%m-%d")},{uid},{update.message.from_user.username},success,{number_of_images}\n")
    except TimedOut as err:
        # Telegram timeout
        t = time.perf_counter() - t0
        logger.warning(f'u{ustr} upload: timeout, t={t:.2f}s')
        await update.message.reply_text(S('tg_err_upload_timeout_but_ok'))
        statistics_file.write(f"{datetime.now().strftime("%Y-%m-%d")},{uid},{update.message.from_user.username},success?,{number_of_images}\n")
    except NetworkError as e:
        logger.error(f'u{ustr} upload: network error', exc_info=True)

# Create user context and log the beginning of conversation
def newpdf(update, context, quick=False):
    """Start new PDF"""
    # sanity check: no other session is in progress
    assert len(context.user_data.get('images', [])) == 0

    uid = update.message.from_user.id
    ustr = str(uid)
    if update.message.from_user.username:
        ustr += f"(t.me/{update.message.from_user.username})"

    context.user_data['images'] = []
    context.user_data['quick'] = quick
    context.user_data['total_size'] = 0
    context.user_data['lower_quality_notified'] = False
    context.user_data['filename'] = None
    context.user_data['pdfname'] = None

    q = "quick " if quick else ""
    logger.info(f"u{ustr} New {q}pdf")
    statistics_file.write(f"{datetime.now().strftime("%Y-%m-%d")},{uid},{update.message.from_user.username},newpdf,{quick}\n")


#### Bot handlers

async def newpdf_handler(update, context):
    user = update.message.from_user
    newpdf(user)
    await update.message.reply_text(S('tg_info_newpdf'), parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardRemove())
    return FILENAME

async def filename_input(update, context):
    # use first non-whitespace line
    text = update.message.text.strip().split('\n')[0].strip()[:MAX_FILENAME_LEN]
    # unicode is fine except of / and \. \ needs to be double-escaped.
    text = re.sub('[/\\\\]', ' ', text)
    context.user_data['filename'] = text
    
    # filename provided after images -> compile
    if 'quick' in context.user_data:
        pdf_success = await compile_pdf(update, context)
        if pdf_success:
            await upload_pdf(update, context)

        # end session regardless of result
        clear_user_cache(update)
        context.user_data.clear()
        logger.info(f"u{update.message.from_user.id} - end")
        return ConversationHandler.END

    # start waiting for images after filename
    context.user_data['images'] = []
    await update.message.reply_text(S('tg_info_newpdf_name_accepted'), parse_mode=ParseMode.HTML)
    return CONTENT

async def save_img(file, update, context):
    uid = update.message.from_user.id
    try:
        if not 'images' in context.user_data:
            # This is a beginning of new conversation.
            newpdf(update.message.from_user, quick=True)
            await update.message.reply_text(S('tg_info_newpdf_quick'))
        
        if len(context.user_data['images']) >= MAX_IMG_N:
            await update.message.reply_text(S('tg_info_max_imgs'))
            return
        if context.user_data['total_size'] >= MAX_TOTAL_IMG_SIZE:
            await update.message.reply_text(S('tg_info_max_total_size'))
            return
        elif context.user_data['total_size'] >= MAX_PDFSIZE and not context.user_data['lower_quality_notified']:
            context.user_data['lower_quality_notified'] = True
            await update.message.reply_text(S('tg_info_low_quality_mode'))

        images = context.user_data['images']
        im_n = len(images)

        if file.file_size is not None and file.file_size > MAX_IMG_SIZE:
            await update.message.reply_text(S('tg_err_img_too_big'), do_quote=True)
            return

        # try to get file type
        dot_index = file.file_path.rfind('.')
        if dot_index == -1:
            await update.message.reply_text(S('tg_err_no_img_format'), do_quote=True)
            return
        filetype = file.file_path[dot_index:].lower()
        if not filetype in ['.jpg', '.jpeg', '.png', '.gif']:
            await update.message.reply_text(S('tg_err_unsupported_img_format'), do_quote=True)
            return
        
        os.makedirs(f'cache/{uid}', exist_ok=True)
        filename = f'cache/{uid}/{im_n}{filetype}'
        
        await file.download_to_drive(filename)

        img_size = os.stat(filename).st_size
        if img_size > MAX_IMG_SIZE:
            await update.message.reply_text(S('tg_err_img_too_big'), do_quote=True)
            os.remove(filename)
            return

        # Add image!
        images.append(filename)
        context.user_data['total_size'] = context.user_data['total_size'] + img_size

        await update.message.reply_text(
            S('tg_info_img_ok').format(im_n+1) + statusbar(context)
            , do_quote=True
        , reply_markup=ReplyKeyboardMarkup([["/compile 🎉"],["/cancel ❌", "/help ℹ"]]))
    except Exception as err:
        ustr = str(uid)
        if update.message.from_user.username:
            ustr += f"(t.me/{update.message.from_user.username})"
        logger.error(f"u{ustr} Error saving image: " + str(err))
        await update.message.reply_text(S('tg_err_img_error'), do_quote=True)

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
        await update.message.reply_text(S('tg_info_enter_name'), reply_markup=ReplyKeyboardRemove())
        return FILENAME
    
    # filename provided, yes images, proceed
    pdf_success = await compile_pdf(update, context)
    if pdf_success:
        await upload_pdf(update, context)
    # end session regardless of result
    clear_user_cache(update)
    context.user_data.clear()
    logger.info(f"u{update.message.from_user.id} - end")
    return ConversationHandler.END

async def cancel(update, context):
    clear_user_cache(update)
    await update.message.reply_text(S('tg_info_cancel'), reply_markup=ReplyKeyboardRemove())
    logger.info(f"u{update.message.from_user.id} - cancelled")
    clear_user_cache(update)
    context.user_data.clear()
    return ConversationHandler.END

# -------------------------

async def help_handler(update, context):
    inprogress = ''
    if 'images' in context.user_data:
        inprogress = '[pdf in progress. send next image, /cancel, or /compile]\n'
    await update.message.reply_text(
        inprogress + S('tg_help')
        , parse_mode=ParseMode.HTML)

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

# TODO: register error handler for large images.

def main():
    if not os.path.exists("cache"):
        os.mkdir("cache")

    statistics_file_name = f"stats.{round(time.time())}.txt"
    global statistics_file
    statistics_file = open(statistics_file_name, "w", buffering=1) 

    global pool
    pool = multiprocessing.Pool(POOL_WORKERS)

    logger.info("Starting up")
    """Start the bot."""

    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    allowed_file_types_filter = Filters.Document.JPG | Filters.Document.GIF | Filters.Document.MimeType("image/png")

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('newpdf', newpdf_handler), # Classic way
            # todo add pdf handling
            MessageHandler(allowed_file_types_filter, addfile), # Quick ways
            MessageHandler(Filters.PHOTO, addphoto)
        ],
        states={
            FILENAME: [
                # MessageHandler(Filters.regex(r'^[a-zA-Z0-9_][a-zA-Z0-9_.]*$'), filename_input),
                MessageHandler(Filters.TEXT & ~Filters.COMMAND, filename_input),
                # MessageHandler(~Filters.command, invalid_filename)
            ],
            CONTENT: [
                MessageHandler(allowed_file_types_filter, addfile),
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
    application.add_handler(CommandHandler('start', help_handler))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(Filters.ALL, unknown_handler))

    # Start the Bot
    application.run_polling(drop_pending_updates=True)

    statistics_file.close()


if __name__ == '__main__':
    main()