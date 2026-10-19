
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <title>{% block title %}School ERP{% endblock %}</title>
  <meta name="theme-color" content="#6366f1">

  <!-- Professional font -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">

  <!-- Apply theme before page loads -->
  <script>
    (function () {
      try {
        const savedTheme = localStorage.getItem("school-erp-theme");
        const systemDark = window.matchMedia(
          "(prefers-color-scheme: dark)"
        ).matches;

        if (savedTheme === "dark" ||
            (!savedTheme && systemDark)) {
          document.documentElement.classList.add("dark");
        }
      } catch (error) {
        // Theme storage may be unavailable.
      }
    })();
  </script>

  <style>
    /* ==============================
       1. DESIGN VARIABLES
    ============================== */
    :root {
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --primary-gradient: linear-gradient(135deg, #6366f1, #8b5cf6);

      --page-bg: #f5f7fb;
      --card-bg: #ffffff;
      --text-color: #172033;
      --muted-color: #64748b;
      --border-color: #e5e7eb;

      --sidebar-bg: #111827;
      --sidebar-text: #cbd5e1;
      --sidebar-hover: #1f2937;

      --danger: #dc2626;
      --success: #15803d;

      --sidebar-width: 260px;
      --topbar-height: 76px;

      color-scheme: light;
    }

    html.dark {
      --page-bg: #0b1120;
      --card-bg: #172033;
      --text-color: #e5e7eb;
      --muted-color: #94a3b8;
      --border-color: #293449;

      --sidebar-bg: #080d18;
      --sidebar-text: #cbd5e1;
      --sidebar-hover: #1e293b;

      color-scheme: dark;
    }

    /* ==============================
       2. GLOBAL
    ============================== */
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    html {
      min-height: 100%;
      scroll-behavior: smooth;
    }

    body {
      min-height: 100vh;
      font-family: "Inter", Arial, sans-serif;
      background: var(--page-bg);
      color: var(--text-color);
      -webkit-font-smoothing: antialiased;
      transition: background .2s, color .2s;
    }

    button,
    input,
    select,
    textarea {
      font: inherit;
    }

    button {
      cursor: pointer;
    }

    a {
      color: inherit;
    }

    svg {
      width: 21px;
      height: 21px;
      flex-shrink: 0;
      stroke: currentColor;
      fill: none;
      stroke-width: 1.8;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    /* ==============================
       3. ICON LIBRARY
       Inline SVG — no emoji dependency
    ============================== */
    .icon-library {
      position: absolute;
      width: 0;
      height: 0;
      overflow: hidden;
    }

    .nav-icon {
      width: 22px;
      height: 22px;
    }

    /* ==============================
       4. SIDEBAR
    ============================== */
    .sidebar {
      position: fixed;
      inset: 0 auto 0 0;
      width: var(--sidebar-width);
      z-index: 100;

      display: flex;
      flex-direction: column;

      background: var(--sidebar-bg);
      color: white;

      overflow-y: auto;
      overscroll-behavior: contain;

      transition: transform .25s ease;
    }

    .sidebar-logo {
      min-height: var(--topbar-height);
      padding: 0 22px;

      display: flex;
      align-items: center;
      gap: 12px;

      border-bottom: 1px solid rgba(255,255,255,.09);
    }

    .logo-mark {
      width: 42px;
      height: 42px;
      border-radius: 12px;

      display: flex;
      align-items: center;
      justify-content: center;

      background: var(--primary-gradient);
      color: white;
    }

    .logo-mark svg {
      width: 25px;
      height: 25px;
    }

    .logo-text {
      font-size: 19px;
      font-weight: 800;
      letter-spacing: -.5px;
    }

    .logo-subtitle {
      margin-top: 3px;
      color: #94a3b8;
      font-size: 11px;
      font-weight: 500;
    }

    .sidebar-nav {
      flex: 1;
      padding: 22px 14px;

      display: flex;
      flex-direction: column;
    }

    .nav-label {
      padding: 0 12px;
      margin-bottom: 12px;

      color: #64748b;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.2px;
      text-transform: uppercase;
    }

    .sidebar-link {
      display: flex;
      align-items: center;
      gap: 13px;

      padding: 13px 15px;
      margin-bottom: 5px;

      border-radius: 10px;
      text-decoration: none;

      color: var(--sidebar-text);
      font-size: 14px;
      font-weight: 600;

      transition: background .2s, color .2s;
    }

    .sidebar-link:hover {
      background: var(--sidebar-hover);
      color: #ffffff;
    }

    .sidebar-link.active {
      background: var(--primary-gradient);
      color: #ffffff;
      box-shadow: 0 5px 15px rgba(99,102,241,.25);
    }

    .sidebar-link:focus-visible {
      outline: 2px solid #a5b4fc;
      outline-offset: 2px;
    }

    .sidebar-divider {
      height: 1px;
      margin: 18px 8px;
      background: rgba(255,255,255,.1);
    }

    .logout-link {
      margin-top: auto;
      color: #fca5a5;
    }

    .logout-link:hover {
      background: rgba(220,38,38,.15);
      color: #fecaca;
    }

    /* ==============================
       5. MAIN LAYOUT
    ============================== */
    .main-content {
      min-height: 100vh;
      min-width: 0;
      margin-left: var(--sidebar-width);

      display: flex;
      flex-direction: column;
    }

    /* ==============================
       6. TOPBAR
    ============================== */
    .topbar {
      position: sticky;
      top: 0;
      z-index: 80;

      min-height: var(--topbar-height);
      padding: 0 28px;

      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;

      background: var(--card-bg);
      border-bottom: 1px solid var(--border-color);
    }

    .topbar-left {
      display: flex;
      align-items: center;
      gap: 14px;
      min-width: 0;
    }

    .topbar h1 {
      font-size: 21px;
      font-weight: 800;
      letter-spacing: -.5px;

      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .topbar-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .icon-button {
      width: 42px;
      height: 42px;

      display: inline-flex;
      align-items: center;
      justify-content: center;

      border: 1px solid var(--border-color);
      border-radius: 11px;

      background: var(--page-bg);
      color: var(--text-color);

      transition: background .2s, transform .15s;
    }

    .icon-button:hover {
      background: var(--border-color);
    }

    .icon-button:active {
      transform: scale(.96);
    }

    .icon-button:focus-visible {
      outline: 2px solid var(--primary);
      outline-offset: 3px;
    }

    #menuBtn {
      display: none;
    }

    .user-profile {
      max-width: 220px;
      padding: 5px 12px 5px 5px;

      display: flex;
      align-items: center;
      gap: 10px;

      background: var(--page-bg);
      border: 1px solid var(--border-color);
      border-radius: 30px;
    }

    .user-avatar {
      width: 36px;
      height: 36px;
      border-radius: 50%;

      display: flex;
      align-items: center;
      justify-content: center;

      background: var(--primary-gradient);
      color: white;

      font-size: 14px;
      font-weight: 800;
    }

    .user-name {
      max-width: 150px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;

      font-size: 13px;
      font-weight: 700;
    }

    /* ==============================
       7. PAGE CONTENT
    ============================== */
    .page-content {
      width: 100%;
      max-width: 1600px;
      margin: 0 auto;
      padding: 28px;
      flex: 1;
    }

    /* ==============================
       8. FLASH MESSAGES
    ============================== */
    .flash {
      display: flex;
      align-items: flex-start;
      gap: 10px;

      padding: 14px 16px;
      margin-bottom: 18px;

      border: 1px solid transparent;
      border-left-width: 4px;
      border-radius: 9px;

      font-size: 14px;
      font-weight: 600;
      line-height: 1.6;
    }

    .flash-success {
      background: #f0fdf4;
      color: #166534;
      border-color: #22c55e;
    }

    .flash-error,
    .flash-danger {
      background: #fef2f2;
      color: #991b1b;
      border-color: #ef4444;
    }

    .flash-warning {
      background: #fffbeb;
      color: #92400e;
      border-color: #f59e0b;
    }

    .flash-info,
    .flash-message {
      background: #eff6ff;
      color: #1e40af;
      border-color: #3b82f6;
    }

    html.dark .flash-success {
      background: #052e16;
      color: #bbf7d0;
    }

    html.dark .flash-error,
    html.dark .flash-danger {
      background: #450a0a;
      color: #fecaca;
    }

    html.dark .flash-warning {
      background: #451a03;
      color: #fde68a;
    }

    html.dark .flash-info,
    html.dark .flash-message {
      background: #172554;
      color: #bfdbfe;
    }

    /* ==============================
       9. MOBILE OVERLAY
    ============================== */
    .overlay {
      position: fixed;
      inset: 0;
      z-index: 95;

      background: rgba(2,6,23,.60);
      opacity: 0;
      visibility: hidden;

      transition: opacity .25s, visibility .25s;
    }

    .overlay.active {
      opacity: 1;
      visibility: visible;
    }

    /* ==============================
       10. RESPONSIVE
    ============================== */
    @media (max-width: 900px) {
      .sidebar {
        transform: translateX(-100%);
      }

      .sidebar.open {
        transform: translateX(0);
      }

      .main-content {
        margin-left: 0;
      }

      #menuBtn {
        display: inline-flex;
      }

      .topbar {
        min-height: 68px;
        padding: 0 15px;
      }

      .topbar h1 {
        font-size: 17px;
      }

      .page-content {
        padding: 18px 15px;
      }

      .user-name {
        display: none;
      }

      .user-profile {
        padding: 4px;
      }

      .user-avatar {
        width: 34px;
        height: 34px;
      }

      .icon-button {
        width: 38px;
        height: 38px;
      }
    }

    @media (max-width: 420px) {
      .topbar {
        gap: 8px;
      }

      .topbar-left {
        gap: 8px;
      }

      .topbar-actions {
        gap: 7px;
      }

      .topbar h1 {
        max-width: 155px;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      *,
      *::before,
      *::after {
        scroll-behavior: auto !important;
        transition-duration: .01ms !important;
      }
    }
  </style>
</head>

<body>

  <!-- SVG icons -->
  <svg class="icon-library" xmlns="http://www.w3.org/2000/svg">
    <symbol id="icon-school" viewBox="0 0 24 24">
      <path d="M3 10 12 4l9 6"/>
      <path d="M5 10v10h14V10"/>
      <path d="M9 20v-6h6v6"/>
      <path d="M2 20h20"/>
    </symbol>

    <symbol id="icon-dashboard" viewBox="0 0 24 24">
      <rect x="3" y="3" width="8" height="8" rx="1"/>
      <rect x="13" y="3" width="8" height="5" rx="1"/>
      <rect x="13" y="10" width="8" height="11" rx="1"/>
      <rect x="3" y="13" width="8" height="8" rx="1"/>
    </symbol>

    <symbol id="icon-students" viewBox="0 0 24 24">
      <circle cx="9" cy="8" r="4"/>
      <path d="M2 21v-2a7 7 0 0 1 14 0v2"/>
      <path d="M16 4a4 4 0 0 1 0 8"/>
      <path d="M19 14a5 5 0 0 1 3 5v2"/>
    </symbol>

    <symbol id="icon-fees" viewBox="0 0 24 24">
      <rect x="3" y="5" width="18" height="14" rx="2"/>
      <path d="M3 10h18"/>
      <path d="M7 15h4"/>
      <path d="M16 14v3"/>
    </symbol>

    <symbol id="icon-attendance" viewBox="0 0 24 24">
      <rect x="3" y="5" width="18" height="16" rx="2"/>
      <path d="M16 3v4M8 3v4M3 10h18"/>
      <path d="m8 15 2 2 5-5"/>
    </symbol>

    <symbol id="icon-staff" viewBox="0 0 24 24">
      <circle cx="12" cy="8" r="4"/>
      <path d="M4 21v-2a8 8 0 0 1 16 0v2"/>
      <path d="M9 13h6"/>
    </symbol>

    <symbol id="icon-notices" viewBox="0 0 24 24">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/>
      <path d="M10 21h4"/>
    </symbol>

    <symbol id="icon-ai" viewBox="0 0 24 24">
      <rect x="4" y="7" width="16" height="13" rx="3"/>
      <path d="M12 3v4M9 3h6"/>
      <circle cx="9" cy="12" r="1"/>
      <circle cx="15" cy="12" r="1"/>
      <path d="M9 16h6M2 12h2M20 12h2"/>
    </symbol>

    <symbol id="icon-logout" viewBox="0 0 24 24">
      <path d="M10 17l5-5-5-5"/>
      <path d="M15 12H3"/>
      <path d="M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7"/>
    </symbol>

    <symbol id="icon-menu" viewBox="0 0 24 24">
      <path d="M4 6h16M4 12h16M4 18h16"/>
    </symbol>

    <symbol id="icon-sun" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="4"/>
      <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.65 17.65l1.42 1.42M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.65 6.35l1.42-1.42"/>
    </symbol>

    <symbol id="icon-moon" viewBox="0 0 24 24">
      <path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/>
    </symbol>

    <symbol id="icon-close" viewBox="0 0 24 24">
      <path d="m6 6 12 12M18 6 6 18"/>
    </symbol>
  </svg>

  <!-- Mobile backdrop -->
  <button
    class="overlay"
    id="overlay"
    type="button"
    aria-label="Close navigation menu"
    tabindex="-1">
  </button>

  <!-- Sidebar -->
  <aside class="sidebar" id="sidebar" aria-label="Main navigation">

    <div class="sidebar-logo">
      <div class="logo-mark">
        <svg aria-hidden="true"><use href="#icon-school"/></svg>
      </div>

      <div>
        <div class="logo-text">School ERP</div>
        <div class="logo-subtitle">Management System</div>
      </div>
    </div>

    <nav class="sidebar-nav">
      <div class="nav-label">Main Menu</div>

      {% set current_path = request.path %}
      {% set nav_items = [
        ('/dashboard', 'Dashboard', 'icon-dashboard'),
        ('/students', 'Students', 'icon-students'),
        ('/fees', 'Fees Management', 'icon-fees'),
        ('/attendance', 'Attendance', 'icon-attendance'),
        ('/staff', 'Staff Management', 'icon-staff'),
        ('/notices', 'Notices', 'icon-notices'),
        ('/ai-assistant', 'AI Assistant', 'icon-ai')
      ] %}

      {% for url, label, icon_id in nav_items %}
        <a
          href="{{ url }}"
          class="sidebar-link {% if current_path == url or current_path.startswith(url + '/') %}active{% endif %}"
          {% if current_path == url or current_path.startswith(url + '/') %}
            aria-current="page"
          {% endif %}>

          <svg class="nav-icon" aria-hidden="true">
            <use href="#{{ icon_id }}"/>
          </svg>

          <span>{{ label }}</span>
        </a>
      {% endfor %}

      <div class="sidebar-divider"></div>

      <a href="/logout" class="sidebar-link logout-link">
        <svg class="nav-icon" aria-hidden="true">
          <use href="#icon-logout"/>
        </svg>
        <span>Logout</span>
      </a>
    </nav>
  </aside>

  <!-- Main content -->
  <main class="main-content">

    <!-- Topbar -->
    <header class="topbar">

      <div class="topbar-left">
        <button
          class="icon-button"
          id="menuBtn"
          type="button"
          aria-label="Open navigation menu"
          aria-expanded="false"
          aria-controls="sidebar">

          <svg aria-hidden="true">
            <use href="#icon-menu"/>
          </svg>
        </button>

        <h1>{% block page_title %}Dashboard{% endblock %}</h1>
      </div>

      <div class="topbar-actions">

        <!-- Theme button -->
        <button
          class="icon-button"
          id="themeBtn"
          type="button"
          aria-label="Switch to dark mode"
          aria-pressed="false">

          <svg aria-hidden="true">
            <use id="themeIcon" href="#icon-moon"/>
          </svg>
        </button>

        <!-- User profile -->
        {% set display_name = session.get('name') or 'Admin' %}
        {% set user_initial = display_name[0]|upper %}

        <div class="user-profile" title="{{ display_name }}">
          <div class="user-avatar" aria-hidden="true">
            {{ user_initial }}
          </div>

          <span class="user-name">{{ display_name }}</span>
        </div>

      </div>
    </header>

    <!-- Page body -->
    <section class="page-content">

      <!-- Flask flash messages -->
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
          {% for category, message in messages %}

            {% set safe_category = category|lower|replace(' ', '-') %}

            <div
              class="flash flash-{{ safe_category }}"
              role="status">

              {{ message }}
            </div>

          {% endfor %}
        {% endif %}
      {% endwith %}

      {% block content %}{% endblock %}

    </section>
  </main>

  <!-- JavaScript -->
  <script>
    "use strict";

    /* ==============================
       MOBILE SIDEBAR
    ============================== */
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("overlay");
    const menuBtn = document.getElementById("menuBtn");

    function openSidebar() {
      sidebar.classList.add("open");
      overlay.classList.add("active");

      menuBtn.setAttribute("aria-expanded", "true");
      menuBtn.setAttribute("aria-label", "Close navigation menu");
    }

    function closeSidebar() {
      sidebar.classList.remove("open");
      overlay.classList.remove("active");

      menuBtn.setAttribute("aria-expanded", "false");
      menuBtn.setAttribute("aria-label", "Open navigation menu");
    }

    function toggleSidebar() {
      if (sidebar.classList.contains("open")) {
        closeSidebar();
      } else {
        openSidebar();
      }
    }

    menuBtn.addEventListener("click", toggleSidebar);
    overlay.addEventListener("click", closeSidebar);

    // Close menu after selecting a navigation item.
    document.querySelectorAll(".sidebar-link").forEach(function (link) {
      link.addEventListener("click", function () {
        if (window.innerWidth <= 900) {
          closeSidebar();
        }
      });
    });

    // Close menu with Escape.
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        closeSidebar();
      }
    });

    // Reset mobile menu if screen becomes desktop.
    window.addEventListener("resize", function () {
      if (window.innerWidth > 900) {
        closeSidebar();
      }
    });

    /* ==============================
       DARK / LIGHT THEME
    ============================== */
    const themeBtn = document.getElementById("themeBtn");
    const themeIcon = document.getElementById("themeIcon");
    const root = document.documentElement;

    function applyTheme() {
      const darkMode = root.classList.contains("dark");

      themeIcon.setAttribute(
        "href",
        darkMode ? "#icon-sun" : "#icon-moon"
      );

      themeBtn.setAttribute(
        "aria-label",
        darkMode ? "Switch to light mode" : "Switch to dark mode"
      );

      themeBtn.setAttribute("aria-pressed", String(darkMode));
    }

    function toggleTheme() {
      const darkMode = root.classList.toggle("dark");

      try {
        localStorage.setItem(
          "school-erp-theme",
          darkMode ? "dark" : "light"
        );
      } catch (error) {
        // Theme still works for the current page.
      }

      applyTheme();
    }

    themeBtn.addEventListener("click", toggleTheme);

    // Show the correct icon on initial page load.
    applyTheme();
  </script>

</body>
</html>
