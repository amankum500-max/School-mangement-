<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}School ERP{% endblock %}</title>

  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">

  <!-- ✅ Apply saved theme BEFORE paint (prevents dark-mode flash) -->
  <script>
    (function () {
      try {
        var saved = localStorage.getItem('theme');
        if (saved === 'dark' ||
           (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
          document.documentElement.classList.add('dark');
        }
      } catch (e) {}
    })();
  </script>

  <style>
    /* ====================================================
       MASTER DESIGN SYSTEM — cleaned & fixed
    ==================================================== */
    :root {
      --primary: #6366f1;
      --primary-grad: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      --bg: #f8fafc;
      --card: #ffffff;
      --text: #0f172a;
      --border: #e2e8f0;
      --sidebar-bg: #0a0e1a;
      --sidebar-hover: #1e293b;
      --danger: #ef4444;
      --danger-hover: #f87171;
    }

    /* ✅ Dark mode via html element → no flash, no FOUC */
    html.dark {
      --bg: #0f172a;
      --card: #1e293b;
      --text: #f1f5f9;
      --border: #334155;
      color-scheme: dark;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    html, body { height: 100%; }

    body {
      font-family: 'Inter', sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      min-height: 100vh;
      transition: background .3s, color .3s;
      -webkit-font-smoothing: antialiased;
    }

    a { color: inherit; }
    button { font-family: inherit; }

    /* ---------- SIDEBAR ---------- */
    .sidebar {
      width: 280px;
      background: var(--sidebar-bg);
      color: #fff;
      display: flex;
      flex-direction: column;
      position: fixed;
      inset: 0 auto 0 0;
      z-index: 100;
      overflow-y: auto;
      transition: transform .3s ease;
    }

    .sidebar::-webkit-scrollbar { width: 6px; }
    .sidebar::-webkit-scrollbar-thumb {
      background: rgba(255,255,255,.15);
      border-radius: 3px;
    }

    .sidebar-logo {
      padding: 25px 20px;
      font-size: 22px;
      font-weight: 800;
      border-bottom: 1px solid rgba(255,255,255,.1);
      display: flex;
      align-items: center;
      gap: 10px;
      letter-spacing: -0.3px;
    }

    .sidebar-nav {
      padding: 20px 15px;
      flex: 1;
      display: flex;
      flex-direction: column;
    }

    .sidebar-link {
      display: flex;
      align-items: center;
      gap: 15px;
      padding: 16px 18px;
      border-radius: 12px;
      color: #94a3b8;
      text-decoration: none;
      font-size: 16px;
      font-weight: 700;
      transition: background .2s, color .2s, transform .2s;
      margin-bottom: 6px;
    }

    .sidebar-link:hover {
      background: var(--sidebar-hover);
      color: #fff;
      transform: translateX(5px);
    }

    .sidebar-link.active {
      background: var(--primary-grad);
      color: #fff;
      box-shadow: 0 6px 16px rgba(99,102,241,.35);
    }

    .sidebar-link .ico { font-size: 22px; width: 24px; text-align: center; }

    .sidebar-divider {
      height: 1px;
      background: rgba(255,255,255,.1);
      margin: 20px 15px 12px;
    }

    .logout-link { color: var(--danger); margin-top: auto; }
    .logout-link:hover {
      background: rgba(239,68,68,.12);
      color: var(--danger-hover);
      transform: translateX(5px);
    }

    /* ---------- MAIN CONTENT ---------- */
    .main-content {
      flex: 1;
      margin-left: 280px;
      display: flex;
      flex-direction: column;
      min-height: 100vh;
      min-width: 0; /* prevents flex overflow */
    }

    /* ---------- TOPBAR ---------- */
    .topbar {
      height: 85px;
      background: var(--card);
      border-bottom: 1px solid var(--border);
      padding: 0 30px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      position: sticky;
      top: 0;
      z-index: 90;
      transition: background .3s, border-color .3s;
    }

    .topbar-left { display: flex; align-items: center; gap: 15px; min-width: 0; }

    .topbar h2 {
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.5px;
      color: var(--text);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .topbar-actions { display: flex; align-items: center; gap: 15px; }

    .topbar-btn {
      width: 48px;
      height: 48px;
      border-radius: 12px;
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text);
      cursor: pointer;
      font-size: 20px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: background .2s, transform .15s;
      text-decoration: none;
      flex-shrink: 0;
    }

    .topbar-btn:hover { background: var(--border); }
    .topbar-btn:active { transform: scale(.95); }
    .topbar-btn:focus-visible {
      outline: 2px solid var(--primary);
      outline-offset: 2px;
    }

    .topbar-user {
      padding: 6px 16px 6px 6px;
      border-radius: 24px;
      background: var(--bg);
      border: 1px solid var(--border);
      font-size: 15px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 10px;
      max-width: 240px;
    }

    .topbar-user span {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .topbar-user .avatar {
      width: 38px;
      height: 38px;
      border-radius: 50%;
      background: var(--primary-grad);
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 15px;
      font-weight: 800;
      flex-shrink: 0;
    }

    /* ---------- PAGE CONTENT ---------- */
    .page-content {
      padding: 30px;
      max-width: 1500px;
      margin: 0 auto;
      width: 100%;
    }

    /* ---------- FLASH MESSAGES ---------- */
    .flash {
      padding: 14px 18px;
      margin-bottom: 16px;
      border-radius: 10px;
      font-weight: 600;
      font-size: 15px;
      border-left: 4px solid;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .flash-error, .flash-danger { background: #fee2e2; color: #991b1b; border-color: #ef4444; }
    .flash-success            { background: #dcfce7; color: #166534; border-color: #22c55e; }
    .flash-warning            { background: #fef3c7; color: #92400e; border-color: #f59e0b; }
    .flash-info, .flash-message { background: #dbeafe; color: #1e40af; border-color: #3b82f6; }

    html.dark .flash-error, html.dark .flash-danger { background: #451a1a; color: #fecaca; }
    html.dark .flash-success { background: #052e16; color: #bbf7d0; }
    html.dark .flash-warning { background: #451a03; color: #fde68a; }
    html.dark .flash-info, html.dark .flash-message { background: #172554; color: #bfdbfe; }

    /* ---------- MOBILE OVERLAY ---------- */
    .overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,.55);
      z-index: 99;
      opacity: 0;
      transition: opacity .3s;
    }
    .overlay.active { display: block; opacity: 1; }

    /* ---------- MENU BUTTON (hidden by default) ---------- */
    #menuBtn { display: none; }

    /* ---------- RESPONSIVE ---------- */
    @media (max-width: 900px) {
      .sidebar { transform: translateX(-100%); }
      .sidebar.open { transform: translateX(0); }

      .main-content { margin-left: 0; }
      .page-content { padding: 15px; }

      .topbar { padding: 0 15px; height: 72px; }
      .topbar h2 { font-size: 18px; }

      #menuBtn { display: inline-flex; }

      .topbar-user span { display: none; }
      .topbar-user { padding: 6px; }

      .topbar-btn { width: 42px; height: 42px; font-size: 18px; }
      .topbar-user .avatar { width: 42px; height: 42px; }
    }
  </style>
</head>
<body>

  <!-- ✅ Mobile backdrop -->
  <div class="overlay" id="overlay" onclick="closeSidebar()"></div>

  <!-- SIDEBAR -->
  <aside class="sidebar" id="sidebar" aria-label="Main navigation">
    <div class="sidebar-logo">🏫 School ERP</div>
    <nav class="sidebar-nav">
      {% set current_path = request.path if request is defined else '' %}
      <a href="/dashboard"     class="sidebar-link {% if current_path.startswith('/dashboard') %}active{% endif %}">
        <span class="ico">📊</span> Dashboard
      </a>
      <a href="/students"      class="sidebar-link {% if current_path.startswith('/students') %}active{% endif %}">
        <span class="ico">🎓</span> Students
      </a>
      <a href="/fees"          class="sidebar-link {% if current_path.startswith('/fees') %}active{% endif %}">
        <span class="ico">💵</span> Fees
      </a>
      <a href="/attendance"    class="sidebar-link {% if current_path.startswith('/attendance') %}active{% endif %}">
        <span class="ico">📅</span> Attendance
      </a>
      <a href="/staff"         class="sidebar-link {% if current_path.startswith('/staff') %}active{% endif %}">
        <span class="ico">👨‍🏫</span> Staff
      </a>
      <a href="/notices"       class="sidebar-link {% if current_path.startswith('/notices') %}active{% endif %}">
        <span class="ico">📢</span> Notices
      </a>
      <a href="/ai-assistant"  class="sidebar-link {% if current_path.startswith('/ai-assistant') %}active{% endif %}">
        <span class="ico">🤖</span> AI Assistant
      </a>

      <div class="sidebar-divider"></div>
      <a href="/logout" class="sidebar-link logout-link">
        <span class="ico">🚪</span> Logout
      </a>
    </nav>
  </aside>

  <!-- MAIN CONTENT -->
  <main class="main-content">
    <header class="topbar">
      <div class="topbar-left">
        <button class="topbar-btn" id="menuBtn"
                aria-label="Toggle sidebar"
                onclick="toggleSidebar()">☰</button>
        <h2>{% block page_title %}Dashboard{% endblock %}</h2>
      </div>

      <div class="topbar-actions">
        <button class="topbar-btn" id="themeBtn"
                aria-label="Toggle dark mode"
                onclick="toggleTheme()">🌙</button>
        <div class="topbar-user" title="{{ session.name or 'Admin' if session is defined else 'Admin' }}">
          <span>{{ session.name or 'Admin' if session is defined else 'Admin' }}</span>
          <div class="avatar">
            {{ ((session.name or 'A') if session is defined else 'A')[0]|upper }}
          </div>
        </div>
      </div>
    </header>

    <div class="page-content">
      {# ✅ Category-based flash messages #}
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for category, msg in messages %}
            <div class="flash flash-{{ category }}">{{ msg }}</div>
          {% endfor %}
        {% endif %}
      {% endwith %}

      {% block content %}{% endblock %}
    </div>
  </main>

  <script>
    /* ---------- Sidebar (mobile) ---------- */
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');

    function openSidebar() {
      sidebar.classList.add('open');
      overlay.classList.add('active');
    }
    function closeSidebar() {
      sidebar.classList.remove('open');
      overlay.classList.remove('active');
    }
    function toggleSidebar() {
      sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
    }

    /* ✅ Auto-close sidebar on link click (mobile) */
    document.querySelectorAll('.sidebar-link').forEach(function (link) {
      link.addEventListener('click', function () {
        if (window.innerWidth <= 900) closeSidebar();
      });
    });

    /* ---------- Dark mode ---------- */
    const themeBtn = document.getElementById('themeBtn');

    function applyThemeIcon() {
      const isDark = document.documentElement.classList.contains('dark');
      themeBtn.textContent = isDark ? '☀️' : '🌙';
      themeBtn.setAttribute('aria-pressed', isDark);
    }

    function toggleTheme() {
      const isDark = document.documentElement.classList.toggle('dark');
      try { localStorage.setItem('theme', isDark ? 'dark' : 'light'); } catch (e) {}
      applyThemeIcon();
    }

    applyThemeIcon(); // set icon on load

    /* ---------- Close sidebar on Escape ---------- */
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeSidebar();
    });
  </script>
</body>
</html>
