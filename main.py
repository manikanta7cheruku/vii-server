"""
SEVEN-SERVER - main.py
Privacy-safe analytics + update distribution server for Seven AI
"""

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
import database as db
from datetime import datetime
import secrets
import json

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
    name: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    referral_code: Optional[str] = None


class UsagePingRequest(BaseModel):
    device_id:      str
    hours_delta:    Optional[float] = None   # legacy
    minutes_delta:  Optional[float] = None   # new — preferred
    email:          Optional[str]   = None


class ReferralRequest(BaseModel):
    device_id: str
    email: str


class PublishUpdateRequest(BaseModel):
    version: str
    download_url: str
    size_mb: float = 0
    changelog: List[str] = []
    target_tier: str = "pro"        # "all", "pro", "ultimate"
    is_critical: bool = False
    download_mode: str = "manual"   # "auto" | "manual"
    auto_deliver: bool = True


class ToggleDeliverRequest(BaseModel):
    version: str
    auto_deliver: bool


# =============================================================================
# PUBLIC API — Called by Seven desktop app
# =============================================================================

@app.post("/api/register")
def register(req: RegisterRequest):
    return db.register_user(
        device_id=req.device_id,
        name=req.name,
        email=req.email,
        country=req.country,
        referral_code=req.referral_code,
    )


@app.post("/api/usage/ping")
def usage_ping(req: UsagePingRequest):
    if req.email:
        db.register_user(req.device_id, email=req.email)
    # Accept minutes_delta (new) or hours_delta (legacy clients)
    return db.update_usage(
        req.device_id,
        hours_delta=req.hours_delta,
        minutes_delta=getattr(req, "minutes_delta", None)
    )


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


