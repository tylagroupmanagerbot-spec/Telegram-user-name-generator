# ============================================================
# PERSONAL TELEGRAM COLLECTIBLE USERNAME TOOL
# File: main.py
# Python 3.10+
# Render Web Service compatible
#
# IMPORTANT:
# - This does NOT bypass Fragment.
# - This does NOT mint fake collectible usernames.
# - A collectible must legitimately belong to your account.
# - Only OWNER_USER_ID can control the bot.
# ============================================================

import os
import re
import asyncio
import secrets
import logging
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.tl.functions.account import (
    CheckUsernameRequest,
    ToggleUsernameRequest,
    ReorderUsernamesRequest,
)
from telethon.errors import RPCError

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
# PATHS / ENVIRONMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
SESSION_DIR = BASE_DIR / "session"

SESSION_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

load_dotenv(BASE_DIR / ".env")


# ============================================================
# CONFIG
# ============================================================

API_ID_RAW = os.getenv(
    "API_ID",
    "",
).strip()

API_HASH = os.getenv(
    "API_HASH",
    "",
).strip()

PHONE_NUMBER = os.getenv(
    "PHONE_NUMBER",
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


# ============================================================
# VALIDATE CONFIG
# ============================================================

if not API_ID_RAW:
    raise RuntimeError(
        "API_ID is missing."
    )

if not API_HASH:
    raise RuntimeError(
        "API_HASH is missing."
    )

if not PHONE_NUMBER:
    raise RuntimeError(
        "PHONE_NUMBER is missing."
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
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    level=logging.INFO,
)

logger = logging.getLogger(
    __name__
)


# ============================================================
# RENDER WEB SERVER
# ============================================================

class HealthHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        if self.path in (
            "/",
            "/health",
            "/healthz",
        ):

            body = (
                b"Telegram Username Tool is running."
            )

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8",
            )

            self.send_header(
                "Content-Length",
                str(len(body)),
            )

            self.end_headers()

            self.wfile.write(
                body
            )

            return

        body = b"Not Found"

        self.send_response(404)

        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.end_headers()

        self.wfile.write(
            body
        )

    def log_message(
        self,
        format,
        *args,
    ):
        return


def start_web_server():

    try:

        server = ThreadingHTTPServer(
            (
                "0.0.0.0",
                PORT,
            ),
            HealthHandler,
        )

        logger.info(
            "Render HTTP server listening "
            "on 0.0.0.0:%s",
            PORT,
        )

        server.serve_forever()

    except Exception:
        logger.exception(
            "HTTP server crashed."
        )

        raise


# ============================================================
# TELEGRAM USER SESSION
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

    if not update.effective_user:
        return False

    return (
        update.effective_user.id
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
# USERNAME HELPERS
# ============================================================

USERNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9_]{5,32}$"
)


def clean_username(
    value: str,
) -> str:

    value = value.strip()

    if value.startswith("@"):
        value = value[1:]

    return value


def valid_username(
    username: str,
) -> bool:

    return bool(
        USERNAME_PATTERN.fullmatch(
            username
        )
    )


def telegram_link(
    username: str,
) -> str:

    return (
        f"https://t.me/{username}"
    )


# ============================================================
# TELEGRAM USER ACCOUNT HELPERS
# ============================================================

async def get_me():

    return await user_client.get_me()


