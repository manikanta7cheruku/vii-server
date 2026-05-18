"""
SEVEN-SERVER - database.py
Minimal SQLite database for analytics + update management
"""

import sqlite3
import os
import json
from datetime import datetime

# DB_PATH — uses persistent disk on Render if DB_PATH env var is set
# Render dashboard → your service → Disks → Mount: /data → then set:
# Environment variable: DB_PATH = /data/seven_analytics.db
DB_PATH = os.environ.get("DB_PATH", "seven_analytics.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── Users ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            device_id    TEXT PRIMARY KEY,
            name         TEXT,
            email        TEXT,
            country      TEXT,
            install_date TEXT,
            last_seen    TEXT,
            total_hours  REAL DEFAULT 0,
            license_tier TEXT DEFAULT 'free'
        )
    """)
    try:
        c.execute("ALTER TABLE users ADD COLUMN name TEXT")
    except sqlite3.OperationalError:
        pass

    # ── Referrals ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            referral_code      TEXT UNIQUE,
            referrer_email     TEXT,
            referrer_device_id TEXT,
            referred_email     TEXT,
            referred_device_id TEXT,
            usage_hours        REAL DEFAULT 0,
            is_complete        INTEGER DEFAULT 0,
            reward_sent        INTEGER DEFAULT 0,
            completed_at       TEXT,
            created_at         TEXT
        )
    """)

    # ── Licenses ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            email       TEXT,
            tier        TEXT,
            plan_type   TEXT,
            created_at  TEXT,
            expires_at  TEXT,
            is_active   INTEGER DEFAULT 1
        )
    """)

    # ── Updates (NEW) ──
    # One row per release you publish
    c.execute("""
        CREATE TABLE IF NOT EXISTS updates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            version         TEXT UNIQUE NOT NULL,
            download_url    TEXT NOT NULL,
            size_mb         REAL DEFAULT 0,
            changelog       TEXT DEFAULT '[]',
            target_tier     TEXT DEFAULT 'pro',
            is_critical     INTEGER DEFAULT 0,
            download_mode   TEXT DEFAULT 'manual',
            auto_deliver    INTEGER DEFAULT 1,
            is_active       INTEGER DEFAULT 1,
            published_at    TEXT,
            created_at      TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Initialized")


def get_db():
    return sqlite3.connect(DB_PATH)


# ── Users ──

def register_user(device_id, email=None, name=None, country=None, referral_code=None):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()

    c.execute("""
        INSERT INTO users (device_id, name, email, country, install_date, last_seen)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET
            name      = COALESCE(?, name),
            email     = COALESCE(?, email),
            country   = COALESCE(?, country),
            last_seen = ?
    """, (device_id, name, email, country, now, now,
          name, email, country, now))

    if referral_code and email:
        c.execute("""
            UPDATE referrals
            SET referred_email = ?, referred_device_id = ?
            WHERE referral_code = ? AND referred_email IS NULL
        """, (email, device_id, referral_code))

    conn.commit()
    conn.close()
    return {"success": True}


def update_usage(device_id, hours_delta=None, minutes_delta=None):
    """
    Accept either minutes_delta (new) or hours_delta (legacy).
    Internally always stores as hours for DB compatibility.
    """
    conn = get_db()
    c    = conn.cursor()
    now  = datetime.now().isoformat()

    # Support both old hours and new minutes
    if minutes_delta is not None:
        hours_add = minutes_delta / 60.0
    elif hours_delta is not None:
        hours_add = hours_delta
    else:
        hours_add = 0

    c.execute("""
        UPDATE users
        SET total_hours = total_hours + ?, last_seen = ?
        WHERE device_id = ?
    """, (hours_add, now, device_id))

    c.execute("""
        SELECT id, usage_hours FROM referrals
        WHERE referred_device_id = ? AND is_complete = 0
    """, (device_id,))
    row = c.fetchone()
    referral_completed = False

    if row:
        ref_id, current = row
        new_hours = current + hours_add   # use hours_add not hours_delta
        c.execute("UPDATE referrals SET usage_hours = ? WHERE id = ?",
                  (new_hours, ref_id))
        if new_hours >= 7:
            c.execute("""
                UPDATE referrals SET is_complete = 1, completed_at = ?
                WHERE id = ?
            """, (now, ref_id))
            referral_completed = True

    conn.commit()
    conn.close()
    return {"success": True, "referral_completed": referral_completed}


def create_referral(device_id, email):
    import hashlib
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT referral_code FROM referrals WHERE referrer_device_id = ?", (device_id,))
    existing = c.fetchone()
    if existing:
        conn.close()
        return {"referral_code": existing[0], "is_new": False}

    raw = f"{device_id}{email}{datetime.now()}".encode()
    code = f"REF-{hashlib.md5(raw).hexdigest()[:8].upper()}"

    c.execute("""
        INSERT INTO referrals (referral_code, referrer_email, referrer_device_id, created_at)
        VALUES (?, ?, ?, ?)
    """, (code, email, device_id, datetime.now().isoformat()))

    conn.commit()
    conn.close()
    return {"referral_code": code, "is_new": True}


def _fmt(total_minutes):
    """Format minutes → '1 day 2 hr 30 min' for admin display."""
    m = int(total_minutes or 0)
    d = m // 1440
    m %= 1440
    h = m // 60
    m %= 60
    if d > 0:
        return f"{d}d {h}h {m}m"
    elif h > 0:
        return f"{h}h {m}m"
    else:
        return f"{m}m"


