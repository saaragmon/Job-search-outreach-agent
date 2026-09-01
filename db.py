import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "outreach.db"

STATUSES = [
    "drafted",
    "sent",
    "replied",
    "interview",
    "rejected",
    "hold",
]


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            position TEXT NOT NULL,
            jd_text TEXT NOT NULL,
            company_notes TEXT,
            contact_name TEXT,
            contact_email TEXT,
            research TEXT,
            match_notes TEXT,
            draft TEXT,
            review TEXT,
            final_message TEXT,
            status TEXT NOT NULL DEFAULT 'drafted',
            next_action TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (role_id) REFERENCES roles(id)
        )
        """
    )
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(roles)").fetchall()}
    extras = {
        "language": "TEXT",
        "linkedin_message": "TEXT",
        "fit": "TEXT",
    }
    for name, typ in extras.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE roles ADD COLUMN {name} {typ}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def insert_role(**fields) -> int:
    conn = connect()
    cols = [
        "company",
        "position",
        "jd_text",
        "company_notes",
        "contact_name",
        "contact_email",
        "research",
        "match_notes",
        "draft",
        "review",
        "final_message",
        "status",
        "next_action",
        "language",
        "linkedin_message",
        "fit",
        "created_at",
    ]
    values = {c: fields.get(c) for c in cols}
    values["created_at"] = now()
    values["status"] = values.get("status") or "drafted"
    q = f"INSERT INTO roles ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"
    cur = conn.execute(q, values)
    conn.commit()
    role_id = cur.lastrowid
    conn.close()
    return int(role_id)


def update_role(role_id: int, **fields) -> None:
    if not fields:
        return
    conn = connect()
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    payload = dict(fields)
    payload["id"] = role_id
    conn.execute(f"UPDATE roles SET {sets} WHERE id = :id", payload)
    conn.commit()
    conn.close()


def add_message(role_id: int, direction: str, body: str) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO messages (role_id, direction, body, created_at) VALUES (?, ?, ?, ?)",
        (role_id, direction, body, now()),
    )
    conn.commit()
    conn.close()


def find_duplicate(company: str, position: str) -> dict | None:
    conn = connect()
    row = conn.execute(
        """
        SELECT * FROM roles
        WHERE lower(company) = lower(?) AND lower(position) = lower(?)
        ORDER BY id DESC LIMIT 1
        """,
        (company.strip(), position.strip()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def export_csv_path() -> Path:
    import csv

    path = Path(__file__).resolve().parent / "outreach_export.csv"
    conn = connect()
    rows = conn.execute(
        """
        SELECT id, company, position, contact_email, language, fit, status,
               next_action, created_at
        FROM roles ORDER BY id DESC
        """
    ).fetchall()
    conn.close()
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "id",
                "company",
                "position",
                "contact_email",
                "language",
                "fit",
                "status",
                "next_action",
                "created_at",
            ]
        )
        w.writerows(rows)
    return path


def get_role(role_id: int) -> dict | None:
    conn = connect()
    row = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_roles() -> list[dict]:
    conn = connect()
    rows = conn.execute(
        "SELECT id, company, position, contact_email, fit, status, next_action, created_at FROM roles ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def tracker_rows() -> list[list]:
    rows = list_roles()
    return [
        [
            r["id"],
            r["company"],
            r["position"],
            r["contact_email"] or "",
            r.get("fit") or "",
            r["status"],
            r["next_action"] or "",
            r["created_at"],
        ]
        for r in rows
    ]
