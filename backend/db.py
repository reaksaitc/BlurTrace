"""
db.py
-----
Database connection handling and operations for BlurTrace.

Fixes the known .env loading issue by resolving the .env path explicitly
relative to this file's location, instead of relying on the current
working directory (which changes depending on how/where uvicorn is launched
from in VS Code on Windows).
"""

import os
import uuid
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# --- Explicit .env path resolution -----------------------------------------
# backend/db.py -> backend/.env  (NOT the current working directory)
ENV_PATH = Path(__file__).resolve().parent / ".env"

_loaded = load_dotenv(dotenv_path=ENV_PATH)

print(f"[db.py] Looking for .env at: {ENV_PATH}")
print(f"[db.py] .env file exists on disk: {ENV_PATH.exists()}")
print(f"[db.py] python-dotenv reports loaded: {_loaded}")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

print(f"[db.py] DB_HOST={DB_HOST}  DB_PORT={DB_PORT}  DB_NAME={DB_NAME}  DB_USER={DB_USER}  "
      f"DB_PASSWORD={'<set>' if DB_PASSWORD else '<MISSING>'}")

if not DB_PASSWORD:
    raise RuntimeError(
        f"DB_PASSWORD is missing. Checked .env at: {ENV_PATH} "
        f"(exists on disk: {ENV_PATH.exists()}). "
        f"Create backend/.env with DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD."
    )
if not DB_NAME or not DB_USER:
    raise RuntimeError(
        f"DB_NAME or DB_USER is missing from .env at: {ENV_PATH}. "
        f"Both are required."
    )


def get_connection():
    """Open a new psycopg2 connection using the loaded .env config."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def init_db():
    """Create the image_pairs table if it doesn't already exist."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS image_pairs (
                    image_id        UUID PRIMARY KEY,
                    original_img    BYTEA NOT NULL,
                    blurred_img     BYTEA NOT NULL,
                    blurred_hash    TEXT UNIQUE NOT NULL,
                    blur_method     TEXT,
                    created_at      TIMESTAMP DEFAULT NOW()
                );
                """
            )
        conn.commit()
        print("[db.py] image_pairs table ready.")
    finally:
        conn.close()


def store_pair(original_bytes: bytes, blurred_bytes: bytes, blurred_hash: str, blur_method: str) -> str:
    """
    Insert a new (original, blurred) pair keyed by the blurred image's hash.

    Returns the new image_id (as a string).

    If the hash already exists (blurred_hash is UNIQUE), this will raise
    psycopg2.errors.UniqueViolation. The caller (main.py) should catch this
    and treat it as "already stored" rather than a hard failure, since the
    UI's Save/Copy buttons show "Already stored in database" on that case.
    """
    image_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO image_pairs (image_id, original_img, blurred_img, blurred_hash, blur_method)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (image_id, psycopg2.Binary(original_bytes), psycopg2.Binary(blurred_bytes), blurred_hash, blur_method),
            )
        conn.commit()
        return image_id
    finally:
        conn.close()


def find_original_by_hash(blurred_hash: str):
    """
    Look up a stored pair by the exact SHA-256 hash of a blurred image's bytes.

    Returns a dict with the row data if found, or None if no match.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT image_id, original_img, blur_method, created_at
                FROM image_pairs
                WHERE blurred_hash = %s
                """,
                (blurred_hash,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def hash_already_stored(blurred_hash: str) -> bool:
    """Quick existence check without pulling the full row (used to avoid duplicate inserts)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM image_pairs WHERE blurred_hash = %s", (blurred_hash,))
            return cur.fetchone() is not None
    finally:
        conn.close()