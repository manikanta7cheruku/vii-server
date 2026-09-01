"""
SEVEN-SERVER - main.py
Production-Grade Analytics, Update Distribution, and License Management Server
"""

import os
import hmac
import hashlib
import smtplib
import secrets
import json
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Seven Enterprise Server",
    version="1.3.3",
    description="Production telemetry, licensing, and administration gateway for Seven AI"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Security Configuration ──
ADMIN_TOKEN = os.environ.get("SEVEN_ADMIN_TOKEN", "seven_fallback_secure_token_2025")
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

import database as db

# ── Request Models ──

class RegisterRequest(BaseModel):
    device_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    referral_code: Optional[str] = None


class LicenseSyncRequest(BaseModel):
    device_id: str
    license_key: str
    license_tier: str


class UsagePingRequest(BaseModel):
    device_id: str
    hours_delta: Optional[float] = None
    minutes_delta: Optional[float] = None
    total_minutes: Optional[float] = None
    email: Optional[str] = None


class ReferralRequest(BaseModel):
    device_id: str
    email: str


class LicenseCreateRequest(BaseModel):
    email: str
    tier: str = "pro"
    plan_type: str = "monthly"
    custom_key: Optional[str] = None


class LicenseValidateRequest(BaseModel):
    license_key: str
    device_id: Optional[str] = None


class PublishUpdateRequest(BaseModel):
    version: str
    download_url: str
    size_mb: float = 0
    changelog: List[str] = []
    target_tier: str = "pro"
    is_critical: bool = False
    download_mode: str = "manual"
    auto_deliver: bool = True


class ToggleDeliverRequest(BaseModel):
    version: str
    auto_deliver: bool


class CreateOrderRequest(BaseModel):
    plan_id: str
    email: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_id: str
    email: str


# ── Dependency Injection for Admin Security ──
def verify_admin_auth(x_admin_token: Optional[str] = Header(None)):
    """Enforce strict token authentication on all administrative endpoints."""
    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Authentication failed. Invalid or missing administrator token."
        )
    return x_admin_token


# =============================================================================
# PUBLIC CLIENT API (Called by Seven Desktop App)
# =============================================================================

