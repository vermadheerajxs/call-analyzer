import os
from datetime import datetime, timezone

import psycopg2

from paths import load_project_env

load_project_env()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "port": os.getenv("DB_PORT", 5432),
}


def process_all_recordings() -> bool:
    """
    PROCESS_ALL_RECORDINGS=true → every row with a recording URL (re-analyze).
    false/unset → only unprocessed rows (aiSummary IS NULL).
    """
    return (os.getenv("PROCESS_ALL_RECORDINGS") or "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def fetch_jobs(limit):
    """
    Fetch call recordings to analyze.
    Default: pending only (aiSummary IS NULL).
    If PROCESS_ALL_RECORDINGS=true: all rows with a non-empty recordingUrl.
    """
    conn = get_conn()
    cur = conn.cursor()

    if process_all_recordings():
        cur.execute(
            """
            SELECT "id", "recordingUrl"
            FROM "CallLog"
            WHERE "recordingUrl" IS NOT NULL
              AND "recordingUrl" <> ''
            LIMIT %s
            """,
            (limit,),
        )
    else:
        cur.execute(
            """
            SELECT "id", "recordingUrl"
            FROM "CallLog"
            WHERE "aiSummary" IS NULL
              AND "recordingUrl" IS NOT NULL
              AND "recordingUrl" <> ''
            LIMIT %s
            """,
            (limit,),
        )

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def update_result(job_id, r):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE "CallLog"
        SET "aiSummary"=%s,
            "aiDisposition"=%s,
            "aiCallRating"=%s,
            "updatedAt"=%s
        WHERE "id"=%s
        """,
        (
            r["ai_summary"],
            r["ai_disposition"],
            r["call_rating"],
            datetime.now(timezone.utc),
            job_id,
        ),
    )

    conn.commit()
    cur.close()
    conn.close()
