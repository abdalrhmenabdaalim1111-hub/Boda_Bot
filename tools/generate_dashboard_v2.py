from dashboard_v2_template import build_dashboard
from pathlib import Path

out_dir = Path(__file__).parent.parent / "webroot" / "dashboard"
out_dir.mkdir(parents=True, exist_ok=True)

html = build_dashboard()
(out_dir / "index.html").write_text(html, encoding="utf-8")

print("✅ Dashboard Rebuilt and Optimised!")
