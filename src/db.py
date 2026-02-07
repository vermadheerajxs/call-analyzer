import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime, timezone


# Load database credentials from environment variables
load_dotenv()

# Database connection configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "port": os.getenv("DB_PORT", 5432),
}


def get_conn():
    """
    Creates and returns a new PostgreSQL database connection.
    """
    return psycopg2.connect(**DB_CONFIG)


def fetch_jobs(limit):
    """
    Fetches pending call records that have not yet been analyzed.
    Limits the number of rows returned per batch.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT "id", "recordingUrl"
        FROM "CallLog"
        --WHERE "aiSummary" IS NULL
        LIMIT %s
    """, (limit,))

    rows = cur.fetchall()

    cur.close()
    conn.close()
    return rows


def update_result(job_id, r):
    """
    Updates analysis results for a processed call record.
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE "CallLog"
        SET "aiSummary"=%s,
            "aiDisposition"=%s,
            "aiCallRating"=%s,
            "updatedAt"=%s
        WHERE "id"=%s
    """, (
        r["ai_summary"],
        r["ai_disposition"],
        r["call_rating"],
        datetime.now(timezone.utc),
        job_id
    ))

    conn.commit()
    cur.close()
    conn.close()
