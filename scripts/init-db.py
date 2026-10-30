#!/usr/bin/env python3
"""Initialize the Six Eyes SQLite database schema."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "metadata" / "sixeyes.db"


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)

    if DB_PATH.exists():
        print(f"Database already exists at {DB_PATH} — recreating.")
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE items (
            id               TEXT PRIMARY KEY,
            title            TEXT,
            module           TEXT,
            cross_modules    TEXT,          -- JSON array as string
            status           TEXT,
            business_impact  INTEGER,
            time_sensitivity INTEGER,
            data_readiness   INTEGER,
            priority_score   REAL,
            created          TEXT,          -- ISO date
            last_touched     TEXT,          -- ISO date
            last_progress    TEXT,          -- ISO date
            mention_count    INTEGER,
            progress_count   INTEGER,
            stale_weeks      INTEGER,
            blocked_reason   TEXT,
            escalation_level INTEGER,
            agent_next_step  TEXT,         -- one-line read-only step (null = no step)
            agent_step_type  TEXT,         -- investigate | check | null
            agent_step_check TEXT,         -- human checkpoint text (null = none)
            agent_step_as_of TEXT          -- ISO date last assessed (null = unassessed)
        );

        CREATE TABLE pulse_mentions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id      TEXT REFERENCES items(id),
            pulse_date   TEXT,             -- ISO date
            had_progress INTEGER,          -- 0 or 1
            context      TEXT,
            source_file  TEXT
        );

        CREATE TABLE score_history (
            item_id          TEXT,
            snapshot_date    TEXT,             -- ISO date
            priority_score   REAL,
            business_impact  INTEGER,
            time_sensitivity INTEGER,
            data_readiness   INTEGER,
            stale_weeks      INTEGER,
            escalation_level INTEGER,
            status           TEXT,
            PRIMARY KEY (item_id, snapshot_date)
        );

        CREATE TABLE cross_module_links (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            item_a_id  TEXT,
            item_b_id  TEXT,
            link_type  TEXT,
            confidence REAL,
            hypothesis TEXT
        );

        CREATE VIRTUAL TABLE items_fts
            USING fts5(id, title, blocked_reason);
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")
    print("Tables created: items, pulse_mentions, score_history, cross_module_links, items_fts")


if __name__ == "__main__":
    init_db()
