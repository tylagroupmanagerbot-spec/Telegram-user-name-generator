# ============================================================
# PERSONAL TELEGRAM USERNAME TOOL
# File: main.py
# Python 3.10+
#
# Render Web Service + HTML + Telegram Bot + Telethon
#
# Project:
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
import io
import json
import time
import asyncio
import secrets
import logging
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import qrcode
from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.errors import (
    RPCError,
    SessionPasswordNeededError,
)
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


# ============================================================
# VALIDATE
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
    ),
)

logger = logging.getLogger(
    "username-tool"
)


# ============================================================
# TELETHON
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
# EVENT LOOP
# ============================================================

MAIN_LOOP = None


# ============================================================
# QR LOGIN STATE
# ============================================================

qr_lock = threading.Lock()

qr_state = {
    "token": None,
    "url": None,
    "created": 0,
    "status": "idle",
    "error": None,
}


# ============================================================
# OWNER SECURITY
# ============================================================

def owner_only(
    update: Update,
):

    user = update.effective_user

    return bool(
        user
        and
        user.id == OWNER_USER_ID
    )


async def deny_if_not_owner(
    update: Update,
):

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
            "Telegram authorization "
            "check failed."
        )

        return False


async def get_me():

    await ensure_connected()

    if not await user_client.is_user_authorized():

        return None

    return await user_client.get_me()


# ============================================================
# CALL ASYNC CODE FROM HTTP THREAD
# ============================================================

def run_async(
    coroutine,
    timeout=20,
):

    if MAIN_LOOP is None:

        raise RuntimeError(
            "Application event loop "
            "is not ready."
        )

    future = (
        asyncio.run_coroutine_threadsafe(
            coroutine,
            MAIN_LOOP,
        )
    )

    return future.result(
        timeout=timeout
    )


# ============================================================
# QR AUTHORIZATION
# ============================================================

async def start_qr_authorization():

    await ensure_connected()

    if await user_client.is_user_authorized():

        return {
            "connected": True,
        }

    qr_login = await (
        user_client.qr_login()
    )

    token = secrets.token_urlsafe(
        24
    )

    with qr_lock:

        qr_state["token"] = token
        qr_state["url"] = qr_login.url
        qr_state["created"] = time.time()
        qr_state["status"] = "waiting"
        qr_state["error"] = None

    asyncio.create_task(
        wait_for_qr(
            qr_login,
            token,
        )
    )

    return {
        "connected": False,
        "token": token,
        "authorization_url": (
            "/connect?token="
            + token
        ),
    }


async def wait_for_qr(
    qr_login,
    token,
):

    try:

        await qr_login.wait(
            timeout=120
        )

        if not await user_client.is_user_authorized():

            raise RuntimeError(
                "Telegram did not authorize "
                "the session."
            )

        me = await user_client.get_me()

        logger.info(
            "Telegram account connected: %s",
            me.id,
        )

        with qr_lock:

            if qr_state["token"] == token:

                qr_state["status"] = (
                    "connected"
                )

                qr_state["error"] = None

    except SessionPasswordNeededError:

        # Do not collect the user's Telegram
        # 2FA password through this website.

        with qr_lock:

            if qr_state["token"] == token:

                qr_state["status"] = "2fa"

                qr_state["error"] = (
                    "Telegram two-step "
                    "verification is enabled."
                )

    except asyncio.TimeoutError:

        with qr_lock:

            if qr_state["token"] == token:

                qr_state["status"] = (
                    "expired"
                )

                qr_state["error"] = (
                    "QR code expired."
                )

    except Exception as error:

        logger.exception(
            "QR authorization failed."
        )

        with qr_lock:

            if qr_state["token"] == token:

                qr_state["status"] = (
                    "error"
                )

                qr_state["error"] = str(
                    error
                )


# ============================================================
# QR IMAGE
# ============================================================

def create_qr_png(
    value,
):

    image = qrcode.make(
        value
    )

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="PNG",
    )

    return buffer.getvalue()


# ============================================================
# HTML
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
templates/index.html was not found.
</p>

</body>
</html>
"""


def connect_page(
    token,
):

    safe_token = json.dumps(
        token
    )

    return f"""<!doctype html>

<html lang="en">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width,initial-scale=1"
>

<title>Connect Telegram</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{

    margin: 0;

    min-height: 100vh;

    background:
        linear-gradient(
            135deg,
            #0f172a,
            #111827,
            #1e293b
        );

    color: white;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    display: flex;

    justify-content: center;
    align-items: center;

    padding: 20px;
}}

.card {{

    width: 100%;
    max-width: 430px;

    background:
        rgba(
            255,
            255,
            255,
            0.07
        );

    border:
        1px solid
        rgba(
            255,
            255,
            255,
            0.10
        );

    border-radius: 22px;

    padding: 26px;

    text-align: center;
}}

h1 {{
    margin-top: 0;
}}

p {{
    color: #cbd5e1;
    line-height: 1.6;
}}

