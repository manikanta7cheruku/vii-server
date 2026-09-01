DASHBOARD_SCRIPTS = """
let currentTab = 'users';
let isAuthenticated = false;
let allUsers = [];
let allRefs = [];
let userFilter = 'all';
let userSearch = '';

function getHeaders() {
    const token = document.getElementById('admin-token').value.trim();
    return { 'Content-Type': 'application/json', 'X-Admin-Token': token };
}

function showAuthError() {
    isAuthenticated = false;
    document.getElementById('auth-status').innerHTML = `
        <div class="bg-red-500/10 border border-red-500/20 rounded-xl p-4 fade-in">
            <p class="text-xs font-semibold text-red-400 mb-1">Authentication Required</p>
            <p class="text-[11px] text-red-300/70">Enter your admin token and click Sync.</p>
        </div>`;
    document.getElementById('stats').innerHTML = '';
    document.getElementById('content').innerHTML = '<div class="py-12 text-center"><p class="text-xs text-zinc-500">Awaiting authentication...</p></div>';
}

async function load() {
    const token = document.getElementById('admin-token').value.trim();
    if (!token) { showAuthError(); return; }
    try {
        const r = await fetch('/admin/stats', { headers: getHeaders() });
        if (r.status === 401) { showAuthError(); return; }
        const stats = await r.json();
        isAuthenticated = true;
        document.getElementById('auth-status').innerHTML = '';
        document.getElementById('stats').innerHTML = `
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 sm:p-5 fade-in">
                <p class="text-[9px] text-zinc-500 tracking-widest font-semibold uppercase mb-1">Total Users</p>
                <p class="text-2xl sm:text-3xl mono font-bold text-white">${stats.total_users}</p>
            </div>
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 sm:p-5 fade-in">
                <p class="text-[9px] text-zinc-500 tracking-widest font-semibold uppercase mb-1">Active 7D</p>
                <p class="text-2xl sm:text-3xl mono font-bold text-green-400">${stats.active_7d}</p>
            </div>
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 sm:p-5 fade-in">
                <p class="text-[9px] text-zinc-500 tracking-widest font-semibold uppercase mb-1">Runtime</p>
                <p class="text-2xl sm:text-3xl mono font-bold text-indigo-400">${stats.total_time}</p>
            </div>`;
        const pending = await fetch('/admin/rewards/pending', { headers: getHeaders() }).then(r => r.json());
        if (pending.length > 0) {
            let html = `<div class="bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-4 space-y-3 fade-in">
                <p class="text-xs font-bold text-emerald-400 uppercase tracking-wider">${pending.length} Reward${pending.length > 1 ? 's' : ''} Ready</p>`;
            pending.forEach(p => {
                html += `<div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 flex flex-col sm:flex-row sm:items-center gap-2">
                    <div class="flex-1 min-w-0">
                        <p class="text-[11px] text-zinc-300 truncate">R: <span class="mono text-indigo-400">${p.referrer}</span> → <span class="mono text-green-400">${p.referred}</span></p>
                    </div>
                    <div class="flex gap-2">
                        <button onclick="dispatchReward('${p.referred}','${p.referrer}','${p.code}')" class="px-3 py-1.5 bg-emerald-500 text-black text-[10px] font-bold rounded-lg">Dispatch</button>
                        <button onclick="markSent('${p.code}')" class="px-3 py-1.5 border border-zinc-800 text-zinc-400 text-[10px] rounded-lg">Mark Sent</button>
                    </div>
                </div>`;
            });
            document.getElementById('pending').innerHTML = html + '</div>';
        } else {
            document.getElementById('pending').innerHTML = '';
        }
        showTab(currentTab);
    } catch (e) { showAuthError(); }
}

function setTabStyles(active) {
    ['users','licenses','referrals','transactions','updates','messages'].forEach(t => {
        const btn = document.getElementById('tab-' + t);
        btn.classList.toggle('active', t === active);
    });
}

async function showTab(tab) {
    currentTab = tab;
    setTabStyles(tab);
    if (!isAuthenticated) return;
    const content = document.getElementById('content');
    content.innerHTML = '<div class="py-8 text-center"><span class="text-xs text-zinc-500 animate-pulse">Loading...</span></div>';
    try {
        if (tab === 'users') {
            allUsers = await fetch('/admin/users', { headers: getHeaders() }).then(r => r.json());
            renderUsers();
        } else if (tab === 'licenses') {
            renderLicenses(await fetch('/admin/licenses', { headers: getHeaders() }).then(r => r.json()));
        } else if (tab === 'referrals') {
            allRefs = await fetch('/admin/referrals', { headers: getHeaders() }).then(r => r.json());
            renderReferrals();
        } else if (tab === 'transactions') {
            renderTransactions(await fetch('/admin/transactions', { headers: getHeaders() }).then(r => r.json()));
        } else if (tab === 'updates') {
            renderUpdates(await fetch('/admin/updates/all', { headers: getHeaders() }).then(r => r.json()));
        } else if (tab === 'messages') {
            renderMessages();
        }
    } catch(e) { content.innerHTML = '<p class="text-xs text-red-400 text-center py-8">Failed to load.</p>'; }
}

function tierBadge(tier) {
    const s = { ultimate: 'bg-indigo-500/10 text-indigo-300 border-indigo-500/20', pro: 'bg-blue-500/10 text-blue-300 border-blue-500/20', free: 'bg-zinc-800 text-zinc-500 border-zinc-800' };
    return `<span class="text-[9px] px-2 py-0.5 rounded mono font-bold tracking-wider border ${s[tier]||s.free}">${tier.toUpperCase()}</span>`;
}

function daysAgoLabel(days) {
    if (days === null || days === undefined) return '';
    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return days + 'd ago';
    if (days < 30) return Math.floor(days/7) + 'w ago';
    return Math.floor(days/30) + 'mo ago';
}

function renderUsers() {
    const content = document.getElementById('content');
    let filtered = allUsers;

    // Apply tier filter
    if (userFilter !== 'all') {
        if (userFilter === 'today') filtered = filtered.filter(u => u.days_joined === 0);
        else if (userFilter === 'week') filtered = filtered.filter(u => u.days_joined !== null && u.days_joined <= 7);
        else if (userFilter === 'month') filtered = filtered.filter(u => u.days_joined !== null && u.days_joined <= 30);
        else if (userFilter === 'active') filtered = filtered.filter(u => u.today_mins > 0);
        else filtered = filtered.filter(u => u.tier === userFilter);
    }

    // Apply search
    if (userSearch) {
        const q = userSearch.toLowerCase();
        filtered = filtered.filter(u => u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q) || u.device_id.toLowerCase().includes(q));
    }

    let html = `
        <div class="flex flex-col sm:flex-row sm:justify-between sm:items-center mb-4 gap-3">
            <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase">Users (${filtered.length} of ${allUsers.length})</p>
            <div class="flex flex-wrap gap-2">
                <input type="text" id="user-search" placeholder="Search name, email..." value="${userSearch}"
                    oninput="userSearch=this.value;renderUsers()"
                    class="bg-zinc-950 border border-zinc-800 text-xs px-3 py-1.5 rounded-lg outline-none focus:border-white/30 w-40 sm:w-52"/>
                <select id="user-filter" onchange="userFilter=this.value;renderUsers()"
                    class="bg-zinc-950 border border-zinc-800 text-xs px-2 py-1.5 rounded-lg outline-none focus:border-white/30">
                    <option value="all" ${userFilter==='all'?'selected':''}>All Users</option>
                    <option value="today" ${userFilter==='today'?'selected':''}>Joined Today</option>
                    <option value="week" ${userFilter==='week'?'selected':''}>This Week</option>
                    <option value="month" ${userFilter==='month'?'selected':''}>This Month</option>
                    <option value="active" ${userFilter==='active'?'selected':''}>Active Today</option>
                    <option value="pro" ${userFilter==='pro'?'selected':''}>Pro Tier</option>
                    <option value="ultimate" ${userFilter==='ultimate'?'selected':''}>Ultimate Tier</option>
                    <option value="free" ${userFilter==='free'?'selected':''}>Free Tier</option>
                </select>
                <button onclick="purgeGhosts()" class="px-2 py-1.5 border border-zinc-800 text-[10px] text-zinc-400 hover:text-red-400 rounded-lg font-semibold uppercase tracking-wider">Purge</button>
            </div>
        </div>

        <!-- History Modal -->
        <div id="history-modal" class="hidden fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4" onclick="if(event.target===this)closeHistory()">
            <div class="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-lg p-5 space-y-4 max-h-[80vh] overflow-y-auto">
                <div class="flex items-center justify-between">
                    <h3 class="text-sm font-semibold text-white">Identity History</h3>
                    <button onclick="closeHistory()" class="text-zinc-500 hover:text-white text-lg">x</button>
                </div>
                <div id="history-content" class="space-y-2"></div>
            </div>
        </div>

        <!-- Desktop Table -->
        <table class="desktop-table w-full text-xs text-left">
            <thead><tr class="text-[10px] text-zinc-500 tracking-widest border-b border-zinc-800">
                <th class="pb-3 uppercase">Name</th>
                <th class="pb-3 uppercase">Email</th>
                <th class="pb-3 uppercase">Usage</th>
                <th class="pb-3 uppercase">Today</th>
                <th class="pb-3 uppercase">Tier</th>
                <th class="pb-3 uppercase">Joined</th>
                <th class="pb-3 uppercase">Last Seen</th>
                <th class="pb-3 uppercase">Actions</th>
            </tr></thead><tbody class="divide-y divide-zinc-800/30">`;

    filtered.forEach(u => {
        html += `<tr class="hover:bg-zinc-800/10 fade-in">
            <td class="py-3 font-medium text-white">${u.name}</td>
            <td class="py-3 text-zinc-300 mono">${u.email}</td>
            <td class="py-3 mono text-indigo-400 font-bold">${u.total_time}</td>
            <td class="py-3 mono text-green-400 font-semibold">${u.today_display}</td>
            <td class="py-3">${tierBadge(u.tier)}</td>
            <td class="py-3 text-zinc-500">${daysAgoLabel(u.days_joined)}</td>
            <td class="py-3 text-zinc-500">${(u.last_seen||'').slice(0,16).replace('T',' ')||'—'}</td>
            <td class="py-3">
                <div class="flex gap-1">
                    ${u.change_count > 0 ? `<button onclick="showHistory('${u.device_id}')" class="text-[9px] px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20">${u.change_count} changes</button>` : ''}
                    <button onclick="deleteUser('${u.device_id}','${u.name}')" class="text-[9px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20">Delete</button>
                </div>
            </td>
        </tr>`;
    });
    html += '</tbody></table>';

    // Mobile Cards
    html += '<div class="mobile-cards space-y-3">';
    filtered.forEach(u => {
        html += `<div class="bg-zinc-950 border border-zinc-800 rounded-lg p-4 space-y-2 fade-in">
            <div class="flex justify-between items-start gap-2">
                <div class="min-w-0 flex-1">
                    <p class="text-sm font-medium text-white truncate">${u.name}</p>
                    <p class="text-[11px] text-zinc-400 mono truncate">${u.email}</p>
                </div>
                ${tierBadge(u.tier)}
            </div>
            <div class="grid grid-cols-3 gap-2 pt-2 border-t border-zinc-900">
                <div><p class="text-[9px] text-zinc-600 uppercase">Total</p><p class="text-xs mono text-indigo-400 font-bold">${u.total_time}</p></div>
                <div><p class="text-[9px] text-zinc-600 uppercase">Today</p><p class="text-xs mono text-green-400 font-bold">${u.today_display||'—'}</p></div>
                <div><p class="text-[9px] text-zinc-600 uppercase">Joined</p><p class="text-[11px] text-zinc-400">${daysAgoLabel(u.days_joined)}</p></div>
            </div>
            <div class="flex gap-2 pt-2">
                ${u.change_count > 0 ? `<button onclick="showHistory('${u.device_id}')" class="flex-1 text-[10px] py-1.5 rounded bg-yellow-500/10 text-yellow-400 font-semibold">${u.change_count} changes</button>` : ''}
                <button onclick="deleteUser('${u.device_id}','${u.name}')" class="flex-1 text-[10px] py-1.5 rounded bg-red-500/10 text-red-400 font-semibold">Delete</button>
            </div>
        </div>`;
    });
    html += '</div>';
    content.innerHTML = html;
}

function renderLicenses(licenses) {
    const content = document.getElementById('content');
    content.innerHTML = `
        <div class="space-y-6">
            <div class="space-y-4">
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase">Generate License</p>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="text-[9px] text-zinc-500 uppercase block mb-1">Email (leave empty for universal key)</label>
                        <input id="l-email" placeholder="user@example.com or leave blank" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30"/>
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
                    <label class="text-[9px] text-zinc-500 uppercase block mb-1">Custom Key Name (optional, e.g. LAUNCH-2025)</label>
                    <input id="l-custom" placeholder="LAUNCH-2025" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30 mono"/>
                </div>
                <button onclick="createLicense()" class="w-full sm:w-auto px-6 py-2.5 bg-white hover:bg-zinc-200 text-black text-xs font-bold rounded-lg uppercase tracking-wider">Generate Key</button>
            </div>
            <div>
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-3">Active Keys (${licenses.length})</p>
                <div class="space-y-2">
                    ${licenses.map(l => `
                        <div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 flex flex-col sm:flex-row sm:items-center gap-2">
                            <div class="flex-1 min-w-0">
                                <p class="text-xs mono text-white break-all">${l.key}</p>
                                <p class="text-[10px] text-zinc-500 mt-0.5 truncate">${l.email} • ${l.tier.toUpperCase()} • ${l.expires_at || 'Lifetime'}</p>
                            </div>
                            <div class="flex gap-2">
                                ${l.active
                                    ? `<button onclick="revokeLicense('${l.key}')" class="text-[10px] px-2 py-1 bg-red-500/10 text-red-400 rounded font-semibold">REVOKE</button>`
                                    : `<span class="text-[10px] text-zinc-600 uppercase font-semibold">REVOKED</span>`}
                                <button onclick="deleteLicense('${l.key}')" class="text-[10px] px-2 py-1 bg-zinc-800 text-zinc-400 hover:text-red-400 rounded font-semibold">DELETE</button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>`;
}

function renderReferrals() {
    const content = document.getElementById('content');
    if (!allRefs || allRefs.length === 0) {
        content.innerHTML = '<p class="text-xs text-zinc-500 text-center py-8">No referrals yet.</p>';
        return;
    }
    let html = `<p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-4">Referrals (${allRefs.length})</p><div class="space-y-2">`;
    allRefs.forEach(r => {
        const pct = Math.min(100, Math.round((r.hours / 7) * 100));
        const barColor = pct >= 100 ? 'bg-emerald-500' : 'bg-indigo-500';
        const status = r.complete ? (r.reward_sent ? 'DISPATCHED' : 'REWARD READY') : 'IN PROGRESS';
        const statusColor = r.complete ? (r.reward_sent ? 'text-zinc-500' : 'text-emerald-400') : 'text-zinc-500';
        html += `<div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 fade-in">
            <div class="flex flex-col sm:flex-row sm:justify-between gap-2 mb-2">
                <div class="min-w-0 flex-1">
                    <p class="text-[11px] text-zinc-400 truncate">R: <span class="mono text-white">${r.referrer}</span> → <span class="mono text-zinc-300">${r.referred}</span></p>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-[9px] ${statusColor} font-bold">${status}</span>
                    <button onclick="deleteReferral('${r.code}')" class="text-[9px] px-1.5 py-0.5 bg-red-500/10 text-red-400 rounded">Delete</button>
                </div>
            </div>
            <div class="flex items-center gap-2">
                <div class="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                    <div class="h-full ${barColor} rounded-full" style="width:${pct}%"></div>
                </div>
                <span class="text-[10px] mono text-zinc-400 font-semibold whitespace-nowrap">${r.hours}h/7h</span>
            </div>
        </div>`;
    });
    content.innerHTML = html + '</div>';
}

function renderTransactions(txs) {
    const content = document.getElementById('content');
    if (!txs || txs.length === 0) { content.innerHTML = '<p class="text-xs text-zinc-500 text-center py-8">No transactions.</p>'; return; }
    let html = `<p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-4">Sales (${txs.length})</p><div class="space-y-2">`;
    txs.forEach(t => {
        html += `<div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 flex flex-col sm:flex-row sm:justify-between gap-2 fade-in">
            <div class="min-w-0"><p class="text-xs mono text-white break-all">${t.email}</p><p class="text-[10px] text-zinc-500">${t.tier.toUpperCase()} • ${t.plan_type} • ${t.date}</p></div>
            <div class="text-right"><p class="text-sm mono text-emerald-400 font-bold">${t.amount}</p><p class="text-[10px] text-zinc-500 mono truncate">${t.license_key}</p></div>
        </div>`;
    });
    content.innerHTML = html + '</div>';
}

function renderUpdates(updates) {
    const content = document.getElementById('content');
    content.innerHTML = `
        <div class="space-y-6">
            <div class="space-y-4">
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase">Publish Build</p>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div><label class="text-[9px] text-zinc-500 uppercase block mb-1">Version</label><input id="u-version" placeholder="1.3.4" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30 mono"/></div>
                    <div><label class="text-[9px] text-zinc-500 uppercase block mb-1">Size (MB)</label><input id="u-size" type="number" placeholder="180" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30 mono"/></div>
                </div>
                <div><label class="text-[9px] text-zinc-500 uppercase block mb-1">Download URL</label><input id="u-url" placeholder="https://github.com/..." class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30"/></div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div><label class="text-[9px] text-zinc-500 uppercase block mb-1">Tier Lock</label>
                        <select id="u-tier" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30">
                            <option value="all">Everyone</option><option value="pro">Pro+</option><option value="ultimate">Ultimate</option>
                        </select>
                    </div>
                    <div class="flex items-end gap-3">
                        <label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" id="u-critical" class="accent-red-500 w-4 h-4"/><span class="text-xs text-zinc-400">Critical</span></label>
                        <label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" id="u-autodeliver" checked class="accent-indigo-500 w-4 h-4"/><span class="text-xs text-zinc-400">Auto Deliver</span></label>
                    </div>
                </div>
                <div><label class="text-[9px] text-zinc-500 uppercase block mb-1">Changelog (one per line)</label><textarea id="u-changelog" rows="3" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30 resize-none"></textarea></div>
                <button onclick="publishRelease()" class="w-full sm:w-auto px-6 py-2.5 bg-white hover:bg-zinc-200 text-black text-xs font-bold rounded-lg uppercase tracking-wider">Publish</button>
            </div>
            <div>
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-3">Build Log (${updates.length})</p>
                <div class="space-y-2">
                    ${updates.map(u => `<div class="bg-zinc-950 border border-zinc-800 rounded-lg p-3 flex flex-col sm:flex-row sm:items-center gap-2">
                        <div class="flex-1"><p class="text-xs mono text-indigo-400 font-bold">v${u.version}</p><p class="text-[10px] text-zinc-500">${u.target_tier.toUpperCase()} • ${u.published_at?u.published_at.slice(0,10):'—'}</p></div>
                        <div class="flex items-center gap-2">
                            ${u.is_active?'<span class="text-[9px] px-2 py-0.5 bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 rounded font-bold">DEPLOYED</span>':'<span class="text-[9px] text-zinc-600">ARCHIVED</span>'}
                            <button onclick="toggleDelivery('${u.version}',${!u.auto_deliver})" class="text-[9px] px-2 py-0.5 rounded font-bold ${u.auto_deliver?'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20':'bg-zinc-800 text-zinc-500'}">${u.auto_deliver?'ACTIVE':'MUTED'}</button>
                        </div>
                    </div>`).join('')}
                </div>
            </div>
        </div>`;
}

async function createLicense() {
    const email = document.getElementById('l-email').value.trim() || 'universal@seven.app';
    const tier = document.getElementById('l-tier').value;
    const plan_type = document.getElementById('l-plan').value;
    const custom_key = document.getElementById('l-custom').value.trim();
    try {
        const r = await fetch('/admin/license/create', { method: 'POST', headers: getHeaders(), body: JSON.stringify({ email, tier, plan_type, custom_key }) });
        if (r.ok) { const d = await r.json(); alert('Key: ' + d.license_key); load(); }
        else alert('Failed');
    } catch(e) { alert(e.message); }
}

async function revokeLicense(key) { if (!confirm('Revoke '+key+'?')) return; await fetch('/admin/licenses/'+key, { method: 'DELETE', headers: getHeaders() }); load(); }
async function deleteLicense(key) { if (!confirm('Permanently delete '+key+'?')) return; await fetch('/admin/licenses/'+key, { method: 'DELETE', headers: getHeaders() }); load(); }
async function publishRelease() {
    const v = document.getElementById('u-version').value.trim(), u = document.getElementById('u-url').value.trim();
    if (!v||!u) return alert('Version and URL required');
    await fetch('/admin/updates/publish', { method: 'POST', headers: getHeaders(), body: JSON.stringify({ version: v, download_url: u, size_mb: parseFloat(document.getElementById('u-size').value)||0, changelog: document.getElementById('u-changelog').value.split('\\n').filter(Boolean), target_tier: document.getElementById('u-tier').value, is_critical: document.getElementById('u-critical').checked, auto_deliver: document.getElementById('u-autodeliver').checked }) });
    load();
}
async function toggleDelivery(v,s) { await fetch('/admin/updates/toggle-deliver', { method: 'POST', headers: getHeaders(), body: JSON.stringify({version:v,auto_deliver:s}) }); load(); }
async function dispatchReward(re,ref,code) {
    await fetch('/admin/license/create', { method:'POST', headers:getHeaders(), body:JSON.stringify({email:re,tier:'pro',plan_type:'monthly'}) });
    await fetch('/admin/license/create', { method:'POST', headers:getHeaders(), body:JSON.stringify({email:ref,tier:'ultimate',plan_type:'monthly'}) });
    await fetch('/admin/rewards/sent/'+code, { method:'POST', headers:getHeaders() });
    alert('Dispatched'); load();
}
async function markSent(code) { await fetch('/admin/rewards/sent/'+code, { method:'POST', headers:getHeaders() }); load(); }
async function deleteReferral(code) { if (!confirm('Delete this referral?')) return; await fetch('/admin/referrals/'+code, { method:'DELETE', headers:getHeaders() }); load(); }
async function deleteUser(id,name) { if (!confirm('Permanently delete user "'+name+'"? This cannot be undone.')) return; await fetch('/admin/users/'+id, { method:'DELETE', headers:getHeaders() }); load(); }
async function purgeGhosts() { if (!confirm('Delete all users with 0 usage?')) return; const r = await fetch('/admin/users/clean-ghosts-real', { method:'DELETE', headers:getHeaders() }); if (r.ok) { const d = await r.json(); alert('Cleaned '+d.total_deleted+' rows'); load(); } }
async function showHistory(deviceId) {
    document.getElementById('history-modal').classList.remove('hidden');
    const c = document.getElementById('history-content');
    c.innerHTML = '<p class="text-xs text-zinc-500">Loading...</p>';
    try {
        const h = await fetch('/admin/users/'+encodeURIComponent(deviceId)+'/history', { headers: getHeaders() }).then(r=>r.json());
        if (!h||!h.length) { c.innerHTML = '<p class="text-xs text-zinc-500 text-center py-4">No changes recorded.</p>'; return; }
        c.innerHTML = h.map(x => `<div class="bg-zinc-800 rounded-lg p-3 space-y-1">
            <div class="flex justify-between"><span class="text-[10px] px-2 py-0.5 rounded font-medium ${x.field==='name'?'bg-indigo-500/20 text-indigo-300':'bg-green-500/20 text-green-300'}">${x.field.toUpperCase()}</span><span class="text-[10px] text-zinc-500 mono">${(x.changed_at||'').slice(0,16).replace('T',' ')}</span></div>
            <div class="flex items-center gap-2 text-xs"><span class="text-zinc-500 line-through">${x.old_value||'—'}</span><span class="text-zinc-600">→</span><span class="text-white font-medium">${x.new_value||'—'}</span></div>
        </div>`).join('');
    } catch(e) { c.innerHTML = '<p class="text-xs text-red-400">Failed.</p>'; }
}
function closeHistory() { document.getElementById('history-modal').classList.add('hidden'); }


// =============================================================================
// EXPORT FUNCTIONS (CSV, PDF, Word) — All client-side, no server cost
// =============================================================================

function exportCSV(data, filename) {
    if (!data || !data.length) return alert('No data to export');
    const headers = Object.keys(data[0]);
    const csvRows = [
        headers.join(','),
        ...data.map(row => headers.map(h => {
            let val = String(row[h] ?? '');
            if (val.includes(',') || val.includes('"') || val.includes('\\n')) {
                val = '"' + val.replace(/"/g, '""') + '"';
            }
            return val;
        }).join(','))
    ];
    const blob = new Blob([csvRows.join('\\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename + '.csv';
    a.click();
    URL.revokeObjectURL(url);
}

function exportPDF(data, title, filename) {
    if (!data || !data.length) return alert('No data to export');
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });

    // Title
    doc.setFontSize(16);
    doc.setTextColor(30, 30, 30);
    doc.text(title, 14, 15);

    // Date
    doc.setFontSize(9);
    doc.setTextColor(120, 120, 120);
    doc.text('Generated: ' + new Date().toLocaleString(), 14, 21);
    doc.text('Total records: ' + data.length, 14, 26);

    // Table
    const headers = Object.keys(data[0]);
    const rows = data.map(row => headers.map(h => String(row[h] ?? '').substring(0, 40)));

    doc.autoTable({
        head: [headers],
        body: rows,
        startY: 30,
        theme: 'grid',
        headStyles: {
            fillColor: [20, 20, 20],
            textColor: [255, 255, 255],
            fontSize: 7,
            fontStyle: 'bold',
            textTransform: 'uppercase'
        },
        bodyStyles: {
            fontSize: 6.5,
            textColor: [40, 40, 40]
        },
        alternateRowStyles: {
            fillColor: [245, 245, 245]
        },
        columnStyles: {
            0: { cellWidth: 35, fontStyle: 'bold' }
        },
        margin: { left: 14, right: 14 },
        didParseCell: function(data) {
            if (data.section === 'head') {
                data.cell.styles.textColor = [255, 255, 255];
            }
        }
    });

    // Footer
    const pageCount = doc.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
        doc.setPage(i);
        doc.setFontSize(8);
        doc.setTextColor(150, 150, 150);
        doc.text(
            'Seven Admin — Page ' + i + ' of ' + pageCount,
            14,
            doc.internal.pageSize.height - 10
        );
    }

    doc.save(filename + '.pdf');
}

function exportWord(data, title, filename) {
    if (!data || !data.length) return alert('No data to export');
    const headers = Object.keys(data[0]);

    let html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
    <head><meta charset="utf-8"><title>${title}</title>
    <style>
        body { font-family: Calibri, sans-serif; font-size: 11pt; color: #1a1a1a; }
        h1 { font-size: 18pt; color: #111; margin-bottom: 4px; }
        .meta { font-size: 9pt; color: #666; margin-bottom: 16px; }
        table { border-collapse: collapse; width: 100%; margin-top: 12px; }
        th { background: #1a1a1a; color: white; padding: 6px 8px; font-size: 9pt; text-transform: uppercase; text-align: left; border: 1px solid #333; }
        td { padding: 5px 8px; font-size: 9pt; border: 1px solid #ddd; }
        tr:nth-child(even) { background: #f5f5f5; }
    </style></head><body>
    <h1>${title}</h1>
    <p class="meta">Generated: ${new Date().toLocaleString()} | Records: ${data.length}</p>
    <table><thead><tr>${headers.map(h => '<th>' + h + '</th>').join('')}</tr></thead><tbody>`;

    data.forEach(row => {
        html += '<tr>' + headers.map(h => '<td>' + String(row[h] ?? '') + '</td>').join('') + '</tr>';
    });

    html += '</tbody></table></body></html>';

    const blob = new Blob(['\\ufeff', html], { type: 'application/msword' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename + '.doc';
    a.click();
    URL.revokeObjectURL(url);
}

function exportCurrentTab() {
    const tab = currentTab;
    const date = new Date().toISOString().slice(0, 10);
    let data = [];
    let title = '';

    if (tab === 'users') {
        data = allUsers.map(u => ({
            Name: u.name, Email: u.email, Device: u.device_short,
            Usage: u.total_time, Today: u.today_display,
            Tier: u.tier, Joined: u.days_joined !== null ? u.days_joined + ' days ago' : '—',
            'Last Seen': (u.last_seen || '').slice(0, 16).replace('T', ' ')
        }));
        title = 'Seven — User Directory';
    } else if (tab === 'licenses') {
        const rows = document.querySelectorAll('#content .bg-zinc-950');
        title = 'Seven — License Registry';
        data = [];
        rows.forEach(r => {
            const text = r.innerText.split('\\n').filter(Boolean);
            if (text.length >= 2) data.push({ Key: text[0], Details: text[1] });
        });
    } else if (tab === 'referrals') {
        data = allRefs.map(r => ({
            Code: r.code, Referrer: r.referrer, Referred: r.referred,
            Hours: r.hours + '/7', Status: r.complete ? (r.reward_sent ? 'Dispatched' : 'Ready') : 'In Progress'
        }));
        title = 'Seven — Referral Funnel';
    } else if (tab === 'transactions') {
        const rows = document.querySelectorAll('#content .bg-zinc-950');
        title = 'Seven — Sales Log';
        data = [];
        rows.forEach(r => {
            const text = r.innerText.split('\\n').filter(Boolean);
            if (text.length >= 2) data.push({ Customer: text[0], Details: text.slice(1).join(' | ') });
        });
    } else {
        return alert('Export is available for Users, Licenses, Referrals, and Sales tabs.');
    }

    if (!data.length) return alert('No data to export');

    // Show format picker
    const format = prompt('Export format:\\n1 = PDF (recommended)\\n2 = CSV\\n3 = Word (.doc)\\n\\nEnter 1, 2, or 3:', '1');
    if (format === '1') exportPDF(data, title, 'seven-' + tab + '-' + date);
    else if (format === '2') exportCSV(data, 'seven-' + tab + '-' + date);
    else if (format === '3') exportWord(data, title, 'seven-' + tab + '-' + date);
    else if (format) alert('Invalid choice');
}

// =============================================================================
// MESSAGES / PUSH NOTIFICATIONS (Free, server-stored, client-polled)
// =============================================================================

async function renderMessages() {
    const content = document.getElementById('content');
    content.innerHTML = `
        <div class="space-y-6">
            <div class="space-y-4">
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase">Send Message to All Users</p>
                <p class="text-[11px] text-zinc-400 leading-relaxed">
                    Messages are stored on the server. When users open Seven, their app checks for new messages
                    and displays a notification banner. This is completely free — no external service required.
                </p>
                <div class="space-y-3">
                    <div>
                        <label class="text-[9px] text-zinc-500 uppercase block mb-1">Title</label>
                        <input id="msg-title" placeholder="e.g., New Update Available" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30"/>
                    </div>
                    <div>
                        <label class="text-[9px] text-zinc-500 uppercase block mb-1">Message Body</label>
                        <textarea id="msg-body" rows="3" placeholder="e.g., Seven 1.4.0 is now available with faster voice recognition and new triggers." class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30 resize-none"></textarea>
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="text-[9px] text-zinc-500 uppercase block mb-1">Target Tier</label>
                            <select id="msg-tier" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30">
                                <option value="all">All Users</option>
                                <option value="free">Free Only</option>
                                <option value="pro">Pro + Ultimate</option>
                                <option value="ultimate">Ultimate Only</option>
                            </select>
                        </div>
                        <div>
                            <label class="text-[9px] text-zinc-500 uppercase block mb-1">Priority</label>
                            <select id="msg-priority" class="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 rounded-lg outline-none focus:border-white/30">
                                <option value="info">Info (blue banner)</option>
                                <option value="warning">Warning (yellow banner)</option>
                                <option value="critical">Critical (red banner)</option>
                            </select>
                        </div>
                    </div>
                    <button onclick="sendMessage()" class="w-full sm:w-auto px-6 py-2.5 bg-white hover:bg-zinc-200 text-black text-xs font-bold rounded-lg uppercase tracking-wider">Send to All Users</button>
                </div>
            </div>
            <div id="messages-list">
                <p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-3">Sent Messages</p>
                <p class="text-xs text-zinc-600">Loading...</p>
            </div>
        </div>`;

    // Load existing messages
    try {
        const msgs = await fetch('/admin/messages', { headers: getHeaders() }).then(r => r.json());
        const list = document.getElementById('messages-list');
        if (!msgs || !msgs.length) {
            list.innerHTML = '<p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-3">Sent Messages</p><p class="text-xs text-zinc-600">No messages sent yet.</p>';
            return;
        }
        let html = '<p class="text-[10px] text-zinc-500 tracking-widest font-semibold uppercase mb-3">Sent Messages (' + msgs.length + ')</p><div class="space-y-2">';
        msgs.forEach(m => {
            const priorityColor = m.priority === 'critical' ? 'border-red-500/30 bg-red-500/5' : m.priority === 'warning' ? 'border-yellow-500/30 bg-yellow-500/5' : 'border-zinc-800 bg-zinc-950';
            html += `<div class="border ${priorityColor} rounded-lg p-3">
                <div class="flex justify-between items-start gap-2 mb-1">
                    <p class="text-xs font-semibold text-white">${m.title}</p>
                    <span class="text-[9px] text-zinc-500 mono whitespace-nowrap">${(m.created_at||'').slice(0,16).replace('T',' ')}</span>
                </div>
                <p class="text-[11px] text-zinc-400">${m.body}</p>
                <div class="flex gap-2 mt-2">
                    <span class="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">${m.target_tier}</span>
                    <span class="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">${m.priority}</span>
                    <span class="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">${m.active ? 'Active' : 'Expired'}</span>
                </div>
            </div>`;
        });
        list.innerHTML = html + '</div>';
    } catch(e) {
        document.getElementById('messages-list').innerHTML = '<p class="text-xs text-zinc-600">Could not load messages.</p>';
    }
}

async function sendMessage() {
    const title = document.getElementById('msg-title').value.trim();
    const body = document.getElementById('msg-body').value.trim();
    const tier = document.getElementById('msg-tier').value;
    const priority = document.getElementById('msg-priority').value;
    if (!title || !body) return alert('Title and body are required');
    try {
        const r = await fetch('/admin/messages/send', {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ title, body, target_tier: tier, priority })
        });
        if (r.ok) { alert('Message sent'); renderMessages(); }
        else alert('Failed to send');
    } catch(e) { alert(e.message); }
}
"""