@app.get("/")
def root_redirect():
    """Root endpoint — redirects to admin dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin")


@app.get("/ping")
def ping_liveness():
    """Lightweight health check for Render keepalive."""
    return {"ok": True, "timestamp": datetime.now().isoformat()}


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.post("/api/register")
def register_client(req: RegisterRequest):
    """Registers user identity and hardware profiles on installation."""
    return db.register_user(
        device_id=req.device_id,
        name=req.name,
        email=req.email,
        country=req.country,
        referral_code=req.referral_code,
    )


@app.post("/api/license/sync-tier")
def sync_license_tier(req: LicenseSyncRequest):
    """Syncs activated license tier with telemetry records."""
    valid_tiers = ["free", "pro", "ultimate"]
    if req.license_tier not in valid_tiers:
        raise HTTPException(status_code=400, detail="Invalid licensing tier.")
    return db.sync_license_tier(req.device_id, req.license_key, req.license_tier)


@app.post("/api/usage/ping")
def log_usage_ping(req: UsagePingRequest):
    """Pushed by the background daemons to track usage statistics."""
    if req.email:
        db.register_user(req.device_id, email=req.email)
    return db.update_usage(
        req.device_id,
        hours_delta=req.hours_delta,
        minutes_delta=req.minutes_delta,
        total_minutes=req.total_minutes
    )


@app.post("/api/referral/create")
def register_referral(req: ReferralRequest):
    """Generates a tracking referral code for the user."""
    if not req.email or "@" not in req.email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    result = db.create_referral(req.device_id, req.email)
    result["referral_link"] = f"https://seven.app/ref/{result['referral_code']}"
    return result


@app.get("/api/referral/stats")
def get_referral_stats(email: Optional[str] = None, device_id: Optional[str] = None):
    """Retrieve referral metrics."""
    stats = db.get_referral_stats(email, device_id)
    return stats or {
        "referral_code": None,
        "completed_referrals": 0,
        "pending_referrals": 0,
    }


@app.post("/api/license/validate")
def validate_license_key(req: LicenseValidateRequest):
    """Validates license keys and registers client hardware IDs."""
    key = req.license_key.upper().strip()
    result = db.validate_license(key)

    if not result:
        raise HTTPException(status_code=404, detail="License key not found.")

    if not result.get("valid"):
        raise HTTPException(status_code=400, detail=result.get("reason", "License key is invalid."))

    if req.device_id and result.get("valid"):
        db.activate_license_on_device(key, req.device_id)

    return result


@app.get("/api/updates/latest")
def get_latest_release(tier: str = "free", current_version: str = "0.0.0"):
    """Returns latest update metadata if eligible for the target tier."""
    update = db.get_latest_update()

    if not update or not update.get("auto_deliver"):
        return {"update_available": False}

    target = update.get("target_tier", "all")
    eligible = False
    if target == "all":
        eligible = True
    elif target == "pro" and tier in ["pro", "ultimate"]:
        eligible = True
    elif target == "ultimate" and tier == "ultimate":
        eligible = True

    if not eligible:
        return {"update_available": False, "reason": "tier_locked"}

    def parse_semver(v):
        try:
            clean = v.strip().lstrip("vV").split("-")[0]
            return [int(x) for x in clean.split(".")]
        except Exception:
            return [0, 0, 0]

    if parse_semver(update["version"]) <= parse_semver(current_version):
        return {"update_available": False}

    return {
        "update_available": True,
        **update,
    }


# =============================================================================
# TRANSACTION PROCESSING (Razorpay Payments)
# =============================================================================

PLAN_PRICES = {
    "pro_monthly": 9900, "pro_yearly": 69900, "pro_lifetime": 129900,
    "ultimate_monthly": 19900, "ultimate_yearly": 99900, "ultimate_lifetime": 199900,
}

PLAN_NAMES = {
    "pro_monthly": ("pro", "monthly"),
    "pro_yearly": ("pro", "yearly"),
    "pro_lifetime": ("pro", "lifetime"),
    "ultimate_monthly": ("ultimate", "monthly"),
    "ultimate_yearly": ("ultimate", "yearly"),
    "ultimate_lifetime": ("ultimate", "lifetime"),
}


def _generate_license_on_purchase(tier: str, plan_type: str) -> str:
    key = f"VII-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
    db.publish_license_to_db(key, tier, plan_type)
    return key


def _send_purchase_email(email: str, key: str, tier: str, plan_type: str):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Your Seven {tier.upper()} License Key"
        msg["From"] = GMAIL_USER
        msg["To"] = email

        expiry = "Never expires — Lifetime access" if plan_type == "lifetime" else f"Valid for 1 {plan_type.replace('ly', '')}"
        body = f"Hi there!\n\nThank you for purchasing Seven {tier.upper()}!\n\nYour license key:\n\n{key}\n\nValid: {expiry}\n\nTo activate:\n1. Open Seven\n2. Go to Plans page\n3. Paste the key and click Activate.\n\n— Seven Team"
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, email, msg.as_string())
    except Exception as e:
        print(f"[PAYMENT ERROR] Email failed: {e}")


@app.post("/api/payment/create-order")
def create_payment_order(req: CreateOrderRequest):
    if req.plan_id not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail="Invalid plan identifier.")
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=500, detail="Payment gateways not configured.")

    try:
        import razorpay
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        amount = PLAN_PRICES[req.plan_id]
        order = client.order.create({
            "amount": amount,
            "currency": "INR",
            "notes": {"email": req.email, "plan_id": req.plan_id}
        })
        return {
            "order_id": order["id"],
            "amount": amount,
            "currency": "INR",
            "key_id": RAZORPAY_KEY_ID,
            "plan_id": req.plan_id,
            "email": req.email,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/payment/verify")
def verify_payment_signature(req: VerifyPaymentRequest):
    if not RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=500, detail="Payment gateways not configured.")

    body = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if expected != req.razorpay_signature:
        raise HTTPException(status_code=400, detail="Payment verification signature mismatch.")

    tier, plan_type = PLAN_NAMES.get(req.plan_id, ("pro", "monthly"))
    key = _generate_license_on_purchase(tier, plan_type)
    _send_purchase_email(req.email, key, tier, plan_type)

    db.save_transaction(
        order_id=req.razorpay_order_id,
        payment_id=req.razorpay_payment_id,
        email=req.email,
        plan_id=req.plan_id,
        tier=tier,
        plan_type=plan_type,
        amount_paise=PLAN_PRICES.get(req.plan_id, 0),
        license_key=key
    )

    return {
        "success": True,
        "license_key": key,
        "tier": tier,
        "plan_type": plan_type,
        "message": f"License key successfully processed and dispatched to {req.email}"
    }


# =============================================================================
# ADMIN OPERATIONS (Authorized via X-Admin-Token header)
# =============================================================================

@app.post("/admin/license/create")
def admin_generate_license(req: LicenseCreateRequest, token: str = Depends(verify_admin_auth)):
    """Generates license keys and persists them to the PostgreSQL cluster."""
    # Build standard license key format
    if req.custom_key:
        clean_custom = req.custom_key.upper().replace(" ", "-")
        built_key = f"VII-{clean_custom}"
    else:
        built_key = f"VII-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"

    # Calculate Expiration Date
    expires_at = None
    if req.plan_type == "monthly":
        expires_at = (datetime.now() + timedelta(days=30)).isoformat()
    elif req.plan_type == "yearly":
        expires_at = (datetime.now() + timedelta(days=365)).isoformat()

    db.create_license(
        license_key=built_key,
        email=req.email,
        tier=req.tier,
        plan_type=req.plan_type,
        expires_at=expires_at
    )
    return {"success": True, "license_key": built_key, "expires_at": expires_at}


@app.get("/admin/licenses")
def admin_fetch_licenses(token: str = Depends(verify_admin_auth)):
    return db.get_all_licenses()


@app.delete("/admin/licenses/{license_key}")
def admin_revoke_license(license_key: str, token: str = Depends(verify_admin_auth)):
    db.revoke_license(license_key.upper().strip())
    return {"success": True}


@app.get("/admin/stats")
def admin_fetch_stats(token: str = Depends(verify_admin_auth)):
    return db.get_stats()


@app.get("/admin/users")
def admin_fetch_users(token: str = Depends(verify_admin_auth)):
    return db.get_all_users()


@app.get("/admin/users/{device_id}/history")
def admin_fetch_identity_history(device_id: str, token: str = Depends(verify_admin_auth)):
    return db.get_identity_history(device_id)


@app.get("/admin/referrals")
def admin_fetch_referrals(token: str = Depends(verify_admin_auth)):
    return db.get_all_referrals()


@app.get("/admin/rewards/pending")
def admin_fetch_pending_rewards(token: str = Depends(verify_admin_auth)):
    return db.get_pending_rewards()


@app.post("/admin/rewards/sent/{code}")
def admin_mark_reward_dispatched(code: str, token: str = Depends(verify_admin_auth)):
    db.mark_reward_sent(code)
    return {"success": True}


@app.post("/admin/updates/publish")
def admin_publish_update(req: PublishUpdateRequest, token: str = Depends(verify_admin_auth)):
    return db.publish_update(
        version=req.version,
        download_url=req.download_url,
        size_mb=req.size_mb,
        changelog=json.dumps(req.changelog),
        target_tier=req.target_tier,
        is_critical=req.is_critical,
        download_mode=req.download_mode,
        auto_deliver=req.auto_deliver,
    )


@app.post("/admin/updates/toggle-deliver")
def admin_toggle_delivery(req: ToggleDeliverRequest, token: str = Depends(verify_admin_auth)):
    db.toggle_auto_deliver(req.version, req.auto_deliver)
    return {"success": True}


@app.get("/admin/updates/all")
def admin_fetch_all_updates(token: str = Depends(verify_admin_auth)):
    return db.get_all_updates()


@app.get("/admin/transactions")
def admin_fetch_transactions(token: str = Depends(verify_admin_auth)):
    return db.get_all_transactions()


@app.delete("/admin/users/clean-ghosts-real")
def admin_purge_ghost_rows(token: str = Depends(verify_admin_auth)):
    return db.clean_ghost_users_real()


# =============================================================================
# REFACTORED ADMIN DASHBOARD WORKSPACE (Tailwind CSS Dark Mode)
# =============================================================================

@app.get("/admin", response_class=HTMLResponse)
def get_elevated_admin_dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Seven Administrator Command Center</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
        .mono { font-family: 'JetBrains Mono', monospace; }
    </style>
</head>
<body class="bg-black text-zinc-100 min-h-screen">
<div class="max-w-7xl mx-auto px-6 py-8 space-y-8">

    <!-- Top Navigation Header -->
    <div class="flex items-center justify-between border-b border-zinc-800 pb-6">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center shadow-lg">
                <span class="font-mono text-sm font-bold text-white tracking-widest">VII</span>
            </div>
            <div>
                <h1 class="text-md font-bold tracking-wider text-white uppercase">Seven Control Center</h1>
                <p class="text-[10px] text-zinc-500 tracking-wide uppercase">Core Server Administration Workspace</p>
            </div>
        </div>
        <div class="flex items-center gap-4">
            <input type="password" id="admin-token" placeholder="Enter Admin Token"
                class="bg-zinc-900 border border-zinc-800 text-xs px-4 py-2 rounded-lg outline-none focus:border-zinc-700 font-mono text-zinc-300 w-48 transition-colors"/>
            <button onclick="load()" class="px-4 py-2 bg-white text-black text-xs font-semibold rounded-lg hover:bg-zinc-200 transition-colors uppercase tracking-wider">
                Sync Workspace
            </button>
        </div>
    </div>

    <!-- Live Performance Metrics -->
    <div id="stats" class="grid grid-cols-3 gap-6">
        <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6 h-24 animate-pulse"></div>
        <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6 h-24 animate-pulse"></div>
        <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-6 h-24 animate-pulse"></div>
    </div>

    <!-- Real-time Dispatched Referral rewards -->
    <div id="pending"></div>

    <!-- Workspace Control Tabs -->
    <div class="flex gap-2 border-b border-zinc-800 pb-3">
        <button onclick="showTab('users')" id="tab-users" class="px-5 py-2.5 rounded-lg text-xs font-semibold tracking-wider uppercase transition-all bg-white text-black">Users</button>
        <button onclick="showTab('licenses')" id="tab-licenses" class="px-5 py-2.5 rounded-lg text-xs font-semibold tracking-wider uppercase transition-all bg-zinc-900 text-zinc-400">Licensing</button>
        <button onclick="showTab('referrals')" id="tab-referrals" class="px-5 py-2.5 rounded-lg text-xs font-semibold tracking-wider uppercase transition-all bg-zinc-900 text-zinc-400">Referrals</button>
        <button onclick="showTab('transactions')" id="tab-transactions" class="px-5 py-2.5 rounded-lg text-xs font-semibold tracking-wider uppercase transition-all bg-zinc-900 text-zinc-400">Sales</button>
        <button onclick="showTab('updates')" id="tab-updates" class="px-5 py-2.5 rounded-lg text-xs font-semibold tracking-wider uppercase transition-all bg-zinc-900 text-zinc-400">Deployments</button>
    </div>

    <!-- Dynamic Output Area -->
    <div id="content" class="bg-zinc-900/30 border border-zinc-800 rounded-2xl p-6 overflow-x-auto min-h-[300px]"></div>

</div>

<script>
let currentTab = 'users';

function getHeaders() {
    const token = document.getElementById('admin-token').value.trim();
    return {
        'Content-Type': 'application/json',
        'X-Admin-Token': token
    };
}

function setTabStyles(active) {
    ['users','licenses','referrals','transactions','updates'].forEach(t => {
        const btn = document.getElementById('tab-' + t);
        if (t === active) {
            btn.className = 'px-5 py-2.5 rounded-lg text-xs font-semibold tracking-wider uppercase transition-all bg-white text-black shadow-md';
        } else {
            btn.className = 'px-5 py-2.5 rounded-lg text-xs font-semibold tracking-wider uppercase transition-all bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-white hover:bg-zinc-800';
        }
    });
}

async function load() {
    const headers = getHeaders();
    try {
        const stats = await fetch('/admin/stats', { headers }).then(r => {
            if (r.status === 401) throw new Error('Unauthorized');
            return r.json();
        });
        
        document.getElementById('stats').innerHTML = `
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6 hover:border-zinc-700 transition-colors">
                <p class="text-[9px] text-zinc-500 tracking-widest font-semibold uppercase mb-1">Total Verified Registrations</p>
                <p class="text-3xl font-mono font-bold text-white">${stats.total_users}</p>
            </div>
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6 hover:border-zinc-700 transition-colors">
                <p class="text-[9px] text-zinc-500 tracking-widest font-semibold uppercase mb-1">Weekly Active Users (7D)</p>
                <p class="text-3xl font-mono font-bold text-green-400">${stats.active_7d}</p>
            </div>
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-6 hover:border-zinc-700 transition-colors">
                <p class="text-[9px] text-zinc-500 tracking-widest font-semibold uppercase mb-1">Cumulative Local Runtime</p>
                <p class="text-3xl font-mono font-bold text-indigo-400">${stats.total_time}</p>
            </div>
        `;

        const pending = await fetch('/admin/rewards/pending', { headers }).then(r => r.json());
        if (pending.length > 0) {
            let html = `<div class="bg-emerald-500/5 border border-emerald-500/10 rounded-2xl p-6 space-y-4">
                <p class="text-xs font-bold text-emerald-400 uppercase tracking-wider">${pending.length} Referral Reward Packages Ready</p>`;
            pending.forEach(p => {
                html += `<div class="bg-zinc-950 border border-zinc-800 rounded-xl p-4 flex items-center justify-between">
                    <div class="space-y-1">
                        <p class="text-xs text-zinc-300">Referrer: <span class="font-mono text-indigo-400">${p.referrer}</span> <span class="text-zinc-500">→</span> <span class="text-zinc-400 font-semibold">1 Month Ultimate</span></p>
                        <p class="text-xs text-zinc-300">Referred: <span class="font-mono text-green-400">${p.referred}</span> <span class="text-zinc-500">→</span> <span class="text-zinc-400 font-semibold">1 Month Pro</span></p>
                    </div>
                    <div class="flex gap-2">
                        <button onclick="dispatchReward('${p.referred}', '${p.referrer}', '${p.code}')" class="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-black text-xs font-bold rounded-lg transition-colors">Dispatch Reward</button>
                        <button onclick="markSent('${p.code}')" class="px-4 py-2 border border-zinc-800 text-zinc-400 hover:text-white rounded-lg text-xs font-semibold transition-colors">Mark Sent (Manual)</button>
                    </div>
                </div>`;
            });
            html += '</div>';
            document.getElementById('pending').innerHTML = html;
        } else {
            document.getElementById('pending').innerHTML = '';
        }

        showTab(currentTab);
    } catch (e) {
        document.getElementById('stats').innerHTML = `
            <div class="col-span-3 p-4 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-center text-xs font-semibold">
                Authorization Error: Please enter a valid X-Admin-Token to sync the command center.
            </div>
        `;
    }
}

async function showTab(tab) {
    currentTab = tab;
    setTabStyles(tab);
    const headers = getHeaders();
    const content = document.getElementById('content');
    content.innerHTML = '<div class="py-12 flex justify-center"><span class="text-xs text-zinc-500 animate-pulse">Syncing tab metadata...</span></div>';

    try {
        if (tab === 'users') {
            const users = await fetch('/admin/users', { headers }).then(r => r.json());
            let html = `
            <div class="flex justify-between items-center mb-4">
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase">Client Directory</p>
                <button onclick="purgeGhosts()" class="px-3 py-1.5 border border-zinc-800 text-[10px] text-zinc-400 hover:text-red-400 rounded-lg transition-all font-semibold uppercase tracking-wider">Purge Ghosts</button>
            </div>
            <table class="w-full text-xs text-left">
                <thead><tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800 pb-3">
                    <th class="pb-3 uppercase">Device ID</th>
                    <th class="pb-3 uppercase">Name</th>
                    <th class="pb-3 uppercase">Email</th>
                    <th class="pb-3 uppercase">Total Usage</th>
                    <th class="pb-3 uppercase">Plan Tier</th>
                    <th class="pb-3 uppercase">Last Seen</th>
                </tr></thead><tbody class="divide-y divide-zinc-800/30">`;
            
            users.forEach(u => {
                html += `<tr class="hover:bg-zinc-800/10">
                    <td class="py-3.5 font-mono text-zinc-500">${u.device_short}</td>
                    <td class="py-3.5 font-medium text-white">${u.name}</td>
                    <td class="py-3.5 text-zinc-300 font-mono">${u.email}</td>
                    <td class="py-3.5 font-mono text-indigo-400 font-bold">${u.total_time}</td>
                    <td class="py-3.5">
                        <span class="text-[9px] px-2 py-0.5 rounded font-mono font-bold tracking-wider ${
                            u.tier === 'ultimate' ? 'bg-indigo-500/10 text-indigo-300 border border-indigo-500/20' :
                            u.tier === 'pro' ? 'bg-blue-500/10 text-blue-300 border border-blue-500/20' :
                            'bg-zinc-800 text-zinc-500'
                        }">${u.tier.toUpperCase()}</span>
                    </td>
                    <td class="py-3.5 text-zinc-500">${u.last_seen ? u.last_seen.replace('T', ' ').slice(0, 16) : '—'}</td>
                </tr>`;
            });
            content.innerHTML = html + '</tbody></table>';

        } else if (tab === 'licenses') {
            const licenses = await fetch('/admin/licenses', { headers }).then(r => r.json());
            let html = `
            <div class="grid grid-cols-5 gap-6 mb-8">
                <div class="col-span-2 space-y-4">
                    <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase">Generate System Licenses</p>
                    <div class="space-y-3">
                        <div>
                            <label class="text-[9px] text-zinc-500 uppercase block mb-1">Target Email</label>
                            <input id="l-email" placeholder="client@example.com" class="w-full bg-zinc-950 border border-zinc-800 text-xs px-3 py-2 rounded-lg outline-none focus:border-zinc-700"/>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="text-[9px] text-zinc-500 uppercase block mb-1">Plan Tier</label>
                                <select id="l-tier" class="w-full bg-zinc-950 border border-zinc-800 text-xs px-3 py-2 rounded-lg outline-none focus:border-zinc-700">
                                    <option value="pro">Pro Plan</option>
                                    <option value="ultimate">Ultimate Plan</option>
                                </select>
                            </div>
                            <div>
                                <label class="text-[9px] text-zinc-500 uppercase block mb-1">Billing Interval</label>
                                <select id="l-plan" class="w-full bg-zinc-950 border border-zinc-800 text-xs px-3 py-2 rounded-lg outline-none focus:border-zinc-700">
                                    <option value="monthly">Monthly</option>
                                    <option value="yearly">Yearly</option>
                                    <option value="lifetime">Lifetime</option>
                                </select>
                            </div>
                        </div>
                        <div>
                            <label class="text-[9px] text-zinc-500 uppercase block mb-1">Custom Key Prefix (Optional)</label>
                            <input id="l-custom" placeholder="LAUNCH-2025" class="w-full bg-zinc-950 border border-zinc-800 text-xs px-3 py-2 rounded-lg outline-none focus:border-zinc-700 font-mono"/>
                        </div>
                        <button onclick="createLicense()" class="w-full py-2.5 bg-white hover:bg-zinc-200 text-black text-xs font-bold rounded-lg transition-colors uppercase tracking-wider">Generate Key</button>
                    </div>
                </div>
                <div class="col-span-3 overflow-y-auto max-h-[320px]">
                    <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-4">Active Key Registry</p>
                    <table class="w-full text-xs">
                        <thead><tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800 pb-2">
                            <th class="pb-2 text-left">LICENSE KEY</th>
                            <th class="pb-2 text-left">EMAIL</th>
                            <th class="pb-2 text-left">TIER</th>
                            <th class="pb-2 text-left">EXPIRES</th>
                            <th class="pb-2 text-right">ACTION</th>
                        </tr></thead><tbody class="divide-y divide-zinc-800/30">`;
            
            licenses.forEach(l => {
                html += `<tr>
                    <td class="py-2.5 font-mono text-zinc-200">${l.key}</td>
                    <td class="py-2.5 text-zinc-400 truncate max-w-xs">${l.email}</td>
                    <td class="py-2.5 font-mono text-indigo-400 font-semibold">${l.tier.toUpperCase()}</td>
                    <td class="py-2.5 text-zinc-500">${l.expires_at ? l.expires_at.slice(0, 10) : 'Lifetime'}</td>
                    <td class="py-2.5 text-right">
                        ${l.active 
                            ? `<button onclick="revokeLicense('${l.key}')" class="text-[9px] px-2 py-0.5 bg-red-500/10 text-red-400 hover:bg-red-500/20 rounded font-semibold transition-colors">REVOKE</button>`
                            : `<span class="text-[9px] text-zinc-600 uppercase font-semibold">REVOKED</span>`
                        }
                    </td>
                </tr>`;
            });
            html += '</tbody></table></div></div>';
            content.innerHTML = html;

        } else if (tab === 'referrals') {
            const referrals = await fetch('/admin/referrals', { headers }).then(r => r.json());
            let html = `
            <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-4">Referral Funnel Statistics</p>
            <table class="w-full text-xs text-left">
                <thead><tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800 pb-3">
                    <th class="pb-3 uppercase">Tracking Code</th>
                    <th class="pb-3 uppercase">Referrer</th>
                    <th class="pb-3 uppercase">Referred Client</th>
                    <th class="pb-3 uppercase">Funnel Progress (7 Hours)</th>
                    <th class="pb-3 uppercase">Status</th>
                </tr></thead><tbody class="divide-y divide-zinc-800/30">`;
            
            referrals.forEach(r => {
                const pct = Math.min(100, Math.round((r.hours / 7) * 100));
                const barColor = pct >= 100 ? 'bg-emerald-500' : 'bg-indigo-500';
                const statusLabel = r.complete 
                    ? (r.reward_sent 
                        ? '<span class="text-[9px] px-2 py-0.5 rounded bg-zinc-850 text-zinc-500">DISPATCHED</span>'
                        : '<span class="text-[9px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20">REWARD READY</span>')
                    : '<span class="text-[9px] px-2 py-0.5 rounded bg-zinc-900 text-zinc-500">IN PROGRESS</span>';
                
                html += `<tr class="hover:bg-zinc-800/10">
                    <td class="py-3.5 font-mono text-zinc-400 font-medium">${r.code}</td>
                    <td class="py-3.5 font-mono text-zinc-300">${r.referrer}</td>
                    <td class="py-3.5 font-mono text-zinc-300">${r.referred}</td>
                    <td class="py-3.5">
                        <div class="flex items-center gap-3">
                            <div class="w-32 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                                <div class="h-full ${barColor} rounded-full" style="width: ${pct}%"></div>
                            </div>
                            <span class="font-mono text-zinc-400 font-semibold">${r.hours}h / 7h</span>
                        </div>
                    </td>
                    <td class="py-3.5">${statusLabel}</td>
                </tr>`;
            });
            content.innerHTML = html + '</tbody></table>';

        } else if (tab === 'transactions') {
            const txs = await fetch('/admin/transactions', { headers }).then(r => r.json());
            let html = `
            <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-4">Real-time Sales Log</p>
            <table class="w-full text-xs text-left">
                <thead><tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800 pb-3">
                    <th class="pb-3 uppercase">Order ID</th>
                    <th class="pb-3 uppercase">Payment ID</th>
                    <th class="pb-3 uppercase">Email</th>
                    <th class="pb-3 uppercase">Amount</th>
                    <th class="pb-3 uppercase">Key Allocated</th>
                    <th class="pb-3 uppercase">Transaction Date</th>
                </tr></thead><tbody class="divide-y divide-zinc-800/30">`;
            
            txs.forEach(t => {
                html += `<tr class="hover:bg-zinc-800/10">
                    <td class="py-3.5 font-mono text-zinc-500">${t.order_id}</td>
                    <td class="py-3.5 font-mono text-zinc-500">${t.payment_id}</td>
                    <td class="py-3.5 font-mono text-zinc-300 font-medium">${t.email}</td>
                    <td class="py-3.5 font-mono text-emerald-400 font-bold">${t.amount}</td>
                    <td class="py-3.5 font-mono text-zinc-400">${t.license_key}</td>
                    <td class="py-3.5 text-zinc-500">${t.date}</td>
                </tr>`;
            });
            content.innerHTML = html + '</tbody></table>';

        } else if (tab === 'updates') {
            const updates = await fetch('/admin/updates/all', { headers }).then(r => r.json());
            let html = `
            <div class="grid grid-cols-5 gap-6">
                <div class="col-span-2 space-y-4">
                    <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase">Publish System Build</p>
                    <div class="space-y-3 text-xs">
                        <div>
                            <label class="text-[9px] text-zinc-500 uppercase block mb-1">Target Version</label>
                            <input id="u-version" placeholder="e.g., 1.3.4" class="w-full bg-zinc-950 border border-zinc-800 text-xs px-3 py-2 rounded-lg outline-none focus:border-zinc-700 font-mono"/>
                        </div>
                        <div>
                            <label class="text-[9px] text-zinc-500 uppercase block mb-1">Executable URL (S3 / GitHub)</label>
                            <input id="u-url" placeholder="https://github.com/..." class="w-full bg-zinc-950 border border-zinc-800 text-xs px-3 py-2 rounded-lg outline-none focus:border-zinc-700"/>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="text-[9px] text-zinc-500 uppercase block mb-1">Build Size (MB)</label>
                                <input id="u-size" type="number" placeholder="180" class="w-full bg-zinc-950 border border-zinc-800 text-xs px-3 py-2 rounded-lg outline-none focus:border-zinc-700 font-mono"/>
                            </div>
                            <div>
                                <label class="text-[9px] text-zinc-500 uppercase block mb-1">License Tier Lock</label>
                                <select id="u-tier" class="w-full bg-zinc-950 border border-zinc-800 text-xs px-3 py-2 rounded-lg outline-none focus:border-zinc-700">
                                    <option value="all">Free (Everyone)</option>
                                    <option value="pro">Pro Only</option>
                                    <option value="ultimate">Ultimate Only</option>
                                </select>
                            </div>
                        </div>
                        <div>
                            <label class="text-[9px] text-zinc-500 uppercase block mb-1">Changelog (Bullet per line)</label>
                            <textarea id="u-changelog" rows="3" placeholder="Fixed trigger latency&#10;Added sound alerts" class="w-full bg-zinc-950 border border-zinc-800 text-xs px-3 py-2 rounded-lg outline-none focus:border-zinc-700 resize-none"></textarea>
                        </div>
                        <div class="flex items-center gap-4">
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" id="u-critical" class="accent-red-500"/>
                                <span class="text-zinc-400">Critical Patch</span>
                            </label>
                            <label class="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" id="u-autodeliver" checked class="accent-indigo-500"/>
                                <span class="text-zinc-400">Auto Deliver</span>
                            </label>
                        </div>
                        <button onclick="publishRelease()" class="w-full py-2.5 bg-white hover:bg-zinc-200 text-black text-xs font-bold rounded-lg transition-colors uppercase tracking-wider">Publish Release</button>
                    </div>
                </div>
                <div class="col-span-3 overflow-y-auto max-h-[360px]">
                    <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-4">Build Log</p>
                    <table class="w-full text-xs">
                        <thead><tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800 pb-2">
                            <th class="pb-2 text-left">VERSION</th>
                            <th class="pb-2 text-left">TARGET</th>
                            <th class="pb-2 text-left">AUTO DELIVER</th>
                            <th class="pb-2 text-left">STATUS</th>
                            <th class="pb-2 text-right">DATE</th>
                        </tr></thead><tbody class="divide-y divide-zinc-800/30">`;
            
            updates.forEach(u => {
                html += `<tr>
                    <td class="py-2.5 font-mono text-indigo-400 font-bold">v${u.version}</td>
                    <td class="py-2.5 text-zinc-400">${u.target_tier.toUpperCase()}</td>
                    <td class="py-2.5">
                        <button onclick="toggleDelivery('${u.version}', ${!u.auto_deliver})" class="text-[9px] px-2 py-0.5 rounded font-bold transition-all ${
                            u.auto_deliver ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-zinc-800 text-zinc-500'
                        }">${u.auto_deliver ? 'ACTIVE' : 'MUTED'}</button>
                    </td>
                    <td class="py-2.5">
                        ${u.is_active 
                            ? '<span class="text-[9px] px-2 py-0.5 bg-indigo-500/10 text-indigo-300 font-bold border border-indigo-500/20 rounded">DEPLOYED</span>' 
                            : '<span class="text-[9px] text-zinc-600">ARCHIVED</span>'
                        }
                    </td>
                    <td class="py-2.5 text-zinc-500 text-right">${u.published_at ? u.published_at.slice(0, 10) : '—'}</td>
                </tr>`;
            });
            html += '</tbody></table></div></div>';
            content.innerHTML = html;
        }
    } catch(e) {
        console.error(e);
    }
}

async function createLicense() {
    const headers = getHeaders();
    const email = document.getElementById('l-email').value.trim();
    const tier = document.getElementById('l-tier').value;
    const plan_type = document.getElementById('l-plan').value;
    const custom_key = document.getElementById('l-custom').value.trim();

    if (!email) return alert('Email parameter is required.');

    try {
        const r = await fetch('/admin/license/create', {
            method: 'POST',
            headers,
            body: JSON.stringify({ email, tier, plan_type, custom_key })
        });
        if (r.ok) {
            const d = await r.json();
            alert(`Key generated successfully:\\n\\n${d.license_key}`);
            load();
        } else {
            alert('Failed to generate key.');
        }
    } catch(e) { alert(e.message); }
}

async function revokeLicense(key) {
    if (!confirm(`Are you sure you want to permanently deactivate license: ${key}?`)) return;
    const headers = getHeaders();
    try {
        const r = await fetch(`/admin/licenses/${key}`, { method: 'DELETE', headers });
        if (r.ok) load();
    } catch(e) { alert(e.message); }
}

async function publishRelease() {
    const headers = getHeaders();
    const version = document.getElementById('u-version').value.trim();
    const url = document.getElementById('u-url').value.trim();
    const size = parseFloat(document.getElementById('u-size').value) || 0;
    const tier = document.getElementById('u-tier').value;
    const critical = document.getElementById('u-critical').checked;
    const deliver = document.getElementById('u-autodeliver').checked;
    const changelog = document.getElementById('u-changelog').value.split('\\n').filter(Boolean);

    if (!version || !url) return alert('Version and URL are required.');

    try {
        const r = await fetch('/admin/updates/publish', {
            method: 'POST',
            headers,
            body: JSON.stringify({
                version, download_url: url, size_mb: size, changelog,
                target_tier: tier, is_critical: critical, auto_deliver: deliver
            })
        });
        if (r.ok) {
            alert('Release published successfully.');
            load();
        } else {
            alert('Failed to publish release.');
        }
    } catch(e) { alert(e.message); }
}

async function toggleDelivery(version, state) {
    const headers = getHeaders();
    await fetch('/admin/updates/toggle-deliver', {
        method: 'POST',
        headers,
        body: JSON.stringify({ version, auto_deliver: state })
    });
    load();
}

async function dispatchReward(referred, referrer, code) {
    const headers = getHeaders();
    try {
        // Generates the two license keys and prints dispatch data to sysout
        const r = await fetch(`/admin/license/create`, {
            method: 'POST',
            headers,
            body: JSON.stringify({ email: referred, tier: 'pro', plan_type: 'monthly' })
        });
        const r2 = await fetch(`/admin/license/create`, {
            method: 'POST',
            headers,
            body: JSON.stringify({ email: referrer, tier: 'ultimate', plan_type: 'monthly' })
        });
        
        if (r.ok && r2.ok) {
            await fetch(`/admin/rewards/sent/${code}`, { method: 'POST', headers });
            alert('Reward licenses generated successfully on the PostgreSQL cluster.');
            load();
        }
    } catch(e) { alert(e.message); }
}

async function markSent(code) {
    const headers = getHeaders();
    await fetch(`/admin/rewards/sent/${code}`, { method: 'POST', headers });
    load();
}

async function purgeGhosts() {
    if (!confirm('Are you sure you want to safely purge ghost rows with 0 usage hours?')) return;
    const headers = getHeaders();
    try {
        const r = await fetch('/admin/users/clean-ghosts-real', { method: 'DELETE', headers });
        if (r.ok) {
            const d = await r.json();
            alert(`Cleaned ${d.total_deleted} ghost records safely.`);
            load();
        }
    } catch(e) { alert(e.message); }
}
</script>
</body>
</html>
"""