.qr {{

    width: 280px;
    max-width: 100%;

    background: white;

    padding: 12px;

    border-radius: 18px;

    margin:
        15px
        auto;
}}

.status {{

    margin-top: 18px;

    padding: 14px;

    background:
        rgba(
            255,
            255,
            255,
            0.07
        );

    border-radius: 14px;
}}

a {{

    color: white;
}}

</style>

</head>

<body>

<div class="card">

<h1>Connect Telegram</h1>

<p>
Open Telegram and go to
<strong>
Settings → Devices → Link Desktop Device
</strong>.
</p>

<img
    class="qr"
    src="/api/qr?token={token}"
    alt="Telegram authorization QR"
>

<div
    class="status"
    id="status"
>
Waiting for Telegram approval...
</div>

<p>
Do not share this QR with anyone.
</p>

</div>


<script>

const token = {safe_token};

async function check() {{

    try {{

        const response =
            await fetch(
                "/api/login-status?token="
                + encodeURIComponent(token),
                {{
                    cache: "no-store"
                }}
            );

        const data =
            await response.json();

        const box =
            document.getElementById(
                "status"
            );

        if (data.status === "connected") {{

            box.textContent =
                "✅ Telegram connected successfully.";

            setTimeout(
                () => {{
                    window.location.href = "/";
                }},
                1000
            );

            return;
        }}

        if (data.status === "expired") {{

            box.textContent =
                "⌛ QR expired. Return and try again.";

            return;
        }}

        if (data.status === "2fa") {{

            box.textContent =
                "🔐 This Telegram account requires "
                + "two-step verification. "
                + "This website does not collect "
                + "your 2FA password.";

            return;
        }}

        if (data.status === "error") {{

            box.textContent =
                "❌ Telegram authorization failed.";

            return;
        }}

        setTimeout(
            check,
            1500
        );

    }} catch (error) {{

        setTimeout(
            check,
            2000
        );
    }}
}}

check();

</script>

