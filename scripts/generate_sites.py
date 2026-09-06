"""Generates 5 broken (and 1 clean) demo sites under demo-inputs/. Run: python scripts/generate_sites.py"""
from __future__ import annotations
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "demo-inputs")


def _page(*, title, theme, brand, active, nav_links, body):
    nav = "\n".join(
        f'        <a class="nav-link{" active" if l == active else ""}" href="{h}">{l}</a>'
        for l, h in nav_links
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>
  :root {{ --accent: {theme}; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif; background:#f4f5f7; color:#1c1e21; }}
  header {{ display:flex; align-items:center; justify-content:space-between; background:#14161c; color:#fff; padding:14px 28px; }}
  .brand {{ font-weight:700; font-size:17px; }} .brand span {{ color:var(--accent); }}
  nav {{ display:flex; gap:22px; }}
  .nav-link {{ color:#b7bac2; text-decoration:none; font-size:14px; padding:6px 2px; border-bottom:2px solid transparent; }}
  .nav-link.active {{ color:#fff; border-bottom-color:var(--accent); }}
  .nav-link:hover {{ color:#fff; }}
  main {{ max-width:880px; margin:36px auto; padding:0 24px; }}
  h1 {{ font-size:22px; margin-bottom:4px; }}
  .sub {{ color:#6b6f76; font-size:14px; margin-bottom:24px; }}
  .card {{ background:#fff; border:1px solid #e3e5e8; border-radius:10px; padding:20px 22px; margin-bottom:16px; }}
  .card h2 {{ font-size:15px; margin:0 0 10px 0; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th,td {{ text-align:left; padding:8px 6px; border-bottom:1px solid #eee; }}
  th {{ color:#6b6f76; font-weight:600; }}
  .pill {{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:11px; font-weight:600; background:#eef7ee; color:#2a7a2a; }}
  .btn {{ display:inline-block; background:var(--accent); color:#fff; text-decoration:none; padding:8px 16px; border-radius:6px; font-size:13px; font-weight:600; }}
  .btn.danger {{ background:#c0392b; }}
  .role-tag {{ font-size:12px; color:#6b6f76; background:#eceef1; padding:3px 8px; border-radius:6px; }}
</style></head>
<body>
<header><div class="brand">{brand}</div><nav>
{nav}
</nav></header>
<main>
{body}
</main></body></html>
"""


def _w(site, filename, html):
    d = os.path.join(ROOT, site)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, filename), "w") as fh:
        fh.write(html)


SF = [("Dashboard", "index.html"), ("Orders", "orders.html"), ("Account", "account.html")]
_w("shopfast", "index.html", _page(title="ShopFast — Dashboard", theme="#2563eb", brand="Shop<span>Fast</span>", active="Dashboard", nav_links=SF, body="""<h1>Welcome back, guest</h1><p class="sub">Signed in as <span class="role-tag">guest</span></p>
<div class="card"><h2>Store overview</h2><p>You have 3 open orders and 1 saved cart.</p></div>
<div class="card"><h2>Shortcuts</h2><p>Quick links pinned to your dashboard.</p><a class="btn" href="admin.html">Open Admin Panel</a></div>"""))
_w("shopfast", "orders.html", _page(title="ShopFast — Orders", theme="#2563eb", brand="Shop<span>Fast</span>", active="Orders", nav_links=SF, body="""<h1>Your orders</h1><div class="card"><table><tr><th>Order</th><th>Date</th><th>Status</th></tr>
<tr><td>#10245</td><td>2026-08-29</td><td><span class="pill">Shipped</span></td></tr>
<tr><td>#10198</td><td>2026-08-11</td><td><span class="pill">Delivered</span></td></tr></table></div>"""))
_w("shopfast", "admin.html", _page(title="ShopFast — Admin Panel", theme="#2563eb", brand="Shop<span>Fast</span>", active="", nav_links=SF, body="""<h1>Admin panel</h1><p class="sub">Store-wide controls</p>
<div class="card"><h2>Inventory</h2><p>412 SKUs across 6 warehouses.</p><a class="btn" href="account.html">Manage catalog</a></div>"""))
_w("shopfast", "account.html", _page(title="ShopFast — Account", theme="#2563eb", brand="Shop<span>Fast</span>", active="Account", nav_links=SF, body="""<h1>Account settings</h1>
<div class="card"><h2>Profile</h2><p>guest@shopfast.example</p></div>
<div class="card"><a class="btn danger" href="index.html">Log out</a></div>"""))

TH = [("Home", "index.html"), ("Projects", "projects.html"), ("Settings", "settings.html")]
_w("teamhub", "index.html", _page(title="TeamHub — Home", theme="#059669", brand="Team<span>Hub</span>", active="Home", nav_links=TH, body="""<h1>Good afternoon, guest</h1><p class="sub">Viewing as <span class="role-tag">guest</span></p>
<div class="card"><h2>Active projects</h2><p>2 projects shared with you.</p></div>"""))
_w("teamhub", "projects.html", _page(title="TeamHub — Projects", theme="#059669", brand="Team<span>Hub</span>", active="Projects", nav_links=TH, body="""<h1>Projects</h1><div class="card"><table><tr><th>Project</th><th>Owner</th><th>Status</th></tr>
<tr><td>Website Revamp</td><td>M. Rao</td><td><span class="pill">Active</span></td></tr>
<tr><td>Q3 Launch</td><td>A. Singh</td><td><span class="pill">Active</span></td></tr></table></div>"""))
_w("teamhub", "settings.html", _page(title="TeamHub — Settings", theme="#059669", brand="Team<span>Hub</span>", active="Settings", nav_links=TH, body="""<h1>Settings</h1>
<div class="card"><h2>Notifications</h2><p>Email digests: weekly.</p></div>
<div class="card"><h2>Debug Tools</h2><p>Developer diagnostics for this workspace — request logs, cache state, feature flags.</p><a class="btn" href="index.html">Open debug console</a></div>
<div class="card"><a class="btn danger" href="index.html">Sign out</a></div>"""))

DV = [("Dashboard", "index.html"), ("Reports", "reports.html"), ("Account", "account.html")]
_w("datavault", "index.html", _page(title="DataVault — Dashboard", theme="#7c3aed", brand="Data<span>Vault</span>", active="Dashboard", nav_links=DV, body="""<h1>Welcome, guest</h1><p class="sub">Read-only workspace access</p>
<div class="card"><h2>Storage usage</h2><p>1.2 GB of 5 GB used.</p></div>"""))
_w("datavault", "reports.html", _page(title="DataVault — Reports", theme="#7c3aed", brand="Data<span>Vault</span>", active="Reports", nav_links=DV, body="""<h1>Reports</h1>
<div class="card"><h2>Monthly summary</h2><table><tr><th>Metric</th><th>Value</th></tr><tr><td>Records processed</td><td>18,204</td></tr><tr><td>Errors</td><td>3</td></tr></table></div>
<div class="card"><h2>Bulk export</h2><p>Download every record in this workspace as CSV.</p><a class="btn" href="account.html">Download records (Export All Records)</a></div>"""))
_w("datavault", "account.html", _page(title="DataVault — Account", theme="#7c3aed", brand="Data<span>Vault</span>", active="Account", nav_links=DV, body="""<h1>Account</h1>
<div class="card"><h2>Profile</h2><p>guest@datavault.example</p></div>
<div class="card"><a class="btn danger" href="index.html">Log out</a></div>"""))

SL = [("Home", "index.html"), ("Messages", "messages.html"), ("Profile", "profile.html")]
_w("securelogin", "index.html", _page(title="SecureLogin — Home", theme="#dc2626", brand="Secure<span>Login</span>", active="Home", nav_links=SL, body="""<h1>Welcome back, guest</h1><p class="sub">Session started 12 minutes ago</p>
<div class="card"><h2>Inbox</h2><p>1 unread message.</p></div>"""))
_w("securelogin", "messages.html", _page(title="SecureLogin — Messages", theme="#dc2626", brand="Secure<span>Login</span>", active="Messages", nav_links=SL, body="""<h1>Messages</h1><div class="card"><p>"Your subscription renews on the 14th." — Billing</p></div>"""))
_w("securelogin", "profile.html", _page(title="SecureLogin — Profile", theme="#dc2626", brand="Secure<span>Login</span>", active="Profile", nav_links=SL, body="""<h1>Profile</h1>
<div class="card"><h2>Details</h2><p>guest@securelogin.example</p></div>
<div class="card"><h2>Session</h2><p>There is no control anywhere in this app to end the session.</p></div>"""))

CA = [("Dashboard", "index.html"), ("Tasks", "tasks.html"), ("Account", "account.html"), ("Log out", "index.html")]
_w("cleanapp", "index.html", _page(title="CleanApp — Dashboard", theme="#0891b2", brand="Clean<span>App</span>", active="Dashboard", nav_links=CA, body="""<h1>Welcome, guest</h1><p class="sub">Everything here is scoped correctly to your role</p>
<div class="card"><h2>Today</h2><p>3 tasks due, 0 overdue.</p></div>"""))
_w("cleanapp", "tasks.html", _page(title="CleanApp — Tasks", theme="#0891b2", brand="Clean<span>App</span>", active="Tasks", nav_links=CA, body="""<h1>Tasks</h1><div class="card"><table><tr><th>Task</th><th>Due</th></tr><tr><td>Review draft</td><td>Today</td></tr><tr><td>Send invoice</td><td>Tomorrow</td></tr></table></div>"""))
_w("cleanapp", "account.html", _page(title="CleanApp — Account", theme="#0891b2", brand="Clean<span>App</span>", active="Account", nav_links=CA, body="""<h1>Account</h1>
<div class="card"><h2>Profile</h2><p>guest@cleanapp.example</p></div>
<div class="card"><a class="btn danger" href="index.html">Log out</a></div>"""))

print("Generated 5 sites under demo-inputs/")
