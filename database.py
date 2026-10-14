# ============================================================
# File: database.py
# SQLite database for username checks
# ============================================================

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_FILE = BASE_DIR / "bot.db"


def connect():

    connection = sqlite3.connect(
        DATABASE_FILE,
        timeout=30
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_database():

    with connect() as db:

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                status TEXT NOT NULL,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        db.commit()


def save_candidate(
    username,
    status
):

    with connect() as db:

        db.execute(
            """
            INSERT INTO candidates (
                username,
                status
            )
            VALUES (?, ?)
            """,
            (
                username,
                status
            )
        )

        db.commit()


def get_candidates(
    limit=20
):

    with connect() as db:

        rows = db.execute(
            """
            SELECT
                id,
                username,
                status,
                checked_at
            FROM candidates
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]
