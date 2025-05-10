#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to catch all user ids from all updates.

Primary usage is to send message to users who tried to use my bot while it was offline.

"""

import json

import logging

from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
file = None

unique_users = set()

async def catch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch the user."""
    user = update.effective_user
    unique_users.add(user.id)
    file.write(f"{update.update_id},{user.id},{user.username}\n")
    print(".", end='', flush=True)
    

def main() -> None:

    global file
    file = open("updates.txt", "w")

    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token("TOKEN").build()

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.ALL, catch))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    file.close()

    with open("users.txt", "w") as f:
        json.dump(tuple(unique_users), f)



if __name__ == "__main__":
    main()