import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import DB_PATH


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connection():
    # WAL plus a timeout lets Streamlit's UI progress updates coexist with the
    # scoring worker instead of failing immediately when a short write overlaps.
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout = 30000')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialise():
    with connection() as conn:
        conn.execute('PRAGMA journal_mode = WAL')
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
          id INTEGER PRIMARY KEY,
          linkedin_url TEXT UNIQUE,
          full_name TEXT, first_name TEXT, last_name TEXT, email TEXT,
          imported_company TEXT, imported_position TEXT, connected_on TEXT,
          headline TEXT, location TEXT, about TEXT, skills TEXT,
          current_position TEXT, current_company TEXT,
          experience_json TEXT DEFAULT '[]', career_start_year INTEGER,
          total_experience_years REAL, number_of_roles INTEGER DEFAULT 0,
          number_of_companies INTEGER DEFAULT 0, longest_tenure_months INTEGER,
          current_tenure_months INTEGER, seniority_level TEXT,
          profile_status TEXT DEFAULT 'Pending', source TEXT,
          raw_row_json TEXT, last_updated TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
          total INTEGER DEFAULT 0, processed INTEGER DEFAULT 0, succeeded INTEGER DEFAULT 0,
          failed INTEGER DEFAULT 0, current_item TEXT, message TEXT,
          settings_json TEXT, started_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS relevance (
          profile_id INTEGER NOT NULL, run_id INTEGER, research_query TEXT NOT NULL,
          research_area TEXT, matched_keywords TEXT, relevance_score REAL,
          relevant_flag TEXT, confidence TEXT, academic_expert TEXT,
          industry_expert TEXT, security_expert TEXT, architecture_expert TEXT,
          potential_validator TEXT, validation_priority TEXT, created_at TEXT NOT NULL,
          PRIMARY KEY (profile_id, research_query),
          FOREIGN KEY(profile_id) REFERENCES profiles(id)
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, run_id INTEGER, level TEXT NOT NULL, message TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        """)


def log(run_id, level, message):
    with connection() as conn:
        conn.execute("INSERT INTO events(run_id,level,message,created_at) VALUES (?,?,?,?)",
                     (run_id, level, message, utcnow()))


def create_run(kind, total=0, settings=None):
    now = utcnow()
    with connection() as conn:
        cursor = conn.execute("""INSERT INTO runs(kind,status,total,settings_json,started_at,updated_at)
            VALUES (?, 'Running', ?, ?, ?, ?)""", (kind, total, json.dumps(settings or {}), now, now))
        return cursor.lastrowid


def update_run(run_id, **fields):
    fields['updated_at'] = utcnow()
    columns = ', '.join(f'{key}=?' for key in fields)
    with connection() as conn:
        conn.execute(f'UPDATE runs SET {columns} WHERE id=?', (*fields.values(), run_id))


def latest_run():
    with connection() as conn:
        return conn.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()


def active_run():
    with connection() as conn:
        # A stop request is deliberately not an active UI job. The worker sees
        # it and stops at its next checkpoint, but it must not freeze controls.
        return conn.execute("SELECT * FROM runs WHERE status IN ('Running', 'Paused') ORDER BY id DESC LIMIT 1").fetchone()


def replace_dataset():
    """Remove profiles and their derived work, keeping the app schema intact."""
    with connection() as conn:
        conn.execute('DELETE FROM relevance')
        conn.execute('DELETE FROM profiles')
        conn.execute('DELETE FROM events')
        conn.execute('DELETE FROM runs')


def delete_profile(profile_id):
    with connection() as conn:
        conn.execute('DELETE FROM relevance WHERE profile_id=?', (profile_id,))
        conn.execute('DELETE FROM profiles WHERE id=?', (profile_id,))


def delete_research_query(query):
    with connection() as conn:
        conn.execute('DELETE FROM relevance WHERE research_query=?', (query,))
