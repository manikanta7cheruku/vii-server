"""CSS styles for admin dashboard."""

DASHBOARD_STYLES = """
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@300;400;500;600;700&display=swap');

    * { -webkit-tap-highlight-color: transparent; }
    body { font-family: 'Inter', sans-serif; -webkit-font-smoothing: antialiased; }
    .mono { font-family: 'JetBrains Mono', monospace; }

    /* Custom scrollbar */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0a0a0a; }
    ::-webkit-scrollbar-thumb { background: #27272a; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #3f3f46; }

    /* Hide scrollbar on tab strip */
    .scrollbar-hide::-webkit-scrollbar { display: none; }
    .scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }

    /* Tab buttons */
    .tab-btn {
        padding: 0.625rem 1rem;
        border-radius: 0.5rem;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        transition: all 0.15s;
        background: rgb(24 24 27);
        border: 1px solid rgb(39 39 42);
        color: rgb(161 161 170);
        white-space: nowrap;
    }
    .tab-btn:hover {
        background: rgb(39 39 42);
        color: white;
    }
    .tab-btn.active {
        background: white;
        color: black;
        border-color: white;
    }

    /* Responsive table wrapper */
    .table-wrap {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }

    /* Mobile-friendly cards for user list */
    @media (max-width: 640px) {
        .desktop-table { display: none; }
        .mobile-cards { display: block; }
    }
    @media (min-width: 641px) {
        .desktop-table { display: table; }
        .mobile-cards { display: none; }
    }

    /* Smooth fade-in */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(4px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .fade-in { animation: fadeIn 0.3s ease-out; }

    /* Form inputs — mobile friendly */
    input, select, textarea {
        font-size: 16px;  /* Prevents iOS zoom */
    }
    @media (min-width: 640px) {
        input, select, textarea { font-size: 12px; }
    }

    /* Touch-friendly buttons on mobile */
    button {
        min-height: 40px;
    }
    @media (min-width: 640px) {
        button { min-height: auto; }
    }
"""