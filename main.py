# ============================================================
# PERSONAL TELEGRAM USERNAME TOOL
# File: main.py
# Python 3.10+
# ============================================================

import os
import re
import json
import asyncio
import logging
import secrets
import threading

from pathlib import Path
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer
)
from urllib.parse import urlparse

from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.account import (
    CheckUsernameRequest,
    ToggleUsernameRequest,
    ReorderUsernamesRequest
)

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)

from database import (
    init_database,
    save_candidate,
    get_candidates
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

SESSION_DIR = BASE_DIR / "session"

SESSION_DIR.mkdir(
    parents=True,
    exist_ok=True
)

SESSION_FILE = (
    SESSION_DIR
    / "personal_account"
)

INDEX_FILE = (
    BASE_DIR
    / "templates"
    / "index.html"
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(
    BASE_DIR / ".env"
)


API_ID_RAW = os.getenv(
    "API_ID",
    ""
).strip()

API_HASH = os.getenv(
    "API_HASH",
    ""
).strip()

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
).strip()

OWNER_USER_ID_RAW = os.getenv(
    "OWNER_USER_ID",
    ""
).strip()

PORT_RAW = os.getenv(
    "PORT",
    "10000"
).strip()


if not API_ID_RAW:
    raise RuntimeError(
        "API_ID is missing."
    )

if not API_HASH:
    raise RuntimeError(
        "API_HASH is missing."
    )

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing."
    )

if not OWNER_USER_ID_RAW:
    raise RuntimeError(
        "OWNER_USER_ID is missing."
    )


try:

    API_ID = int(
        API_ID_RAW
    )

except ValueError:

    raise RuntimeError(
        "API_ID must be a number."
    )


try:

    OWNER_USER_ID = int(
        OWNER_USER_ID_RAW
    )

except ValueError:

    raise RuntimeError(
        "OWNER_USER_ID must be a number."
    )


try:

    PORT = int(
        PORT_RAW
    )

except ValueError:

    PORT = 10000


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    )
)

logger = logging.getLogger(
    "telegram-username-tool"
)


# ============================================================
# TELETHON
# ============================================================

user_client = TelegramClient(
    str(SESSION_FILE),
    API_ID,
    API_HASH
)


MAIN_LOOP = None


# ============================================================
# OWNER SECURITY
# ============================================================

def owner_only(update):

    user = update.effective_user

    return bool(
        user
        and
        user.id == OWNER_USER_ID
    )


async def deny_if_not_owner(
    update
):

    if owner_only(update):
        return False

    if update.effective_message:

        await update.effective_message.reply_text(
            "⛔ You are not authorized "
            "to use this bot."
        )

    return True


# ============================================================
# TELEGRAM ACCOUNT
# ============================================================

async def ensure_connected():

    if not user_client.is_connected():

        await user_client.connect()


async def is_account_connected():

    try:

        await ensure_connected()

        return await (
            user_client
            .is_user_authorized()
        )

    except Exception:

        logger.exception(
            "Telegram status check failed."
        )

        return False


async def get_me():

    await ensure_connected()

    authorized = await (
        user_client
        .is_user_authorized()
    )

    if not authorized:
        return None

    return await user_client.get_me()


# ============================================================
# RUN COROUTINE FROM WEB THREAD
# ============================================================

def run_async(
    coroutine,
    timeout=15
):

    if MAIN_LOOP is None:

        raise RuntimeError(
            "Main event loop unavailable."
        )

    future = (
        asyncio.run_coroutine_threadsafe(
            coroutine,
            MAIN_LOOP
        )
    )

    return future.result(
        timeout=timeout
    )


# ============================================================
# HTML
# ============================================================

def load_index():

    if INDEX_FILE.exists():

        return INDEX_FILE.read_text(
            encoding="utf-8"
        )

    return """
    <!doctype html>

    <html>

    <body>

    <h1>
        Telegram Username Tool
    </h1>

    <p>
        templates/index.html
        was not found.
    </p>

    </body>

    </html>
    """


# ============================================================
# WEBSITE
# ============================================================