def get_stats():
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("""
        SELECT COUNT(*) FROM users
        WHERE last_seen > datetime('now', '-7 days')
    """)
    active = c.fetchone()[0]
    c.execute("SELECT SUM(total_hours) FROM users")
    hours      = c.fetchone()[0] or 0
    total_mins = hours * 60
    conn.close()
    return {
        "total_users":  total,
        "active_7d":    active,
        "total_hours":  round(hours, 1),
        "total_time":   _fmt(total_mins),   # e.g. "16h 57m"
    }


def get_all_users():
    conn = get_db()
    c    = conn.cursor()
    c.execute("""
        SELECT device_id, name, email, country, total_hours, license_tier, last_seen
        FROM users ORDER BY last_seen DESC
    """)
    users = []
    for row in c.fetchall():
        total_mins = (row[4] or 0) * 60
        users.append({
            "device_id":   (row[0][:12] + "...") if row[0] else None,
            "name":        row[1] or "—",
            "email":       row[2] or "—",
            "country":     row[3] or "—",
            "total_hours": round(row[4] or 0, 1),
            "total_time":  _fmt(total_mins),   # "16h 57m"
            "tier":        row[5] or "free",
            "last_seen":   row[6],
        })
    conn.close()
    return users


def get_all_referrals():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT referral_code, referrer_email, referred_email,
               usage_hours, is_complete, reward_sent, completed_at
        FROM referrals ORDER BY created_at DESC
    """)
    refs = []
    for row in c.fetchall():
        refs.append({
            "code":         row[0],
            "referrer":     row[1],
            "referred":     row[2] or "—",
            "hours":        round(row[3] or 0, 1),
            "complete":     bool(row[4]),
            "reward_sent":  bool(row[5]),
            "completed_at": row[6],
        })
    conn.close()
    return refs


def get_pending_rewards():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT referral_code, referrer_email, referred_email
        FROM referrals WHERE is_complete = 1 AND reward_sent = 0
    """)
    pending = [{"code": r[0], "referrer": r[1], "referred": r[2]} for r in c.fetchall()]
    conn.close()
    return pending


def mark_reward_sent(code):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE referrals SET reward_sent = 1 WHERE referral_code = ?", (code,))
    conn.commit()
    conn.close()


def get_referral_stats(email=None, device_id=None):
    conn = get_db()
    c = conn.cursor()
    if email:
        c.execute("SELECT referral_code FROM referrals WHERE referrer_email = ?", (email,))
    else:
        c.execute("SELECT referral_code FROM referrals WHERE referrer_device_id = ?", (device_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    code = row[0]
    c.execute("""
        SELECT COUNT(*) FROM referrals
        WHERE referrer_email = (SELECT referrer_email FROM referrals WHERE referral_code = ?)
        AND is_complete = 1
    """, (code,))
    completed = c.fetchone()[0]
    c.execute("""
        SELECT COUNT(*) FROM referrals
        WHERE referrer_email = (SELECT referrer_email FROM referrals WHERE referral_code = ?)
        AND is_complete = 0 AND referred_email IS NOT NULL
    """, (code,))
    pending = c.fetchone()[0]
    conn.close()
    return {"referral_code": code, "completed_referrals": completed, "pending_referrals": pending}


# ── Updates ──

def publish_update(version, download_url, size_mb, changelog,
                   target_tier, is_critical, download_mode, auto_deliver):
    """
    Publish a new release. Called from admin dashboard.
    Sets all previous releases to inactive, making this the live one.
    """
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()

    # Deactivate all previous releases
    c.execute("UPDATE updates SET is_active = 0")

    c.execute("""
        INSERT INTO updates
            (version, download_url, size_mb, changelog, target_tier,
             is_critical, download_mode, auto_deliver, is_active, published_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(version) DO UPDATE SET
            download_url  = ?,
            size_mb       = ?,
            changelog     = ?,
            target_tier   = ?,
            is_critical   = ?,
            download_mode = ?,
            auto_deliver  = ?,
            is_active     = 1,
            published_at  = ?
    """, (
        version, download_url, size_mb, changelog, target_tier,
        is_critical, download_mode, auto_deliver, now, now,
        download_url, size_mb, changelog, target_tier,
        is_critical, download_mode, auto_deliver, now
    ))

    conn.commit()
    conn.close()
    return {"success": True, "version": version}


def get_latest_update():
    """Return the currently active release or None."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT version, download_url, size_mb, changelog, target_tier,
               is_critical, download_mode, auto_deliver, published_at
        FROM updates
        WHERE is_active = 1
        ORDER BY published_at DESC LIMIT 1
    """)
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    import json
    return {
        "version":       row[0],
        "download_url":  row[1],
        "size_mb":       row[2],
        "changelog":     json.loads(row[3]) if row[3] else [],
        "target_tier":   row[4],
        "is_critical":   bool(row[5]),
        "download_mode": row[6],
        "auto_deliver":  bool(row[7]),
        "published_at":  row[8],
    }


def get_all_updates():
    """All releases for admin dashboard."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT version, target_tier, is_critical, download_mode,
               auto_deliver, is_active, published_at
        FROM updates ORDER BY published_at DESC
    """)
    updates = []
    for row in c.fetchall():
        updates.append({
            "version":       row[0],
            "target_tier":   row[1],
            "is_critical":   bool(row[2]),
            "download_mode": row[3],
            "auto_deliver":  bool(row[4]),
            "is_active":     bool(row[5]),
            "published_at":  row[6],
        })
    conn.close()
    return updates


def toggle_auto_deliver(version, state):
    """Toggle auto_deliver for a specific release."""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE updates SET auto_deliver = ? WHERE version = ?", (1 if state else 0, version))
    conn.commit()
    conn.close()


init_db()