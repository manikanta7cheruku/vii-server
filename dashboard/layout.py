"""Main dashboard shell with responsive layout."""


def render_dashboard() -> str:
    from dashboard.styles import DASHBOARD_STYLES
    from dashboard.scripts import DASHBOARD_SCRIPTS

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
    <meta name="theme-color" content="#000000">
    <title>Seven Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf-autotable/3.8.2/jspdf.plugin.autotable.min.js"></script>
    <style>{DASHBOARD_STYLES}</style>
</head>
<body class="bg-black text-zinc-100 min-h-screen">

<div class="min-h-screen">

    <!-- Top Bar (Fixed on mobile) -->
    <div class="sticky top-0 z-40 bg-black/95 backdrop-blur-lg border-b border-zinc-900">
        <div class="max-w-7xl mx-auto px-4 py-3 sm:px-6 sm:py-4">
            <div class="flex items-center justify-between gap-3">
                <div class="flex items-center gap-2.5 min-w-0">
                    <div class="w-8 h-8 sm:w-9 sm:h-9 rounded-lg bg-white flex items-center justify-center flex-shrink-0">
                        <span class="font-mono text-[10px] sm:text-xs font-bold text-black tracking-wider">VII</span>
                    </div>
                    <div class="min-w-0">
                        <h1 class="text-xs sm:text-sm font-bold tracking-widest text-white uppercase truncate">Seven Admin</h1>
                        <p class="text-[9px] text-zinc-500 uppercase tracking-wide hidden sm:block">Control Center</p>
                    </div>
                </div>
                <div class="flex items-center gap-2">
                    <input type="password" id="admin-token" placeholder="Admin token"
                        class="bg-zinc-900 border border-zinc-800 text-[11px] px-3 py-2 rounded-lg outline-none focus:border-white/30 font-mono text-zinc-300 w-32 sm:w-48 transition-colors"/>
                    <button onclick="load()" class="px-3 py-2 sm:px-4 bg-white text-black text-[10px] sm:text-xs font-semibold rounded-lg hover:bg-zinc-200 transition-colors uppercase tracking-wider whitespace-nowrap">
                        Sync
                    </button>
                </div>
            </div>
        </div>
    </div>

    <div class="max-w-7xl mx-auto px-4 py-4 sm:px-6 sm:py-6 space-y-4 sm:space-y-6">

        <!-- Auth Status Banner -->
        <div id="auth-status"></div>

        <!-- Live Metrics -->
        <div id="stats" class="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 sm:p-5 h-20 animate-pulse"></div>
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 sm:p-5 h-20 animate-pulse"></div>
            <div class="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 sm:p-5 h-20 animate-pulse"></div>
        </div>

        <!-- Pending Rewards -->
        <div id="pending"></div>

        <!-- Tab Navigation (Scroll horizontally on mobile) -->
        <div class="overflow-x-auto scrollbar-hide -mx-4 sm:mx-0 px-4 sm:px-0">
            <div class="flex gap-1.5 sm:gap-2 min-w-max sm:min-w-0 pb-2">
                <button onclick="showTab('users')" id="tab-users" class="tab-btn active">Users</button>
                <button onclick="showTab('licenses')" id="tab-licenses" class="tab-btn">Licenses</button>
                <button onclick="showTab('referrals')" id="tab-referrals" class="tab-btn">Referrals</button>
                <button onclick="showTab('transactions')" id="tab-transactions" class="tab-btn">Sales</button>
                <button onclick="showTab('updates')" id="tab-updates" class="tab-btn">Deploy</button>
                <button onclick="showTab('messages')" id="tab-messages" class="tab-btn">Messages</button>
            </div>
        </div>

        <!-- Export Button -->
        <div class="flex justify-end">
            <button onclick="exportCurrentTab()" class="px-3 py-1.5 border border-zinc-800 text-[10px] text-zinc-400 hover:text-white rounded-lg font-semibold uppercase tracking-wider transition-colors flex items-center gap-1.5">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                Export PDF / CSV / Word
            </button>
        </div>

        <!-- Content Panel -->
        <div id="content" class="bg-zinc-900/30 border border-zinc-800 rounded-xl sm:rounded-2xl p-4 sm:p-6 overflow-x-auto min-h-[300px]">
            <div class="py-12 text-center">
                <p class="text-xs text-zinc-500">Enter your admin token above and click Sync to load data.</p>
            </div>
        </div>

    </div>
</div>

<script>{DASHBOARD_SCRIPTS}</script>
</body>
</html>"""