class WebHandler(
    BaseHTTPRequestHandler
):

    def send_bytes(
        self,
        body,
        status=200,
        content_type="text/plain"
    ):

        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            content_type
        )

        self.send_header(
            "Content-Length",
            str(len(body))
        )

        self.send_header(
            "Cache-Control",
            "no-store"
        )

        self.end_headers()

        self.wfile.write(
            body
        )


    def send_text(
        self,
        text,
        status=200,
        content_type=(
            "text/plain; charset=utf-8"
        )
    ):

        self.send_bytes(
            text.encode("utf-8"),
            status,
            content_type
        )


    def send_json(
        self,
        data,
        status=200
    ):

        body = json.dumps(
            data
        ).encode(
            "utf-8"
        )

        self.send_bytes(
            body,
            status,
            "application/json; charset=utf-8"
        )


    def do_GET(self):

        path = urlparse(
            self.path
        ).path


        # ----------------------------------------
        # HOME
        # ----------------------------------------

        if path == "/":

            self.send_text(
                load_index(),
                200,
                "text/html; charset=utf-8"
            )

            return


        # ----------------------------------------
        # HEALTH
        # ----------------------------------------

        if path in (
            "/health",
            "/healthz"
        ):

            self.send_text(
                "OK"
            )

            return


        # ----------------------------------------
        # TELEGRAM STATUS API
        # ----------------------------------------

        if path == "/api/status":

            try:

                connected = run_async(
                    is_account_connected()
                )

                result = {
                    "connected":
                        bool(connected)
                }


                if connected:

                    me = run_async(
                        get_me()
                    )

                    if me:

                        result["id"] = (
                            me.id
                        )

                        result["username"] = (
                            me.username
                            or None
                        )


                self.send_json(
                    result
                )


            except Exception as error:

                logger.exception(
                    "Status API error."
                )

                self.send_json(
                    {
                        "connected": False,
                        "error": str(error)
                    },
                    500
                )


            return


        self.send_text(
            "Not Found",
            404
        )


    def log_message(
        self,
        format,
        *args
    ):

        return


def start_web_server():

    server = ThreadingHTTPServer(
        (
            "0.0.0.0",
            PORT
        ),
        WebHandler
    )

    logger.info(
        "Website running on "
        "0.0.0.0:%s",
        PORT
    )

    server.serve_forever()


# ============================================================
# USERNAME HELPERS
# ============================================================

USERNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9_]{5,32}$"
)


def clean_username(
    value
):

    value = value.strip()

    if value.startswith("@"):

        value = value[1:]

    return value


def valid_username(
    username
):

    return bool(
        USERNAME_PATTERN.fullmatch(
            username
        )
    )


def generate_candidate(
    base
):

    base = clean_username(
        base
    )

    base = re.sub(
        r"[^A-Za-z0-9_]",
        "",
        base
    )

    if not base:

        base = "user"

    base = base[:22]

    choices = [

        f"{base}{secrets.randbelow(900) + 100}",

        f"{base}_dev",

        f"{base}_tech",

        f"{base}_ng",

        f"real_{base}",

        f"mr_{base}"
    ]

    candidate = secrets.choice(
        choices
    )[:32]

    while len(candidate) < 5:

        candidate += "0"

    return candidate


def get_username_lists(
    me
):

    main_username = getattr(
        me,
        "username",
        None
    )

    active = []
    inactive = []

    usernames = (
        getattr(
            me,
            "usernames",
            None
        )
        or []
    )


    for item in usernames:

        username = getattr(
            item,
            "username",
            None
        )

        if not username:
            continue


        if getattr(
            item,
            "active",
            False
        ):

            active.append(
                username
            )

        else:

            inactive.append(
                username
            )


    return (
        main_username,
        active,
        inactive
    )


# ============================================================
# /start
# ============================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if await deny_if_not_owner(
        update
    ):
        return


    connected = await (
        is_account_connected()
    )


    if connected:

        status = (
            "🟢 Connected"
        )

    else:

        status = (
            "🔴 Not connected"
        )


    text = (
        "💎 TELEGRAM USERNAME TOOL\n\n"

        f"Account: {status}\n\n"

        "Commands:\n\n"

        "/status\n"

        "/createuser name\n"

        "/myusernames\n"

        "/activate username\n"

        "/deactivate username\n"

        "/reorder name1 name2 ...\n"

        "/history"
    )


    await (
        update.effective_message
        .reply_text(
            text
        )
    )


# ============================================================
# /status
# ============================================================

async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if await deny_if_not_owner(
        update
    ):
        return


    me = await get_me()


    if not me:

        await (
            update.effective_message
            .reply_text(
                "🔴 Telegram account "
                "is not connected.\n\n"
                "Run login.py first."
            )
        )

        return


    username = (
        f"@{me.username}"
        if me.username
        else "None"
    )


    await (
        update.effective_message
        .reply_text(
            "🟢 TELEGRAM CONNECTED\n\n"

            f"ID: {me.id}\n"

            f"Username: {username}"
        )
    )


# ============================================================
# /createuser
# ============================================================

