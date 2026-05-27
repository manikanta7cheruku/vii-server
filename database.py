"""
SEVEN-SERVER - database.py
PostgreSQL database for analytics + update management
Never wipes on Render restart.
"""

import os
import json
import hashlib
import psycopg2
import psycopg2.extras
from datetime import datetime

# ── Database URL from Render environment variable ──
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://seven_db_or97_user:uXh4jBxZNPt3WWhp61syNfF7hymjXqoX@dpg-d85gniuk1jcs73flj5eg-a/seven_db_or97"
)


def get_db():
    """Get PostgreSQL connection."""
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    c    = conn.cursor()

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

    # ── Identity Change History ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_identity_history (
            id         SERIAL PRIMARY KEY,
            device_id  TEXT NOT NULL,
            field      TEXT NOT NULL,
            old_value  TEXT,
            new_value  TEXT,
            changed_at TEXT NOT NULL
        )
    """)

    # ── Referrals ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id                 SERIAL PRIMARY KEY,
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

    # ── Updates ──
    c.execute("""
        CREATE TABLE IF NOT EXISTS updates (
            id            SERIAL PRIMARY KEY,
            version       TEXT UNIQUE NOT NULL,
            download_url  TEXT NOT NULL,
            size_mb       REAL DEFAULT 0,
            changelog     TEXT DEFAULT '[]',
            target_tier   TEXT DEFAULT 'pro',
            is_critical   INTEGER DEFAULT 0,
            download_mode TEXT DEFAULT 'manual',
            auto_deliver  INTEGER DEFAULT 1,
            is_active     INTEGER DEFAULT 1,
            published_at  TEXT,
            created_at    TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] PostgreSQL initialized ✓")


# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────

def _fmt(total_minutes):
    """Format minutes → '1d 2h 30m' for admin display."""
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


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────

