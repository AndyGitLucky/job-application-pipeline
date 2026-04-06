from __future__ import annotations

import json
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from market_explorer.paths import data_path, exports_path


DEFAULT_JOBS_INPUT = data_path("market_jobs.json")
DEFAULT_SUMMARY_INPUT = data_path("market_summary.json")
DEFAULT_OUTPUT = exports_path("market_explorer_dashboard.html")


def render_market_dashboard(
    jobs_input_path: str | Path | None = None,
    summary_input_path: str | Path | None = None,
    output_path: str | Path | None = None,
    *,
    variant: str = "signal",
) -> Path:
    jobs_path = Path(jobs_input_path) if jobs_input_path else DEFAULT_JOBS_INPUT
    summary_path = Path(summary_input_path) if summary_input_path else DEFAULT_SUMMARY_INPUT
    out_path = Path(output_path) if output_path else DEFAULT_OUTPUT

    jobs = json.loads(jobs_path.read_text(encoding="utf-8")) if jobs_path.exists() else []
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    if str(variant).strip().lower() == "classic":
        html = _build_html_classic(jobs, summary)
    elif str(variant).strip().lower() == "plotly":
        html = _build_html_plotly(jobs, summary)
    else:
        html = _build_html_signal(jobs, summary)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def _build_html_signal(jobs: list[dict], summary: dict) -> str:
    jobs_json = json.dumps(jobs, ensure_ascii=False)
    summary_json = json.dumps(summary, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market Explorer</title>
  <style>
    :root {{
      --bg: #f7f2e8;
      --paper: #fffdf8;
      --panel: #fdf8ee;
      --ink: #181512;
      --muted: #6f665f;
      --line: #1e1a16;
      --soft-line: #d8c9b5;
      --accent: #c2410c;
      --accent-2: #0f766e;
      --accent-3: #1d4ed8;
      --shadow: 0 10px 0 rgba(24, 21, 18, 0.06);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Segoe UI", system-ui, sans-serif;
      background:
        linear-gradient(90deg, rgba(194,65,12,0.04) 0, rgba(194,65,12,0.04) 1px, transparent 1px, transparent 80px),
        linear-gradient(180deg, rgba(15,118,110,0.03) 0, rgba(15,118,110,0.03) 1px, transparent 1px, transparent 80px),
        linear-gradient(180deg, #fbf7ef 0%, #f7f2e8 100%);
    }}
    .wrap {{
      max-width: 1540px;
      margin: 0 auto;
      padding: 18px 18px 48px;
    }}
    .signalbar {{
      display: grid;
      grid-template-columns: 180px 1fr 240px;
      gap: 10px;
      margin-bottom: 14px;
    }}
    .signalbox {{
      border: 2px solid var(--line);
      background: var(--paper);
      min-height: 72px;
      padding: 12px 14px;
      box-shadow: var(--shadow);
    }}
    .signalbox .tiny {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 0.72rem;
      color: var(--muted);
      margin-bottom: 7px;
      font-weight: 700;
    }}
    .signalbox .big {{
      font-size: 1.35rem;
      font-weight: 800;
      line-height: 1;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.4fr 0.9fr;
      gap: 14px;
      margin-bottom: 16px;
    }}
    .hero-main, .hero-side, .panel {{
      border: 2px solid var(--line);
      background: var(--paper);
      box-shadow: var(--shadow);
    }}
    .hero-main {{
      padding: 22px 24px 24px;
      position: relative;
      overflow: hidden;
    }}
    .hero-main::after {{
      content: "";
      position: absolute;
      right: -60px;
      top: -30px;
      width: 220px;
      height: 220px;
      background: radial-gradient(circle, rgba(194,65,12,0.12), transparent 65%);
      pointer-events: none;
    }}
    .hero-side {{
      padding: 18px;
      display: grid;
      gap: 10px;
      align-content: start;
    }}
    .eyebrow {{
      display: inline-block;
      padding: 6px 10px;
      background: var(--accent);
      color: white;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 0.72rem;
      font-weight: 800;
      margin-bottom: 12px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(2.4rem, 4vw, 4.9rem);
      line-height: 0.92;
      max-width: 11ch;
    }}
    .sub {{
      margin: 0;
      color: var(--muted);
      max-width: 68ch;
      line-height: 1.6;
      font-size: 1rem;
    }}
    .hero-note {{
      border-top: 2px solid var(--line);
      padding-top: 10px;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.5;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 340px 1fr;
      gap: 14px;
      align-items: start;
    }}
    .filters {{
      position: sticky;
      top: 14px;
      padding: 18px;
    }}
    .filters-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      border-bottom: 2px solid var(--line);
      padding-bottom: 10px;
      margin-bottom: 14px;
    }}
    .filters-head h2, .content h2 {{
      margin: 0;
      font-size: 1.08rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 900;
    }}
    .filter-group {{
      margin-bottom: 14px;
    }}
    label {{
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 800;
    }}
    select, input {{
      width: 100%;
      padding: 11px 12px;
      border: 2px solid var(--line);
      background: #fffdfa;
      color: var(--ink);
      border-radius: 0;
      font-size: 0.97rem;
      box-shadow: inset 0 1px 0 rgba(0,0,0,0.02);
    }}
    .legend-strip {{
      display: grid;
      gap: 8px;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 2px dashed var(--soft-line);
    }}
    .legend-item {{
      display: grid;
      grid-template-columns: 14px 1fr;
      gap: 8px;
      align-items: start;
      font-size: 0.86rem;
      color: var(--muted);
    }}
    .legend-item span {{
      display: block;
      width: 14px;
      height: 14px;
      margin-top: 2px;
      border: 2px solid var(--line);
    }}
    .content {{
      display: grid;
      gap: 14px;
    }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }}
    .kpi {{
      border: 2px solid var(--line);
      background: var(--paper);
      padding: 16px;
      min-height: 110px;
      display: grid;
      align-content: space-between;
    }}
    .kpi:nth-child(1) {{ background: linear-gradient(180deg, rgba(194,65,12,0.08), transparent 70%), var(--paper); }}
    .kpi:nth-child(2) {{ background: linear-gradient(180deg, rgba(15,118,110,0.08), transparent 70%), var(--paper); }}
    .kpi:nth-child(3) {{ background: linear-gradient(180deg, rgba(29,78,216,0.08), transparent 70%), var(--paper); }}
    .kpi:nth-child(4) {{ background: linear-gradient(180deg, rgba(24,21,18,0.06), transparent 70%), var(--paper); }}
    .kpi .value {{
      font-size: 2.25rem;
      font-weight: 900;
      line-height: 1;
    }}
    .kpi .label {{
      color: var(--muted);
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-weight: 800;
    }}
    .two-col {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .panel {{
      padding: 18px;
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 2px solid var(--line);
      padding-bottom: 10px;
      margin-bottom: 14px;
    }}
    .panel-tag {{
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.09em;
      color: var(--muted);
      font-weight: 800;
    }}
    .chart-list {{
      display: grid;
      gap: 9px;
    }}
    .row {{
      display: grid;
      grid-template-columns: 170px 1fr 50px;
      gap: 10px;
      align-items: center;
      font-size: 0.9rem;
    }}
    .name {{
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-weight: 700;
    }}
    .bar {{
      height: 14px;
      border: 2px solid var(--line);
      background: repeating-linear-gradient(90deg, #f4ebdc 0, #f4ebdc 12px, #fffaf1 12px, #fffaf1 24px);
      overflow: hidden;
    }}
    .bar > span {{
      display: block;
      height: 100%;
      background: linear-gradient(90deg, var(--accent), #ea580c);
    }}
    .bar.alt > span {{
      background: linear-gradient(90deg, var(--accent-2), #14b8a6);
    }}
    .meta {{
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.55;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    th, td {{
      text-align: left;
      padding: 12px 10px;
      border-bottom: 1px solid var(--soft-line);
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .pill {{
      display: inline-block;
      padding: 4px 7px;
      margin: 2px 5px 2px 0;
      border: 1.5px solid var(--line);
      background: #fff6eb;
      color: var(--accent);
      font-size: 0.76rem;
      font-weight: 700;
    }}
    .timeline {{
      display: grid;
      grid-auto-flow: column;
      grid-auto-columns: minmax(18px, 1fr);
      align-items: end;
      gap: 5px;
      height: 220px;
      margin-top: 8px;
    }}
    .col {{
      display: flex;
      flex-direction: column;
      justify-content: end;
      align-items: center;
      gap: 7px;
      min-width: 18px;
    }}
    .col span {{
      width: 100%;
      border: 2px solid var(--line);
      border-bottom: 0;
      background: linear-gradient(180deg, #0f766e, #115e59);
      min-height: 8px;
    }}
    .timeline-label {{
      writing-mode: vertical-rl;
      transform: rotate(180deg);
      color: var(--muted);
      font-size: 0.7rem;
    }}
    .footer {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 0.83rem;
      line-height: 1.5;
    }}
    @media (max-width: 1180px) {{
      .hero, .grid, .two-col, .signalbar {{
        grid-template-columns: 1fr;
      }}
      .filters {{
        position: static;
      }}
      .kpis {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 760px) {{
      .kpis {{
        grid-template-columns: 1fr;
      }}
      .row {{
        grid-template-columns: 110px 1fr 36px;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="signalbar">
      <div class="signalbox"><div class="tiny">Mode</div><div class="big">Signal</div></div>
      <div class="signalbox"><div class="tiny">Market pulse</div><div class="big">Labor demand scanner for Germany</div></div>
      <div class="signalbox"><div class="tiny">Dataset</div><div class="big">${len(jobs)} postings indexed</div></div>
    </section>
    <section class="hero">
      <div class="hero-main">
        <div class="eyebrow">Distinct Variant</div>
        <h1>Job Market Signal Desk</h1>
        <p class="sub">This version is intentionally not a generic job dashboard. It is styled like an analyst workbench: bold sections, visible grid, stronger hierarchy, and clearer separation between discovery signals, public market signals, and employer-side primary sources.</p>
      </div>
      <div class="hero-side">
        <div class="signalbox">
          <div class="tiny">Readout</div>
          <div class="big">Compare role pressure, region density, listing sources, and company types in one pass.</div>
        </div>
        <div class="hero-note">Rollback stays easy: this renderer now supports both `signal` and `classic`. If you dislike the new look, we switch back without touching the data pipeline.</div>
      </div>
    </section>
    {_shared_dashboard_markup(jobs_json, summary_json)}
</body>
</html>"""


def _build_html_classic(jobs: list[dict], summary: dict) -> str:
    jobs_json = json.dumps(jobs, ensure_ascii=False)
    summary_json = json.dumps(summary, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market Explorer</title>
  <style>
    :root {{
      --bg: #f3efe6;
      --paper: rgba(255, 252, 247, 0.96);
      --ink: #1f2a37;
      --muted: #667085;
      --line: #dccfb6;
      --accent: #0f766e;
      --accent-soft: rgba(15, 118, 110, 0.14);
      --accent-2: #b45309;
      --shadow: 0 14px 36px rgba(31, 42, 55, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(180, 83, 9, 0.08), transparent 28%),
        linear-gradient(180deg, #fbf8f2 0%, #f3efe6 100%);
    }}
    .wrap {{ max-width: 1480px; margin: 0 auto; padding: 32px 24px 64px; }}
    .hero, .panel {{ background: var(--paper); border: 1px solid var(--line); border-radius: 24px; box-shadow: var(--shadow); }}
    .hero {{ padding: 28px 30px; margin-bottom: 22px; }}
    .eyebrow {{ text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.78rem; color: var(--accent); margin-bottom: 8px; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(2.2rem, 4vw, 4.2rem); line-height: 0.95; }}
    .sub {{ margin: 0; color: var(--muted); font-family: "Segoe UI", system-ui, sans-serif; max-width: 980px; line-height: 1.6; }}
    .grid {{ display: grid; grid-template-columns: 320px 1fr; gap: 22px; align-items: start; }}
    .filters {{ position: sticky; top: 20px; padding: 22px; }}
    .filters h2, .content h2 {{ margin: 0 0 16px; font-size: 1.2rem; }}
    .filter-group {{ margin-bottom: 16px; }}
    label {{ display: block; margin-bottom: 7px; color: var(--muted); font-family: "Segoe UI", system-ui, sans-serif; font-size: 0.92rem; }}
    select {{ width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line); background: #fffdfa; color: var(--ink); font-size: 0.97rem; }}
    .content {{ display: grid; gap: 22px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }}
    .kpi {{ padding: 18px; border-radius: 20px; background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(250,245,236,0.95)); border: 1px solid var(--line); }}
    .kpi .value {{ font-size: 2rem; font-weight: 700; margin-bottom: 6px; }}
    .kpi .label {{ color: var(--muted); font-family: "Segoe UI", system-ui, sans-serif; font-size: 0.94rem; }}
    .two-col {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }}
    .panel {{ padding: 22px; }}
    .chart-list {{ display: grid; gap: 10px; }}
    .row {{ display: grid; grid-template-columns: 180px 1fr 52px; gap: 12px; align-items: center; font-family: "Segoe UI", system-ui, sans-serif; font-size: 0.93rem; }}
    .name {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .bar {{ height: 12px; border-radius: 999px; background: #efe6d4; overflow: hidden; }}
    .bar > span {{ display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--accent), #1d9a91); }}
    .bar.alt > span {{ background: linear-gradient(90deg, var(--accent-2), #cf7c2b); }}
    .meta {{ color: var(--muted); font-family: "Segoe UI", system-ui, sans-serif; font-size: 0.9rem; margin-top: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-family: "Segoe UI", system-ui, sans-serif; }}
    th, td {{ text-align: left; padding: 11px 10px; border-bottom: 1px solid #eadfcb; vertical-align: top; font-size: 0.92rem; }}
    th {{ color: var(--muted); font-weight: 600; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .pill {{ display: inline-block; padding: 4px 8px; margin: 2px 6px 2px 0; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-size: 0.78rem; }}
    .timeline {{ display: grid; grid-auto-flow: column; grid-auto-columns: minmax(20px, 1fr); align-items: end; gap: 6px; height: 220px; margin-top: 10px; }}
    .col {{ display: flex; flex-direction: column; justify-content: end; align-items: center; gap: 8px; min-width: 20px; }}
    .col span {{ width: 100%; border-radius: 10px 10px 0 0; background: linear-gradient(180deg, #d97706, #b45309); min-height: 6px; }}
    .timeline-label {{ writing-mode: vertical-rl; transform: rotate(180deg); color: var(--muted); font-size: 0.72rem; font-family: "Segoe UI", system-ui, sans-serif; }}
    .footer {{ margin-top: 14px; color: var(--muted); font-family: "Segoe UI", system-ui, sans-serif; font-size: 0.88rem; }}
    @media (max-width: 1100px) {{
      .grid, .two-col {{ grid-template-columns: 1fr; }}
      .filters {{ position: static; }}
      .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 700px) {{
      .kpis {{ grid-template-columns: 1fr; }}
      .row {{ grid-template-columns: 110px 1fr 36px; }}
      .timeline {{ overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">Market Explorer</div>
      <h1>Job Market Atlas</h1>
      <p class="sub">A first interactive view on the current job market based on deduplicated postings from the existing pipeline. Filter by source type, region, role cluster, remote mode, and seniority to surface structural patterns instead of reading jobs one by one.</p>
    </section>
    {_shared_dashboard_markup(jobs_json, summary_json)}
  </div>
</body>
</html>"""


def _build_html_plotly(jobs: list[dict], summary: dict) -> str:
    jobs_json = json.dumps(jobs, ensure_ascii=False)
    summary_json = json.dumps(summary, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market Explorer Plotly</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {{
      --bg: #08111f;
      --bg-2: #0d1728;
      --panel: rgba(14, 24, 42, 0.82);
      --panel-strong: rgba(12, 20, 36, 0.96);
      --ink: #eef4ff;
      --muted: #9cb0cf;
      --line: rgba(122, 161, 255, 0.18);
      --line-strong: rgba(122, 161, 255, 0.35);
      --accent: #3b82f6;
      --accent-2: #14b8a6;
      --accent-3: #f97316;
      --accent-4: #a855f7;
      --shadow: 0 24px 64px rgba(0, 0, 0, 0.34);
      --radius: 24px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Segoe UI", system-ui, sans-serif;
      background:
        radial-gradient(circle at 10% 12%, rgba(59,130,246,0.24), transparent 22%),
        radial-gradient(circle at 90% 14%, rgba(20,184,166,0.18), transparent 18%),
        radial-gradient(circle at 78% 74%, rgba(249,115,22,0.16), transparent 20%),
        linear-gradient(180deg, #07101c 0%, #0b1424 38%, #08111f 100%);
    }}
    .wrap {{
      width: 100%;
      min-height: 100vh;
      padding: 18px;
    }}
    .shell {{
      display: grid;
      gap: 18px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.34fr 0.66fr;
      gap: 18px;
      align-items: start;
    }}
    .hero-card, .panel, .filter-card, .info-box {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(20px);
    }}
    .hero-card {{
      padding: 30px 32px;
      position: relative;
      overflow: hidden;
      min-height: 300px;
      background:
        linear-gradient(135deg, rgba(59,130,246,0.12), rgba(14,24,42,0.90)),
        var(--panel);
    }}
    .hero-card::after {{
      content: "";
      position: absolute;
      inset: auto -40px -60px auto;
      width: 260px;
      height: 260px;
      background: radial-gradient(circle, rgba(20,184,166,0.16), transparent 70%);
      pointer-events: none;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(59,130,246,0.16);
      color: #dbeafe;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.76rem;
      font-weight: 700;
      margin-bottom: 12px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: clamp(3.2rem, 5vw, 6.2rem);
      line-height: 0.92;
      font-family: Georgia, "Times New Roman", serif;
      max-width: 9ch;
    }}
    .sub {{
      margin: 0;
      max-width: 70ch;
      color: var(--muted);
      line-height: 1.65;
      font-size: 1.02rem;
    }}
    .hero-side {{
      display: grid;
      gap: 14px;
      align-content: start;
    }}
    .hero-note {{
      padding: 18px 20px;
      background:
        linear-gradient(135deg, rgba(20,184,166,0.10), rgba(14,24,42,0.90)),
        var(--panel-strong);
      color: var(--muted);
      line-height: 1.55;
      align-self: start;
    }}
    .hero-note strong {{
      display: block;
      color: var(--ink);
      margin-bottom: 10px;
      font-size: 0.94rem;
      letter-spacing: 0.01em;
    }}
    .crawl-list {{
      display: grid;
      gap: 10px;
    }}
    .crawl-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 12px;
      align-items: baseline;
      padding-bottom: 10px;
      border-bottom: 1px solid rgba(122,161,255,0.12);
    }}
    .crawl-row:last-child {{
      padding-bottom: 0;
      border-bottom: 0;
    }}
    .crawl-source {{
      color: var(--ink);
      font-weight: 700;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .crawl-metric {{
      color: var(--muted);
      font-size: 0.84rem;
      white-space: nowrap;
    }}
    .hero-meta-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }}
    .hero-mini {{
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(7, 16, 28, 0.52);
    }}
    .hero-mini .label {{
      color: var(--muted);
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
      font-weight: 700;
    }}
    .hero-mini .value {{
      color: var(--ink);
      font-size: 1.18rem;
      font-weight: 800;
      line-height: 1.1;
    }}
    .hero-stats {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 22px;
    }}
    .hero-stat {{
      padding: 14px 14px 12px;
      border-radius: 18px;
      background: rgba(7, 16, 28, 0.42);
      border: 1px solid var(--line);
    }}
    .hero-stat .label {{
      color: var(--muted);
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
      font-weight: 700;
    }}
    .hero-stat .value {{
      font-size: 1.75rem;
      font-weight: 800;
      line-height: 1;
    }}
    .controlbar {{
      display: grid;
      grid-template-columns: 1.2fr repeat(6, minmax(0, 1fr));
      gap: 12px;
    }}
    .filter-card {{
      padding: 12px 14px;
      min-height: 90px;
      background: var(--panel-strong);
    }}
    .filter-card label {{
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 800;
    }}
    select, input {{
      width: 100%;
      padding: 11px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(7, 16, 28, 0.86);
      color: var(--ink);
      font-size: 0.95rem;
    }}
    .filter-actions {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-top: 10px;
    }}
    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line-strong);
      background: rgba(59,130,246,0.10);
      color: #dbeafe;
      font-size: 0.8rem;
      font-weight: 700;
    }}
    .chip button {{
      border: 0;
      background: transparent;
      color: inherit;
      cursor: pointer;
      font-size: 0.86rem;
      padding: 0;
    }}
    .content {{
      display: grid;
      gap: 18px;
    }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }}
    .kpi {{
      padding: 18px 20px;
      border-radius: 20px;
      border: 1px solid var(--line);
      background:
        linear-gradient(180deg, rgba(59,130,246,0.08), rgba(14,24,42,0.92)),
        var(--panel-strong);
    }}
    .kpi .value {{
      font-size: 2.3rem;
      font-weight: 800;
      margin-bottom: 6px;
    }}
    .kpi .label {{
      color: var(--muted);
      font-size: 0.86rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .dashboard-grid {{
      display: grid;
      grid-template-columns: 1.16fr 0.84fr;
      gap: 18px;
    }}
    .stack {{
      display: grid;
      gap: 18px;
    }}
    .panel {{
      padding: 18px 18px 14px;
      background: var(--panel);
    }}
    .plot {{
      width: 100%;
      min-height: 380px;
    }}
    .plot.tall {{
      min-height: 540px;
    }}
    .micro-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }}
    .panel-head h2 {{
      margin: 0;
      font-size: 1rem;
      letter-spacing: 0.01em;
    }}
    .panel-tag {{
      font-size: 0.74rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    th, td {{
      text-align: left;
      padding: 11px 10px;
      border-bottom: 1px solid rgba(122,161,255,0.12);
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .pill {{
      display: inline-block;
      padding: 4px 8px;
      margin: 2px 6px 2px 0;
      border-radius: 999px;
      background: rgba(59,130,246,0.14);
      color: #dbeafe;
      font-size: 0.76rem;
      font-weight: 700;
    }}
    .footer {{
      margin-top: 12px;
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.5;
    }}
    .info-strip {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 14px;
    }}
    .info-box {{
      padding: 16px 18px;
      color: var(--muted);
      line-height: 1.55;
    }}
    .info-box strong {{
      display: block;
      color: var(--ink);
      margin-bottom: 6px;
      font-size: 0.96rem;
    }}
    @media (max-width: 1180px) {{
      .hero, .dashboard-grid, .micro-grid, .controlbar, .info-strip {{
        grid-template-columns: 1fr;
      }}
      .kpis {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .hero-stats {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 760px) {{
      .kpis {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="shell">
    <section class="hero">
      <div class="hero-card">
        <div class="eyebrow">Plotly Command Desk</div>
        <h1>Germany Job Market Live Surface</h1>
        <p class="sub">This redesign is built like a modern command center: full-width, chart-first, visually louder, and click-driven. Regions, roles, source strategies, and industries are now active controls. Click Munich in the region view and the dashboard applies that filter immediately.</p>
        <div class="hero-stats">
          <div class="hero-stat"><div class="label">Indexed jobs</div><div class="value">${len(jobs)}</div></div>
          <div class="hero-stat"><div class="label">Variant</div><div class="value">Plotly</div></div>
          <div class="hero-stat"><div class="label">Interaction</div><div class="value">Click to filter</div></div>
        </div>
      </div>
      <div class="hero-side">
        <div class="hero-note" id="heroCrawlBox">Loading crawl footprint...</div>
        <div class="hero-note" id="heroScopeBox">Loading dataset scope...</div>
      </div>
    </section>
    <section class="controlbar">
      <div class="filter-card">
        <label for="searchInput">Search title or company</label>
        <input id="searchInput" type="text" placeholder="koch, dresden, siemens, pflege">
        <div class="filter-actions">
          <div class="chip">live slice</div>
          <div class="chip"><button id="resetFilters" type="button">reset all</button></div>
        </div>
      </div>
      <div class="filter-card"><label for="sourceFilter">Listing source</label><select id="sourceFilter"></select></div>
      <div class="filter-card"><label for="regionFilter">Region</label><select id="regionFilter"></select></div>
      <div class="filter-card"><label for="roleFilter">Role cluster</label><select id="roleFilter"></select></div>
      <div class="filter-card"><label for="industryFilter">Industry</label><select id="industryFilter"></select></div>
      <div class="filter-card"><label for="remoteFilter">Remote mode</label><select id="remoteFilter"></select></div>
      <div class="filter-card"><label for="seniorityFilter">Seniority</label><select id="seniorityFilter"></select></div>
    </section>
    <main class="content">
      <section class="kpis">
        <div class="kpi"><div class="value" id="jobsCount">0</div><div class="label">Visible jobs</div></div>
        <div class="kpi"><div class="value" id="companyCount">0</div><div class="label">Hiring companies</div></div>
        <div class="kpi"><div class="value" id="avgScore">0.0</div><div class="label">Average market score</div></div>
        <div class="kpi"><div class="value" id="topRegion">-</div><div class="label">Dominant region</div></div>
      </section>
      <section class="dashboard-grid">
        <section class="stack">
          <section class="panel">
            <div class="panel-head"><h2>Regional demand map</h2><div class="panel-tag">click a region</div></div>
            <div class="plot tall" id="regionPlot"></div>
          </section>
          <section class="micro-grid">
            <section class="panel">
              <div class="panel-head"><h2>Role pressure</h2><div class="panel-tag">click filters role</div></div>
              <div class="plot" id="rolePlot"></div>
            </section>
            <section class="panel">
              <div class="panel-head"><h2>Industry mix</h2><div class="panel-tag">click filters industry</div></div>
              <div class="plot" id="industryPlot"></div>
            </section>
          </section>
        </section>
        <section class="stack">
          <section class="micro-grid">
            <section class="panel">
              <div class="panel-head"><h2>Listing mix</h2><div class="panel-tag">click filters source</div></div>
              <div class="plot" id="sourcePlot"></div>
            </section>
            <section class="panel">
              <div class="panel-head"><h2>Company type</h2><div class="panel-tag">signal quality</div></div>
              <div class="plot" id="companyKindPlot"></div>
            </section>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>Market tempo</h2><div class="panel-tag">time-series view</div></div>
            <div class="plot" id="timelinePlot"></div>
          </section>
          <section class="panel">
            <div class="panel-head"><h2>Employer concentration</h2><div class="panel-tag">company volume</div></div>
            <div class="plot" id="companyPlot"></div>
          </section>
        </section>
      </section>
      <section class="info-strip">
        <div class="info-box" id="sliceInfo"><strong>Current slice</strong>Loading slice guidance.</div>
        <div class="info-box" id="generationInfo"><strong>Dataset</strong>Loading current dataset information.</div>
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Representative postings</h2><div class="panel-tag">top results inside current slice</div></div>
        <table>
          <thead>
            <tr><th>Title</th><th>Company</th><th>Region</th><th>Role</th><th>Industry</th><th>Remote</th><th>Score</th></tr>
          </thead>
          <tbody id="jobsTable"></tbody>
        </table>
      </section>
    </main>
    </div>
  </div>
  <script>
    const JOBS = {jobs_json};
    const SUMMARY = {summary_json};
  </script>
  <script>
{_plotly_dashboard_script()}
  </script>
</body>
</html>"""


def _shared_dashboard_markup(jobs_json: str, summary_json: str) -> str:
    return f"""
    <section class="grid">
      <aside class="panel filters">
        <div class="filters-head"><h2>Filters</h2><div class="panel-tag">interactive slice</div></div>
        <div class="filter-group"><label for="searchInput">Search title or company</label><input id="searchInput" type="text" placeholder="e.g. koch, dresden, siemens" style="width:100%;"></div>
        <div class="filter-group"><label for="sourceFilter">Source group</label><select id="sourceFilter"></select></div>
        <div class="filter-group"><label for="regionFilter">Region</label><select id="regionFilter"></select></div>
        <div class="filter-group"><label for="roleFilter">Role cluster</label><select id="roleFilter"></select></div>
        <div class="filter-group"><label for="remoteFilter">Remote mode</label><select id="remoteFilter"></select></div>
        <div class="filter-group"><label for="seniorityFilter">Seniority</label><select id="seniorityFilter"></select></div>
        <div class="legend-strip">
          <div class="legend-item"><span style="background:#ea580c;"></span><div>Discovery-heavy signals like jobboards tend to broaden the market picture.</div></div>
          <div class="legend-item"><span style="background:#14b8a6;"></span><div>Public and primary sources increase confidence and are worth comparing separately.</div></div>
        </div>
        <div class="footer" id="generationInfo"></div>
      </aside>
      <main class="content">
        <section class="kpis">
          <div class="kpi"><div class="value" id="jobsCount">0</div><div class="label">Visible jobs</div></div>
          <div class="kpi"><div class="value" id="companyCount">0</div><div class="label">Hiring companies</div></div>
          <div class="kpi"><div class="value" id="avgScore">0.0</div><div class="label">Average market score</div></div>
          <div class="kpi"><div class="value" id="topRegion">-</div><div class="label">Leading region</div></div>
        </section>
        <section class="two-col">
          <section class="panel"><div class="panel-head"><h2>Role landscape</h2><div class="panel-tag">structure</div></div><div class="chart-list" id="roleChart"></div></section>
          <section class="panel"><div class="panel-head"><h2>Regional demand</h2><div class="panel-tag">geography</div></div><div class="chart-list" id="regionChart"></div></section>
        </section>
        <section class="two-col">
          <section class="panel"><div class="panel-head"><h2>Skill signals</h2><div class="panel-tag">language</div></div><div class="chart-list" id="skillChart"></div></section>
          <section class="panel"><div class="panel-head"><h2>Source mix</h2><div class="panel-tag">coverage</div></div><div class="chart-list" id="sourceChart"></div></section>
        </section>
        <section class="two-col">
          <section class="panel"><div class="panel-head"><h2>Source strategy</h2><div class="panel-tag">confidence</div></div><div class="chart-list" id="sourceStrategyChart"></div></section>
          <section class="panel"><div class="panel-head"><h2>Industry mix</h2><div class="panel-tag">context</div></div><div class="chart-list" id="industryChart"></div></section>
        </section>
        <section class="two-col">
          <section class="panel"><div class="panel-head"><h2>Company quality</h2><div class="panel-tag">cleanliness</div></div><div class="chart-list" id="companyKindChart"></div></section>
          <section class="panel"><div class="panel-head"><h2>Top hiring companies</h2><div class="panel-tag">employers</div></div><div class="chart-list" id="companyChart"></div></section>
        </section>
        <section class="two-col">
          <section class="panel"><div class="panel-head"><h2>Time trend</h2><div class="panel-tag">tempo</div></div><div class="timeline" id="timelineChart"></div><div class="meta">Daily posting activity inside the currently filtered slice.</div></section>
          <section class="panel"><div class="panel-head"><h2>How to read this</h2><div class="panel-tag">guide</div></div><div class="meta">Use source mix and source strategy together: jobboards are broad discovery, public portals are strong local market signals, and primary sources are the highest-quality employer-side listings.</div></section>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Representative postings</h2><div class="panel-tag">examples</div></div>
          <table>
            <thead>
              <tr><th>Title</th><th>Company</th><th>Region</th><th>Role</th><th>Remote</th><th>Skills</th><th>Score</th></tr>
            </thead>
            <tbody id="jobsTable"></tbody>
          </table>
        </section>
      </main>
    </section>
    <script>
      const JOBS = {jobs_json};
      const SUMMARY = {summary_json};
    </script>
    <script>
    {_dashboard_script()}
    </script>
"""


def _dashboard_script() -> str:
    return """
const filters = {
  search: document.getElementById("searchInput"),
  source: document.getElementById("sourceFilter"),
  region: document.getElementById("regionFilter"),
  role: document.getElementById("roleFilter"),
  remote: document.getElementById("remoteFilter"),
  seniority: document.getElementById("seniorityFilter"),
};

function counter(items, keyFn) {
  const map = new Map();
  for (const item of items) {
    const key = keyFn(item) || "Unknown";
    map.set(key, (map.get(key) || 0) + 1);
  }
  return [...map.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
}

function average(items, key) {
  if (!items.length) return 0;
  const total = items.reduce((sum, item) => sum + (Number(item[key]) || 0), 0);
  return total / items.length;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fillSelect(select, values) {
  const options = ["All", ...values];
  select.innerHTML = options.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
}

function currentFilters() {
  return {
    search: filters.search.value.trim().toLowerCase(),
    source: filters.source.value,
    region: filters.region.value,
    role: filters.role.value,
    remote: filters.remote.value,
    seniority: filters.seniority.value,
  };
}

function matches(job, active) {
  const haystack = `${job.title_clean || ""} ${job.company_clean || ""} ${job.location_clean || ""}`.toLowerCase();
  return (active.source === "All" || job.source_group === active.source)
    && (active.region === "All" || job.region === active.region)
    && (active.role === "All" || job.role_cluster === active.role)
    && (active.remote === "All" || job.remote_mode === active.remote)
    && (active.seniority === "All" || job.seniority === active.seniority)
    && (!active.search || haystack.includes(active.search));
}

function renderBars(targetId, rows, variant = "default") {
  const target = document.getElementById(targetId);
  const max = Math.max(...rows.map(row => row.count), 1);
  target.innerHTML = rows.slice(0, 8).map(row => `
    <div class="row">
      <div class="name">${escapeHtml(row.label)}</div>
      <div class="bar ${variant === "alt" ? "alt" : ""}"><span style="width:${(row.count / max) * 100}%"></span></div>
      <div>${row.count}</div>
    </div>
  `).join("") || '<div class="meta">No data for this filter.</div>';
}

function renderTimeline(items) {
  const grouped = counter(items, job => job.date_label).sort((a, b) => String(a[0]).localeCompare(String(b[0])));
  const target = document.getElementById("timelineChart");
  const max = Math.max(...grouped.map(row => row[1]), 1);
  target.innerHTML = grouped.slice(-18).map(([label, count]) => `
    <div class="col" title="${escapeHtml(label)}: ${count}">
      <span style="height:${Math.max((count / max) * 180, 8)}px"></span>
      <div class="timeline-label">${escapeHtml(label.slice(5))}</div>
    </div>
  `).join("") || '<div class="meta">No timeline data.</div>';
}

function renderTable(items) {
  const target = document.getElementById("jobsTable");
  const rows = [...items].sort((a, b) => (Number(b.market_score) || 0) - (Number(a.market_score) || 0)).slice(0, 12);
  target.innerHTML = rows.map(job => `
    <tr>
      <td><strong>${escapeHtml(job.title_clean || job.title || "Unknown")}</strong></td>
      <td>${escapeHtml(job.company_clean || "Unknown")}</td>
      <td>${escapeHtml(job.region || "Unknown")}</td>
      <td>${escapeHtml(job.role_cluster || "Other")}</td>
      <td>${escapeHtml(job.remote_mode || "Unknown")}</td>
      <td>${(job.skills || []).map(skill => `<span class="pill">${escapeHtml(skill)}</span>`).join("")}</td>
      <td>${Number(job.market_score || 0).toFixed(1)}</td>
    </tr>
  `).join("") || '<tr><td colspan="7">No jobs match the current filters.</td></tr>';
}

function render() {
  const active = currentFilters();
  const filtered = JOBS.filter(job => matches(job, active));
  const companies = new Set(filtered.map(job => job.company_clean).filter(Boolean));
  const topRegion = counter(filtered, job => job.region)[0];

  document.getElementById("jobsCount").textContent = filtered.length;
  document.getElementById("companyCount").textContent = companies.size;
  document.getElementById("avgScore").textContent = average(filtered, "market_score").toFixed(1);
  document.getElementById("topRegion").textContent = topRegion ? `${topRegion[0]} (${topRegion[1]})` : "-";

  renderBars("roleChart", counter(filtered, job => job.role_cluster).map(([label, count]) => ({ label, count })));
  renderBars("regionChart", counter(filtered, job => job.region).map(([label, count]) => ({ label, count })), "alt");
  renderBars("skillChart", counter(filtered.flatMap(job => (job.skills || []).map(skill => ({ skill }))), item => item.skill).map(([label, count]) => ({ label, count })));
  renderBars("sourceChart", counter(filtered, job => job.source_group).map(([label, count]) => ({ label, count })), "alt");
  renderBars("sourceStrategyChart", counter(filtered, job => job.source_strategy).map(([label, count]) => ({ label, count })));
  renderBars("industryChart", counter(filtered, job => job.industry).map(([label, count]) => ({ label, count })), "alt");
  renderBars("companyKindChart", counter(filtered, job => job.company_kind).map(([label, count]) => ({ label, count })));
  renderBars("companyChart", counter(filtered, job => job.company_clean).map(([label, count]) => ({ label, count })));
  renderTimeline(filtered);
  renderTable(filtered);
}

fillSelect(filters.source, SUMMARY.filter_options?.sources || []);
fillSelect(filters.region, SUMMARY.filter_options?.regions || []);
fillSelect(filters.role, SUMMARY.filter_options?.roles || []);
fillSelect(filters.remote, SUMMARY.filter_options?.remote_modes || []);
fillSelect(filters.seniority, SUMMARY.filter_options?.seniority || []);
document.getElementById("generationInfo").textContent =
  `Generated: ${SUMMARY.generated_at || "unknown"} | Jobs in dataset: ${SUMMARY.total_jobs || 0} | Visible slice: ${SUMMARY.visible_jobs || 0}`;

filters.search.addEventListener("input", render);
Object.values(filters).filter(node => node.tagName === "SELECT").forEach(select => select.addEventListener("change", render));
render();
"""


def _plotly_dashboard_script() -> str:
    return """
const filters = {
  search: document.getElementById("searchInput"),
  source: document.getElementById("sourceFilter"),
  region: document.getElementById("regionFilter"),
  role: document.getElementById("roleFilter"),
  industry: document.getElementById("industryFilter"),
  remote: document.getElementById("remoteFilter"),
  seniority: document.getElementById("seniorityFilter"),
};

const resetButton = document.getElementById("resetFilters");

const SOURCE_LABELS = {
  "All": "All",
  "Jobboard": "Job boards",
  "Public Portal": "Agentur für Arbeit",
  "Primary Source": "Employer career pages",
  "Company or ATS": "Company or ATS",
  "Unknown": "Unknown",
};

const COMPANY_KIND_LABELS = {
  "Employer": "Direct employer",
  "Employer or Public Listing": "Employer or public listing",
  "Aggregator": "Aggregator listing",
  "Staffing": "Staffing / recruiting",
  "Unknown": "Unknown",
};

function displayLabel(kind, value) {
  const text = String(value ?? "");
  if (kind === "source") return SOURCE_LABELS[text] || text;
  if (kind === "companyKind") return COMPANY_KIND_LABELS[text] || text;
  return text;
}

const plotLayout = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: {family: "Segoe UI, sans-serif", color: "#eef4ff"},
  margin: {l: 90, r: 20, t: 20, b: 50},
  xaxis: {
    gridcolor: "rgba(122,161,255,0.12)",
    zerolinecolor: "rgba(122,161,255,0.12)",
    tickfont: {color: "#9cb0cf"},
    titlefont: {color: "#9cb0cf"},
  },
  yaxis: {
    gridcolor: "rgba(122,161,255,0.12)",
    zerolinecolor: "rgba(122,161,255,0.12)",
    tickfont: {color: "#dce7fb"},
    titlefont: {color: "#9cb0cf"},
  },
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fillSelect(select, values) {
  const options = ["All", ...values];
  const labelKind = select.id === "sourceFilter" ? "source" : "";
  select.innerHTML = options.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(displayLabel(labelKind, value))}</option>`).join("");
}

function counter(items, keyFn) {
  const map = new Map();
  for (const item of items) {
    const key = keyFn(item) || "Unknown";
    map.set(key, (map.get(key) || 0) + 1);
  }
  return [...map.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
}

function average(items, key) {
  if (!items.length) return 0;
  const total = items.reduce((sum, item) => sum + (Number(item[key]) || 0), 0);
  return total / items.length;
}

function currentFilters() {
  return {
    search: filters.search.value.trim().toLowerCase(),
    source: filters.source.value,
    region: filters.region.value,
    role: filters.role.value,
    industry: filters.industry.value,
    remote: filters.remote.value,
    seniority: filters.seniority.value,
  };
}

function matches(job, active) {
  const haystack = `${job.title_clean || ""} ${job.company_clean || ""} ${job.location_clean || ""}`.toLowerCase();
  return (active.source === "All" || (job.source_display || job.source_group) === active.source)
    && (active.region === "All" || job.region === active.region)
    && (active.role === "All" || job.role_cluster === active.role)
    && (active.industry === "All" || job.industry === active.industry)
    && (active.remote === "All" || job.remote_mode === active.remote)
    && (active.seniority === "All" || job.seniority === active.seniority)
    && (!active.search || haystack.includes(active.search));
}

function topRows(items, keyFn, limit = 10) {
  return counter(items, keyFn).slice(0, limit);
}

function renderHorizontalBar(targetId, rows, color) {
  const labelKind = targetId === "sourcePlot" ? "source" : "";
  const labels = rows.map(row => displayLabel(labelKind, row[0])).reverse();
  const values = rows.map(row => row[1]).reverse();
  Plotly.newPlot(targetId, [{
    type: "bar",
    orientation: "h",
    x: values,
    y: labels,
    customdata: rows.map(row => row[0]).reverse(),
    marker: {color},
    hovertemplate: "%{y}: %{x}<extra></extra>",
  }], {
    ...plotLayout,
    margin: {l: 160, r: 20, t: 12, b: 40},
  }, {displayModeBar: false, responsive: true});
}

function renderTimeline(targetId, items) {
  const grouped = counter(items, job => job.date_label).sort((a, b) => String(a[0]).localeCompare(String(b[0])));
  if (!grouped.length) {
    Plotly.purge(targetId);
    document.getElementById(targetId).innerHTML = '<div style="color:#9cb0cf;padding:28px 18px;">No timeline data for this slice.</div>';
    return;
  }
  const x = grouped.map(row => row[0]);
  const y = grouped.map(row => row[1]);
  Plotly.newPlot(targetId, [
    {
      type: "bar",
      x,
      y,
      marker: {
        color: "rgba(56,189,248,0.45)",
        line: {color: "rgba(56,189,248,0.95)", width: 1.2},
      },
      hovertemplate: "%{x}: %{y}<extra></extra>",
    },
    {
      type: "scatter",
      mode: "lines+markers",
      x,
      y,
      line: {color: "#2dd4bf", width: 3, shape: "spline", smoothing: 0.7},
      marker: {color: "#f97316", size: 8, line: {color: "#fff", width: 1}},
      hovertemplate: "%{x}: %{y}<extra></extra>",
    }
  ], {
    ...plotLayout,
    margin: {l: 56, r: 20, t: 16, b: 54},
    xaxis: {
      ...plotLayout.xaxis,
      type: "category",
      tickangle: -28,
      title: "",
    },
    yaxis: {
      ...plotLayout.yaxis,
      type: "linear",
      rangemode: "tozero",
      tickformat: ",d",
      tickmode: "auto",
      title: "Jobs",
    },
    bargap: 0.18,
    showlegend: false,
  }, {displayModeBar: false, responsive: true});
}

function renderDonut(targetId, rows, colors, titleText = "") {
  const labelKind = targetId === "companyKindPlot" ? "companyKind" : "";
  Plotly.newPlot(targetId, [{
    type: "pie",
    hole: 0.58,
    labels: rows.map(row => displayLabel(labelKind, row[0])),
    values: rows.map(row => row[1]),
    customdata: rows.map(row => row[0]),
    marker: {colors},
    textinfo: "label+percent",
    hovertemplate: "%{label}: %{value}<extra></extra>",
  }], {
    ...plotLayout,
    margin: {l: 10, r: 10, t: 10, b: 10},
    showlegend: false,
    annotations: titleText ? [{
      text: titleText,
      x: 0.5,
      y: 0.5,
      showarrow: false,
      font: {size: 15, color: "#eef4ff"},
    }] : [],
  }, {displayModeBar: false, responsive: true});
}

function renderMetaBars(targetId, rows, color, xTitle = "") {
  const labels = rows.map(row => row.label).reverse();
  const values = rows.map(row => row.value).reverse();
  Plotly.newPlot(targetId, [{
    type: "bar",
    orientation: "h",
    x: values,
    y: labels,
    marker: {color},
    hovertemplate: "%{y}: %{x}<extra></extra>",
  }], {
    ...plotLayout,
    margin: {l: 190, r: 20, t: 12, b: 40},
    xaxis: {...plotLayout.xaxis, title: xTitle},
  }, {displayModeBar: false, responsive: true});
}

function renderBubbleRegions(targetId, rows) {
  const ordered = [...rows].sort((a, b) => b[1] - a[1]);
  Plotly.newPlot(targetId, [{
    type: "scatter",
    mode: "markers+text",
    x: ordered.map((_, index) => index + 1),
    y: ordered.map(row => row[1]),
    text: ordered.map(row => row[0]),
    textposition: "top center",
    marker: {
      size: ordered.map(row => Math.max(18, Math.sqrt(row[1]) * 4)),
      color: ordered.map((_, index) => index),
      colorscale: [
        [0.0, "#3b82f6"],
        [0.5, "#14b8a6"],
        [1.0, "#f97316"]
      ],
      line: {width: 1.5, color: "rgba(255,255,255,0.18)"},
      opacity: 0.86,
    },
    customdata: ordered.map(row => row[0]),
    hovertemplate: "%{customdata}: %{y}<extra></extra>",
  }], {
    ...plotLayout,
    margin: {l: 50, r: 20, t: 14, b: 40},
    xaxis: {...plotLayout.xaxis, showticklabels: false, title: ""},
    yaxis: {...plotLayout.yaxis, title: "Posting volume"},
  }, {displayModeBar: false, responsive: true});
}

function renderTreemap(targetId, rows) {
  Plotly.newPlot(targetId, [{
    type: "treemap",
    labels: rows.map(row => row[0]),
    parents: rows.map(() => ""),
    values: rows.map(row => row[1]),
    marker: {
      colors: rows.map((_, index) => index),
      colorscale: [
        [0.0, "#3b82f6"],
        [0.5, "#14b8a6"],
        [1.0, "#a855f7"]
      ],
      line: {width: 1.2, color: "rgba(255,255,255,0.18)"},
    },
    textinfo: "label+value",
    hovertemplate: "%{label}: %{value}<extra></extra>",
  }], {
    ...plotLayout,
    margin: {l: 8, r: 8, t: 8, b: 8},
  }, {displayModeBar: false, responsive: true});
}

function renderTable(items) {
  const target = document.getElementById("jobsTable");
  const rows = [...items].sort((a, b) => (Number(b.market_score) || 0) - (Number(a.market_score) || 0)).slice(0, 12);
  target.innerHTML = rows.map(job => `
    <tr>
      <td><strong>${escapeHtml(job.title_clean || job.title || "Unknown")}</strong></td>
      <td>${escapeHtml(job.company_clean || "Unknown")}</td>
      <td>${escapeHtml(job.region || "Unknown")}</td>
      <td>${escapeHtml(job.role_cluster || "Other")}</td>
      <td>${escapeHtml(job.industry || "Other")}</td>
      <td>${escapeHtml(job.remote_mode === "Unknown" ? "Not specified" : (job.remote_mode || "Not specified"))}</td>
      <td>${Number(job.market_score || 0).toFixed(1)}</td>
    </tr>
  `).join("") || '<tr><td colspan="7">No jobs match the current filters.</td></tr>';
}

function setFilterValue(filterName, value) {
  const node = filters[filterName];
  if (!node) return;
  if ([...node.options].some(option => option.value === value)) {
    node.value = value;
    render();
  }
}

function attachBarClick(targetId, filterName) {
  const node = document.getElementById(targetId);
  if (typeof node.removeAllListeners === "function") node.removeAllListeners("plotly_click");
  node.on("plotly_click", event => {
    const label = event?.points?.[0]?.customdata || event?.points?.[0]?.y || event?.points?.[0]?.label;
    if (label) setFilterValue(filterName, label);
  });
}

function attachBubbleClick(targetId, filterName) {
  const node = document.getElementById(targetId);
  if (typeof node.removeAllListeners === "function") node.removeAllListeners("plotly_click");
  node.on("plotly_click", event => {
    const label = event?.points?.[0]?.customdata;
    if (label) setFilterValue(filterName, label);
  });
}

function attachTreemapClick(targetId, filterName) {
  const node = document.getElementById(targetId);
  if (typeof node.removeAllListeners === "function") node.removeAllListeners("plotly_click");
  node.on("plotly_click", event => {
    const label = event?.points?.[0]?.label;
    if (label) setFilterValue(filterName, label);
  });
}

function attachDonutClick(targetId, filterName) {
  const node = document.getElementById(targetId);
  if (typeof node.removeAllListeners === "function") node.removeAllListeners("plotly_click");
  node.on("plotly_click", event => {
    const label = event?.points?.[0]?.label;
    if (label) setFilterValue(filterName, label);
  });
}

function attachCompanyClick(targetId) {
  const node = document.getElementById(targetId);
  if (typeof node.removeAllListeners === "function") node.removeAllListeners("plotly_click");
  node.on("plotly_click", event => {
    const label = event?.points?.[0]?.y || event?.points?.[0]?.label || event?.points?.[0]?.customdata;
    if (label) {
      filters.search.value = label;
      render();
    }
  });
}

function bindInteractions() {
  attachBubbleClick("regionPlot", "region");
  attachBarClick("rolePlot", "role");
  attachBarClick("sourcePlot", "source");
  attachTreemapClick("industryPlot", "industry");
  attachCompanyClick("companyPlot");
}

function render() {
  const active = currentFilters();
  const filtered = JOBS.filter(job => matches(job, active));
  const companies = new Set(filtered.map(job => job.company_clean).filter(Boolean));
  const topRegion = topRows(filtered, job => job.region, 1)[0];
  const sourceMix = topRows(filtered, job => job.source_display || job.source_group, 8);
  const companyKinds = topRows(filtered, job => job.company_kind, 5);

  document.getElementById("jobsCount").textContent = filtered.length;
  document.getElementById("companyCount").textContent = companies.size;
  document.getElementById("avgScore").textContent = average(filtered, "market_score").toFixed(1);
  document.getElementById("topRegion").textContent = topRegion ? `${topRegion[0]} (${topRegion[1]})` : "-";

  renderBubbleRegions("regionPlot", topRows(filtered, job => job.region, 12));
  renderHorizontalBar("rolePlot", topRows(filtered, job => job.role_cluster, 10), "#14b8a6");
  renderHorizontalBar("sourcePlot", sourceMix, "#3b82f6");
  renderTreemap("industryPlot", topRows(filtered, job => job.industry, 12));
  renderDonut("companyKindPlot", companyKinds, ["#38bdf8", "#2dd4bf", "#f59e0b", "#f472b6", "#94a3b8"], "type");
  renderTimeline("timelinePlot", filtered);
  renderHorizontalBar("companyPlot", topRows(filtered, job => job.company_clean, 10), "#f97316");
  renderTable(filtered);
  bindInteractions();
}

fillSelect(filters.source, SUMMARY.filter_options?.sources || []);
fillSelect(filters.region, SUMMARY.filter_options?.regions || []);
fillSelect(filters.role, SUMMARY.filter_options?.roles || []);
fillSelect(filters.industry, SUMMARY.filter_options?.industries || []);
fillSelect(filters.remote, SUMMARY.filter_options?.remote_modes || []);
fillSelect(filters.seniority, SUMMARY.filter_options?.seniority || []);
document.getElementById("generationInfo").textContent =
  "";
document.getElementById("generationInfo").innerHTML =
  `<strong>Dataset</strong>Generated: ${SUMMARY.generated_at || "unknown"}<br>Indexed jobs: ${SUMMARY.total_jobs || 0}<br>Visible market jobs: ${SUMMARY.visible_jobs || 0}`;
const searchedSources = SUMMARY.searched_sources || [];
document.getElementById("heroCrawlBox").innerHTML =
  searchedSources.length
    ? `<strong>Crawl footprint</strong><div class="crawl-list">${
        searchedSources.slice(0, 5).map(item => `
          <div class="crawl-row">
            <div class="crawl-source">${escapeHtml(item.label)}</div>
            <div class="crawl-metric">${item.queries} queries</div>
            <div class="crawl-metric">${item.hits} hits</div>
          </div>
        `).join("")
      }</div>`
    : "<strong>Crawl footprint</strong>No crawl metadata available for this dataset.";
document.getElementById("heroScopeBox").innerHTML =
  `<strong>Scope this run</strong>
   <div class="hero-meta-grid">
     <div class="hero-mini"><div class="label">Live sources</div><div class="value">${searchedSources.length || 0}</div></div>
     <div class="hero-mini"><div class="label">Regions covered</div><div class="value">${(SUMMARY.filter_options?.regions || []).length}</div></div>
     <div class="hero-mini"><div class="label">Role clusters</div><div class="value">${(SUMMARY.filter_options?.roles || []).length}</div></div>
     <div class="hero-mini"><div class="label">Industry clusters</div><div class="value">${(SUMMARY.filter_options?.industries || []).length}</div></div>
   </div>`;
document.getElementById("sliceInfo").innerHTML =
  `<strong>Current slice</strong>Charts are controls. Region bubbles set <code>region</code>, role bars set <code>role</code>, source bars set <code>listing source</code>, and the industry map sets <code>industry</code>. The crawl footprint above reflects the sources that were actually searched for this dataset.`;

filters.search.addEventListener("input", render);
Object.values(filters).filter(node => node.tagName === "SELECT").forEach(select => select.addEventListener("change", render));
resetButton.addEventListener("click", () => {
  filters.search.value = "";
  Object.values(filters).filter(node => node.tagName === "SELECT").forEach(select => { select.value = "All"; });
  render();
});
render();
"""


if __name__ == "__main__":
    path = render_market_dashboard()
    print(path)