async def createuser_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if await deny_if_not_owner(
        update
    ):
        return


    if not context.args:

        await (
            update.effective_message
            .reply_text(
                "Usage:\n\n"
                "/createuser simon"
            )
        )

        return


    if not await is_account_connected():

        await (
            update.effective_message
            .reply_text(
                "❌ Telegram account "
                "is not connected."
            )
        )

        return


    base = context.args[0]

    candidate = generate_candidate(
        base
    )


    message = await (
        update.effective_message
        .reply_text(
            f"🔎 Checking "
            f"@{candidate}..."
        )
    )


    try:

        available = await user_client(
            CheckUsernameRequest(
                username=candidate
            )
        )


        status = (
            "AVAILABLE"
            if available
            else
            "TAKEN"
        )


        save_candidate(
            candidate,
            status
        )


        if available:

            text = (
                "✅ USERNAME AVAILABLE\n\n"

                f"@{candidate}\n\n"

                "This checks ordinary Telegram "
                "username availability."
            )

        else:

            text = (
                "❌ USERNAME UNAVAILABLE\n\n"

                f"@{candidate}"
            )


        await message.edit_text(
            text
        )


    except RPCError as error:

        save_candidate(
            candidate,
            "ERROR"
        )

        await message.edit_text(
            "❌ Telegram error:\n\n"
            f"{error}"
        )


    except Exception as error:

        logger.exception(
            "createuser error"
        )

        await message.edit_text(
            f"❌ Error:\n\n{error}"
        )


# ============================================================
# /myusernames
# ============================================================

async def myusernames_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if await deny_if_not_owner(
        update
    ):
        return


    me = await get_me()


    if not me:

        await (
            update.effective_message
            .reply_text(
                "❌ Telegram account "
                "is not connected."
            )
        )

        return


    main_username, active, inactive = (
        get_username_lists(
            me
        )
    )


    lines = [

        "👤 MY TELEGRAM USERNAMES",

        "",

        (
            "Main: "
            + (
                f"@{main_username}"
                if main_username
                else "None"
            )
        ),

        "",

        "🟢 Active:"
    ]


    if active:

        for username in active:

            lines.append(
                f"• @{username}"
            )

    else:

        lines.append(
            "• None"
        )


    lines.extend(
        [
            "",
            "⚪ Inactive:"
        ]
    )


    if inactive:

        for username in inactive:

            lines.append(
                f"• @{username}"
            )

    else:

        lines.append(
            "• None"
        )


    await (
        update.effective_message
        .reply_text(
            "\n".join(lines)
        )
    )


# ============================================================
# /activate
# ============================================================

async def activate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if await deny_if_not_owner(
        update
    ):
        return


    if not context.args:

        await (
            update.effective_message
            .reply_text(
                "Usage:\n"
                "/activate username"
            )
        )

        return


    username = clean_username(
        context.args[0]
    )


    if not valid_username(
        username
    ):

        await (
            update.effective_message
            .reply_text(
                "❌ Invalid username."
            )
        )

        return


    if not await is_account_connected():

        await (
            update.effective_message
            .reply_text(
                "❌ Telegram account "
                "is not connected."
            )
        )

        return


    try:

        result = await user_client(
            ToggleUsernameRequest(
                username=username,
                active=True
            )
        )


        if result:

            text = (
                f"✅ @{username} activated."
            )

        else:

            text = (
                "❌ Telegram did not "
                "activate the username."
            )


        await (
            update.effective_message
            .reply_text(
                text
            )
        )


    except RPCError as error:

        await (
            update.effective_message
            .reply_text(
                "❌ Activation failed.\n\n"
                f"{error}"
            )
        )


# ============================================================
# /deactivate
# ============================================================

async def deactivate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if await deny_if_not_owner(
        update
    ):
        return


    if not context.args:

        await (
            update.effective_message
            .reply_text(
                "Usage:\n"
                "/deactivate username"
            )
        )

        return


    username = clean_username(
        context.args[0]
    )


    if not valid_username(
        username
    ):

        await (
            update.effective_message
            .reply_text(
                "❌ Invalid username."
            )
        )

        return


    if not await is_account_connected():

        await (
            update.effective_message
            .reply_text(
                "❌ Telegram account "
                "is not connected."
            )
        )

        return


    try:

        result = await user_client(
            ToggleUsernameRequest(
                username=username,
                active=False
            )
        )


        if result:

            text = (
                f"✅ @{username} deactivated."
            )

        else:

            text = (
                "❌ Telegram did not "
                "deactivate the username."
            )


        await (
            update.effective_message
            .reply_text(
                text
            )
        )


    except RPCError as error:

        await (
            update.effective_message
            .reply_text(
                "❌ Deactivation failed.\n\n"
                f"{error}"
            )
        )


# ============================================================
# /reorder
# ============================================================

