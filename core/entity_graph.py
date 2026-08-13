"""
Persistent entity graph for Bakasura.
SQLite-backed store of entities (person/email/phone/username/domain/ip/url) and the
edges between them, so pivots discovered in one hunt are remembered and can be
cross-linked the next time the same email/phone/username shows up in a different hunt.
No external dependencies - stdlib sqlite3 only.
"""
import sqlite3
import datetime
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DB_PATH = Path(__file__).parent.parent / "memories" / "entity_graph.db"


def _connect() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            value TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            UNIQUE(type, value)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            src_id INTEGER NOT NULL,
            dst_id INTEGER NOT NULL,
            relation TEXT,
            source_url TEXT,
            confidence REAL,
            investigation TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(src_id) REFERENCES entities(id),
            FOREIGN KEY(dst_id) REFERENCES entities(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_value ON entities(value)")
    conn.commit()
    return conn


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _normalize(type_: str, value: str) -> str:
    value = (value or "").strip()
    if type_ in ("email", "domain", "username", "url"):
        value = value.lower()
    return value


def get_or_create_entity(conn: sqlite3.Connection, type_: str, value: str) -> int:
    value = _normalize(type_, value)
    now = _now()
    cur = conn.execute("SELECT id FROM entities WHERE type=? AND value=?", (type_, value))
    row = cur.fetchone()
    if row:
        conn.execute("UPDATE entities SET last_seen=? WHERE id=?", (now, row[0]))
        conn.commit()
        return row[0]
    cur = conn.execute(
        "INSERT INTO entities (type, value, first_seen, last_seen) VALUES (?, ?, ?, ?)",
        (type_, value, now, now),
    )
    conn.commit()
    return cur.lastrowid


def add_edge(conn: sqlite3.Connection, src_id: int, dst_id: int, relation: str,
             source_url: Optional[str] = None, confidence: Optional[float] = None,
             investigation: Optional[str] = None) -> None:
    conn.execute(
        "INSERT INTO edges (src_id, dst_id, relation, source_url, confidence, investigation, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (src_id, dst_id, relation, source_url, confidence, investigation, _now()),
    )
    conn.commit()


def find_prior_hits(type_: str, value: str, exclude_investigation: Optional[str] = None) -> List[Dict]:
    """
    Look up whether this pivot (email/phone/username/...) was already linked to a
    person entity in a PREVIOUS investigation. Returns a list of
    {"person": name, "investigation": ..., "relation": ..., "seen": timestamp}.
    """
    value = _normalize(type_, value)
    try:
        conn = _connect()
        cur = conn.execute(
            """
            SELECT p.value, e.investigation, e.relation, e.created_at
            FROM entities pivot
            JOIN edges e ON (e.src_id = pivot.id OR e.dst_id = pivot.id)
            JOIN entities p ON (p.id = e.src_id OR p.id = e.dst_id) AND p.type = 'person'
            WHERE pivot.type = ? AND pivot.value = ?
            ORDER BY e.created_at DESC
            """,
            (type_, value),
        )
        results = []
        for name, investigation, relation, created_at in cur.fetchall():
            if exclude_investigation and investigation == exclude_investigation:
                continue
            results.append({
                "person": name,
                "investigation": investigation,
                "relation": relation,
                "seen": created_at,
            })
        conn.close()
        return results
    except Exception as e:
        print(f"[ENTITY GRAPH] find_prior_hits failed: {e}")
        return []


def record_hunt(profile: Dict, pivots: Dict[str, List[str]]) -> List[Dict]:
    """
    Persists the target + all confirmed pivots (emails/phones/usernames/domains/ips)
    found during a hunt, linked as edges off the person entity.
    Returns any cross-investigation hits found for those pivots BEFORE recording
    this hunt's own edges, so callers can surface "this email also showed up
    investigating <other person>" during analysis.
    """
    name = profile.get("name")
    if not name:
        return []

    investigation = f"{name}::{_now()}"
    cross_hits: List[Dict] = []

    try:
        conn = _connect()
        person_id = get_or_create_entity(conn, "person", name)

        seed = {
            "nickname": profile.get("nickname"),
            "phone": profile.get("phone"),
        }
        for type_, val in seed.items():
            if not val:
                continue
            entity_type = "username" if type_ == "nickname" else type_
            cross_hits.extend(find_prior_hits(entity_type, val, exclude_investigation=investigation))
            pid = get_or_create_entity(conn, entity_type, val)
            add_edge(conn, person_id, pid, relation="self_reported", investigation=investigation)

        for type_, values in (pivots or {}).items():
            for val in values:
                if not val:
                    continue
                cross_hits.extend(find_prior_hits(type_, val, exclude_investigation=investigation))
                pid = get_or_create_entity(conn, type_, val)
                add_edge(conn, person_id, pid, relation="discovered", investigation=investigation)

        conn.close()
    except Exception as e:
        print(f"[ENTITY GRAPH] record_hunt failed: {e}")

    return cross_hits