def register_user(device_id, email=None, name=None,
                  country=None, referral_code=None):

    # ── Reject anonymous registrations ──
    # Don't create a row unless we have at least a name OR email.
    # This prevents ghost rows from pre-setup pings.
    if not name and not email:
        return {"success": False, "reason": "no_identity"}

    conn = get_db()
    c    = conn.cursor()
    now  = datetime.now().isoformat()

    # ── Get current values before update (for history tracking) ──
    c.execute("""
        SELECT name, email FROM users WHERE device_id = %s
    """, (device_id,))
    existing = c.fetchone()

    # ── Upsert user ──
    c.execute("""
        INSERT INTO users
            (device_id, name, email, country, install_date, last_seen)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (device_id) DO UPDATE SET
            name      = COALESCE(%s, users.name),
            email     = COALESCE(%s, users.email),
            country   = COALESCE(%s, users.country),
            last_seen = %s
    """, (device_id, name, email, country, now, now,
          name, email, country, now))

    # ── Log identity changes if user already existed ──
    if existing:
        old_name, old_email = existing

        # Log name change
        if name and old_name and name.strip() != old_name.strip():
            c.execute("""
                INSERT INTO user_identity_history
                    (device_id, field, old_value, new_value, changed_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (device_id, "name", old_name, name, now))

        # Log email change
        if email and old_email and email.strip() != old_email.strip():
            c.execute("""
                INSERT INTO user_identity_history
                    (device_id, field, old_value, new_value, changed_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (device_id, "email", old_email, email, now))

    if referral_code and email:
        c.execute("""
            UPDATE referrals
            SET referred_email     = %s,
                referred_device_id = %s
            WHERE referral_code = %s
              AND referred_email IS NULL
        """, (email, device_id, referral_code))

    conn.commit()
    conn.close()
    return {"success": True}


def get_identity_history(device_id):
    """Get name/email change history for a device."""
    conn = get_db()
    c    = conn.cursor()
    c.execute("""
        SELECT field, old_value, new_value, changed_at
        FROM user_identity_history
        WHERE device_id = %s
        ORDER BY changed_at DESC
    """, (device_id,))
    rows = c.fetchall()
    conn.close()
    return [
        {
            "field":      row[0],
            "old_value":  row[1],
            "new_value":  row[2],
            "changed_at": row[3],
        }
        for row in rows
    ]


def update_usage(device_id, hours_delta=None, minutes_delta=None,
                 total_minutes=None):
    """
    Accept:
      minutes_delta  — add this many minutes (regular ping)
      hours_delta    — add this many hours (legacy)
      total_minutes  — set absolute total (sync correction on startup)
    """
    conn = get_db()
    c    = conn.cursor()
    now  = datetime.now().isoformat()

    if total_minutes is not None:
        # Absolute sync — only update if local total is GREATER than server
        # GREATEST() ensures server never goes backwards
        hours_total = total_minutes / 60.0
        c.execute("""
            UPDATE users
            SET total_hours = GREATEST(total_hours, %s),
                last_seen   = %s
            WHERE device_id = %s
        """, (hours_total, now, device_id))
        print(f"[DB] Absolute sync: {round(hours_total, 2)}h for {device_id[:8]}")
    else:
        if minutes_delta is not None:
            hours_add = minutes_delta / 60.0
        elif hours_delta is not None:
            hours_add = hours_delta
        else:
            hours_add = 0

        if hours_add > 0:
            c.execute("""
                UPDATE users
                SET total_hours = total_hours + %s,
                    last_seen   = %s
                WHERE device_id = %s
            """, (hours_add, now, device_id))

    # ── Referral progress tracking ──
    c.execute("""
        SELECT id, usage_hours FROM referrals
        WHERE referred_device_id = %s AND is_complete = 0
    """, (device_id,))
    row = c.fetchone()
    referral_completed = False

    if row:
        ref_id, current = row
        new_hours = (current or 0) + hours_add
        c.execute(
            "UPDATE referrals SET usage_hours = %s WHERE id = %s",
            (new_hours, ref_id)
        )
        if new_hours >= 7:
            c.execute("""
                UPDATE referrals
                SET is_complete  = 1,
                    completed_at = %s
                WHERE id = %s
            """, (now, ref_id))
            referral_completed = True

    conn.commit()
    conn.close()
    return {"success": True, "referral_completed": referral_completed}


def get_stats():
    conn = get_db()
    c    = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]

    from datetime import timedelta
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute("""
        SELECT COUNT(*) FROM users WHERE last_seen > %s
    """, (seven_days_ago,))
    active = c.fetchone()[0]

    c.execute("SELECT SUM(total_hours) FROM users")
    hours      = c.fetchone()[0] or 0
    total_mins = hours * 60

    conn.close()
    return {
        "total_users": total,
        "active_7d":   active,
        "total_hours": round(hours, 1),
        "total_time":  _fmt(total_mins),
    }


def get_all_users():
    conn = get_db()
    c    = conn.cursor()
    c.execute("""
        SELECT u.device_id, u.name, u.email, u.country,
               u.total_hours, u.license_tier, u.last_seen,
               COUNT(h.id) as change_count
        FROM users u
        LEFT JOIN user_identity_history h ON h.device_id = u.device_id
        GROUP BY u.device_id, u.name, u.email, u.country,
                 u.total_hours, u.license_tier, u.last_seen
        ORDER BY u.last_seen DESC
    """)
    users = []
    for row in c.fetchall():
        total_mins = (row[4] or 0) * 60
        users.append({
            "device_id":    row[0],
            "device_short": (row[0][:12] + "...") if row[0] else None,
            "name":         row[1] or "—",
            "email":        row[2] or "—",
            "country":      row[3] or "—",
            "total_hours":  round(row[4] or 0, 1),
            "total_time":   _fmt(total_mins),
            "tier":         row[5] or "free",
            "last_seen":    row[6],
            "change_count": int(row[7] or 0),
        })
    conn.close()
    return users


# ─────────────────────────────────────────────
# REFERRALS
# ─────────────────────────────────────────────

def create_referral(device_id, email):
    conn = get_db()
    c    = conn.cursor()

    c.execute("""
        SELECT referral_code FROM referrals
        WHERE referrer_device_id = %s
    """, (device_id,))
    existing = c.fetchone()
    if existing:
        conn.close()
        return {"referral_code": existing[0], "is_new": False}

    raw  = f"{device_id}{email}{datetime.now()}".encode()
    code = f"REF-{hashlib.md5(raw).hexdigest()[:8].upper()}"

    c.execute("""
        INSERT INTO referrals
            (referral_code, referrer_email, referrer_device_id, created_at)
        VALUES (%s, %s, %s, %s)
    """, (code, email, device_id, datetime.now().isoformat()))

    conn.commit()
    conn.close()
    return {"referral_code": code, "is_new": True}


