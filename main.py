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
from datetime import datetime
import secrets

app = FastAPI(title="Seven Analytics")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request Models ──

class RegisterRequest(BaseModel):
    device_id: str
    name: Optional[str] = None          # ← NEW: from setup wizard
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
# PUBLIC API (Called by Seven desktop app)
# =============================================================================

@app.post("/api/register")
def register(req: RegisterRequest):
    return db.register_user(
        device_id=req.device_id,
        name=req.name,                  # ← passes name through
        email=req.email,
        country=req.country,
        referral_code=req.referral_code,
    )


@app.post("/api/usage/ping")
def usage_ping(req: UsagePingRequest):
    if req.email:
        db.register_user(req.device_id, email=req.email)
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
    return stats or {
        "referral_code": None,
        "completed_referrals": 0,
        "pending_referrals": 0,
    }


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
    return {
        "license_key": key,
        "email": email,
        "tier": tier,
        "plan_type": plan_type,
    }


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
        <div class="flex items-center gap-3 mb-8">
            <div class="w-8 h-8 rounded-lg bg-indigo-500 flex items-center justify-center">
                <span class="font-mono text-xs font-bold text-white">VII</span>
            </div>
            <h1 class="text-xl font-bold tracking-wide">SEVEN ADMIN</h1>
            <div class="ml-auto text-xs text-zinc-600 font-mono" id="last-refresh"></div>
        </div>

        <div id="stats" class="grid grid-cols-3 gap-4 mb-6"></div>
        <div id="pending" class="mb-6"></div>

        <div class="flex gap-2 mb-4">
            <button onclick="showTab('users')"
                class="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 rounded text-sm font-medium transition-colors"
                id="tab-users">
                Users
            </button>
            <button onclick="showTab('referrals')"
                class="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded text-sm transition-colors"
                id="tab-referrals">
                Referrals
            </button>
        </div>

        <div id="content" class="bg-zinc-900 border border-zinc-800 rounded-xl p-4 overflow-x-auto"></div>
    </div>

    <script>
        let currentTab = 'users';

        async function load() {
            document.getElementById('last-refresh').textContent =
                'Refreshed: ' + new Date().toLocaleTimeString();

            // Stats
            const stats = await fetch('/admin/stats').then(r => r.json());
            document.getElementById('stats').innerHTML = `
                <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
                    <div class="text-[10px] text-zinc-500 tracking-widest mb-1">TOTAL USERS</div>
                    <div class="text-3xl font-mono font-bold">${stats.total_users}</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
                    <div class="text-[10px] text-zinc-500 tracking-widest mb-1">ACTIVE (7D)</div>
                    <div class="text-3xl font-mono font-bold text-green-400">${stats.active_7d}</div>
                </div>
                <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
                    <div class="text-[10px] text-zinc-500 tracking-widest mb-1">TOTAL HOURS</div>
                    <div class="text-3xl font-mono font-bold text-indigo-400">${stats.total_hours}</div>
                </div>
            `;

            // Pending rewards
            const pending = await fetch('/admin/rewards/pending').then(r => r.json());
            if (pending.length > 0) {
                let html = `
                    <div class="bg-green-500/5 border border-green-500/20 rounded-xl p-5 mb-2">
                        <div class="text-green-400 font-semibold text-sm mb-3">
                            ${pending.length} reward${pending.length > 1 ? 's' : ''} pending
                        </div>`;
                pending.forEach(p => {
                    html += `
                        <div class="bg-zinc-900 rounded-lg p-4 mb-2 flex items-center justify-between">
                            <div class="space-y-1">
                                <div class="text-sm">
                                    Referrer: <span class="text-indigo-400 font-mono">${p.referrer}</span>
                                    <span class="text-zinc-600 mx-2">→</span>
                                    <span class="text-xs text-zinc-400">Ultimate 1 month</span>
                                </div>
                                <div class="text-sm">
                                    Referred: <span class="text-green-400 font-mono">${p.referred}</span>
                                    <span class="text-zinc-600 mx-2">→</span>
                                    <span class="text-xs text-zinc-400">Pro 1 month</span>
                                </div>
                            </div>
                            <button onclick="markSent('${p.code}')"
                                class="px-4 py-2 bg-green-500 hover:bg-green-600 rounded-lg text-sm font-medium transition-colors">
                                Mark Sent
                            </button>
                        </div>`;
                });
                html += '</div>';
                document.getElementById('pending').innerHTML = html;
            } else {
                document.getElementById('pending').innerHTML = '';
            }

            showTab(currentTab);
        }

        async function showTab(tab) {
            currentTab = tab;

            // Update tab styles
            document.getElementById('tab-users').className =
                tab === 'users'
                    ? 'px-4 py-2 bg-indigo-500 hover:bg-indigo-600 rounded text-sm font-medium transition-colors'
                    : 'px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded text-sm transition-colors';
            document.getElementById('tab-referrals').className =
                tab === 'referrals'
                    ? 'px-4 py-2 bg-indigo-500 hover:bg-indigo-600 rounded text-sm font-medium transition-colors'
                    : 'px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded text-sm transition-colors';

            const content = document.getElementById('content');

            if (tab === 'users') {
                const users = await fetch('/admin/users').then(r => r.json());
                let html = `
                    <table class="w-full text-sm">
                        <thead>
                            <tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800">
                                <th class="text-left pb-3 font-medium">DEVICE</th>
                                <th class="text-left pb-3 font-medium">NAME</th>
                                <th class="text-left pb-3 font-medium">EMAIL</th>
                                <th class="text-left pb-3 font-medium">HOURS</th>
                                <th class="text-left pb-3 font-medium">TIER</th>
                                <th class="text-left pb-3 font-medium">LAST SEEN</th>
                            </tr>
                        </thead>
                        <tbody>`;
                users.forEach(u => {
                    html += `
                        <tr class="border-b border-zinc-800/50 hover:bg-zinc-800/20 transition-colors">
                            <td class="py-3 font-mono text-xs text-zinc-500">${u.device_id}</td>
                            <td class="py-3 font-medium text-zinc-200">${u.name}</td>
                            <td class="py-3 text-zinc-300">${u.email}</td>
                            <td class="py-3 font-mono text-indigo-400">${u.total_hours}h</td>
                            <td class="py-3">
                                <span class="text-[10px] px-2 py-0.5 rounded font-medium ${
                                    u.tier === 'ultimate' ? 'bg-indigo-500/20 text-indigo-300' :
                                    u.tier === 'pro' ? 'bg-blue-500/20 text-blue-300' :
                                    'bg-zinc-700/50 text-zinc-400'
                                }">${u.tier.toUpperCase()}</span>
                            </td>
                            <td class="py-3 text-zinc-500 text-xs">${u.last_seen || '—'}</td>
                        </tr>`;
                });
                html += '</tbody></table>';
                content.innerHTML = html;

            } else {
                const refs = await fetch('/admin/referrals').then(r => r.json());
                let html = `
                    <table class="w-full text-sm">
                        <thead>
                            <tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800">
                                <th class="text-left pb-3 font-medium">CODE</th>
                                <th class="text-left pb-3 font-medium">REFERRER</th>
                                <th class="text-left pb-3 font-medium">REFERRED</th>
                                <th class="text-left pb-3 font-medium">PROGRESS</th>
                                <th class="text-left pb-3 font-medium">STATUS</th>
                            </tr>
                        </thead>
                        <tbody>`;
                refs.forEach(r => {
                    const pct = Math.min(Math.round((r.hours / 7) * 100), 100);
                    const statusBadge = r.complete
                        ? (r.reward_sent
                            ? '<span class="text-[10px] px-2 py-0.5 rounded bg-zinc-700/50 text-zinc-400">SENT</span>'
                            : '<span class="text-[10px] px-2 py-0.5 rounded bg-green-500/20 text-green-400">REWARD PENDING</span>')
                        : '<span class="text-[10px] px-2 py-0.5 rounded bg-zinc-700/50 text-zinc-500">IN PROGRESS</span>';

                    html += `
                        <tr class="border-b border-zinc-800/50 hover:bg-zinc-800/20 transition-colors">
                            <td class="py-3 font-mono text-xs text-zinc-400">${r.code}</td>
                            <td class="py-3 text-zinc-300">${r.referrer || '—'}</td>
                            <td class="py-3 text-zinc-300">${r.referred || '—'}</td>
                            <td class="py-3">
                                <div class="flex items-center gap-2">
                                    <div class="w-20 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                                        <div class="h-full bg-indigo-500 rounded-full"
                                             style="width: ${pct}%"></div>
                                    </div>
                                    <span class="text-xs font-mono text-zinc-400">${r.hours}h/7h</span>
                                </div>
                            </td>
                            <td class="py-3">${statusBadge}</td>
                        </tr>`;
                });
                html += '</tbody></table>';
                content.innerHTML = html;
            }
        }

        async function markSent(code) {
            await fetch('/admin/rewards/sent/' + code, { method: 'POST' });
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
    return {"status": "ok", "time": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)