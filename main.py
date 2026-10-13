# ============================================================
# TELEGRAM PERSONAL COLLECTIBLE USERNAME TOOL
#
# Python 3.10+
#
# Personal-use tool for:
# - Connecting to your Telegram account
# - Showing your usernames
# - Showing collectible usernames associated with your account
# - Activating/deactivating collectibles you own
# - Reordering active usernames
# - Checking ordinary username availability
# - Generating ONE candidate username at a time
#
# IMPORTANT:
# This does NOT bypass Fragment.
# It does NOT create fake collectible usernames.
# A collectible must legitimately belong to your account.
# ============================================================

import os
import re
import asyncio
import secrets
import string
from pathlib import Path

from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.tl.functions.account import (
    CheckUsernameRequest,
    ToggleUsernameRequest,
    ReorderUsernamesRequest,
)
from telethon.errors import RPCError

from database import (
    init_database,
    save_candidate,
    get_candidates,
)


# ------------------------------------------------------------
# LOAD ENVIRONMENT
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
SESSION_DIR = BASE_DIR / "session"

SESSION_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")


API_ID_RAW = os.getenv("API_ID", "").strip()
API_HASH = os.getenv("API_HASH", "").strip()
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "").strip()


if not API_ID_RAW:
    raise RuntimeError("API_ID is missing from .env")

if not API_HASH:
    raise RuntimeError("API_HASH is missing from .env")

if not PHONE_NUMBER:
    raise RuntimeError("PHONE_NUMBER is missing from .env")


try:
    API_ID = int(API_ID_RAW)
except ValueError:
    raise RuntimeError("API_ID must be a number")


# ------------------------------------------------------------
# TELEGRAM CLIENT
# ------------------------------------------------------------

SESSION_FILE = SESSION_DIR / "personal_account"

client = TelegramClient(
    str(SESSION_FILE),
    API_ID,
    API_HASH,
)


# ------------------------------------------------------------
# USERNAME HELPERS
# ------------------------------------------------------------

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_]{5,32}$")


def clean_username(username):
    """
    Remove @ and spaces.
    """

    username = username.strip()

    if username.startswith("@"):
        username = username[1:]

    return username


def valid_username(username):
    """
    Telegram username format check.

    This checks syntax only.
    It does not mean the username is available.
    """

    return bool(USERNAME_REGEX.fullmatch(username))


def username_link(username):
    return f"https://t.me/{username}"


# ------------------------------------------------------------
# GET USERNAME DATA
# ------------------------------------------------------------

async def get_my_account():
    return await client.get_me()


def extract_usernames(me):
    """
    Return:
        normal username
        active usernames
        inactive usernames
    """

    normal_username = getattr(me, "username", None)

    active = []
    inactive = []

    usernames = getattr(me, "usernames", None) or []

    for item in usernames:
        name = getattr(item, "username", None)

        if not name:
            continue

        is_active = getattr(item, "active", False)

        if is_active:
            active.append(name)
        else:
            inactive.append(name)

    return normal_username, active, inactive


# ------------------------------------------------------------
# DISPLAY ACCOUNT
# ------------------------------------------------------------

async def show_account():
    me = await get_my_account()

    normal, active, inactive = extract_usernames(me)

    print()
    print("=" * 55)
    print("YOUR TELEGRAM ACCOUNT")
    print("=" * 55)

    print(f"Name: {me.first_name or ''} {me.last_name or ''}".strip())
    print(f"ID:   {me.id}")

    if normal:
        print(f"Normal username: @{normal}")
    else:
        print("Normal username: None")

    print()

    print("Active usernames:")

    if active:
        for index, username in enumerate(active, start=1):
            print(f"  {index}. @{username}")
            print(f"     {username_link(username)}")
    else:
        print("  None")

    print()

    print("Inactive usernames:")

    if inactive:
        for index, username in enumerate(inactive, start=1):
            print(f"  {index}. @{username}")
    else:
        print("  None")

    print("=" * 55)
    print()


# ------------------------------------------------------------
# CHECK ORDINARY USERNAME
# ------------------------------------------------------------

async def check_username(username):
    """
    Check a username using Telegram's official
    account.checkUsername method.

    Important:
    An available ordinary username is NOT automatically
    a collectible username.
    """

    username = clean_username(username)

    if not valid_username(username):
        print()
        print("❌ Invalid username format.")
        print("   Use 5-32 characters: letters, numbers and _.")
        print()
        return False

    try:
        result = await client(
            CheckUsernameRequest(username)
        )

        if result:
            print()
            print(f"✅ @{username} is available as an ordinary username.")
            print(f"🔗 {username_link(username)}")
            print()
            save_candidate(username, "AVAILABLE")
            return True

        print()
        print(f"❌ @{username} is not available.")
        print()

        save_candidate(username, "TAKEN")

        return False

    except RPCError as error:
        print()
        print("Telegram response:")
        print(f"❌ {error}")
        print()

        save_candidate(username, f"ERROR: {error}")

        return False


