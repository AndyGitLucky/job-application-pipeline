from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from source.job_visibility import hidden_reason, load_apply_log, should_hide_job
from source.link_extractor import annotate_job_links
from source.project_paths import artifacts_path, resolve_artifacts_path, resolve_runtime_path, runtime_path


DEFAULT_RAW = runtime_path("jobs_raw.json")
DEFAULT_SCORED = runtime_path("jobs_scored.json")
DEFAULT_OUTPUT = artifacts_path("present_dashboard.html")
DEFAULT_APPLY_LOG = runtime_path("apply_log.json")


def generate_present_dashboard(
    jobs_raw_path: str | Path | None = None,
    jobs_scored_path: str | Path | None = None,
    output_path: str | Path | None = None,
    apply_log_path: str | Path | None = None,
) -> Path:
    out_path = resolve_artifacts_path(output_path or DEFAULT_OUTPUT)
    html_text = render_present_dashboard(
        jobs_raw_path=jobs_raw_path,
        jobs_scored_path=jobs_scored_path,
        apply_log_path=apply_log_path,
    )
    out_path.write_text(html_text, encoding="utf-8")
    return out_path


def render_present_dashboard(
    jobs_raw_path: str | Path | None = None,
    jobs_scored_path: str | Path | None = None,
    apply_log_path: str | Path | None = None,
    *,
    interactive: bool = False,
    action_message: str = "",
) -> str:
    raw_path = resolve_runtime_path(jobs_raw_path or DEFAULT_RAW)
    scored_path = resolve_runtime_path(jobs_scored_path or DEFAULT_SCORED)
    apply_log = load_apply_log(apply_log_path or DEFAULT_APPLY_LOG)

    raw_jobs = _load_json_list(raw_path)
    scored_jobs = _load_json_list(scored_path)
    rows = _merge_jobs(raw_jobs, scored_jobs)

    hidden_rows = [job for job in rows if should_hide_job(job, apply_log)]
    visible_rows = [job for job in rows if not should_hide_job(job, apply_log)]

    link_quality_counts = Counter(job.get("best_link_quality") or "unknown" for job in visible_rows)
    description_quality_counts = Counter(job.get("description_quality") or "unknown" for job in visible_rows)
    bucket_counts = Counter(job.get("final_bucket") or "unknown" for job in visible_rows)
    hidden_counts = Counter(hidden_reason(job, apply_log) or "hidden" for job in hidden_rows)
    source_value_rows = _build_source_value_rows(visible_rows)

    top_jobs = sorted(
        visible_rows,
        key=lambda item: (
            _bucket_rank(item.get("final_bucket", "")),
            _description_quality_rank(item.get("description_quality", "")),
            _link_quality_rank(item.get("best_link_quality", "")),
            -(float(item.get("ranking_score") or item.get("score") or 0)),
        ),
    )[:5]

    review_jobs = [job for job in visible_rows if job.get("final_bucket") == "needs_review"]
    review_jobs.sort(key=lambda item: float(item.get("ranking_score") or item.get("score") or 0), reverse=True)
    review_jobs = review_jobs[:10]

    return _render_dashboard(
        total_raw=len(raw_jobs),
        total_scored=len(scored_jobs),
        total_visible=len(visible_rows),
        total_hidden=len(hidden_rows),
        link_quality_counts=link_quality_counts,
        description_quality_counts=description_quality_counts,
        bucket_counts=bucket_counts,
        hidden_counts=hidden_counts,
        source_value_rows=source_value_rows,
        top_jobs=top_jobs,
        review_jobs=review_jobs,
        interactive=interactive,
        action_message=action_message,
    )


