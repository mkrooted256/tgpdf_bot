

# States
FILENAME, CONTENT, QUICK_FILENAME, PDF_PENDING = range(4)

# pdf converter
DEFAULT_QUALITY = 100
MAGICK_BIN = 'convert'
MAGICK, IMG2PDF = range(2)
MAX_IMG_N = 100
MAX_FILENAME_LEN = 60
MAX_PDFSIZE = 18_000_000 # ~18 MB
MAX_IMG_SIZE = 10_000_000 # ~10 MB
MAX_TOTAL_IMG_SIZE = MAX_PDFSIZE * 4  # because compression 
COMPILATION_TIMEOUT = 30.0  # seconds
POOL_WORKERS = 1
LIMITS = f"{MAX_IMG_N} imgs, {int(MAX_IMG_SIZE/1e6)} MB per img, {int(MAX_PDFSIZE/1e6)} MB total ({int(MAX_TOTAL_IMG_SIZE/1e6)} MB in low quality mode)"


STRINGS = {};

# DONATIONS_TEXT = """https://send.monobank.ua/jar/9f3uvzpYLD"""
DONATIONS_TEXT = """donate to help my friend's father kill russian invaders https://send.monobank.ua/jar/6VqGPBpKeU (details: https://t.me/katotheca/84802)"""

STRINGS['tg_info_start_compiling'] = (
    'compiling...\n'
    'it can take up to several minutes'
)
STRINGS['tg_info_start_compiling_high'] = (
    'compiling using original image quality...\n'
    'it can take up to several minutes'
)
STRINGS['tg_info_start_compiling_mid'] = (
    'compiling using lower quality images...\n'
    'it can take up to several minutes'
)
STRINGS['tg_info_start_compiling_low'] = (
    'compiling using even lower quality images...\n'
    'it can take up to several minutes'
)
STRINGS['tg_info_pdf_success'] = "Uploading PDF..."
STRINGS['tg_info_newpdf'] = "New PDF. Enter document name (/help ?)"
STRINGS['tg_info_newpdf_name_accepted'] = (
    'Got it. Now send the contents of your pdf: telegram photos, JPG, PNG, GIF.\n'
    f'Current limits: {LIMITS}.\n'
    'When you are ready, send /compile. Send /cancel to cancel.'
)
STRINGS['tg_info_newpdf_quick'] = (
    'You are creating a new pdf. Supported formats: telegram photos, JPG, PNG, GIF.\n'
    f'Current limits: {LIMITS}.\n'
    'Send /compile when you are ready. Send /cancel to cancel.'
)
STRINGS['tg_info_max_imgs'] = (
    f'Too many images. /compile or /cancel ?'
)
STRINGS['tg_info_max_total_size'] = (
    f'Total size is too large. /compile or /cancel ?'
)
STRINGS['tg_info_low_quality_mode'] = (
    f'PDF size limit reached. Entering low quality mode. This may or may not help!'
)
STRINGS['tg_info_img_ok'] = 'image {} added'
STRINGS['tg_info_enter_name'] = "Enter document name"
STRINGS['tg_info_no_imgs'] = "Send some images first"
STRINGS['tg_info_cancel'] = "Okay, aborting."

STRINGS['tg_err_no_img_format'] = "cannot recognize image format"
STRINGS['tg_err_unsupported_img_format'] = "unsupported image format"
STRINGS['tg_err_img_too_big'] = 'image too big'
STRINGS['tg_err_img_error'] = 'something gone wrong saving this image, try again'

STRINGS['tg_err_too_many'] = 'Too many photos, sorry. Aborting.'
STRINGS['tg_err_pdf_too_big'] = 'Sorry, pdf is too large for telegram. Try again with less images, using lower quality images, or sending with telegram compression'
STRINGS['tg_err_bot'] = 'bot error, sorry. try again later, with less images, with lower quality images, or sending photos using telegram compression'
STRINGS['tg_err_unknown_cmd'] = 'Unknown command, sorry. Try /cancel or /help'
STRINGS['tg_err_unimplemented'] = "Further development is in progress! 🚧"
STRINGS['tg_err_timeout'] = 'pdf compilation took too long. try again with less images or lower image quality (e.g. sending as photos and not files)'
STRINGS['tg_err_upload_timeout_but_ok'] = 'pdf upload is taking longer than expected. if you don\'t receive the file in a minute or so, try again with smaller pdf.'

STRINGS['tg_warn_unknown_error_retry'] = "Unknown error. Trying again with lower quality."
STRINGS['tg_warn_timeout_retry'] = "PDF compilation takes too long. Trying lower quality."
STRINGS['tg_warn_size_retry'] = "PDF is too big. Trying lower quality."
STRINGS['tg_warn_size_retry_n'] = "PDF is too big ({}). Trying lower quality."

STRINGS['tg_help'] = (
        'I create PDF from your images: photos (sent with telegram compression, \'as photo\') and jpg/png/gif files (sent without compression, \'as file\').'
        'Just send me some images and click /compile.'
        'You can cancel adding images using /cancel.\n\n'
        f'<b>Current limits: {LIMITS}</b>\n'
        'This bot collects per-user statistics, but deletes all your images and pdfs as soon as possible after success, failure, or /cancel.'
        'Neverthless, do not use this bot for sensitive info, and don\'t trust random software on the internet.\n\n'
        'Developer: @mkrooted\n'
        f'If you are enjoying this bot, {DONATIONS_TEXT}'
)

class StringSupplier:
    def __init__(self, lang=None):
        self.lang = lang
        # TODO handle several languages.

    def get_string(self, str_code, lang=None):
        # TODO handle several languages.
        # return STRINGS.get(str_code, '"' + str_code + '"')
        return STRINGS.get(str_code) # strict mode

    def __call__(self, str_code, lang=None):
        return self.get_string(str_code, lang)