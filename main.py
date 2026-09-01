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

@app.api_route("/", methods=["GET", "HEAD"])
def root_redirect():
    """Root endpoint — redirects to admin dashboard. Supports HEAD for Render health checks."""
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


@app.delete("/admin/users/{device_id}")
def admin_delete_user(device_id: str, token: str = Depends(verify_admin_auth)):
    """Permanently delete a user and all their data."""
    deleted = db.delete_user(device_id)
    return {"success": True, "deleted": deleted}


@app.delete("/admin/referrals/{referral_code}")
def admin_delete_referral(referral_code: str, token: str = Depends(verify_admin_auth)):
    """Delete a referral record."""
    deleted = db.delete_referral(referral_code)
    return {"success": True, "deleted": deleted}


# =============================================================================
# REFACTORED ADMIN DASHBOARD WORKSPACE (Tailwind CSS Dark Mode)
# =============================================================================

@app.get("/admin", response_class=HTMLResponse)
def get_admin_dashboard():
    """Serve modular responsive admin dashboard."""
    from dashboard.layout import render_dashboard
    return render_dashboard()