# -*- coding: utf-8 -*-

def build_dashboard(api_base: str = "") -> str:
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Boda Super-Dash V2</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Cairo', sans-serif; background-color: #010409; color: #c9d1d9; }}
        .bot-card {{ background-color: #0d1117; border: 1px solid #30363d; border-radius: 12px; transition: 0.2s; }}
        .bot-card:hover {{ border-color: #58a6ff; transform: translateY(-2px); }}
        .btn-action {{ transition: 0.2s; cursor: pointer; }}
        .btn-action:active {{ transform: scale(0.95); }}
        .nav-tab.active {{ border-bottom: 2px solid #58a6ff; color: #58a6ff; font-weight: bold; }}
    </style>
</head>
<body class="p-4 md:p-6">
    <div class="max-w-6xl mx-auto">
        <!-- Header -->
        <header class="flex flex-col md:flex-row justify-between items-center mb-6 gap-4 border-b border-gray-800 pb-4">
            <div>
                <h1 class="text-2xl font-bold text-white flex items-center gap-2">
                    <span class="text-blue-500">⚡</span> Boda Dashboard
                </h1>
            </div>
            <!-- Tabs -->
            <div class="flex gap-6">
                <button onclick="switchTab('bots')" id="tab-bots-btn" class="nav-tab active py-2 px-1 text-sm">🤖 إدارة البوتات</button>
                <button onclick="switchTab('analytics')" id="tab-analytics-btn" class="nav-tab py-2 px-1 text-sm text-gray-400">📊 التحليلات والنمو</button>
            </div>
        </header>

        <!-- BOTS TAB -->
        <div id="tab-bots">
            <!-- Stats -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div class="bot-card p-4 text-center"><div class="text-gray-500 text-xs">إجمالي البوتات</div><div id="s-total" class="text-xl font-bold">—</div></div>
                <div class="bot-card p-4 text-center"><div class="text-gray-500 text-xs">نشط الآن</div><div id="s-active" class="text-xl font-bold text-green-500">—</div></div>
                <div class="bot-card p-4 text-center"><div class="text-gray-500 text-xs">مستخدمين المنظومة</div><div id="s-users" class="text-xl font-bold text-blue-400">—</div></div>
                <div class="bot-card p-4 text-center"><div class="text-gray-500 text-xs">المستويات المفتوحة</div><div id="s-levels" class="text-xl font-bold text-purple-400">—</div></div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" id="grid">
                <div class="col-span-full text-center py-20 text-gray-500">⚡ جاري الفحص السريع...</div>
            </div>
        </div>

        <!-- ANALYTICS TAB -->
        <div id="tab-analytics" class="hidden">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                <div class="bot-card p-5">
                    <h3 class="text-lg font-bold text-white mb-4">📈 مؤشرات التفاعل اليومية</h3>
                    <div class="space-y-3" id="analytics-growth">
                        <div class="flex justify-between border-b border-gray-800 pb-2">
                            <span class="text-gray-400">المستخدمين النشطين (DAU):</span>
                            <span class="font-bold text-green-400" id="an-dau">—</span>
                        </div>
                        <div class="flex justify-between border-b border-gray-800 pb-2">
                            <span class="text-gray-400">المستخدمين الأسبوعيين (WAU):</span>
                            <span class="font-bold text-blue-400" id="an-wau">—</span>
                        </div>
                        <div class="flex justify-between border-b border-gray-800 pb-2">
                            <span class="text-gray-400">المستخدمين الشهريين (MAU):</span>
                            <span class="font-bold text-purple-400" id="an-mau">—</span>
                        </div>
                    </div>
                </div>

                <div class="bot-card p-5">
                    <h3 class="text-lg font-bold text-white mb-4">👑 الأكثر استخداماً هذا الأسبوع</h3>
                    <div class="space-y-2 text-sm" id="analytics-top-bots">
                        <div class="text-gray-500 text-center py-4">جاري تحليل البيانات...</div>
                    </div>
                </div>
            </div>
        </div>

    </div>

    <!-- Terminal Modal -->
    <div id="logs-modal" class="fixed inset-0 bg-black/90 hidden z-50 flex items-center justify-center p-4">
        <div class="bg-[#0d1117] border border-gray-700 rounded-xl w-full max-w-3xl overflow-hidden">
            <div class="p-4 border-b border-gray-800 flex justify-between items-center bg-[#161b22]">
                <h3 class="font-bold text-white">📜 السجلات: <span id="m-id" class="text-blue-400"></span></h3>
                <button onclick="closeLogs()" class="text-gray-400 hover:text-white">✕</button>
            </div>
            <div id="m-content" class="p-4 h-[350px] overflow-y-auto text-green-400 font-mono text-xs whitespace-pre-wrap"></div>
        </div>
    </div>

    <script>
        const API_V1 = "http://127.0.0.1:8080/api";
        const API_V2 = "http://127.0.0.1:8001/api/v2";

        function switchTab(tab) {{
            document.getElementById('tab-bots').classList.toggle('hidden', tab !== 'bots');
            document.getElementById('tab-analytics').classList.toggle('hidden', tab !== 'analytics');
            document.getElementById('tab-bots-btn').classList.toggle('active', tab === 'bots');
            document.getElementById('tab-analytics-btn').classList.toggle('active', tab === 'analytics');
            if(tab === 'analytics') loadAnalytics();
        }}

        async function loadData() {{
            try {{
                const [bots, stats] = await Promise.all([
                    fetch(`${{API_V2}}/bots?t=${{Date.now()}}`).then(r => r.json()),
                    fetch(`${{API_V1}}/stats?t=${{Date.now()}}`).then(r => r.json())
                ]);
                renderBots(bots);
                document.getElementById('s-total').innerText = bots.length;
                document.getElementById('s-active').innerText = bots.filter(b => b.running).length;
                document.getElementById('s-users').innerText = (stats.total_users || 0).toLocaleString();
                document.getElementById('s-levels').innerText = "مفعلة ✅";
            }} catch (e) {{
                document.getElementById('grid').innerHTML = `<div class="col-span-full text-center text-red-500 py-10">❌ السيرفر مغلق. يرجى تشغيل run_boda.bat</div>`;
            }}
        }}

        async function loadAnalytics() {{
            try {{
                const data = await fetch(`${{API_V1}}/overview?t=${{Date.now()}}`).then(r => r.json());
                if(data.users) {{
                    document.getElementById('an-dau').innerText = data.users.dau || 0;
                    document.getElementById('an-wau').innerText = data.users.wau || 0;
                    document.getElementById('an-mau').innerText = data.users.mau || 0;
                }}
                if(data.top_bots) {{
                    document.getElementById('analytics-top-bots').innerHTML = data.top_bots.map(b => `
                        <div class="flex justify-between items-center bg-black/20 p-2 rounded">
                            <span>🤖 ${{b.bot_name}}</span>
                            <span class="font-bold text-blue-400">${{b.users}} مستخدم</span>
                        </div>
                    `).join('');
                }}
            }} catch(e) {{
                console.error(e);
            }}
        }}

        function renderBots(bots) {{
            const grid = document.getElementById('grid');
            grid.innerHTML = bots.map(bot => `
                <div class="bot-card p-4 flex flex-col justify-between">
                    <div>
                        <div class="flex justify-between items-start mb-2">
                            <span class="font-bold text-white">${{bot.name}}</span>
                            <span class="w-3 h-3 rounded-full ${{bot.running ? 'bg-green-500 shadow-[0_0_8px_#22c55e]' : 'bg-red-500'}}"></span>
                        </div>
                        <p class="text-gray-500 text-xs font-mono mb-3">${{bot.id}}</p>
                    </div>
                    <div class="flex gap-2">
                        ${{bot.running 
                            ? `<button onclick="action('${{bot.id}}','stop')" class="flex-1 bg-red-900/30 text-red-400 py-2 rounded-lg text-xs font-bold btn-action">⏹ إيقاف</button>`
                            : `<button onclick="action('${{bot.id}}','start')" class="flex-1 bg-green-900/30 text-green-400 py-2 rounded-lg text-xs font-bold btn-action">▶ تشغيل</button>`
                        }}
                        <button onclick="viewLogs('${{bot.id}}')" class="bg-gray-800 text-white px-3 py-2 rounded-lg text-xs btn-action">📜</button>
                        <button onclick="action('${{bot.id}}','restart')" class="bg-gray-800 text-white px-3 py-2 rounded-lg text-xs btn-action">🔄</button>
                    </div>
                </div>
            `).join('');
        }}

        async function action(id, act) {{
            try {{
                await fetch(`${{API_V2}}/bots/${{id}}/action?action=${{act}}&t=${{Date.now()}}`, {{ method: 'POST' }});
                loadData();
            }} catch(e) {{ alert("فشل تنفيذ الإجراء"); }}
        }}

        async function viewLogs(id) {{
            document.getElementById('m-id').innerText = id;
            document.getElementById('logs-modal').classList.remove('hidden');
            const box = document.getElementById('m-content');
            box.innerText = "جاري التجميع...";
            const res = await fetch(`${{API_V2}}/bots/${{id}}/logs?limit=50&t=${{Date.now()}}`);
            const data = await res.json();
            box.innerText = data.logs.map(l => `[${{new Date(l.ts*1000).toLocaleTimeString()}}] ${{l.line}}`).join('\\n') || "لا توجد سجلات.";
            box.scrollTop = box.scrollHeight;
        }}

        function closeLogs() {{ document.getElementById('logs-modal').classList.add('hidden'); }}

        setInterval(loadData, 3000); // تحديث سريع جداً وسلس
        window.onload = loadData;
    </script>
</body>
</html>"""