@app.get("/api/updates/latest")
def get_latest_update(tier: str = "free", current_version: str = "0.0.0"):
    """
    Called by Seven desktop app on startup.
    Returns latest update info if one is available for the device's tier.
    Returns null if no update or tier not eligible.

    Tier eligibility:
        target_tier = "all"      → everyone gets it
        target_tier = "pro"      → pro + ultimate get it
        target_tier = "ultimate" → only ultimate gets it
    """
    update = db.get_latest_update()

    if not update:
        return {"update_available": False}

    if not update["auto_deliver"]:
        return {"update_available": False}

    # Check tier eligibility
    target = update["target_tier"]
    eligible = False
    if target == "all":
        eligible = True
    elif target == "pro" and tier in ["pro", "ultimate"]:
        eligible = True
    elif target == "ultimate" and tier == "ultimate":
        eligible = True

    if not eligible:
        return {"update_available": False, "reason": "tier_locked"}

    # Compare versions — strips any suffix like "-test" or "-beta"
    def parse_version(v):
        try:
            # Remove suffix like -test, -beta, -rc1
            clean = v.strip().split("-")[0]
            return [int(x) for x in clean.split(".")]
        except Exception:
            return [0, 0, 0]

    latest  = parse_version(update["version"])
    current = parse_version(current_version)

    if latest <= current:
        return {"update_available": False}

    return {
        "update_available": True,
        **update,
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


@app.get("/admin/users/{device_id}/history")
def admin_user_history(device_id: str):
    """Get name/email change history for a specific device."""
    return db.get_identity_history(device_id)


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


@app.post("/admin/updates/publish")
def publish_update(req: PublishUpdateRequest):
    """Publish a new release. Called from admin dashboard form."""
    result = db.publish_update(
        version=req.version,
        download_url=req.download_url,
        size_mb=req.size_mb,
        changelog=json.dumps(req.changelog),
        target_tier=req.target_tier,
        is_critical=req.is_critical,
        download_mode=req.download_mode,
        auto_deliver=req.auto_deliver,
    )
    return result


@app.post("/admin/updates/toggle-deliver")
def toggle_deliver(req: ToggleDeliverRequest):
    """Toggle auto_deliver for a release without republishing."""
    db.toggle_auto_deliver(req.version, req.auto_deliver)
    return {"success": True}


@app.get("/admin/updates/all")
def all_updates():
    return db.get_all_updates()


@app.delete("/admin/users/clear")
def clear_all_users():
    """Clear all users for testing. Remove this in production."""
    conn = db.get_db()
    c = conn.cursor()
    c.execute("DELETE FROM users")
    c.execute("DELETE FROM referrals")
    conn.commit()
    conn.close()
    return {"success": True, "message": "All users cleared"}


@app.delete("/admin/users/clean-ghosts")
def clean_ghost_users():
    """
    Remove ghost rows — users with 0 usage AND no name.
    Safe to run anytime. Keeps all real users.
    """
    conn = db.get_db()
    c = conn.cursor()

    # Delete rows where total_hours is 0 AND name is null or empty
    c.execute("""
        DELETE FROM users
        WHERE total_hours = 0
        AND (name IS NULL OR name = '' OR name = '—')
    """)
    deleted_nameless = c.rowcount

    # Delete duplicate device_ids — keep only the row with most usage
    c.execute("""
        DELETE FROM users
        WHERE ctid NOT IN (
            SELECT DISTINCT ON (device_id) ctid
            FROM users
            ORDER BY device_id, total_hours DESC
        )
    """)
    deleted_dupes = c.rowcount

    conn.commit()
    conn.close()
    return {
        "success": True,
        "deleted_nameless": deleted_nameless,
        "deleted_duplicates": deleted_dupes,
        "message": f"Cleaned {deleted_nameless + deleted_dupes} ghost rows"
    }


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/ping")
def ping():
    """Lightweight keepalive endpoint."""
    return {"ok": True}


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
<div class="max-w-6xl mx-auto space-y-6">

    <!-- Header -->
    <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-lg bg-indigo-500 flex items-center justify-center">
                <span class="font-mono text-xs font-bold text-white">VII</span>
            </div>
            <h1 class="text-lg font-bold tracking-wide">SEVEN ADMIN</h1>
        </div>
        <div class="text-xs text-zinc-600 font-mono" id="last-refresh"></div>
    </div>

    <!-- Stats -->
    <div id="stats" class="grid grid-cols-3 gap-4"></div>

    <!-- Pending rewards -->
    <div id="pending"></div>

    <!-- Tabs -->
    <div class="flex gap-2">
        <button onclick="showTab('users')" id="tab-users"
            class="px-4 py-2 rounded text-sm font-medium transition-colors">Users</button>
        <button onclick="showTab('referrals')" id="tab-referrals"
            class="px-4 py-2 rounded text-sm font-medium transition-colors">Referrals</button>
        <button onclick="showTab('updates')" id="tab-updates"
            class="px-4 py-2 rounded text-sm font-medium transition-colors">Updates</button>
    </div>

    <div id="content" class="bg-zinc-900 border border-zinc-800 rounded-xl p-5 overflow-x-auto"></div>
</div>

<script>
let currentTab = 'users';

function setTabStyles(active) {
    ['users','referrals','updates'].forEach(t => {
        document.getElementById('tab-' + t).className =
            t === active
                ? 'px-4 py-2 rounded text-sm font-medium transition-colors bg-indigo-500 text-white'
                : 'px-4 py-2 rounded text-sm font-medium transition-colors bg-zinc-800 text-zinc-300 hover:bg-zinc-700';
    });
}

async function load() {
    document.getElementById('last-refresh').textContent =
        'Refreshed: ' + new Date().toLocaleTimeString();

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
            <div class="text-[10px] text-zinc-500 tracking-widest mb-1">TOTAL TIME</div>
            <div class="text-3xl font-mono font-bold text-indigo-400">${stats.total_time}</div>
        </div>
    `;

    const pending = await fetch('/admin/rewards/pending').then(r => r.json());
    if (pending.length > 0) {
        let html = `<div class="bg-green-500/5 border border-green-500/20 rounded-xl p-5">
            <div class="text-green-400 font-semibold text-sm mb-3">
                ${pending.length} reward${pending.length > 1 ? 's' : ''} pending
            </div>`;
        pending.forEach(p => {
            html += `<div class="bg-zinc-900 rounded-lg p-4 mb-2 flex items-center justify-between">
                <div class="space-y-1">
                    <div class="text-sm">Referrer: <span class="text-indigo-400 font-mono">${p.referrer}</span>
                        <span class="text-zinc-600 mx-2">→</span>
                        <span class="text-xs text-zinc-400">Ultimate 1 month</span></div>
                    <div class="text-sm">Referred: <span class="text-green-400 font-mono">${p.referred}</span>
                        <span class="text-zinc-600 mx-2">→</span>
                        <span class="text-xs text-zinc-400">Pro 1 month</span></div>
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
    setTabStyles(tab);
    const content = document.getElementById('content');

    if (tab === 'users') {
        const users = await fetch('/admin/users').then(r => r.json());
        let html = `
        <!-- History modal -->
        <div id="history-modal" class="hidden fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-6">
            <div class="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-lg p-6 space-y-4">
                <div class="flex items-center justify-between">
                    <h3 class="text-sm font-semibold text-zinc-200">Identity Change History</h3>
                    <button onclick="closeHistory()" class="text-zinc-500 hover:text-zinc-200 text-lg">✕</button>
                </div>
                <div id="history-content" class="space-y-2 max-h-80 overflow-y-auto"></div>
            </div>
        </div>

        <table class="w-full text-sm">
            <thead><tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800">
                <th class="text-left pb-3">DEVICE</th>
                <th class="text-left pb-3">NAME</th>
                <th class="text-left pb-3">EMAIL</th>
                <th class="text-left pb-3">TIME USED</th>
                <th class="text-left pb-3">TIER</th>
                <th class="text-left pb-3">LAST SEEN</th>
                <th class="text-left pb-3">CHANGES</th>
            </tr></thead><tbody>`;
        users.forEach(u => {
            const changesBadge = u.change_count > 0
                ? `<button onclick="showHistory('${u.device_id}')"
                    class="text-[10px] px-2 py-0.5 rounded bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 transition-colors">
                    ${u.change_count} change${u.change_count > 1 ? 's' : ''}
                  </button>`
                : `<span class="text-[10px] text-zinc-600">—</span>`;

            html += `<tr class="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                <td class="py-3 font-mono text-xs text-zinc-500">${u.device_short}</td>
                <td class="py-3 font-medium">${u.name}</td>
                <td class="py-3 text-zinc-300">${u.email}</td>
                <td class="py-3 font-mono text-indigo-400">${u.total_time}</td>
                <td class="py-3">
                    <span class="text-[10px] px-2 py-0.5 rounded font-medium ${
                        u.tier==='ultimate' ? 'bg-indigo-500/20 text-indigo-300' :
                        u.tier==='pro'      ? 'bg-blue-500/20 text-blue-300' :
                                              'bg-zinc-700/50 text-zinc-400'
                    }">${u.tier.toUpperCase()}</span>
                </td>
                <td class="py-3 text-zinc-500 text-xs">${(u.last_seen||'').slice(0,16).replace('T',' ')}</td>
                <td class="py-3">${changesBadge}</td>
            </tr>`;
        });
        content.innerHTML = html + '</tbody></table>';

    } else if (tab === 'referrals') {
        const refs = await fetch('/admin/referrals').then(r => r.json());
        const pending = await fetch('/admin/rewards/pending').then(r => r.json());

        let html = '';

        // Pending rewards banner
        if (pending.length > 0) {
            html += `<div class="mb-4 bg-green-500/5 border border-green-500/20 rounded-xl p-4">
                <div class="text-green-400 font-semibold text-sm mb-3">
                    ${pending.length} reward${pending.length > 1 ? 's' : ''} ready to send
                </div>`;
            pending.forEach(p => {
                html += `<div class="bg-zinc-900 rounded-lg p-3 mb-2">
                    <div class="text-xs mb-1">
                        Referrer: <span class="text-indigo-400 font-mono">${p.referrer||'—'}</span>
                        <span class="text-zinc-600 mx-1">→</span>
                        <span class="text-[10px] text-zinc-400">Ultimate 1 month</span>
                    </div>
                    <div class="text-xs mb-2">
                        Referred: <span class="text-green-400 font-mono">${p.referred||'—'}</span>
                        <span class="text-zinc-600 mx-1">→</span>
                        <span class="text-[10px] text-zinc-400">Pro 1 month</span>
                    </div>
                    <div class="text-[10px] text-zinc-500 font-mono bg-zinc-800 rounded px-2 py-1">
                        python admin_tools.py reward ${p.referred||'?'} ${p.referrer||'?'}
                    </div>
                    <button onclick="markSent('${p.code}')"
                        class="mt-2 px-3 py-1 bg-green-500 hover:bg-green-600 rounded text-xs font-medium transition-colors">
                        Mark Sent
                    </button>
                </div>`;
            });
            html += '</div>';
        }

        // Stats summary
        const total    = refs.length;
        const done     = refs.filter(r => r.complete).length;
        const progress = refs.filter(r => !r.complete).length;

        html += `<div class="grid grid-cols-3 gap-3 mb-4">
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-3 text-center">
                <div class="text-2xl font-mono font-bold">${total}</div>
                <div class="text-[10px] text-zinc-500 mt-1">TOTAL</div>
            </div>
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-3 text-center">
                <div class="text-2xl font-mono font-bold text-green-400">${done}</div>
                <div class="text-[10px] text-zinc-500 mt-1">COMPLETED</div>
            </div>
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-3 text-center">
                <div class="text-2xl font-mono font-bold text-yellow-400">${progress}</div>
                <div class="text-[10px] text-zinc-500 mt-1">IN PROGRESS</div>
            </div>
        </div>`;

        if (refs.length === 0) {
            html += '<p class="text-sm text-zinc-600 text-center py-8">No referrals yet.</p>';
        } else {
            html += `<table class="w-full text-sm">
                <thead><tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800">
                    <th class="text-left pb-3">REFERRER</th>
                    <th class="text-left pb-3">REFERRED</th>
                    <th class="text-left pb-3">PROGRESS</th>
                    <th class="text-left pb-3">STATUS</th>
                </tr></thead><tbody>`;

            refs.forEach(r => {
                const pct   = Math.min(Math.round((r.hours / 7) * 100), 100);
                const color = pct >= 100 ? 'bg-green-500' : pct >= 50 ? 'bg-yellow-500' : 'bg-indigo-500';
                const badge = r.complete
                    ? (r.reward_sent
                        ? '<span class="text-[10px] px-2 py-0.5 rounded bg-zinc-700/50 text-zinc-400">SENT</span>'
                        : '<span class="text-[10px] px-2 py-0.5 rounded bg-green-500/20 text-green-400 font-medium">REWARD PENDING</span>')
                    : '<span class="text-[10px] px-2 py-0.5 rounded bg-zinc-700/50 text-zinc-500">IN PROGRESS</span>';

                const hoursDisplay = r.hours >= 1
                    ? `${r.hours}h`
                    : `${Math.round(r.hours * 60)}m`;

                html += `<tr class="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                    <td class="py-3 text-xs">${r.referrer||'—'}</td>
                    <td class="py-3 text-xs">${r.referred||'—'}</td>
                    <td class="py-3">
                        <div class="flex items-center gap-2">
                            <div class="w-24 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                                <div class="h-full ${color} rounded-full transition-all" style="width:${pct}%"></div>
                            </div>
                            <span class="text-xs font-mono text-zinc-400">${hoursDisplay}/7h</span>
                        </div>
                    </td>
                    <td class="py-3">${badge}</td>
                </tr>`;
            });
            html += '</tbody></table>';
        }

        content.innerHTML = html;

    } else if (tab === 'updates') {
        const updates = await fetch('/admin/updates/all').then(r => r.json());
        content.innerHTML = `
        <div class="space-y-6">

            <!-- Publish form -->
            <div class="space-y-4">
                <p class="text-[10px] text-zinc-500 tracking-widest font-medium">PUBLISH NEW RELEASE</p>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="text-xs text-zinc-500 block mb-1">Version</label>
                        <input id="u-version" placeholder="1.2.0"
                            class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono focus:border-indigo-500 outline-none"/>
                    </div>
                    <div>
                        <label class="text-xs text-zinc-500 block mb-1">Download URL (GitHub Releases)</label>
                        <input id="u-url" placeholder="https://github.com/manikanta7cheruku/seven-releases/releases/download/v1.2.0/SEVEN-Setup-1.2.0.exe"
                            class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 outline-none"/>
                    </div>
                    <div>
                        <label class="text-xs text-zinc-500 block mb-1">File size (MB)</label>
                        <input id="u-size" type="number" placeholder="145"
                            class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono focus:border-indigo-500 outline-none"/>
                    </div>
                    <div>
                        <label class="text-xs text-zinc-500 block mb-1">Target tier</label>
                        <select id="u-tier"
                            class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 outline-none">
                            <option value="pro">Pro + Ultimate</option>
                            <option value="ultimate">Ultimate only</option>
                            <option value="all">Everyone (including free)</option>
                        </select>
                    </div>
                    <div>
                        <label class="text-xs text-zinc-500 block mb-1">Download mode</label>
                        <select id="u-dlmode"
                            class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 outline-none">
                            <option value="manual">Manual (user clicks Download)</option>
                            <option value="auto">Auto (silent background download)</option>
                        </select>
                    </div>
                    <div class="flex items-end gap-4 pb-1">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" id="u-critical" class="accent-red-500"/>
                            <span class="text-sm text-zinc-300">Critical update</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" id="u-autodeliver" checked class="accent-indigo-500"/>
                            <span class="text-sm text-zinc-300">Auto-deliver now</span>
                        </label>
                    </div>
                </div>
                <div>
                    <label class="text-xs text-zinc-500 block mb-1">
                        Changelog (one item per line)
                    </label>
                    <textarea id="u-changelog" rows="4" placeholder="Fixed memory recall bug&#10;Faster wake word detection&#10;New voice options"
                        class="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 outline-none resize-none"></textarea>
                </div>
                <button onclick="publishUpdate()"
                    class="px-6 py-2.5 bg-indigo-500 hover:bg-indigo-600 rounded-lg text-sm font-medium transition-colors">
                    Publish Release
                </button>
                <div id="publish-status" class="text-xs text-zinc-500 mt-1"></div>
            </div>

            <!-- Existing releases -->
            <div>
                <p class="text-[10px] text-zinc-500 tracking-widest font-medium mb-3">PUBLISHED RELEASES</p>
                ${updates.length === 0
                    ? '<p class="text-sm text-zinc-600">No releases published yet.</p>'
                    : `<table class="w-full text-sm">
                        <thead><tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800">
                            <th class="text-left pb-3">VERSION</th>
                            <th class="text-left pb-3">TARGET</th>
                            <th class="text-left pb-3">MODE</th>
                            <th class="text-left pb-3">CRITICAL</th>
                            <th class="text-left pb-3">AUTO-DELIVER</th>
                            <th class="text-left pb-3">STATUS</th>
                            <th class="text-left pb-3">PUBLISHED</th>
                        </tr></thead><tbody>
                        ${updates.map(u => `
                            <tr class="border-b border-zinc-800/50">
                                <td class="py-3 font-mono text-indigo-300">${u.version}</td>
                                <td class="py-3 text-xs">${u.target_tier}</td>
                                <td class="py-3 text-xs font-mono">${u.download_mode}</td>
                                <td class="py-3">${u.is_critical
                                    ? '<span class="text-[10px] px-2 py-0.5 rounded bg-red-500/20 text-red-400">YES</span>'
                                    : '<span class="text-[10px] px-2 py-0.5 rounded bg-zinc-700/50 text-zinc-500">NO</span>'}</td>
                                <td class="py-3">
                                    <button onclick="toggleDeliver('${u.version}', ${!u.auto_deliver})"
                                        class="text-[10px] px-2 py-0.5 rounded font-medium transition-colors ${u.auto_deliver
                                            ? 'bg-green-500/20 text-green-400 hover:bg-red-500/20 hover:text-red-400'
                                            : 'bg-zinc-700/50 text-zinc-500 hover:bg-green-500/20 hover:text-green-400'}">
                                        ${u.auto_deliver ? 'ON' : 'OFF'}
                                    </button>
                                </td>
                                <td class="py-3">${u.is_active
                                    ? '<span class="text-[10px] px-2 py-0.5 rounded bg-green-500/20 text-green-400">LIVE</span>'
                                    : '<span class="text-[10px] px-2 py-0.5 rounded bg-zinc-700/50 text-zinc-500">ARCHIVED</span>'}</td>
                                <td class="py-3 text-zinc-500 text-xs">${(u.published_at||'').slice(0,10)}</td>
                            </tr>`).join('')}
                        </tbody></table>`
                }
            </div>
        </div>`;
    }
}

async function publishUpdate() {
    const version   = document.getElementById('u-version').value.trim();
    const url       = document.getElementById('u-url').value.trim();
    const size      = parseFloat(document.getElementById('u-size').value) || 0;
    const tier      = document.getElementById('u-tier').value;
    const dlmode    = document.getElementById('u-dlmode').value;
    const critical  = document.getElementById('u-critical').checked;
    const deliver   = document.getElementById('u-autodeliver').checked;
    const rawLog    = document.getElementById('u-changelog').value;
    const changelog = rawLog.split('\\n').map(l=>l.trim()).filter(Boolean);
    const status    = document.getElementById('publish-status');

    if (!version || !url) {
        status.textContent = 'Version and URL are required.';
        status.className = 'text-xs text-red-400 mt-1';
        return;
    }

    status.textContent = 'Publishing...';
    status.className = 'text-xs text-zinc-400 mt-1';

    try {
        const r = await fetch('/admin/updates/publish', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                version, download_url: url, size_mb: size,
                changelog, target_tier: tier,
                is_critical: critical, download_mode: dlmode,
                auto_deliver: deliver
            })
        });
        const data = await r.json();
        if (data.success) {
            status.textContent = `Version ${version} published successfully.`;
            status.className = 'text-xs text-green-400 mt-1';
            load();
        } else {
            status.textContent = 'Publish failed.';
            status.className = 'text-xs text-red-400 mt-1';
        }
    } catch(e) {
        status.textContent = 'Server error: ' + e.message;
        status.className = 'text-xs text-red-400 mt-1';
    }
}

