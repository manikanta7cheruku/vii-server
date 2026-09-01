"""JavaScript for admin dashboard."""

DASHBOARD_SCRIPTS = """
let currentTab = 'users';
let isAuthenticated = false;

function getHeaders() {
    const token = document.getElementById('admin-token').value.trim();
    return {
        'Content-Type': 'application/json',
        'X-Admin-Token': token
    };
}

function showAuthError() {
    document.getElementById('auth-status').innerHTML = `
        <div class="bg-red-500/10 border border-red-500/20 rounded-xl p-4 fade-in">
            <div class="flex items-start gap-3">
                <div class="w-5 h-5 rounded-full bg-red-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span class="text-red-400 text-xs font-bold">!</span>
                </div>
                <div class="min-w-0">
                    <p class="text-xs font-semibold text-red-400 mb-1">Authentication Required</p>
                    <p class="text-[11px] text-red-300/70 leading-relaxed">Enter your admin token in the field above and click Sync. If you don't have one, add SEVEN_ADMIN_TOKEN in your Render environment variables.</p>
                </div>
            </div>
        </div>
    `;
    document.getElementById('stats').innerHTML = `
        <div class="col-span-full text-center py-8">
            <p class="text-xs text-zinc-600">Awaiting authentication...</p>
        </div>
    `;
    document.getElementById('content').innerHTML = `
        <div class="py-12 text-center">
            <p class="text-xs text-zinc-500">Please authenticate to view data.</p>
        </div>
    `;
}

async function load() {
    const token = document.getElementById('admin-token').value.trim();
    if (!token) {
        showAuthError();
        return;
    }

    try {
        const r = await fetch('/admin/stats', { headers: getHeaders() });
        if (r.status === 401) {
            showAuthError();
            isAuthenticated = false;
            return;
        }

        const stats = await r.json();
        isAuthenticated = true;
        document.getElementById('auth-status').innerHTML = '';

        document.getElementById('stats').innerHTML = `
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 sm:p-5 fade-in">
                <p class="text-[9px] sm:text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-1">Total Users</p>
                <p class="text-2xl sm:text-3xl mono font-bold text-white">${stats.total_users}</p>
            </div>
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 sm:p-5 fade-in">
                <p class="text-[9px] sm:text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-1">Active 7D</p>
                <p class="text-2xl sm:text-3xl mono font-bold text-green-400">${stats.active_7d}</p>
            </div>
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 sm:p-5 fade-in">
                <p class="text-[9px] sm:text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-1">Runtime</p>
                <p class="text-2xl sm:text-3xl mono font-bold text-indigo-400">${stats.total_time}</p>
            </div>
        `;

        const pending = await fetch('/admin/rewards/pending', { headers: getHeaders() }).then(r => r.json());
        if (pending.length > 0) {
            let html = `<div class="bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-4 sm:p-5 space-y-3 fade-in">
                <p class="text-xs font-bold text-emerald-400 uppercase tracking-wider">${pending.length} Reward${pending.length > 1 ? 's' : ''} Ready</p>`;
            pending.forEach(p => {
                html += `<div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 sm:p-4 space-y-3">
                    <div class="space-y-1.5">
                        <p class="text-[11px] text-zinc-300 break-all">Referrer: <span class="mono text-indigo-400">${p.referrer}</span></p>
                        <p class="text-[11px] text-zinc-300 break-all">Referred: <span class="mono text-green-400">${p.referred}</span></p>
                    </div>
                    <div class="flex flex-col sm:flex-row gap-2">
                        <button onclick="dispatchReward('${p.referred}', '${p.referrer}', '${p.code}')" class="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-black text-[11px] font-bold rounded-lg transition-colors">Dispatch</button>
                        <button onclick="markSent('${p.code}')" class="px-4 py-2 border border-zinc-800 text-zinc-400 hover:text-white rounded-lg text-[11px] font-semibold transition-colors">Mark Sent</button>
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
        showAuthError();
    }
}

function setTabStyles(active) {
    ['users','licenses','referrals','transactions','updates'].forEach(t => {
        const btn = document.getElementById('tab-' + t);
        if (t === active) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
}

async function showTab(tab) {
    currentTab = tab;
    setTabStyles(tab);
    if (!isAuthenticated) return;

    const headers = getHeaders();
    const content = document.getElementById('content');
    content.innerHTML = '<div class="py-8 text-center"><span class="text-xs text-zinc-500 animate-pulse">Loading...</span></div>';

    try {
        if (tab === 'users') {
            const users = await fetch('/admin/users', { headers }).then(r => r.json());
            renderUsers(users, content);
        } else if (tab === 'licenses') {
            const licenses = await fetch('/admin/licenses', { headers }).then(r => r.json());
            renderLicenses(licenses, content);
        } else if (tab === 'referrals') {
            const refs = await fetch('/admin/referrals', { headers }).then(r => r.json());
            renderReferrals(refs, content);
        } else if (tab === 'transactions') {
            const txs = await fetch('/admin/transactions', { headers }).then(r => r.json());
            renderTransactions(txs, content);
        } else if (tab === 'updates') {
            const updates = await fetch('/admin/updates/all', { headers }).then(r => r.json());
            renderUpdates(updates, content);
        }
    } catch(e) {
        content.innerHTML = '<p class="text-xs text-red-400 text-center py-8">Failed to load data.</p>';
    }
}

function renderUsers(users, content) {
    if (!users || users.length === 0) {
        content.innerHTML = '<p class="text-xs text-zinc-500 text-center py-8">No users yet.</p>';
        return;
    }

    let html = `
        <div class="flex flex-col sm:flex-row sm:justify-between sm:items-center mb-4 gap-2">
            <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase">Client Directory (${users.length})</p>
            <button onclick="purgeGhosts()" class="px-3 py-1.5 border border-zinc-800 text-[10px] text-zinc-400 hover:text-red-400 rounded-lg transition-all font-semibold uppercase tracking-wider self-start sm:self-auto">Purge Ghosts</button>
        </div>

        <!-- Desktop Table -->
        <table class="desktop-table w-full text-xs text-left">
            <thead><tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800">
                <th class="pb-3 uppercase">Device</th>
                <th class="pb-3 uppercase">Name</th>
                <th class="pb-3 uppercase">Email</th>
                <th class="pb-3 uppercase">Usage</th>
                <th class="pb-3 uppercase">Tier</th>
                <th class="pb-3 uppercase">Last Seen</th>
            </tr></thead><tbody class="divide-y divide-zinc-800/30">`;

    users.forEach(u => {
        html += `<tr class="hover:bg-zinc-800/10 fade-in">
            <td class="py-3 mono text-zinc-500">${u.device_short}</td>
            <td class="py-3 font-medium text-white">${u.name}</td>
            <td class="py-3 text-zinc-300 mono">${u.email}</td>
            <td class="py-3 mono text-indigo-400 font-bold">${u.total_time}</td>
            <td class="py-3">${tierBadge(u.tier)}</td>
            <td class="py-3 text-zinc-500">${(u.last_seen || '').slice(0, 16).replace('T', ' ') || '—'}</td>
        </tr>`;
    });
    html += '</tbody></table>';

    // Mobile Cards
    html += '<div class="mobile-cards space-y-3">';
    users.forEach(u => {
        html += `<div class="bg-zinc-950 border border-zinc-800 rounded-lg p-4 space-y-2 fade-in">
            <div class="flex justify-between items-start gap-2">
                <div class="min-w-0 flex-1">
                    <p class="text-sm font-medium text-white truncate">${u.name}</p>
                    <p class="text-[11px] text-zinc-400 mono truncate">${u.email}</p>
                </div>
                ${tierBadge(u.tier)}
            </div>
            <div class="flex justify-between items-center pt-2 border-t border-zinc-900">
                <div>
                    <p class="text-[9px] text-zinc-600 uppercase">Usage</p>
                    <p class="text-xs mono text-indigo-400 font-bold">${u.total_time}</p>
                </div>
                <div class="text-right">
                    <p class="text-[9px] text-zinc-600 uppercase">Last Seen</p>
                    <p class="text-[11px] text-zinc-400">${(u.last_seen || '').slice(0, 10) || '—'}</p>
                </div>
            </div>
        </div>`;
    });
    html += '</div>';

    content.innerHTML = html;
}

function tierBadge(tier) {
    const styles = {
        ultimate: 'bg-indigo-500/10 text-indigo-300 border-indigo-500/20',
        pro: 'bg-blue-500/10 text-blue-300 border-blue-500/20',
        free: 'bg-zinc-800 text-zinc-500 border-zinc-800'
    };
    const cls = styles[tier] || styles.free;
    return `<span class="text-[9px] px-2 py-0.5 rounded mono font-bold tracking-wider border ${cls}">${tier.toUpperCase()}</span>`;
}

function renderLicenses(licenses, content) {
    content.innerHTML = `
        <div class="space-y-6">
            <div class="space-y-4">
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase">Generate License</p>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="text-[9px] text-zinc-500 uppercase block mb-1">Email</label>
                        <input id="l-email" placeholder="user@example.com" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30"/>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="text-[9px] text-zinc-500 uppercase block mb-1">Tier</label>
                            <select id="l-tier" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30">
                                <option value="pro">Pro</option>
                                <option value="ultimate">Ultimate</option>
                            </select>
                        </div>
                        <div>
                            <label class="text-[9px] text-zinc-500 uppercase block mb-1">Plan</label>
                            <select id="l-plan" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30">
                                <option value="monthly">Monthly</option>
                                <option value="yearly">Yearly</option>
                                <option value="lifetime">Lifetime</option>
                            </select>
                        </div>
                    </div>
                </div>
                <div>
                    <label class="text-[9px] text-zinc-500 uppercase block mb-1">Custom Prefix (optional)</label>
                    <input id="l-custom" placeholder="LAUNCH-2025" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30 mono"/>
                </div>
                <button onclick="createLicense()" class="w-full sm:w-auto px-6 py-2.5 bg-white hover:bg-zinc-200 text-black text-xs font-bold rounded-lg transition-colors uppercase tracking-wider">Generate Key</button>
            </div>

            <div>
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-3">Active Keys (${licenses.length})</p>
                <div class="space-y-2">
                    ${licenses.map(l => `
                        <div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 flex flex-col sm:flex-row sm:items-center gap-2">
                            <div class="flex-1 min-w-0">
                                <p class="text-xs mono text-white break-all">${l.key}</p>
                                <p class="text-[10px] text-zinc-500 mt-0.5 truncate">${l.email} • ${l.tier.toUpperCase()} • Expires ${l.expires_at || 'Lifetime'}</p>
                            </div>
                            ${l.active
                                ? `<button onclick="revokeLicense('${l.key}')" class="text-[10px] px-3 py-1 bg-red-500/10 text-red-400 hover:bg-red-500/20 rounded font-semibold transition-colors self-start">REVOKE</button>`
                                : `<span class="text-[10px] text-zinc-600 uppercase font-semibold self-start">REVOKED</span>`
                            }
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `;
}

function renderReferrals(refs, content) {
    if (!refs || refs.length === 0) {
        content.innerHTML = '<p class="text-xs text-zinc-500 text-center py-8">No referrals yet.</p>';
        return;
    }

    let html = `<p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-4">Referral Funnel (${refs.length})</p>`;
    html += '<div class="space-y-2">';
    refs.forEach(r => {
        const pct = Math.min(100, Math.round((r.hours / 7) * 100));
        const barColor = pct >= 100 ? 'bg-emerald-500' : 'bg-indigo-500';
        const status = r.complete
            ? (r.reward_sent ? 'DISPATCHED' : 'REWARD READY')
            : 'IN PROGRESS';
        const statusColor = r.complete
            ? (r.reward_sent ? 'text-zinc-500' : 'text-emerald-400')
            : 'text-zinc-500';

        html += `<div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 fade-in">
            <div class="flex flex-col sm:flex-row sm:justify-between gap-2 mb-2">
                <div class="min-w-0">
                    <p class="text-[11px] text-zinc-400 truncate">R: <span class="mono text-white">${r.referrer}</span></p>
                    <p class="text-[11px] text-zinc-400 truncate">→ <span class="mono text-zinc-300">${r.referred}</span></p>
                </div>
                <span class="text-[9px] ${statusColor} font-bold whitespace-nowrap self-start">${status}</span>
            </div>
            <div class="flex items-center gap-2">
                <div class="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                    <div class="h-full ${barColor} rounded-full transition-all" style="width: ${pct}%"></div>
                </div>
                <span class="text-[10px] mono text-zinc-400 font-semibold whitespace-nowrap">${r.hours}h / 7h</span>
            </div>
        </div>`;
    });
    html += '</div>';
    content.innerHTML = html;
}

function renderTransactions(txs, content) {
    if (!txs || txs.length === 0) {
        content.innerHTML = '<p class="text-xs text-zinc-500 text-center py-8">No transactions yet.</p>';
        return;
    }

    let html = `<p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-4">Sales Log (${txs.length})</p>`;
    html += '<div class="space-y-2">';
    txs.forEach(t => {
        html += `<div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 fade-in">
            <div class="flex flex-col sm:flex-row sm:justify-between gap-2">
                <div class="min-w-0">
                    <p class="text-xs mono text-white break-all">${t.email}</p>
                    <p class="text-[10px] text-zinc-500 mt-0.5">${t.tier.toUpperCase()} • ${t.plan_type} • ${t.date}</p>
                </div>
                <div class="text-right">
                    <p class="text-sm mono text-emerald-400 font-bold">${t.amount}</p>
                    <p class="text-[10px] text-zinc-500 mono truncate">${t.license_key}</p>
                </div>
            </div>
        </div>`;
    });
    html += '</div>';
    content.innerHTML = html;
}

function renderUpdates(updates, content) {
    content.innerHTML = `
        <div class="space-y-6">
            <div class="space-y-4">
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase">Publish Build</p>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="text-[9px] text-zinc-500 uppercase block mb-1">Version</label>
                        <input id="u-version" placeholder="1.3.4" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30 mono"/>
                    </div>
                    <div>
                        <label class="text-[9px] text-zinc-500 uppercase block mb-1">Size (MB)</label>
                        <input id="u-size" type="number" placeholder="180" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30 mono"/>
                    </div>
                </div>
                <div>
                    <label class="text-[9px] text-zinc-500 uppercase block mb-1">Download URL</label>
                    <input id="u-url" placeholder="https://github.com/..." class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30"/>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="text-[9px] text-zinc-500 uppercase block mb-1">Tier Lock</label>
                        <select id="u-tier" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30">
                            <option value="all">Everyone</option>
                            <option value="pro">Pro+</option>
                            <option value="ultimate">Ultimate Only</option>
                        </select>
                    </div>
                    <div class="flex items-end gap-3">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" id="u-critical" class="accent-red-500 w-4 h-4"/>
                            <span class="text-xs text-zinc-400">Critical</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" id="u-autodeliver" checked class="accent-indigo-500 w-4 h-4"/>
                            <span class="text-xs text-zinc-400">Auto Deliver</span>
                        </label>
                    </div>
                </div>
                <div>
                    <label class="text-[9px] text-zinc-500 uppercase block mb-1">Changelog (one per line)</label>
                    <textarea id="u-changelog" rows="4" placeholder="Fixed trigger latency&#10;Added new voices" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30 resize-none"></textarea>
                </div>
                <button onclick="publishRelease()" class="w-full sm:w-auto px-6 py-2.5 bg-white hover:bg-zinc-200 text-black text-xs font-bold rounded-lg transition-colors uppercase tracking-wider">Publish Release</button>
            </div>

            <div>
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-3">Build Log (${updates.length})</p>
                <div class="space-y-2">
                    ${updates.map(u => `
                        <div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 flex flex-col sm:flex-row sm:items-center gap-2">
                            <div class="flex-1">
                                <p class="text-xs mono text-indigo-400 font-bold">v${u.version}</p>
                                <p class="text-[10px] text-zinc-500 mt-0.5">${u.target_tier.toUpperCase()} • ${u.published_at ? u.published_at.slice(0, 10) : '—'}</p>
                            </div>
                            <div class="flex items-center gap-2">
                                ${u.is_active
                                    ? '<span class="text-[9px] px-2 py-0.5 bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 rounded font-bold">DEPLOYED</span>'
                                    : '<span class="text-[9px] text-zinc-600">ARCHIVED</span>'
                                }
                                <button onclick="toggleDelivery('${u.version}', ${!u.auto_deliver})" class="text-[9px] px-2 py-0.5 rounded font-bold ${u.auto_deliver ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-zinc-800 text-zinc-500'}">${u.auto_deliver ? 'ACTIVE' : 'MUTED'}</button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `;
}

async function createLicense() {
    const email = document.getElementById('l-email').value.trim();
    const tier = document.getElementById('l-tier').value;
    const plan_type = document.getElementById('l-plan').value;
    const custom_key = document.getElementById('l-custom').value.trim();

    if (!email) return alert('Email is required');

    try {
        const r = await fetch('/admin/license/create', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ email, tier, plan_type, custom_key })
        });
        if (r.ok) {
            const d = await r.json();
            alert(`Key generated:\\n\\n${d.license_key}`);
            load();
        } else {
            alert('Failed to generate key');
        }
    } catch(e) { alert(e.message); }
}

async function revokeLicense(key) {
    if (!confirm(`Revoke ${key}?`)) return;
    try {
        const r = await fetch(`/admin/licenses/${key}`, { method: 'DELETE', headers: getHeaders() });
        if (r.ok) load();
    } catch(e) { alert(e.message); }
}

async function publishRelease() {
    const version = document.getElementById('u-version').value.trim();
    const url = document.getElementById('u-url').value.trim();
    const size = parseFloat(document.getElementById('u-size').value) || 0;
    const tier = document.getElementById('u-tier').value;
    const critical = document.getElementById('u-critical').checked;
    const deliver = document.getElementById('u-autodeliver').checked;
    const changelog = document.getElementById('u-changelog').value.split('\\n').filter(Boolean);

    if (!version || !url) return alert('Version and URL required');

    try {
        const r = await fetch('/admin/updates/publish', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({
                version, download_url: url, size_mb: size, changelog,
                target_tier: tier, is_critical: critical, auto_deliver: deliver
            })
        });
        if (r.ok) {
            alert('Published');
            load();
        }
    } catch(e) { alert(e.message); }
}

async function toggleDelivery(version, state) {
    await fetch('/admin/updates/toggle-deliver', {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ version, auto_deliver: state })
    });
    load();
}

async function dispatchReward(referred, referrer, code) {
    try {
        await fetch('/admin/license/create', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ email: referred, tier: 'pro', plan_type: 'monthly' })
        });
        await fetch('/admin/license/create', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ email: referrer, tier: 'ultimate', plan_type: 'monthly' })
        });
        await fetch(`/admin/rewards/sent/${code}`, { method: 'POST', headers: getHeaders() });
        alert('Reward dispatched');
        load();
    } catch(e) { alert(e.message); }
}

async function markSent(code) {
    await fetch(`/admin/rewards/sent/${code}`, { method: 'POST', headers: getHeaders() });
    load();
}

async function purgeGhosts() {
    if (!confirm('Purge ghost users with 0 hours?')) return;
    try {
        const r = await fetch('/admin/users/clean-ghosts-real', { method: 'DELETE', headers: getHeaders() });
        if (r.ok) {
            const d = await r.json();
            alert(`Cleaned ${d.total_deleted} rows`);
            load();
        }
    } catch(e) { alert(e.message); }
}
"""