def get_all_referrals():
    conn = get_db()
    c    = conn.cursor()
    c.execute("""
        SELECT referral_code, referrer_email, referred_email,
               usage_hours, is_complete, reward_sent, completed_at
        FROM referrals ORDER BY created_at DESC
    """)
    refs = []
    for row in c.fetchall():
        refs.append({
            "code":        row[0],
            "referrer":    row[1],
            "referred":    row[2] or "—",
            "hours":       round(row[3] or 0, 1),
            "complete":    bool(row[4]),
            "reward_sent": bool(row[5]),
            "completed_at": row[6],
        })
    conn.close()
    return refs


def get_pending_rewards():
    conn = get_db()
    c    = conn.cursor()
    c.execute("""
        SELECT referral_code, referrer_email, referred_email
        FROM referrals
        WHERE is_complete = 1 AND reward_sent = 0
    """)
    pending = [
        {"code": r[0], "referrer": r[1], "referred": r[2]}
        for r in c.fetchall()
    ]
    conn.close()
    return pending


def mark_reward_sent(code):
    conn = get_db()
    c    = conn.cursor()
    c.execute(
        "UPDATE referrals SET reward_sent = 1 WHERE referral_code = %s",
        (code,)
    )
    conn.commit()
    conn.close()


def get_referral_stats(email=None, device_id=None):
    conn = get_db()
    c    = conn.cursor()

    if email:
        c.execute("""
            SELECT referral_code FROM referrals
            WHERE referrer_email = %s
        """, (email,))
    else:
        c.execute("""
            SELECT referral_code FROM referrals
            WHERE referrer_device_id = %s
        """, (device_id,))

    row = c.fetchone()
    if not row:
        conn.close()
        return None

    code = row[0]

    c.execute("""
        SELECT COUNT(*) FROM referrals
        WHERE referrer_email = (
            SELECT referrer_email FROM referrals WHERE referral_code = %s
        ) AND is_complete = 1
    """, (code,))
    completed = c.fetchone()[0]

    c.execute("""
        SELECT COUNT(*) FROM referrals
        WHERE referrer_email = (
            SELECT referrer_email FROM referrals WHERE referral_code = %s
        ) AND is_complete = 0 AND referred_email IS NOT NULL
    """, (code,))
    pending = c.fetchone()[0]

    conn.close()
    return {
        "referral_code":       code,
        "completed_referrals": completed,
        "pending_referrals":   pending,
    }


# ─────────────────────────────────────────────
# UPDATES
# ─────────────────────────────────────────────

def publish_update(version, download_url, size_mb, changelog,
                   target_tier, is_critical, download_mode, auto_deliver):
    conn = get_db()
    c    = conn.cursor()
    now  = datetime.now().isoformat()

    c.execute("UPDATE updates SET is_active = 0")

    c.execute("""
        INSERT INTO updates
            (version, download_url, size_mb, changelog, target_tier,
             is_critical, download_mode, auto_deliver, is_active,
             published_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
        ON CONFLICT (version) DO UPDATE SET
            download_url  = %s,
            size_mb       = %s,
            changelog     = %s,
            target_tier   = %s,
            is_critical   = %s,
            download_mode = %s,
            auto_deliver  = %s,
            is_active     = 1,
            published_at  = %s
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
    conn = get_db()
    c    = conn.cursor()
    c.execute("""
        SELECT version, download_url, size_mb, changelog,
               target_tier, is_critical, download_mode,
               auto_deliver, published_at
        FROM updates
        WHERE is_active = 1
        ORDER BY published_at DESC LIMIT 1
    """)
    row = c.fetchone()
    conn.close()
    if not row:
        return None
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
    conn = get_db()
    c    = conn.cursor()
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
    conn = get_db()
    c    = conn.cursor()
    c.execute(
        "UPDATE updates SET auto_deliver = %s WHERE version = %s",
        (1 if state else 0, version)
    )
    conn.commit()
    conn.close()


init_db()