# ------------------------------------------------------------
# GENERATE ONE CANDIDATE
# ------------------------------------------------------------

def generate_one_candidate(base):
    """
    Generate exactly ONE candidate.

    This does not claim the username.
    """

    base = clean_username(base)

    # Keep only Telegram-safe characters.
    base = re.sub(r"[^a-zA-Z0-9_]", "", base)

    if len(base) < 3:
        base = "user"

    # Keep room for suffix.
    base = base[:25]

    styles = [
        lambda: f"{base}{secrets.randbelow(90) + 10}",
        lambda: f"{base}_dev",
        lambda: f"{base}_tech",
        lambda: f"{base}_ng",
        lambda: f"real_{base}",
        lambda: f"mr_{base}",
    ]

    candidate = secrets.choice(styles)()

    # Final length protection.
    candidate = candidate[:32]

    # Make sure minimum length is satisfied.
    if len(candidate) < 5:
        candidate += "01"

    return candidate


async def generate_and_check_one():
    print()
    print("=" * 55)
    print("GENERATE ONE USERNAME")
    print("=" * 55)

    base = input("Enter a name/keyword: ").strip()

    if not base:
        print("❌ Nothing entered.")
        return

    candidate = generate_one_candidate(base)

    print()
    print(f"Generated: @{candidate}")
    print("Checking Telegram...")
    print()

    await check_username(candidate)


# ------------------------------------------------------------
# ACTIVATE COLLECTIBLE
# ------------------------------------------------------------

async def activate_collectible():
    """
    Activate a collectible username that is already
    associated with this Telegram account.

    It does NOT purchase or create one.
    """

    await show_account()

    username = input(
        "Enter the collectible username to activate: "
    ).strip()

    username = clean_username(username)

    if not username:
        return

    try:
        result = await client(
            ToggleUsernameRequest(
                username=username,
                active=True,
            )
        )

        if result:
            print()
            print(f"✅ @{username} activated.")
            print(f"🔗 {username_link(username)}")
            print()
        else:
            print()
            print(f"❌ Telegram did not activate @{username}.")
            print()

    except RPCError as error:
        print()
        print("❌ Telegram rejected the request.")
        print(f"   {error}")
        print()
        print(
            "Make sure this is a collectible username "
            "already associated with your account."
        )
        print()


# ------------------------------------------------------------
# DEACTIVATE COLLECTIBLE
# ------------------------------------------------------------

async def deactivate_collectible():
    """
    Deactivate a collectible username already associated
    with the account.
    """

    await show_account()

    username = input(
        "Enter the collectible username to deactivate: "
    ).strip()

    username = clean_username(username)

    if not username:
        return

    try:
        result = await client(
            ToggleUsernameRequest(
                username=username,
                active=False,
            )
        )

        if result:
            print()
            print(f"✅ @{username} deactivated.")
            print()
        else:
            print()
            print(f"❌ Telegram did not deactivate @{username}.")
            print()

    except RPCError as error:
        print()
        print("❌ Telegram rejected the request.")
        print(f"   {error}")
        print()


# ------------------------------------------------------------
# REORDER ACTIVE USERNAMES
# ------------------------------------------------------------

async def reorder_usernames():
    """
    Telegram requires all currently active usernames
    to be supplied in the new order.
    """

    me = await get_my_account()

    normal, active, inactive = extract_usernames(me)

    if not active:
        print()
        print("No active collectible usernames to reorder.")
        print()
        return

    print()
    print("=" * 55)
    print("ACTIVE COLLECTIBLE USERNAMES")
    print("=" * 55)

    for index, username in enumerate(active, start=1):
        print(f"{index}. @{username}")

    print()
    print("Enter the usernames in the new order.")
    print("Example:")
    print(",".join(active))

    raw = input("> ").strip()

    if not raw:
        return

    requested = [
        clean_username(x)
        for x in raw.split(",")
        if x.strip()
    ]

    # Telegram requires every active username.
    if set(requested) != set(active):
        print()
        print("❌ Invalid order.")
        print("You must include every currently active username exactly once.")
        print()
        return

    if len(requested) != len(active):
        print()
        print("❌ Duplicate usernames detected.")
        print()
        return

    try:
        result = await client(
            ReorderUsernamesRequest(
                order=requested
            )
        )

        if result:
            print()
            print("✅ Username order updated.")
            print()

    except RPCError as error:
        print()
        print("❌ Telegram rejected the reorder.")
        print(f"   {error}")
        print()


