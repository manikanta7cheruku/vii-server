"""
SEVEN-SERVER - database.py
Minimal SQLite database for analytics
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = "seven_analytics.db"


def init_db():
    """Initialize database tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            device_id TEXT PRIMARY KEY,
            email TEXT,
            country TEXT,
            install_date TEXT,
            last_seen TEXT,
            total_hours REAL DEFAULT 0,
            license_tier TEXT DEFAULT 'free'
        )
    """)
    
    # Referrals table
    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referral_code TEXT UNIQUE,
            referrer_email TEXT,
            referrer_device_id TEXT,
            referred_email TEXT,
            referred_device_id TEXT,
            usage_hours REAL DEFAULT 0,
            is_complete INTEGER DEFAULT 0,
            reward_sent INTEGER DEFAULT 0,
            completed_at TEXT,
            created_at TEXT
        )
    """)
    
    # Licenses table
    c.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            email TEXT,
            tier TEXT,
            plan_type TEXT,
            created_at TEXT,
            expires_at TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    
    conn.commit()
    conn.close()
    print("[DB] Initialized")


def get_db():
    return sqlite3.connect(DB_PATH)


def register_user(device_id: str, email: str = None, country: str = None, referral_code: str = None):
    """Register or update user."""
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    
    c.execute("""
        INSERT INTO users (device_id, email, country, install_date, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET
            email = COALESCE(?, email),
            country = COALESCE(?, country),
            last_seen = ?
    """, (device_id, email, country, now, now, email, country, now))
    
    # Link referral if provided
    if referral_code and email:
        c.execute("""
            UPDATE referrals 
            SET referred_email = ?, referred_device_id = ?
            WHERE referral_code = ? AND referred_email IS NULL
        """, (email, device_id, referral_code))
    
    conn.commit()
    conn.close()
    return {"success": True}


def update_usage(device_id: str, hours_delta: float):
    """Update usage hours and check referral completion."""
    conn = get_db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    
    # Update user hours
    c.execute("""
        UPDATE users 
        SET total_hours = total_hours + ?, last_seen = ?
        WHERE device_id = ?
    """, (hours_delta, now, device_id))
    
    # Check referral progress
    c.execute("""
        SELECT id, usage_hours FROM referrals 
        WHERE referred_device_id = ? AND is_complete = 0
    """, (device_id,))
    
    row = c.fetchone()
    referral_completed = False
    
    if row:
        ref_id, current_hours = row
        new_hours = current_hours + hours_delta
        
        c.execute("UPDATE referrals SET usage_hours = ? WHERE id = ?", (new_hours, ref_id))
        
        if new_hours >= 7:
            c.execute("""
                UPDATE referrals SET is_complete = 1, completed_at = ? WHERE id = ?
            """, (now, ref_id))
            referral_completed = True
    
    conn.commit()
    conn.close()
    
    return {"success": True, "referral_completed": referral_completed}


def create_referral(device_id: str, email: str):
    """Create referral code."""
    import hashlib
    
    conn = get_db()
    c = conn.cursor()
    
    # Check existing
    c.execute("SELECT referral_code FROM referrals WHERE referrer_device_id = ?", (device_id,))
    existing = c.fetchone()
    if existing:
        conn.close()
        return {"referral_code": existing[0], "is_new": False}
    
    # Create new
    code_hash = hashlib.md5(f"{device_id}{email}{datetime.now()}".encode()).hexdigest()[:8].upper()
    referral_code = f"REF-{code_hash}"
    
    c.execute("""
        INSERT INTO referrals (referral_code, referrer_email, referrer_device_id, created_at)
        VALUES (?, ?, ?, ?)
    """, (referral_code, email, device_id, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    return {"referral_code": referral_code, "is_new": True}


def get_stats():
    """Get overview stats."""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE last_seen > datetime('now', '-7 days')")
    active = c.fetchone()[0]
    
    c.execute("SELECT SUM(total_hours) FROM users")
    hours = c.fetchone()[0] or 0
    
    conn.close()
    
    return {"total_users": total, "active_7d": active, "total_hours": round(hours, 1)}


def get_all_users():
    """Get all users."""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT device_id, email, country, total_hours, license_tier, last_seen
        FROM users ORDER BY last_seen DESC
    """)
    
    users = []
    for row in c.fetchall():
        users.append({
            "device_id": row[0][:12] + "..." if row[0] else None,
            "email": row[1] or "—",
            "country": row[2] or "Unknown",
            "total_hours": round(row[3] or 0, 1),
            "tier": row[4] or "free",
            "last_seen": row[5]
        })
    
    conn.close()
    return users


def get_all_referrals():
    """Get all referrals."""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT referral_code, referrer_email, referred_email, usage_hours, 
               is_complete, reward_sent, completed_at
        FROM referrals ORDER BY created_at DESC
    """)
    
    refs = []
    for row in c.fetchall():
        refs.append({
            "code": row[0],
            "referrer": row[1],
            "referred": row[2] or "—",
            "hours": round(row[3] or 0, 1),
            "complete": bool(row[4]),
            "reward_sent": bool(row[5]),
            "completed_at": row[6]
        })
    
    conn.close()
    return refs


def get_pending_rewards():
    """Get completed referrals awaiting rewards."""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT referral_code, referrer_email, referred_email
        FROM referrals WHERE is_complete = 1 AND reward_sent = 0
    """)
    
    pending = [{"code": r[0], "referrer": r[1], "referred": r[2]} for r in c.fetchall()]
    conn.close()
    return pending


def mark_reward_sent(code: str):
    """Mark reward as sent."""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE referrals SET reward_sent = 1 WHERE referral_code = ?", (code,))
    conn.commit()
    conn.close()


def get_referral_stats(email: str = None, device_id: str = None):
    """Get user's referral stats."""
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
    
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_email = (SELECT referrer_email FROM referrals WHERE referral_code = ?) AND is_complete = 1", (code,))
    completed = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_email = (SELECT referrer_email FROM referrals WHERE referral_code = ?) AND is_complete = 0 AND referred_email IS NOT NULL", (code,))
    pending = c.fetchone()[0]
    
    conn.close()
    return {"referral_code": code, "completed_referrals": completed, "pending_referrals": pending}


# Initialize on import
init_db()