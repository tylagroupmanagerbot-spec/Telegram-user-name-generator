# ============================================================
# PERSONAL TELEGRAM USERNAME TOOL
# File: main.py
# Python 3.10+
#
# Structure:
#
# telegram_username_tool/
# ├── main.py
# ├── database.py
# ├── requirements.txt
# ├── .env
# └── templates/
#     └── index.html
# ============================================================

import os
import re
import asyncio
import logging
import secrets
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.account import (
    CheckUsernameRequest,
    ToggleUsernameRequest,
    ReorderUsernamesRequest,
)

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from database import (
    init_database,
    save_candidate,
    get_candidates,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

TEMPLATE_DIR = BASE_DIR / "templates"

INDEX_FILE = TEMPLATE_DIR / "index.html"

SESSION_DIR = BASE_DIR / "session"

SESSION_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

load_dotenv(
    BASE_DIR / ".env"
)


# ============================================================
# ENVIRONMENT
# ============================================================

API_ID_RAW = os.getenv(
    "API_ID",
    "",
).strip()

API_HASH = os.getenv(
    "API_HASH",
    "",
).strip()

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "",
).strip()

OWNER_USER_ID_RAW = os.getenv(
    "OWNER_USER_ID",
    "",
).strip()

PORT_RAW = os.getenv(
    "PORT",
    "10000",
).strip()

PUBLIC_URL = os.getenv(
    "PUBLIC_URL",
    "",
).strip().rstrip("/")


# ============================================================
# VALIDATION
# ============================================================

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
    API_ID = int(API_ID_RAW)
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
    PORT = int(PORT_RAW)
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
    ),
)

logger = logging.getLogger(
    "telegram-username-tool"
)


# ============================================================
# TELETHON USER SESSION
# ============================================================

SESSION_FILE = (
    SESSION_DIR
    / "personal_account"
)

user_client = TelegramClient(
    str(SESSION_FILE),
    API_ID,
    API_HASH,
)


# ============================================================
# SECURITY
# ============================================================

def owner_only(
    update: Update,
) -> bool:

    user = update.effective_user

    if not user:
        return False

    return (
        user.id
        == OWNER_USER_ID
    )


async def deny_if_not_owner(
    update: Update,
) -> bool:

    if owner_only(update):
        return False

    if update.effective_message:

        await (
            update.effective_message
            .reply_text(
                "⛔ You are not authorized "
                "to use this bot."
            )
        )

    return True


# ============================================================
# TELETHON HELPERS
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
            "Authorization check failed."
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
# HTML SERVER
# ============================================================

def load_index_html():

    if INDEX_FILE.exists():

        return INDEX_FILE.read_text(
            encoding="utf-8"
        )

    return """<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta
        name="viewport"
        content="width=device-width,initial-scale=1"
    >

    <title>Telegram Username Tool</title>
</head>

<body>

    <h1>Telegram Username Tool</h1>

    <p>
        index.html was not found.
    </p>

    <p>
        Create:
        templates/index.html
    </p>

</body>
</html>
"""


class WebHandler(
    BaseHTTPRequestHandler
):

    def send_content(
        self,
        body,
        status=200,
        content_type=(
            "text/html; charset=utf-8"
        ),
    ):

        if isinstance(body, str):

            body = body.encode(
                "utf-8"
            )

        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            content_type,
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.send_header(
            "Cache-Control",
            "no-store",
        )

        self.end_headers()

        self.wfile.write(
            body
        )

    def do_GET(self):

        # --------------------------------------------
        # HOME PAGE
        # --------------------------------------------

        if self.path == "/":

            self.send_content(
                load_index_html()
            )

            return

        # --------------------------------------------
        # HEALTH CHECK
        # --------------------------------------------

        if self.path in (
            "/health",
            "/healthz",
        ):

            self.send_content(
                "OK",
                content_type=(
                    "text/plain; charset=utf-8"
                ),
            )

            return

        # --------------------------------------------
        # 404
        # --------------------------------------------

        self.send_content(
            "Not Found",
            status=404,
            content_type=(
                "text/plain; charset=utf-8"
            ),
        )

    def log_message(
        self,
        format,
        *args,
    ):
        return


def start_web_server():

    server = ThreadingHTTPServer(
        (
            "0.0.0.0",
            PORT,
        ),
        WebHandler,
    )

    logger.info(
        "Website listening on "
        "0.0.0.0:%s",
        PORT,
    )

    server.serve_forever()


# ============================================================
# USERNAME HELPERS
# ============================================================

USERNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9_]{5,32}$"
)


def clean_username(
    value,
):

    value = value.strip()

    if value.startswith("@"):
        value = value[1:]

    return value


def valid_username(
    username,
):

    return bool(
        USERNAME_PATTERN.fullmatch(
            username
        )
    )


def generate_candidate(
    base,
):

    base = clean_username(
        base
    )

    base = re.sub(
        r"[^A-Za-z0-9_]",
        "",
        base,
    )

    if not base:
        base = "user"

    base = base[:22]

    options = [
        f"{base}{secrets.randbelow(900) + 100}",
        f"{base}_dev",
        f"{base}_tech",
        f"{base}_ng",
        f"real_{base}",
        f"mr_{base}",
    ]

    candidate = secrets.choice(
        options
    )[:32]

    while len(candidate) < 5:
        candidate += "0"

    return candidate


