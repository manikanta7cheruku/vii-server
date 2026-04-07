"""
SEVEN-SERVER - main.py
Privacy-safe analytics server for Seven AI
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import database as db
from datetime import datetime, timedelta
import secrets

app = FastAPI(title="Seven Analytics")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request Models
class RegisterRequest(BaseModel):
    device_id: str
    email: Optional[str] = None
    country: Optional[str] = None
    referral_code: Optional[str] = None


class UsagePingRequest(BaseModel):
    device_id: str
    hours_delta: float
    email: Optional[str] = None


class ReferralRequest(BaseModel):
    device_id: str
    email: str


# =============================================================================
# PUBLIC API (Called by Seven app)
# =============================================================================

@app.post("/api/register")
def register(req: RegisterRequest):
    return db.register_user(req.device_id, req.email, req.country, req.referral_code)


@app.post("/api/usage/ping")
def usage_ping(req: UsagePingRequest):
    if req.email:
        db.register_user(req.device_id, req.email)
    return db.update_usage(req.device_id, req.hours_delta)


@app.post("/api/referral/create")
def create_referral(req: ReferralRequest):
    if not req.email or "@" not in req.email:
        raise HTTPException(400, "Valid email required")
    result = db.create_referral(req.device_id, req.email)
    result["referral_link"] = f"https://seven.app/ref/{result['referral_code']}"
    return result


@app.get("/api/referral/stats")
def referral_stats(email: str = None, device_id: str = None):
    stats = db.get_referral_stats(email, device_id)
    return stats or {"referral_code": None, "completed_referrals": 0, "pending_referrals": 0}


# =============================================================================
# ADMIN API
# =============================================================================

@app.get("/admin/stats")
def admin_stats():
    return db.get_stats()


@app.get("/admin/users")
def admin_users():
    return db.get_all_users()


@app.get("/admin/referrals")
def admin_referrals():
    return db.get_all_referrals()


@app.get("/admin/rewards/pending")
def admin_pending():
    return db.get_pending_rewards()


@app.post("/admin/rewards/sent/{code}")
def admin_mark_sent(code: str):
    db.mark_reward_sent(code)
    return {"success": True}


@app.post("/admin/license/generate")
def generate_license(email: str, tier: str = "pro", plan_type: str = "monthly"):
    key = f"VII-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
    return {"license_key": key, "email": email, "tier": tier, "plan_type": plan_type}


# =============================================================================
# ADMIN DASHBOARD UI
# =============================================================================

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Seven Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-zinc-950 text-zinc-200 p-6">
    <div class="max-w-6xl mx-auto">
        <h1 class="text-2xl font-bold text-indigo-400 mb-6">SEVEN ADMIN DASHBOARD</h1>
        
        <div id="stats" class="grid grid-cols-3 gap-4 mb-6"></div>
        <div id="pending" class="mb-6"></div>
        
        <div class="flex gap-2 mb-4">
            <button onclick="showTab('users')" class="px-4 py-2 bg-indigo-500 rounded text-sm">Users</button>
            <button onclick="showTab('referrals')" class="px-4 py-2 bg-zinc-800 rounded text-sm">Referrals</button>
        </div>
        
        <div id="content" class="bg-zinc-900 border border-zinc-800 rounded p-4"></div>
    </div>
    
    <script>
        async function load() {
            const stats = await fetch('/admin/stats').then(r => r.json());
            document.getElementById('stats').innerHTML = `
                <div class="bg-zinc-900 border border-zinc-800 rounded p-4">
                    <div class="text-xs text-zinc-500">TOTAL USERS</div>
                    <div class="text-3xl font-mono">${stats.total_users}</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 rounded p-4">
                    <div class="text-xs text-zinc-500">ACTIVE (7D)</div>
                    <div class="text-3xl font-mono text-green-400">${stats.active_7d}</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 rounded p-4">
                    <div class="text-xs text-zinc-500">TOTAL HOURS</div>
                    <div class="text-3xl font-mono">${stats.total_hours}</div>
                </div>
            `;
            
            const pending = await fetch('/admin/rewards/pending').then(r => r.json());
            if (pending.length > 0) {
                let html = '<div class="bg-green-500/10 border border-green-500/30 rounded p-4 mb-4">';
                html += '<div class="text-green-400 font-medium mb-2">🎉 ' + pending.length + ' Reward(s) to Send!</div>';
                pending.forEach(p => {
                    html += '<div class="bg-zinc-900 rounded p-3 mb-2">';
                    html += '<div>Referrer: <span class="text-indigo-400">' + p.referrer + '</span> → Ultimate 1mo</div>';
                    html += '<div>Referred: <span class="text-green-400">' + p.referred + '</span> → Pro 1mo</div>';
                    html += '<button onclick="markSent(\\''+p.code+'\\')\" class="mt-2 px-3 py-1 bg-green-500 rounded text-sm">Mark Sent</button>';
                    html += '</div>';
                });
                html += '</div>';
                document.getElementById('pending').innerHTML = html;
            }
            
            showTab('users');
        }
        
        async function showTab(tab) {
            const content = document.getElementById('content');
            
            if (tab === 'users') {
                const users = await fetch('/admin/users').then(r => r.json());
                let html = '<table class="w-full text-sm"><tr class="text-zinc-500 text-xs"><th class="text-left pb-2">Device</th><th class="text-left pb-2">Email</th><th class="text-left pb-2">Hours</th><th class="text-left pb-2">Last Seen</th></tr>';
                users.forEach(u => {
                    html += '<tr class="border-t border-zinc-800"><td class="py-2 font-mono text-xs">' + u.device_id + '</td><td>' + u.email + '</td><td class="font-mono">' + u.total_hours + 'h</td><td class="text-zinc-500 text-xs">' + (u.last_seen || '—') + '</td></tr>';
                });
                content.innerHTML = html + '</table>';
            } else {
                const refs = await fetch('/admin/referrals').then(r => r.json());
                let html = '<table class="w-full text-sm"><tr class="text-zinc-500 text-xs"><th class="text-left pb-2">Code</th><th class="text-left pb-2">Referrer</th><th class="text-left pb-2">Referred</th><th class="text-left pb-2">Progress</th></tr>';
                refs.forEach(r => {
                    const status = r.complete ? (r.reward_sent ? '✅' : '🎉') : Math.round(r.hours/7*100) + '%';
                    html += '<tr class="border-t border-zinc-800"><td class="py-2 font-mono text-xs">' + r.code + '</td><td>' + r.referrer + '</td><td>' + r.referred + '</td><td>' + r.hours + 'h/7h ' + status + '</td></tr>';
                });
                content.innerHTML = html + '</table>';
            }
        }
        
        async function markSent(code) {
            await fetch('/admin/rewards/sent/' + code, {method: 'POST'});
            load();
        }
        
        load();
        setInterval(load, 30000);
    </script>
</body>
</html>
"""


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)