def _load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _merge_jobs(raw_jobs: list[dict], scored_jobs: list[dict]) -> list[dict]:
    scored_by_id = {str(job.get("id") or ""): job for job in scored_jobs if job.get("id")}
    raw_by_id = {str(job.get("id") or ""): job for job in raw_jobs if job.get("id")}

    all_ids = []
    seen_ids = set()
    for job in raw_jobs + scored_jobs:
        job_id = str(job.get("id") or "")
        if job_id and job_id not in seen_ids:
            seen_ids.add(job_id)
            all_ids.append(job_id)

    rows = []
    for job_id in all_ids:
        merged = {}
        if job_id in raw_by_id:
            merged.update(raw_by_id[job_id])
        if job_id in scored_by_id:
            merged.update(scored_by_id[job_id])
        if not merged:
            continue
        merged.update(annotate_job_links(merged))
        rows.append(merged)
    return rows


def _render_dashboard(
    *,
    total_raw: int,
    total_scored: int,
    total_visible: int,
    total_hidden: int,
    link_quality_counts: Counter,
    description_quality_counts: Counter,
    bucket_counts: Counter,
    hidden_counts: Counter,
    source_value_rows: list[dict],
    top_jobs: list[dict],
    review_jobs: list[dict],
    interactive: bool,
    action_message: str,
) -> str:
    flash_html = ""
    if action_message:
        flash_html = f'<section class="flash">{html.escape(action_message)}</section>'

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Job Pipeline Dashboard</title>
  <style>
    :root {{
      --bg: #edf3f6;
      --panel: rgba(255, 255, 255, 0.94);
      --panel-strong: rgba(255, 255, 255, 0.99);
      --ink: #17253d;
      --muted: #61718c;
      --line: #d6e0e8;
      --accent: #13766f;
      --accent-soft: rgba(19, 118, 111, 0.12);
      --accent-2: #ca7a2c;
      --accent-2-soft: rgba(202, 122, 44, 0.12);
      --warn: #b91c1c;
      --warn-soft: rgba(185, 28, 28, 0.08);
      --good: #16654b;
      --good-soft: rgba(22, 101, 75, 0.12);
      --shadow: 0 12px 28px rgba(23, 37, 61, 0.07);
      --shadow-soft: 0 6px 16px rgba(23, 37, 61, 0.045);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Segoe UI", system-ui, sans-serif;
      background:
        linear-gradient(180deg, #f8fbfc 0%, #edf3f6 100%);
    }}
    .wrap {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 36px 32px 84px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(246,250,252,0.95));
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: 24px;
      padding: 28px 32px 26px;
      margin-bottom: 28px;
    }}
    h1, h2, h3 {{
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: clamp(2.6rem, 4vw, 4.35rem);
      line-height: 0.95;
      letter-spacing: -0.035em;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid rgba(19, 118, 111, 0.18);
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .sub {{
      color: var(--muted);
      font-size: 1rem;
      max-width: 820px;
      line-height: 1.55;
    }}
    .hero-points {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .hero-point {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(19,118,111,0.045);
      color: var(--ink);
      font-size: 0.84rem;
      font-weight: 600;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 18px;
      margin-top: 28px;
    }}
    .stat {{
      background: rgba(255,255,255,0.88);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 18px 20px;
      box-shadow: var(--shadow-soft);
    }}
    .stat .k {{
      color: var(--muted);
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-weight: 600;
    }}
    .stat .v {{
      margin-top: 8px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 1.9rem;
      font-weight: 700;
    }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.68fr) minmax(320px, 0.82fr);
      gap: 24px;
      align-items: start;
    }}
    .sidebar {{
      position: sticky;
      top: 24px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      box-shadow: var(--shadow);
      padding: 24px 26px 22px;
      margin-bottom: 24px;
    }}
    .panel p {{
      margin: 0 0 12px;
      color: var(--muted);
      line-height: 1.55;
      font-size: 0.96rem;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 1.45rem;
      line-height: 1.1;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
      table-layout: fixed;
    }}
    th, td {{
      text-align: left;
      padding: 13px 6px;
      border-bottom: 1px solid rgba(214, 224, 232, 0.92);
      vertical-align: top;
      overflow-wrap: anywhere;
      word-break: break-word;
    }}
    th {{
      color: var(--muted);
      font-size: 0.72rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    tbody tr:last-child td {{
      border-bottom: none;
    }}
    .top-reasons-table th:first-child,
    .top-reasons-table td:first-child {{
      width: 48%;
    }}
    .top-reasons-table th:nth-child(2),
    .top-reasons-table td:nth-child(2) {{
      width: 16%;
      white-space: nowrap;
    }}
    .top-reasons-table th:nth-child(3),
    .top-reasons-table td:nth-child(3) {{
      width: 38%;
    }}
    .source-value-table th:first-child,
    .source-value-table td:first-child {{
      width: 38%;
    }}
    .source-value-table th:nth-child(2),
    .source-value-table td:nth-child(2) {{
      width: 13%;
      white-space: nowrap;
    }}
    .source-value-table th:nth-child(3),
    .source-value-table td:nth-child(3) {{
      width: 13%;
      white-space: nowrap;
    }}
    .source-value-table th:nth-child(4),
    .source-value-table td:nth-child(4) {{
      width: 18%;
      white-space: nowrap;
    }}
    .source-value-table th:nth-child(5),
    .source-value-table td:nth-child(5) {{
      width: 18%;
      white-space: nowrap;
    }}
    .joblist {{
      display: grid;
      gap: 20px;
    }}
    .job {{
      position: relative;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 24px 22px 20px;
      background: var(--panel-strong);
      box-shadow: var(--shadow-soft);
      overflow: hidden;
    }}
    .job.ready::after {{
      content: "";
      position: absolute;
      top: 0;
      right: 0;
      width: 0;
      height: 0;
      border-top: 38px solid rgba(22, 101, 75, 0.58);
      border-left: 42px solid transparent;
    }}
    .job h3 {{
      margin: 0;
      font-size: 1.22rem;
      line-height: 1.28;
    }}
    .meta {{
      color: var(--muted);
      font-size: 0.92rem;
      margin-top: 6px;
      margin-bottom: 16px;
    }}
    .tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 16px;
    }}
    .tag {{
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.76rem;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.92);
      color: var(--ink);
      line-height: 1;
    }}
    .tag.good {{ color: var(--good); border-color: rgba(22,101,75,0.22); background: var(--good-soft); }}
    .tag.warn {{ color: var(--accent-2); border-color: rgba(202,122,44,0.22); background: var(--accent-2-soft); }}
    .tag.bad {{ color: var(--warn); border-color: rgba(185,28,28,0.22); background: var(--warn-soft); }}
    .job-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }}
    .row {{
      font-size: 0.95rem;
      line-height: 1.45;
    }}
    .label {{
      color: var(--muted);
      font-weight: 700;
      margin-right: 6px;
    }}
    .job-link {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      max-width: 100%;
      padding: 8px 10px;
      border-radius: 12px;
      background: rgba(19, 118, 111, 0.06);
      border: 1px solid rgba(19, 118, 111, 0.12);
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
      overflow-wrap: anywhere;
    }}
    .job-link small {{
      color: var(--muted);
      font-weight: 500;
    }}
    .desc {{
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.55;
      padding-top: 14px;
    }}
    .source-note {{
      margin-top: 16px;
      padding: 12px 14px 10px;
      border-radius: 14px;
      background: rgba(237, 243, 246, 0.78);
      border: 1px solid rgba(214, 224, 232, 0.9);
    }}
    .source-note-label {{
      display: inline-block;
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .muted {{ color: var(--muted); }}
    .flash {{
      background: rgba(19,118,111,0.12);
      border: 1px solid rgba(19,118,111,0.22);
      border-radius: 18px;
      padding: 14px 16px;
      margin-bottom: 18px;
      font-size: 0.96rem;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
    }}
    .actions form {{
      margin: 0;
    }}
    .actions button {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 999px;
      padding: 8px 13px;
      cursor: pointer;
      font-size: 0.8rem;
      font-weight: 600;
      transition: transform 120ms ease, background 120ms ease;
    }}
    .actions button:hover {{
      transform: translateY(-1px);
    }}
    .actions button.primary {{
      background: var(--good-soft);
      border-color: rgba(22,101,52,0.24);
      color: var(--good);
    }}
    .actions button.secondary {{
      background: var(--accent-soft);
      border-color: rgba(19,118,111,0.24);
      color: var(--accent);
    }}
    .actions button.warn {{
      background: var(--accent-2-soft);
      border-color: rgba(180,83,9,0.24);
      color: var(--accent-2);
    }}
    .actions button.bad {{
      background: var(--warn-soft);
      border-color: rgba(185,28,28,0.22);
      color: var(--warn);
    }}
    .actions form.reject-form button {{
      box-shadow: inset 0 0 0 1px rgba(202,122,44,0.05);
    }}
    .modal-backdrop {{
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      background: rgba(23, 37, 61, 0.28);
      backdrop-filter: blur(3px);
      z-index: 1000;
    }}
    .modal-backdrop.open {{
      display: flex;
    }}
    .modal {{
      width: min(520px, 100%);
      background: rgba(255, 255, 255, 0.985);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 24px 60px rgba(23, 37, 61, 0.18);
      padding: 22px 22px 18px;
    }}
    .modal h3 {{
      margin: 0 0 10px;
      font-size: 1.4rem;
    }}
    .modal p {{
      margin: 0 0 12px;
      color: var(--muted);
      line-height: 1.5;
    }}
    .modal textarea {{
      width: 100%;
      min-height: 108px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      font: inherit;
      color: var(--ink);
      background: rgba(255,255,255,0.92);
      outline: none;
    }}
    .modal textarea:focus {{
      border-color: rgba(19,118,111,0.30);
      box-shadow: 0 0 0 3px rgba(19,118,111,0.08);
    }}
    .modal-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 12px;
    }}
    .modal-chip {{
      border: 1px solid var(--line);
      background: rgba(237, 243, 246, 0.72);
      color: var(--ink);
      border-radius: 999px;
      padding: 7px 11px;
      cursor: pointer;
      font-size: 0.8rem;
      line-height: 1;
      font-weight: 600;
    }}
    .modal-chip:hover {{
      background: rgba(19,118,111,0.08);
      border-color: rgba(19,118,111,0.18);
    }}
    .modal-meta {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 0.82rem;
    }}
    .modal-actions {{
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      margin-top: 16px;
    }}
    .modal-actions button {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 999px;
      padding: 9px 16px;
      cursor: pointer;
      font-size: 0.86rem;
      font-weight: 600;
    }}
    .modal-actions .primary {{
      background: var(--accent-2-soft);
      border-color: rgba(202,122,44,0.24);
      color: var(--accent-2);
    }}
    @media (max-width: 1080px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .sidebar {{ position: static; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    {flash_html}
    <section class="hero">
      <div class="eyebrow">Human-in-the-loop Job Review</div>
      <h1>Review Workbench</h1>
      <div class="sub">Diese Oberfl&auml;che priorisiert nicht einfach alle Funde, sondern genau die Jobs, bei denen die n&auml;chste Entscheidung sinnvoll ist: Quelle, Linkpfad, Beschreibungstiefe und fachlicher Fit.</div>
      <div class="hero-points">
        <div class="hero-point">Discovery von Bewertung getrennt</div>
        <div class="hero-point">Firmenquellen vor Jobboards</div>
        <div class="hero-point">Review statt Vollautomation</div>
      </div>
      <div class="stats">
        <div class="stat"><div class="k">Jobs Raw</div><div class="v">{total_raw}</div></div>
        <div class="stat"><div class="k">Jobs Scored</div><div class="v">{total_scored}</div></div>
        <div class="stat"><div class="k">Visible</div><div class="v">{total_visible}</div></div>
        <div class="stat"><div class="k">Resolved</div><div class="v">{total_hidden}</div></div>
        <div class="stat"><div class="k">Direct Apply</div><div class="v">{bucket_counts.get('autoapply_ready', 0)}</div></div>
        <div class="stat"><div class="k">Manual Ready</div><div class="v">{bucket_counts.get('manual_apply_ready', 0)}</div></div>
        <div class="stat"><div class="k">Open Review</div><div class="v">{bucket_counts.get('needs_review', 0)}</div></div>
      </div>
    </section>

    <div class="grid">
      <div>
        <section class="panel">
          <h2>Top 5 Jobs Heute</h2>
          <p>Die kurze Arbeitsliste f&uuml;r den n&auml;chsten Blick: priorisiert nach Review-Relevanz, Beschreibungstiefe, Linkqualit&auml;t und Score.</p>
          <div class="joblist">
            {''.join(_render_job_card(job, interactive=interactive) for job in top_jobs) or '<div class="muted">Keine Jobs verf&uuml;gbar.</div>'}
          </div>
        </section>

        <section class="panel">
          <h2>Warum Nicht Ready</h2>
          <p>Hier liegen gute oder fast gute Jobs, die noch an Quelle, Linkpfad oder offenen Risiken h&auml;ngen.</p>
          <div class="joblist">
            {''.join(_render_job_card(job, compact=True, interactive=interactive) for job in review_jobs) or '<div class="muted">Keine offenen Review-Jobs.</div>'}
          </div>
        </section>
      </div>

      <div class="sidebar">
        <section class="panel">
          <h2>Warum Diese Jobs</h2>
          <p>Verdichtete Begr&uuml;ndung f&uuml;r die aktuelle Top-Auswahl: Fit, Arbeitsaufwand und realer Bewerbungsweg.</p>
          <table class="top-reasons-table">
            <thead><tr><th>Job</th><th>Score</th><th>Bucket</th></tr></thead>
            <tbody>
              {''.join(_render_top_reason_row(job) for job in top_jobs)}
            </tbody>
          </table>
        </section>

        <section class="panel">
          <h2>Welche Quellen Liefern Wert</h2>
          <p>Nicht nur Menge, sondern was nach Bewertung und Filterung wirklich übrig bleibt. So wird schnell sichtbar, welche Quellen echte Arbeit sparen.</p>
          <table class="source-value-table">
            <thead><tr><th>Quelle</th><th>Jobs</th><th>High</th><th>Medium</th><th>Ready</th></tr></thead>
            <tbody>
              {''.join(_render_source_value_row(row) for row in source_value_rows)}
            </tbody>
          </table>
        </section>

        <section class="panel">
          <h2>Linkqualit&auml;t</h2>
          <table>
            <thead><tr><th>Qualit&auml;t</th><th>Anzahl</th></tr></thead>
            <tbody>
              {''.join(f"<tr><td>{_escape_display(label)}</td><td>{count}</td></tr>" for label, count in link_quality_counts.items())}
            </tbody>
          </table>
        </section>

        <section class="panel">
          <h2>Beschreibungsqualit&auml;t</h2>
          <table>
            <thead><tr><th>Qualit&auml;t</th><th>Anzahl</th></tr></thead>
            <tbody>
              {''.join(f"<tr><td>{_escape_display(label)}</td><td>{count}</td></tr>" for label, count in description_quality_counts.items())}
            </tbody>
          </table>
        </section>

        <section class="panel">
          <h2>Bucket-Stand</h2>
          <table>
            <thead><tr><th>Bucket</th><th>Anzahl</th></tr></thead>
            <tbody>
              {''.join(f"<tr><td>{_escape_display(label)}</td><td>{count}</td></tr>" for label, count in bucket_counts.items())}
            </tbody>
          </table>
        </section>

        <section class="panel">
          <h2>Ausgeblendet</h2>
          <p>Bereits bearbeitete oder final aussortierte Jobs erscheinen nicht mehr in der aktiven Arbeitsliste.</p>
          <table>
            <thead><tr><th>Grund</th><th>Anzahl</th></tr></thead>
            <tbody>
              {''.join(f"<tr><td>{_escape_display(label)}</td><td>{count}</td></tr>" for label, count in hidden_counts.items()) or '<tr><td colspan="2" class="muted">Nichts ausgeblendet.</td></tr>'}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  </div>
  <div class="modal-backdrop" id="reject-modal" aria-hidden="true">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="reject-modal-title">
      <h3 id="reject-modal-title">Ablehnungsgrund</h3>
      <div class="modal-chips">
        <button type="button" class="modal-chip" data-note="falsche Richtung oder Spezialisierung">Falsche Richtung</button>
        <button type="button" class="modal-chip" data-note="zu research-lastig">Research-lastig</button>
        <button type="button" class="modal-chip" data-note="zu senior">Zu senior</button>
        <button type="button" class="modal-chip" data-note="zu viel Consulting">Zu viel Consulting</button>
        <button type="button" class="modal-chip" data-note="Studium hart vorausgesetzt">Studium vorausgesetzt</button>
        <button type="button" class="modal-chip" data-note="zu wenig Infos">Zu wenig Infos</button>
        <button type="button" class="modal-chip" data-note="Link kaputt oder instabil">Link kaputt</button>
        <button type="button" class="modal-chip" data-note="falscher Ort">Falscher Ort</button>
      </div>
      <textarea id="reject-note-input" maxlength="255" placeholder="z. B. falsche Richtung oder Spezialisierung"></textarea>
      <div class="modal-meta">
        <span id="reject-note-counter">0 / 255</span>
      </div>
      <div class="modal-actions">
        <button type="button" id="reject-cancel">Abbrechen</button>
        <button type="button" class="primary" id="reject-confirm">Speichern</button>
      </div>
    </div>
  </div>
  <script>
    document.addEventListener("DOMContentLoaded", function () {{
      var modal = document.getElementById("reject-modal");
      var input = document.getElementById("reject-note-input");
      var counter = document.getElementById("reject-note-counter");
      var cancelBtn = document.getElementById("reject-cancel");
      var confirmBtn = document.getElementById("reject-confirm");
      var chips = document.querySelectorAll(".modal-chip");
      var pendingForm = null;

      function updateCounter() {{
        counter.textContent = (input.value || "").length + " / 255";
      }}

      function closeModal() {{
        modal.classList.remove("open");
        modal.setAttribute("aria-hidden", "true");
        pendingForm = null;
      }}

      function openModal(form) {{
        pendingForm = form;
        var field = form.querySelector('input[name="note"]');
        input.value = field ? (field.value || "") : "";
        updateCounter();
        modal.classList.add("open");
        modal.setAttribute("aria-hidden", "false");
        window.setTimeout(function () {{
          input.focus();
          input.setSelectionRange(input.value.length, input.value.length);
        }}, 0);
      }}

      document.querySelectorAll(".reject-form").forEach(function (form) {{
        form.addEventListener("submit", function (event) {{
          event.preventDefault();
          openModal(form);
        }});
      }});

      chips.forEach(function (chip) {{
        chip.addEventListener("click", function () {{
          var note = chip.getAttribute("data-note") || "";
          var current = (input.value || "").trim();
          if (!current) {{
            input.value = note;
          }} else if (current !== note && !current.toLowerCase().includes(note.toLowerCase())) {{
            input.value = (current + "; " + note).slice(0, 255);
          }}
          updateCounter();
          input.focus();
          input.setSelectionRange(input.value.length, input.value.length);
        }});
      }});

      input.addEventListener("input", updateCounter);
      cancelBtn.addEventListener("click", closeModal);
      confirmBtn.addEventListener("click", function () {{
        if (!pendingForm) return;
        var field = pendingForm.querySelector('input[name="note"]');
        if (field) {{
          field.value = (input.value || "").trim().slice(0, 255);
        }}
        pendingForm.submit();
      }});

      modal.addEventListener("click", function (event) {{
        if (event.target === modal) {{
          closeModal();
        }}
      }});

      document.addEventListener("keydown", function (event) {{
        if (!modal.classList.contains("open")) return;
        if (event.key === "Escape") {{
          closeModal();
        }}
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {{
          confirmBtn.click();
        }}
      }});
    }});
  </script>
</body>
</html>
"""


def _render_job_card(job: dict, *, compact: bool = False, interactive: bool = False) -> str:
    title = _escape_display(job.get("title") or "Ohne Titel")
    company = _escape_display(job.get("company") or "Unbekannt")
    location = _escape_display(job.get("location") or "")
    source = _escape_display(job.get("source") or "")
    bucket = _escape_display(job.get("final_bucket") or "unknown")
    score = _escape_display(job.get("score") or "-")
    kind = _escape_display(job.get("best_link_kind") or "")
    link_quality = str(job.get("best_link_quality") or "unknown")
    quality_class = "good" if link_quality == "high" else "warn" if link_quality == "medium" else "bad"
    description_quality = str(job.get("description_quality") or "unknown")
    description_class = "good" if description_quality == "high" else "warn" if description_quality == "medium" else "bad"
    why = _escape_display(_why_job(job))
    reason = _escape_display(job.get("best_link_reason") or "")
    description_reason = _escape_display(job.get("description_reason") or "")
    link_url = str(job.get("best_link") or "").strip()
    link_host = _escape_display(_display_link_label(link_url))
    link_meta = _escape_display(_display_link_meta(link_url))
    description = " ".join(_clean_text(job.get("description") or "").split())[:260]
    actions_html = _render_actions(job) if interactive else ""

    link_html = '<span class="muted">Kein brauchbarer Link</span>'
    if link_url:
        link_html = (
            f'<a class="job-link" href="{html.escape(link_url)}" target="_blank" rel="noopener noreferrer">'
            f"{link_host}<small>{link_meta}</small></a>"
        )

    description_html = ""
    if not compact and description:
        description_html = (
            '<div class="source-note">'
            '<span class="source-note-label">Quellnotiz</span>'
            f'<div class="desc">{html.escape(description)}</div>'
            "</div>"
        )

    meta = _escape_display(_compose_meta(company, location, source))
    card_class = "job ready" if str(job.get("final_bucket") or "") == "manual_apply_ready" else "job"

    return f"""
    <article class="{card_class}">
      <h3>{title}</h3>
      <div class="meta">{meta}</div>
      <div class="tags">
        <span class="tag">{bucket}</span>
        <span class="tag">{score}</span>
        <span class="tag {quality_class}">{_escape_display(link_quality)}</span>
        <span class="tag {description_class}">desc {_escape_display(description_quality)}</span>
        <span class="tag">{kind}</span>
      </div>
      <div class="job-grid">
        <div class="row"><span class="label">Warum</span>{why}</div>
        <div class="row"><span class="label">Link</span>{link_html}</div>
        <div class="row muted"><span class="label">Grund</span>{reason}</div>
        <div class="row muted"><span class="label">Beschreibung</span>{description_reason}</div>
      </div>
      {actions_html}
      {description_html}
    </article>
    """


def _bucket_rank(bucket: str) -> int:
    order = {
        "autoapply_ready": 0,
        "manual_apply_ready": 1,
        "needs_review": 2,
        "rejected": 3,
    }
    return order.get(bucket, 9)


def _link_quality_rank(quality: str) -> int:
    order = {"high": 0, "medium": 1, "low": 2}
    return order.get(quality, 9)


def _description_quality_rank(quality: str) -> int:
    order = {"high": 0, "medium": 1, "low": 2}
    return order.get(quality, 9)


def _why_job(job: dict) -> str:
    parts = []
    score = job.get("score")
    if score not in (None, ""):
        parts.append(f"Score {score}")
    delta = float(job.get("feedback_delta") or 0)
    if abs(delta) >= 0.1:
        parts.append(f"Feedback {'+' if delta > 0 else ''}{delta:g}")
    bucket = job.get("final_bucket")
    if bucket:
        parts.append(f"Bucket {bucket}")
    quality = job.get("best_link_quality")
    if quality:
        parts.append(f"Link {quality}")
    description_quality = job.get("description_quality")
    if description_quality:
        parts.append(f"Desc {description_quality}")
    kind = job.get("best_link_kind")
    if kind:
        parts.append(kind)
    return " | ".join(parts) or "Noch keine ausreichenden Signale"


def _build_source_value_rows(rows: list[dict]) -> list[dict]:
    per_source: dict[str, dict] = {}
    for job in rows:
        source = (job.get("source") or "unknown").strip() or "unknown"
        row = per_source.setdefault(
            source,
            {"source": source, "jobs": 0, "high": 0, "medium": 0, "ready": 0},
        )
        row["jobs"] += 1
        quality = job.get("best_link_quality")
        if quality == "high":
            row["high"] += 1
        if quality == "medium":
            row["medium"] += 1
        if job.get("final_bucket") in {"autoapply_ready", "manual_apply_ready"}:
            row["ready"] += 1
    return sorted(
        per_source.values(),
        key=lambda item: (-item["ready"], -item["high"], -item["medium"], -item["jobs"], item["source"]),
    )


def _render_top_reason_row(job: dict) -> str:
    return (
        "<tr>"
        f"<td>{_escape_display(job.get('title') or 'Ohne Titel')}</td>"
        f"<td>{_escape_display(job.get('score') or '-')}</td>"
        f"<td>{_escape_display(job.get('final_bucket') or 'unknown')}</td>"
        "</tr>"
    )


def _render_source_value_row(row: dict) -> str:
    return (
        "<tr>"
        f"<td>{_escape_display(row['source'])}</td>"
        f"<td>{row['jobs']}</td>"
        f"<td>{row['high']}</td>"
        f"<td>{row['medium']}</td>"
        f"<td>{row['ready']}</td>"
        "</tr>"
    )


def _render_actions(job: dict) -> str:
    job_id = str(job.get("id") or "").strip()
    if not job_id:
        return ""
    escaped_id = html.escape(job_id)
    return f"""
    <div class="actions">
      {_action_form(escaped_id, "generate_application", "Unterlagen", css_class="secondary")}
      {_action_form(escaped_id, "mark_applied", "Beworben", css_class="primary")}
      {_action_form(escaped_id, "verify_ready", "Freigeben")}
      {_action_form(escaped_id, "reject", "Reject", css_class="warn")}
      {_action_form(escaped_id, "dead_listing", "Dead Listing", css_class="bad")}
    </div>
    """


def _action_form(job_id: str, action: str, label: str, css_class: str = "") -> str:
    class_attr = f' class="{css_class}"' if css_class else ""
    form_class = ' class="reject-form"' if action == "reject" else ""
    return (
        f'<form method="post" action="/action"{form_class}>'
        f'<input type="hidden" name="job_id" value="{job_id}">'
        f'<input type="hidden" name="action" value="{html.escape(action)}">'
        '<input type="hidden" name="note" value="">'
        f'<button type="submit"{class_attr}>{html.escape(label)}</button>'
        "</form>"
    )


def _display_link_label(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.replace("www.", "")
    return host or url[:48]


def _display_link_meta(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if len(path) > 46:
        path = path[:43] + "..."
    return path


def _compose_meta(*parts: str) -> str:
    clean_parts = [part.strip() for part in parts if part and part.strip()]
    return " · ".join(clean_parts)


def _escape_display(value: object) -> str:
    return html.escape(_clean_text(value))


def _clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))

    for _ in range(2):
        if not any(marker in text for marker in ("\u00c3", "\u00c2", "\u00e2", "\u00f0", "\ufffd")):
            break
        repaired = _try_redecode(text)
        if not repaired or repaired == text:
            break
        text = repaired

    replacements = {
        "\xa0": " ",
        "\u00c2\u00b7": "·",
        "\u00e2\u20ac\u201c": "–",
        "\u00e2\u20ac\u201d": "—",
        "\u00e2\u20ac\u017e": "„",
        "\u00e2\u20ac\u0153": "“",
        "\u00e2\u20ac\u0161": "‚",
        "\u00e2\u20ac\u2122": "’",
        "\u00e2\u20ac\u02dc": "‘",
        "\u00e2\u20ac\u00a6": "…",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _try_redecode(text: str) -> str:
    for source_encoding in ("latin-1", "cp1252"):
        try:
            return text.encode(source_encoding).decode("utf-8")
        except Exception:
            continue
    return text


if __name__ == "__main__":
    path = generate_present_dashboard()
    print(path)