def get_username_lists(me):

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

    text = (
        "🤖 *Personal Telegram Username Tool*\n\n"

        "Your control bot is connected to your "
        "Telegram user account.\n\n"

        "*Commands*\n\n"

        "/createuser name\n"
        "Generate one username candidate and "
        "check ordinary Telegram availability.\n\n"

        "/myusernames\n"
        "Show usernames currently attached "
        "to your account.\n\n"

        "/activate username\n"
        "Activate an owned username.\n\n"

        "/deactivate username\n"
        "Deactivate an owned username.\n\n"

        "/reorder name1 name2 ...\n"
        "Reorder active usernames.\n\n"

        "/info username\n"
        "Request collectible information "
        "when supported.\n\n"

        "/history\n"
        "Show recent username checks."
    )

    await (
        update.effective_message
        .reply_text(
            text,
            parse_mode="Markdown",
        )
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

    try:

        me = await get_me()

        (
            normal,
            active,
            inactive,
        ) = get_username_lists(
            me
        )

        lines = [
            "👤 *YOUR TELEGRAM ACCOUNT*",
            "",
            (
                f"Name: "
                f"{me.first_name or ''} "
                f"{me.last_name or ''}"
            ).strip(),
            f"ID: `{me.id}`",
            "",
        ]

        if normal:

            lines.append(
                f"Normal username: "
                f"@{normal}"
            )

        else:

            lines.append(
                "Normal username: None"
            )

        lines.append("")
        lines.append(
            "🟢 *Active usernames:*"
        )

        if active:

            for username in active:

                lines.append(
                    f"• @{username}\n"
                    f"  "
                    f"{telegram_link(username)}"
                )

        else:

            lines.append(
                "• None"
            )

        lines.append("")
        lines.append(
            "⚪ *Inactive usernames:*"
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
                "\n".join(lines),
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        )

    except Exception as error:

        logger.exception(
            "/myusernames failed"
        )

        await (
            update.effective_message
            .reply_text(
                f"❌ Error:\n{error}"
            )
        )


# ============================================================
# GENERATE CANDIDATE
# ============================================================

def generate_candidate(
    base: str,
) -> str:

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

    base = base[:24]

    choices = [
        (
            f"{base}"
            f"{secrets.randbelow(90) + 10}"
        ),
        f"{base}_dev",
        f"{base}_tech",
        f"{base}_ng",
        f"real_{base}",
        f"mr_{base}",
    ]

    candidate = secrets.choice(
        choices
    )

    candidate = candidate[:32]

    while len(candidate) < 5:
        candidate += "0"

    return candidate


# ============================================================
# TELEGRAM USERNAME CHECK
# ============================================================

async def telegram_check(
    username: str,
):

    result = await user_client(
        CheckUsernameRequest(
            username=username
        )
    )

    return bool(result)


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
                "/createuser mrdarkdev"
            )
        )

        return

    base = context.args[0]

    candidate = generate_candidate(
        base
    )

    if not valid_username(
        candidate
    ):

        await (
            update.effective_message
            .reply_text(
                "❌ Generated username "
                "was invalid."
            )
        )

        return

    message = await (
        update.effective_message
        .reply_text(
            f"🔎 Checking "
            f"@{candidate}..."
        )
    )

    try:

        available = await telegram_check(
            candidate
        )

        if available:

            status = "AVAILABLE"

            save_candidate(
                candidate,
                status,
            )

            text = (
                "✅ *USERNAME AVAILABLE*\n\n"

                f"Username: "
                f"`@{candidate}`\n\n"

                "Type: Ordinary Telegram "
                "username\n\n"

                f"🔗 "
                f"{telegram_link(candidate)}"
                "\n\n"

                "⚠️ Availability does not mean "
                "the username is a Fragment "
                "collectible."
            )

        else:

            status = "TAKEN"

            save_candidate(
                candidate,
                status,
            )

            text = (
                "❌ *USERNAME UNAVAILABLE*\n\n"

                f"@{candidate}\n\n"

                "Telegram did not make this "
                "username available."
            )

        await message.edit_text(
            text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

    except RPCError as error:

        logger.exception(
            "Telegram username check failed"
        )

        save_candidate(
            candidate,
            f"ERROR: {error}",
        )

        await message.edit_text(
            "❌ Telegram returned an error:"
            "\n\n"
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
                "Usage:\n\n"
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

    try:

        result = await user_client(
            ToggleUsernameRequest(
                username=username,
                active=True,
            )
        )

        if result:

            await (
                update.effective_message
                .reply_text(
                    "✅ *Activated*\n\n"
                    f"@{username}\n\n"
                    f"🔗 "
                    f"{telegram_link(username)}",
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
            )

        else:

            await (
                update.effective_message
                .reply_text(
                    "❌ Telegram did not "
                    "activate it."
                )
            )

    except RPCError as error:

        await (
            update.effective_message
            .reply_text(
                "❌ Could not activate "
                "username.\n\n"
                f"{error}\n\n"
                "Make sure the username "
                "belongs to your account and "
                "Telegram allows it to be activated."
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
                "Usage:\n\n"
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

    try:

        result = await user_client(
            ToggleUsernameRequest(
                username=username,
                active=False,
            )
        )

        if result:

            await (
                update.effective_message
                .reply_text(
                    f"✅ @{username} "
                    "deactivated."
                )
            )

        else:

            await (
                update.effective_message
                .reply_text(
                    "❌ Telegram did not "
                    "deactivate it."
                )
            )

    except RPCError as error:

        await (
            update.effective_message
            .reply_text(
                "❌ Could not deactivate "
                "username.\n\n"
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
                "/reorder username1 "
                "username2 username3"
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
                "❌ One or more usernames "
                "are invalid."
            )
        )

        return

    try:

        me = await get_me()

        _, active, _ = (
            get_username_lists(me)
        )

        if set(requested) != set(active):

            await (
                update.effective_message
                .reply_text(
                    "❌ Invalid order.\n\n"
                    "Include every currently "
                    "active username exactly once."
                )
            )

            return

        if len(requested) != len(
            set(requested)
        ):

            await (
                update.effective_message
                .reply_text(
                    "❌ Duplicate username "
                    "detected."
                )
            )

            return

        result = await user_client(
            ReorderUsernamesRequest(
                order=requested
            )
        )

        if result:

            await (
                update.effective_message
                .reply_text(
                    "✅ Username order updated."
                )
            )

        else:

            await (
                update.effective_message
                .reply_text(
                    "❌ Telegram did not "
                    "update the order."
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
# /info
# ============================================================

async def info_command(
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
                "/info username"
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

    try:

        # These Telegram API objects may depend
        # on the Telethon/API layer version.
        from telethon.tl.functions.fragment import (
            GetCollectibleInfoRequest,
        )

        from telethon.tl.types import (
            InputCollectibleUsername,
        )

    except ImportError:

        await (
            update.effective_message
            .reply_text(
                "⚠️ Your installed Telethon "
                "version does not expose the "
                "collectible-info helper types."
            )
        )

        return

    try:

        result = await user_client(
            GetCollectibleInfoRequest(
                collectible=(
                    InputCollectibleUsername(
                        username=username
                    )
                )
            )
        )

        lines = [
            "💎 *COLLECTIBLE INFORMATION*",
            "",
            f"Username: @{username}",
        ]

        for field in (
            "purchase_date",
            "currency",
            "amount",
            "crypto_currency",
            "crypto_amount",
            "url",
        ):

            value = getattr(
                result,
                field,
                None,
            )

            if value is not None:

                lines.append(
                    f"{field}: {value}"
                )

        await (
            update.effective_message
            .reply_text(
                "\n".join(lines),
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        )

    except RPCError as error:

        await (
            update.effective_message
            .reply_text(
                "❌ Could not retrieve "
                "collectible information.\n\n"
                f"{error}"
            )
        )

    except Exception as error:

        logger.exception(
            "/info failed"
        )

        await (
            update.effective_message
            .reply_text(
                "❌ Collectible information "
                "is not available.\n\n"
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
        "📋 *RECENT CHECKS*",
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
            "\n".join(lines),
            parse_mode="Markdown",
        )
    )


# ============================================================
# BOT ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.error(
        "Bot error while processing update: %s",
        context.error,
        exc_info=context.error,
    )


# ============================================================
# TELEGRAM CONTROL BOT
# ============================================================

def build_application():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "createuser",
            createuser_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "myusernames",
            myusernames_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "activate",
            activate_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "deactivate",
            deactivate_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "reorder",
            reorder_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "info",
            info_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "history",
            history_command,
        )
    )

    application.add_error_handler(
        error_handler
    )

    return application


# ============================================================
# STARTUP
# ============================================================

async def run():

    init_database()

    print("=" * 60)
    print(
        "PERSONAL TELEGRAM USERNAME TOOL"
    )
    print("=" * 60)
    print()

    # --------------------------------------------------------
    # CONNECT USER ACCOUNT
    # --------------------------------------------------------

    print(
        "Connecting to Telegram "
        "user account..."
    )

    await user_client.connect()

    # If a valid saved session exists,
    # no login code is needed again.
    if not await user_client.is_user_authorized():

        print()
        print(
            "No authorized Telegram "
            "session was found."
        )
        print()
        print(
            "A first-time Telegram login "
            "is required."
        )
        print(
            "Do not place your login code "
            "or 2FA password in .env."
        )
        print()

        # This can request a Telegram login code
        # interactively during first-time setup.
        # For a long-running Render deployment,
        # create/persist the session securely.
        await user_client.start(
            phone=PHONE_NUMBER
        )

    me = await user_client.get_me()

    print(
        "Logged in as:",
        (
            f"{me.first_name or ''} "
            f"{me.last_name or ''}"
        ).strip(),
    )

    if me.username:

        print(
            f"Username: @{me.username}"
        )

    print(
        f"Telegram ID: {me.id}"
    )

    print()
    print(
        "Telegram user account connected."
    )
    print()

    # --------------------------------------------------------
    # START BOTFATHER CONTROL BOT
    # --------------------------------------------------------

    print(
        "Starting Telegram control bot..."
    )

    application = build_application()

    await application.initialize()
    await application.start()

    if application.updater is None:

        raise RuntimeError(
            "Telegram updater is unavailable."
        )

    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )

    print()
    print(
        "Control bot is running."
    )
    print(
        "Send /start to your bot."
    )
    print()

    try:

        # Keep both Telegram clients alive.
        await asyncio.Event().wait()

    finally:

        logger.info(
            "Shutting down..."
        )

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

    # Render requires a Web Service to bind
    # to an HTTP port.
    web_thread = threading.Thread(
        target=start_web_server,
        daemon=True,
        name="render-health-server",
    )

    web_thread.start()

    try:

        asyncio.run(
            run()
        )

    except KeyboardInterrupt:

        print()
        print(
            "Stopped."
        )

    except Exception as error:

        logger.exception(
            "Fatal application error"
        )

        print()
        print(
            "Fatal error:"
        )
        print(
            error
        )