async function toggleDeliver(version, state) {
    await fetch('/admin/updates/toggle-deliver', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({version, auto_deliver: state})
    });
    load();
}

async function markSent(code) {
    await fetch('/admin/rewards/sent/' + code, {method: 'POST'});
    load();
}

async function showHistory(deviceId) {
    const modal = document.getElementById('history-modal');
    const content = document.getElementById('history-content');
    content.innerHTML = '<p class="text-xs text-zinc-500">Loading...</p>';
    modal.classList.remove('hidden');

    try {
        const history = await fetch('/admin/users/' + encodeURIComponent(deviceId) + '/history').then(r => r.json());

        if (!history || history.length === 0) {
            content.innerHTML = '<p class="text-xs text-zinc-500 text-center py-4">No changes recorded yet.</p>';
            return;
        }

        content.innerHTML = history.map(h => `
            <div class="bg-zinc-800 rounded-lg p-3 space-y-1">
                <div class="flex items-center justify-between">
                    <span class="text-[10px] px-2 py-0.5 rounded font-medium ${
                        h.field === 'name'
                            ? 'bg-indigo-500/20 text-indigo-300'
                            : 'bg-green-500/20 text-green-300'
                    }">${h.field.toUpperCase()} CHANGED</span>
                    <span class="text-[10px] text-zinc-500 font-mono">${(h.changed_at||'').slice(0,16).replace('T',' ')}</span>
                </div>
                <div class="flex items-center gap-2 text-xs">
                    <span class="text-zinc-500 line-through">${h.old_value || '—'}</span>
                    <span class="text-zinc-600">→</span>
                    <span class="text-zinc-200 font-medium">${h.new_value || '—'}</span>
                </div>
            </div>
        `).join('');
    } catch(e) {
        content.innerHTML = '<p class="text-xs text-red-400">Failed to load history.</p>';
    }
}

function closeHistory() {
    document.getElementById('history-modal').classList.add('hidden');
}

load();
setInterval(load, 30000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)