import json
import sqlite3

from app.models import StaffUser

# Mocked support users for demonstrating account-scoped authorization —
# not a real ParcelPilot org chart. Derived from the `csm` column in `accounts` (Task 1 data).
_STAFF = [
    ("priya_mehta", "Priya Mehta", "agent", json.dumps(["ACCT-001", "ACCT-004"])),
    ("arjun_rao", "Arjun Rao", "agent", json.dumps(["ACCT-002"])),
    ("neha_kapoor", "Neha Kapoor", "agent", json.dumps(["ACCT-003"])),
    # NOTE: `"*"` in assigned_account_ids is a display-only placeholder; authorize() never
    # interprets it directly. Authorization for manager role is handled entirely by the
    # role == "manager" check in authorize(). Anyone reading assigned_account_ids elsewhere
    # should not check `"*" in list` or iterate expecting real account IDs.
    ("manager", "Manager", "manager", json.dumps(["*"])),
]


def load(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO staff_users (user_id, name, role, assigned_account_ids) VALUES (?, ?, ?, ?)",
        _STAFF,
    )
    conn.commit()


def get_user(conn: sqlite3.Connection, user_id: str) -> StaffUser:
    row = conn.execute("SELECT * FROM staff_users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown user_id: {user_id}")
    return StaffUser(row["user_id"], row["name"], row["role"], json.loads(row["assigned_account_ids"]))


def authorize(user: StaffUser, account_id: str) -> bool:
    return user.role == "manager" or account_id in user.assigned_account_ids