async def reorder_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if await deny_if_not_owner(
        update
    ):
        return


    if not context.args:

        await (
            update.effective_message
            .reply_text(
                "Usage:\n\n"

                "/reorder username1 "
                "username2"
            )
        )

        return


    requested = [

        clean_username(
            username
        )

        for username
        in context.args
    ]


    if (
        len(requested)
        !=
        len(set(requested))
    ):

        await (
            update.effective_message
            .reply_text(
                "❌ Duplicate username."
            )
        )

        return


    if any(
        not valid_username(username)
        for username
        in requested
    ):

        await (
            update.effective_message
            .reply_text(
                "❌ Invalid username."
            )
        )

        return


    me = await get_me()


    if not me:

        await (
            update.effective_message
            .reply_text(
                "❌ Telegram account "
                "is not connected."
            )
        )

        return


    _, active, _ = (
        get_username_lists(
            me
        )
    )


    if set(requested) != set(active):

        await (
            update.effective_message
            .reply_text(
                "❌ Include every currently "
                "active username exactly once."
            )
        )

        return


    try:

        result = await user_client(
            ReorderUsernamesRequest(
                order=requested
            )
        )


        if result:

            text = (
                "✅ Username order updated."
            )

        else:

            text = (
                "❌ Telegram did not "
                "update the order."
            )


        await (
            update.effective_message
            .reply_text(
                text
            )
        )


    except RPCError as error:

        await (
            update.effective_message
            .reply_text(
                "❌ Reorder failed.\n\n"
                f"{error}"
            )
        )


# ============================================================
# /history
# ============================================================

async def history_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if await deny_if_not_owner(
        update
    ):
        return


    rows = get_candidates()


    if not rows:

        await (
            update.effective_message
            .reply_text(
                "No username checks yet."
            )
        )

        return


    lines = [

        "📋 RECENT USERNAME CHECKS",

        ""
    ]


    for row in rows:

        lines.append(
            f"@{row['username']} "
            f"→ {row['status']}"
        )


    await (
        update.effective_message
        .reply_text(
            "\n".join(lines)
        )
    )


# ============================================================
# BOT ERROR
# ============================================================

async def error_handler(
    update,
    context
):

    logger.error(
        "Bot error: %s",
        context.error,
        exc_info=context.error
    )


# ============================================================
# BUILD BOT
# ============================================================

def build_application():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )


    handlers = [

        (
            "start",
            start_command
        ),

        (
            "status",
            status_command
        ),

        (
            "createuser",
            createuser_command
        ),

        (
            "myusernames",
            myusernames_command
        ),

        (
            "activate",
            activate_command
        ),

        (
            "deactivate",
            deactivate_command
        ),

        (
            "reorder",
            reorder_command
        ),

        (
            "history",
            history_command
        )
    ]


    for command, callback in handlers:

        application.add_handler(
            CommandHandler(
                command,
                callback
            )
        )


    application.add_error_handler(
        error_handler
    )


    return application


# ============================================================
# MAIN APPLICATION
# ============================================================

async def run():

    global MAIN_LOOP

    MAIN_LOOP = (
        asyncio.get_running_loop()
    )


    init_database()


    print("=" * 60)

    print(
        "PERSONAL TELEGRAM USERNAME TOOL"
    )

    print("=" * 60)


    await user_client.connect()


    authorized = await (
        user_client
        .is_user_authorized()
    )


    if authorized:

        me = await (
            user_client
            .get_me()
        )

        logger.info(
            "Telegram account connected: %s",
            me.id
        )

    else:

        logger.warning(
            "Telegram account is NOT authorized. "
            "Run login.py on your trusted device "
            "and provide the resulting private "
            "session to this deployment."
        )


    # --------------------------------------------
    # START WEBSITE
    # --------------------------------------------

    web_thread = threading.Thread(
        target=start_web_server,
        daemon=True,
        name="web-server"
    )

    web_thread.start()


    # --------------------------------------------
    # START CONTROL BOT
    # --------------------------------------------

    application = (
        build_application()
    )


    await application.initialize()

    await application.start()


    if application.updater is None:

        raise RuntimeError(
            "Telegram bot updater "
            "unavailable."
        )


    await (
        application.updater
        .start_polling(
            allowed_updates=(
                Update.ALL_TYPES
            )
        )
    )


    logger.info(
        "Control bot running."
    )


    try:

        await (
            asyncio.Event()
            .wait()
        )


    finally:

        if application.updater:

            await (
                application.updater
                .stop()
            )


        await application.stop()

        await application.shutdown()

        await user_client.disconnect()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            run()
        )

    except KeyboardInterrupt:

        print(
            "Application stopped."
        )

    except Exception as error:

        logger.exception(
            "Fatal application error."
        )

        print(
            "Fatal error:",
            repr(error)
)