def get_username_lists(
    me,
):

    normal = getattr(
        me,
        "username",
        None,
    )

    active = []
    inactive = []

    usernames = (
        getattr(
            me,
            "usernames",
            None,
        )
        or []
    )

    for item in usernames:

        username = getattr(
            item,
            "username",
            None,
        )

        if not username:
            continue

        if getattr(
            item,
            "active",
            False,
        ):

            active.append(
                username
            )

        else:

            inactive.append(
                username
            )

    return (
        normal,
        active,
        inactive,
    )


# ============================================================
# /start
# ============================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
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
            "🟢 Telegram account connected"
        )

    else:

        status = (
            "🔴 Telegram account not connected"
        )

    text = (
        "💎 TELEGRAM USERNAME TOOL\n\n"

        f"{status}\n\n"

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
    context: ContextTypes.DEFAULT_TYPE,
):

    if await deny_if_not_owner(
        update
    ):
        return

    me = await get_me()

    if not me:

        website = (
            PUBLIC_URL
            if PUBLIC_URL
            else "Render website"
        )

        await (
            update.effective_message
            .reply_text(
                "🔴 Telegram account "
                "is not connected.\n\n"
                "Open the website to connect:\n"
                f"{website}"
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
    context: ContextTypes.DEFAULT_TYPE,
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
                "❌ Connect your Telegram "
                "account first."
            )
        )

        return

    candidate = generate_candidate(
        context.args[0]
    )

    message = await (
        update.effective_message
        .reply_text(
            f"🔎 Checking @{candidate}..."
        )
    )

    try:

        available = await user_client(
            CheckUsernameRequest(
                username=candidate
            )
        )

        if available:

            status = "AVAILABLE"

            result = (
                "✅ USERNAME AVAILABLE\n\n"
                f"@{candidate}\n\n"
                "This means ordinary Telegram "
                "username availability.\n"
                "It does not mean the username "
                "is a Fragment collectible."
            )

        else:

            status = "TAKEN"

            result = (
                "❌ USERNAME UNAVAILABLE\n\n"
                f"@{candidate}"
            )

        save_candidate(
            candidate,
            status,
        )

        await message.edit_text(
            result
        )

    except RPCError as error:

        save_candidate(
            candidate,
            "ERROR",
        )

        await message.edit_text(
            "❌ Telegram error:\n\n"
            f"{error}"
        )

    except Exception as error:

        logger.exception(
            "/createuser failed"
        )

        await message.edit_text(
            "❌ Error:\n\n"
            f"{error}"
        )


# ============================================================
# /myusernames
# ============================================================

async def myusernames_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
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
                "❌ Connect Telegram first."
            )
        )

        return

    normal, active, inactive = (
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
                f"@{normal}"
                if normal
                else "None"
            )
        ),
        "",
        "🟢 Active:",
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
            "⚪ Inactive:",
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
    context: ContextTypes.DEFAULT_TYPE,
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
                "❌ Connect Telegram first."
            )
        )

        return

    try:

        result = await user_client(
            ToggleUsernameRequest(
                username=username,
                active=True,
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
    context: ContextTypes.DEFAULT_TYPE,
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
                "❌ Connect Telegram first."
            )
        )

        return

    try:

        result = await user_client(
            ToggleUsernameRequest(
                username=username,
                active=False,
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
    context: ContextTypes.DEFAULT_TYPE,
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
                "/reorder username1 username2"
            )
        )

        return

    requested = [
        clean_username(x)
        for x in context.args
    ]

    if any(
        not valid_username(x)
        for x in requested
    ):

        await (
            update.effective_message
            .reply_text(
                "❌ Invalid username "
                "in the list."
            )
        )

        return

    me = await get_me()

    if not me:

        await (
            update.effective_message
            .reply_text(
                "❌ Connect Telegram first."
            )
        )

        return

    _, active, _ = (
        get_username_lists(me)
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
    context: ContextTypes.DEFAULT_TYPE,
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
        "📋 RECENT CHECKS",
        "",
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
# ERROR HANDLER
# ============================================================

async def error_handler(
    update,
    context,
):

    logger.error(
        "Bot error: %s",
        context.error,
        exc_info=context.error,
    )


# ============================================================
# BUILD BOT
# ============================================================

def build_application():

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "status",
            status_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "createuser",
            createuser_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "myusernames",
            myusernames_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "activate",
            activate_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "deactivate",
            deactivate_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "reorder",
            reorder_command,
        )
    )

    app.add_handler(
        CommandHandler(
            "history",
            history_command,
        )
    )

    app.add_error_handler(
        error_handler
    )

    return app


# ============================================================
# START
# ============================================================

async def run():

    init_database()

    print("=" * 60)
    print(
        "PERSONAL TELEGRAM USERNAME TOOL"
    )
    print("=" * 60)

    # Connect Telethon, but DO NOT use
    # interactive terminal login on Render.

    await user_client.connect()

    if await user_client.is_user_authorized():

        me = await user_client.get_me()

        logger.info(
            "Telegram session connected: %s",
            me.id,
        )

    else:

        logger.info(
            "Telegram account is not "
            "authorized yet."
        )

    # Start Render HTTP server.

    web_thread = threading.Thread(
        target=start_web_server,
        daemon=True,
        name="render-web-server",
    )

    web_thread.start()

    # Start Telegram BotFather bot.

    application = (
        build_application()
    )

    await application.initialize()

    await application.start()

    if application.updater is None:

        raise RuntimeError(
            "Telegram updater unavailable."
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

        await asyncio.Event().wait()

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
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            run()
        )

    except KeyboardInterrupt:

        print(
            "Stopped."
        )

    except Exception as error:

        logger.exception(
            "Fatal application error."
        )

        print(
            "Fatal error:",
            repr(error),
)