# ------------------------------------------------------------
# SHOW SAVED CANDIDATES
# ------------------------------------------------------------

def show_saved_candidates():
    rows = get_candidates()

    print()
    print("=" * 55)
    print("SAVED USERNAME CHECKS")
    print("=" * 55)

    if not rows:
        print("No username checks yet.")
        print()
        return

    for row in rows:
        print(
            f"@{row['username']} "
            f"→ {row['status']} "
            f"({row['created_at']})"
        )

    print()


# ------------------------------------------------------------
# FRAGMENT INFO
# ------------------------------------------------------------

async def show_fragment_info():
    """
    Try to retrieve Fragment collectible information.

    This is only for collectibles visible to your account.
    """

    username = input(
        "Enter collectible username (without @): "
    ).strip()

    username = clean_username(username)

    if not username:
        return

    try:
        # Import only when needed because availability of
        # the generated Fragment TL wrapper can vary by
        # Telethon version.
        from telethon.tl.functions.fragment import (
            GetCollectibleInfoRequest
        )
        from telethon.tl.types import (
            InputCollectibleUsername
        )

    except ImportError:
        print()
        print(
            "This Telethon installation does not expose "
            "the Fragment helper classes."
        )
        print(
            "The username management functions still work."
        )
        print()
        return

    try:
        result = await client(
            GetCollectibleInfoRequest(
                collectible=InputCollectibleUsername(
                    username=username
                )
            )
        )

        print()
        print("=" * 55)
        print("FRAGMENT COLLECTIBLE INFORMATION")
        print("=" * 55)

        print(f"Username: @{username}")

        purchase_date = getattr(
            result,
            "purchase_date",
            None
        )

        currency = getattr(
            result,
            "currency",
            None
        )

        amount = getattr(
            result,
            "amount",
            None
        )

        crypto_currency = getattr(
            result,
            "crypto_currency",
            None
        )

        crypto_amount = getattr(
            result,
            "crypto_amount",
            None
        )

        url = getattr(
            result,
            "url",
            None
        )

        print(f"Purchase date: {purchase_date}")
        print(f"Currency: {currency}")
        print(f"Amount: {amount}")

        if crypto_currency:
            print(
                f"Crypto: {crypto_amount} "
                f"{crypto_currency}"
            )

        if url:
            print(f"Fragment URL: {url}")

        print("=" * 55)
        print()

    except RPCError as error:
        print()
        print("❌ Could not retrieve collectible information.")
        print(f"   {error}")
        print()
        print(
            "The username may not be a visible collectible "
            "to your account."
        )


# ------------------------------------------------------------
# MENU
# ------------------------------------------------------------

def print_menu():
    print()
    print("=" * 55)
    print("     PERSONAL TELEGRAM USERNAME TOOL")
    print("=" * 55)
    print()
    print("1. Show my account and usernames")
    print("2. Generate ONE username and check it")
    print("3. Check a username")
    print("4. Activate owned collectible")
    print("5. Deactivate collectible")
    print("6. Reorder active usernames")
    print("7. Show Fragment collectible information")
    print("8. Show saved username checks")
    print("0. Exit")
    print()


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

async def main():
    init_database()

    print()
    print("=" * 55)
    print("PERSONAL TELEGRAM USERNAME TOOL")
    print("=" * 55)
    print()

    print("Connecting to Telegram...")

    await client.start(
        phone=PHONE_NUMBER
    )

    me = await client.get_me()

    print()
    print("✅ Telegram connected.")
    print(
        f"Logged in as: "
        f"{me.first_name or ''} "
        f"{me.last_name or ''}".strip()
    )

    if me.username:
        print(f"Username: @{me.username}")

    print()

    while True:
        print_menu()

        choice = input("Choose an option: ").strip()

        try:
            if choice == "1":
                await show_account()

            elif choice == "2":
                await generate_and_check_one()

            elif choice == "3":
                username = input(
                    "Enter username to check: "
                ).strip()

                await check_username(username)

            elif choice == "4":
                await activate_collectible()

            elif choice == "5":
                await deactivate_collectible()

            elif choice == "6":
                await reorder_usernames()

            elif choice == "7":
                await show_fragment_info()

            elif choice == "8":
                show_saved_candidates()

            elif choice == "0":
                print()
                print("Goodbye.")
                break

            else:
                print()
                print("❌ Invalid option.")
                print()

        except KeyboardInterrupt:
            print()
            print("Operation cancelled.")
            print()

        except Exception as error:
            print()
            print("❌ Unexpected error:")
            print(error)
            print()


# ------------------------------------------------------------
# RUN
# ------------------------------------------------------------

if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print()
        print("Stopped.")

    except Exception as error:
        print()
        print("Fatal error:")
        print(error)
