

# States
FILENAME, CONTENT, QUICK_FILENAME, PDF_PENDING = range(4)

# pdf converter
DEFAULT_QUALITY = 100
MAGICK_BIN = 'convert'
MAGICK, IMG2PDF = range(2)
MAX_IMG_N = 100
MAX_FILENAME_LEN = 60
MAX_PDFSIZE = 20_000_000 # ~20 MB

# V2. Pymudf settings
PDF_QUALITY = {
    "high": {},
    "mid": {},
    "low": {}
}


STRINGS = {};

DONATIONS_TEXT = """https://send.monobank.ua/jar/9f3uvzpYLD or 4441114464735412"""

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
STRINGS['tg_info_pdf_success'] = "here is your pdf"
STRINGS['tg_info_newpdf_quick'] = 'New PDF. Send /compile to finish when you are ready. Send /cancel to cancel.'
STRINGS['tg_info_newpdf'] = "New PDF. Enter document name. (/help ?)"
STRINGS['tg_info_newpdf_name_accepted'] = (
    'Got it. Now send content of your pdf - photos or *.jpg files.\n'
    'When you are ready to compile pdf, send /compile. Send /cancel to cancel.'
)
STRINGS['tg_info_max_imgs'] = (
    'Sorry, maximum image number reached.\n'
    '/compile or /cancel ?'
)
STRINGS['tg_info_img_ok'] = 'image {} - ok'
STRINGS['tg_info_enter_name'] = "Enter document name"
STRINGS['tg_info_no_imgs'] = "Add images first"
STRINGS['tg_info_cancel'] = "Okay, aborting."

STRINGS['tg_err_no_img_format'] = "image {} - cannot recognize image format"
STRINGS['tg_err_unsupported_img_format'] = "image {} - unsupported image format"
STRINGS['tg_err_img_too_big'] = 'image {} is way too big! I work for images up to 15 MB.'

STRINGS['tg_err_too_big'] = 'Too many photos, sorry. Aborting.'
STRINGS['tg_err_too_big_largefiles'] = "Sorry, pdf is too large. Try again with less images, using lower quality images, or sending with telegram compression"
STRINGS['tg_err_pdf_too_big'] = 'Sorry, pdf is too large. Try again with less images, using lower quality images, or sending with telegram compression'
STRINGS['tg_err_pdf_too_big_retry'] = 'Sorry, pdf is too large. I will try again with lower quality.'
STRINGS['tg_err_pdf_too_big_largefiles'] = "Sorry, pdf is too large for telegram. Try again with telegram compression"
STRINGS['tg_err_unknown_error'] = 'unknown error, sorry. try again later or try sending images with telegram compression'
STRINGS['tg_err_bot'] = 'bot error, sorry. try again later. if you are feeling lucky, try using less images, lower quality images, or sending photos with telegram compression'
STRINGS['tg_err_unknown_cmd'] = 'Unknown command, sorry. Try /cancel , /start or /help'
STRINGS['tg_err_unimplemented'] = "Further development is in progress! 🚧"
STRINGS['tg_err_timeout'] = 'pdf compilation took too long. try again with less images or lower image quality (e.g. sending as photos and not files)'
STRINGS['tg_err_timeout_but_ok'] = 'pdf upload is taking longer than expected. if you don\'t receive the file in a minute or so, try again with smaller pdf.'

STRINGS['tg_warn_quality_too_high'] = "PDF is too big. Trying lower quality."
STRINGS['tg_warn_quality_too_high_n'] = "PDF is too big ({}). Trying lower quality."

STRINGS['tg_help'] = (
        'I can create PDF from your images: photos (sent with telegram compression, \'as photo\') and jpg/png files (sent without compression, \'as file\').\n\n'
        f'<b>Current limits: 100 images or {MAX_PDFSIZE/1000000}MB</b>\n'
        'There are 2 ways:\n'
        '1. send /start or /newpdf, enter pdf name, then send images;\n'
        '2. just send me some images, then /compile and enter pdf name.\n'
        'You can cancel operation anytime using /cancel; then you will be able to start again.\n'
        '<i>By the way, I do not store your data; everything on server is deleted after successful compilation</i>\n\n'
        'developer - @mkrooted\n'
        f'also pls consider donating (servers aren\'t free): {DONATIONS_TEXT}'
)

class StringSupplier:
    def __init__(self, lang=None):
        self.lang = lang
        # TODO handle several languages.

    def get_string(self, str_code, lang=None):
        # TODO handle several languages.
        return STRINGS.get(str_code, '"' + str_code + '"')

    def __call__(self, str_code, lang=None):
        return self.get_string(str_code, lang)