</body>
</html>
"""


# ============================================================
# HTTP SERVER
# ============================================================

class WebHandler(
    BaseHTTPRequestHandler
):

    def send_bytes(
        self,
        body,
        status=200,
        content_type=(
            "application/octet-stream"
        ),
    ):

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

    def send_text(
        self,
        text,
        status=200,
        content_type=(
            "text/plain; charset=utf-8"
        ),
    ):

        body = text.encode(
            "utf-8"
        )

        self.send_bytes(
            body,
            status,
            content_type,
        )

    def send_json(
        self,
        data,
        status=200,
    ):

        body = json.dumps(
            data
        ).encode(
            "utf-8"
        )

        self.send_bytes(
            body,
            status,
            "application/json; charset=utf-8",
        )

    def send_html(
        self,
        content,
        status=200,
    ):

        self.send_text(
            content,
            status,
            "text/html; charset=utf-8",
        )

    def do_GET(self):

        parsed = urlparse(
            self.path
        )

        path = parsed.path

        query = {}

        if parsed.query:

            from urllib.parse import (
                parse_qs,
            )

            query = parse_qs(
                parsed.query
            )

        # ----------------------------------------------------
        # HOME
        # ----------------------------------------------------

        if path == "/":

            self.send_html(
                load_index_html()
            )

            return

        # ----------------------------------------------------
        # HEALTH
        # ----------------------------------------------------

        if path in (
            "/health",
            "/healthz",
        ):

            self.send_text(
                "OK"
            )

            return

        # ----------------------------------------------------
        # CONNECT PAGE
        # ----------------------------------------------------

        if path == "/connect":

            token = (
                query.get(
                    "token",
                    [""],
                )[0]
            )

            with qr_lock:

                valid = (
                    token
                    and
                    qr_state["token"]
                    == token
                )

            if not valid:

                self.send_html(
                    "<h1>Invalid or expired "
                    "connection.</h1>",
                    400,
                )

                return

            self.send_html(
                connect_page(
                    token
                )
            )

            return

        # ----------------------------------------------------
        # API STATUS
        # ----------------------------------------------------

        if path == "/api/status":

            try:

                connected = run_async(
                    is_account_connected()
                )

                result = {
                    "connected": bool(
                        connected
                    )
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
                    "Status API failed."
                )

                self.send_json(
                    {
                        "connected": False,
                        "error": str(error),
                    },
                    500,
                )

            return

        # ----------------------------------------------------
        # LOGIN STATUS
        # ----------------------------------------------------

        if path == "/api/login-status":

            token = (
                query.get(
                    "token",
                    [""],
                )[0]
            )

            with qr_lock:

                if (
                    not token
                    or
                    qr_state["token"]
                    != token
                ):

                    self.send_json(
                        {
                            "status": "invalid"
                        },
                        404,
                    )

                    return

                status = (
                    qr_state["status"]
                )

                error = (
                    qr_state["error"]
                )

            self.send_json(
                {
                    "status": status,
                    "error": error,
                }
            )

            return

        # ----------------------------------------------------
        # QR IMAGE
        # ----------------------------------------------------

        if path == "/api/qr":

            token = (
                query.get(
                    "token",
                    [""],
                )[0]
            )

            with qr_lock:

                if (
                    not token
                    or
                    qr_state["token"]
                    != token
                ):

                    self.send_text(
                        "Invalid QR.",
                        404,
                    )

                    return

                qr_url = (
                    qr_state["url"]
                )

            if not qr_url:

                self.send_text(
                    "QR unavailable.",
                    404,
                )

                return

            image = create_qr_png(
                qr_url
            )

            self.send_bytes(
                image,
                200,
                "image/png",
            )

            return

        # ----------------------------------------------------
        # NOT FOUND
        # ----------------------------------------------------

        self.send_text(
            "Not Found",
            404,
        )

    def do_POST(self):

        parsed = urlparse(
            self.path
        )

        # ----------------------------------------------------
        # START TELEGRAM CONNECTION
        # ----------------------------------------------------

        if parsed.path == "/api/connect":

            try:

                result = run_async(
                    start_qr_authorization()
                )

                self.send_json(
                    result
                )

            except Exception as error:

                logger.exception(
                    "Could not start "
                    "Telegram authorization."
                )

                self.send_json(
                    {
                        "connected": False,
                        "error": str(error),
                    },
                    500,
                )

            return

        self.send_json(
            {
                "error": "Not Found"
            },
            404,
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
        "Render web server listening "
        "on 0.0.0.0:%s",
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

    choices = [
        f"{base}{secrets.randbelow(900) + 100}",
        f"{base}_dev",
        f"{base}_tech",
        f"{base}_ng",
        f"real_{base}",
        f"mr_{base}",
    ]

    candidate = secrets.choice(
        choices
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

    status = (
        "🟢 Connected"
        if connected
        else
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
                "🔴 Telegram account "
                "is not connected."
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
            status,
        )

        if available:

            text = (
                "✅ USERNAME AVAILABLE\n\n"
                f"@{candidate}\n\n"
                "Ordinary Telegram username "
                "availability.\n"
                "This does not mean it is a "
                "Fragment collectible."
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
            "ERROR",
        )

        await message.edit_text(
            "❌ Telegram error:\n\n"
            f"{error}"
        )

    except Exception as error:

        logger.exception(
            "/createuser failed."
        )

        await message.edit_text(
            f"❌ Error:\n\n{error}"
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
        "👤 MY USERNAMES",
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

        await (
            update.effective_message
            .reply_text(
                (
                    f"✅ @{username} activated."
                    if result
                    else
                    "❌ Telegram did not "
                    "activate the username."
                )
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

        await (
            update.effective_message
            .reply_text(
                (
                    f"✅ @{username} deactivated."
                    if result
                    else
                    "❌ Telegram did not "
                    "deactivate the username."
                )
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

    if (
        len(requested)
        != len(set(requested))
    ):

        await (
            update.effective_message
            .reply_text(
                "❌ Duplicate username."
            )
        )

        return

    if any(
        not valid_username(x)
        for x in requested
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

        await (
            update.effective_message
            .reply_text(
                (
                    "✅ Username order updated."
                    if result
                    else
                    "❌ Telegram did not "
                    "update the order."
                )
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
# BOT ERROR HANDLER
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
# BUILD TELEGRAM BOT
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
            start_command,
        ),
        (
            "status",
            status_command,
        ),
        (
            "createuser",
            createuser_command,
        ),
        (
            "myusernames",
            myusernames_command,
        ),
        (
            "activate",
            activate_command,
        ),
        (
            "deactivate",
            deactivate_command,
        ),
        (
            "reorder",
            reorder_command,
        ),
        (
            "history",
            history_command,
        ),
    ]

    for command, callback in handlers:

        application.add_handler(
            CommandHandler(
                command,
                callback,
            )
        )

    application.add_error_handler(
        error_handler
    )

    return application


# ============================================================
# RUN
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

    # Connect MTProto client without
    # interactive terminal login.

    await user_client.connect()

    if await user_client.is_user_authorized():

        me = await user_client.get_me()

        logger.info(
            "Telegram user account "
            "connected: %s",
            me.id,
        )

    else:

        logger.info(
            "Telegram user account is "
            "not authorized yet."
        )

    # Start Render HTTP server.

    web_thread = threading.Thread(
        target=start_web_server,
        daemon=True,
        name="render-web-server",
    )

    web_thread.start()

    # Start BotFather control bot.

    application = (
        build_application()
    )

    await application.initialize()

    await application.start()

    if application.updater is None:

        raise RuntimeError(
            "Telegram bot updater "
            "is unavailable."
        )

    await (
        application.updater
        .start_polling(
            allowed_updates=(
                Update.ALL_TYPES
            ),
            drop_pending_updates=False,
        )
    )

    logger.info(
        "Telegram control bot running."
    )

    try:

        await asyncio.Event().wait()

    finally:

        logger.info(
            "Shutting down."
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
