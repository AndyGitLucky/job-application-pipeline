from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from source.project_paths import resolve_runtime_path, runtime_path

DEFAULT_JOBS_PATH = runtime_path("jobs_scored.json")
DEFAULT_EVAL_LOG_PATH = runtime_path("job_similarity_eval.json")
DEFAULT_BATCH_SIZE = 8
ALLOWED_DECISIONS = {"merge_ok", "not_same_job", "unclear"}
SUMMARY_THRESHOLDS = (0.85, 0.8, 0.75, 0.7)


def load_similarity_jobs(jobs_path: str | Path | None = None) -> list[dict]:
    path = resolve_runtime_path(jobs_path or DEFAULT_JOBS_PATH)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def load_eval_log(log_path: str | Path | None = None) -> dict:
    path = resolve_runtime_path(log_path or DEFAULT_EVAL_LOG_PATH)
    if not path.exists():
        return {"decisions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("decisions"), dict):
            return payload
    except Exception:
        pass
    return {"decisions": {}}


def save_eval_log(payload: dict, log_path: str | Path | None = None) -> Path:
    path = resolve_runtime_path(log_path or DEFAULT_EVAL_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def pair_key(left_id: str, right_id: str) -> str:
    ordered = sorted([str(left_id), str(right_id)])
    return "||".join(ordered)


def build_similarity_pairs(jobs: list[dict]) -> list[dict]:
    by_id = {str(job.get("id") or ""): job for job in jobs if str(job.get("id") or "").strip()}
    pairs: dict[str, dict] = {}

    for left in jobs:
        left_id = str(left.get("id") or "").strip()
        if not left_id:
            continue
        for hint in left.get("similar_job_hints") or []:
            right_id = str(hint.get("job_id") or "").strip()
            if not right_id or right_id == left_id or right_id not in by_id:
                continue
            key = pair_key(left_id, right_id)
            similarity = float(hint.get("similarity") or 0.0)
            candidate = {
                "pair_key": key,
                "left_id": left_id,
                "right_id": right_id,
                "similarity": similarity,
                "left": left,
                "right": by_id[right_id],
            }
            existing = pairs.get(key)
            if not existing or similarity > existing.get("similarity", 0.0):
                pairs[key] = candidate

    results = list(pairs.values())
    results.sort(
        key=lambda item: (
            -float(item.get("similarity") or 0.0),
            str(item["left"].get("company") or ""),
            str(item["left"].get("title") or ""),
        )
    )
    return results


def pending_similarity_pairs(
    jobs_path: str | Path | None = None,
    log_path: str | Path | None = None,
) -> tuple[list[dict], dict]:
    jobs = load_similarity_jobs(jobs_path)
    log = load_eval_log(log_path)
    decisions = log.get("decisions", {})
    pairs = [pair for pair in build_similarity_pairs(jobs) if pair["pair_key"] not in decisions]
    return pairs, log


def record_similarity_decision(
    left_id: str,
    right_id: str,
    decision: str,
    *,
    log_path: str | Path | None = None,
) -> str:
    decision = str(decision or "").strip().lower()
    if decision not in ALLOWED_DECISIONS:
        raise ValueError("unknown_decision")

    log = load_eval_log(log_path)
    key = pair_key(left_id, right_id)
    log.setdefault("decisions", {})[key] = {
        "left_id": str(left_id),
        "right_id": str(right_id),
        "decision": decision,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    save_eval_log(log, log_path=log_path)
    return key


def summarize_similarity_eval(
    *,
    jobs_path: str | Path | None = None,
    log_path: str | Path | None = None,
    thresholds: tuple[float, ...] = SUMMARY_THRESHOLDS,
) -> list[dict]:
    all_pairs = build_similarity_pairs(load_similarity_jobs(jobs_path))
    by_key = {pair["pair_key"]: pair for pair in all_pairs}
    decisions = load_eval_log(log_path).get("decisions", {})

    rows: list[dict] = []
    for threshold in thresholds:
        decided_pairs = [
            pair
            for key, pair in by_key.items()
            if pair.get("similarity", 0.0) >= threshold and key in decisions
        ]
        merge_ok = sum(1 for pair in decided_pairs if decisions[pair["pair_key"]]["decision"] == "merge_ok")
        not_same = sum(1 for pair in decided_pairs if decisions[pair["pair_key"]]["decision"] == "not_same_job")
        unclear = sum(1 for pair in decided_pairs if decisions[pair["pair_key"]]["decision"] == "unclear")
        decisive_total = merge_ok + not_same
        merge_rate = round(merge_ok / decisive_total, 2) if decisive_total else None
        rows.append(
            {
                "threshold": threshold,
                "total": len(decided_pairs),
                "merge_ok": merge_ok,
                "not_same_job": not_same,
                "unclear": unclear,
                "merge_rate": merge_rate,
            }
        )
    return rows


def render_similarity_eval_page(
    *,
    jobs_path: str | Path | None = None,
    log_path: str | Path | None = None,
    page: int = 1,
    batch_size: int = DEFAULT_BATCH_SIZE,
    action_message: str = "",
) -> str:
    pairs, log = pending_similarity_pairs(jobs_path, log_path)
    all_pairs = build_similarity_pairs(load_similarity_jobs(jobs_path))
    summary_rows = summarize_similarity_eval(jobs_path=jobs_path, log_path=log_path)
    total = len(all_pairs)
    decided = len(log.get("decisions", {}))
    pending = len(pairs)

    safe_batch_size = max(1, int(batch_size or DEFAULT_BATCH_SIZE))
    total_pages = max(1, (pending + safe_batch_size - 1) // safe_batch_size) if pending else 1
    current_page = max(1, min(int(page or 1), total_pages))
    start = (current_page - 1) * safe_batch_size
    batch = pairs[start : start + safe_batch_size]

    cards = "\n".join(_render_pair_card(pair, current_page, safe_batch_size) for pair in batch) or _empty_state()
    pager = _render_pager(current_page, total_pages, safe_batch_size) if pending else ""
    flash = f'<div class="flash">{html.escape(action_message)}</div>' if action_message else ""
    summary = _render_summary(summary_rows)

    return f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Embedding Eval</title>
  <style>
    :root {{
      --ink: #1d2c4a;
      --muted: #5f7397;
      --line: #c9d8ea;
      --teal: #117d79;
      --teal-soft: #e4f4f1;
      --amber: #b46c1c;
      --amber-soft: #fff2e5;
      --rose: #b6444f;
      --rose-soft: #fff0f1;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, 'Times New Roman', serif;
      background: linear-gradient(180deg, #edf3f8 0%, #eaf1f8 100%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1520px;
      margin: 0 auto;
      padding: 28px;
    }}
    .hero, .stats, .summary, .pair {{
      background: rgba(255,255,255,0.94);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: 0 18px 42px rgba(34, 57, 94, 0.08);
    }}
    .hero {{
      padding: 28px 32px;
      margin-bottom: 20px;
    }}
    .eyebrow {{
      display: inline-block;
      margin-bottom: 12px;
      padding: 7px 14px;
      border-radius: 999px;
      border: 1px solid #98d8d2;
      background: var(--teal-soft);
      color: var(--teal);
      font: 700 12px/1.2 system-ui, sans-serif;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 58px;
      line-height: 0.96;
    }}
    .lead {{
      margin: 0;
      color: var(--muted);
      font: 500 18px/1.6 system-ui, sans-serif;
      max-width: 960px;
    }}
    .flash {{
      margin: 0 0 18px;
      padding: 14px 18px;
      border: 1px solid #9fd4cb;
      border-radius: 18px;
      background: var(--teal-soft);
      color: var(--ink);
      font: 600 16px/1.4 system-ui, sans-serif;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      padding: 18px;
      margin-bottom: 20px;
    }}
    .stat {{
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: #fff;
    }}
    .stat-label {{
      color: #60759a;
      font: 700 12px/1 system-ui, sans-serif;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .stat-value {{
      font-size: 28px;
      font-weight: 700;
    }}
    .summary {{
      padding: 22px 24px;
      margin-bottom: 20px;
    }}
    .summary h2 {{
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.1;
    }}
    .summary p {{
      margin: 0 0 16px;
      color: var(--muted);
      font: 500 15px/1.6 system-ui, sans-serif;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font: 600 14px/1.45 system-ui, sans-serif;
    }}
    th, td {{
      padding: 11px 8px;
      text-align: left;
      border-top: 1px solid #deebf5;
    }}
    th {{
      color: #60759a;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 12px;
    }}
    td {{
      color: var(--ink);
    }}
    .pair {{
      padding: 24px;
      margin-bottom: 18px;
    }}
    .pair-top {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      margin-bottom: 18px;
    }}
    .pair-title {{
      font: 700 15px/1 system-ui, sans-serif;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #60759a;
    }}
    .sim-chip {{
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid #c9ded7;
      background: var(--teal-soft);
      color: var(--teal);
      font: 700 14px/1 system-ui, sans-serif;
    }}
    .cols {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
    .job {{
      padding: 20px;
      border: 1px solid var(--line);
      border-radius: 22px;
      background: #fff;
    }}
    .job h2 {{
      margin: 0 0 10px;
      font-size: 24px;
      line-height: 1.15;
    }}
    .meta, .desc, .small {{
      color: var(--muted);
      font: 500 16px/1.6 system-ui, sans-serif;
    }}
    .small {{
      font-size: 14px;
    }}
    .links {{
      margin-top: 12px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .links a {{
      color: #0a6d93;
      text-decoration: none;
      font: 600 14px/1.4 system-ui, sans-serif;
      word-break: break-all;
    }}
    .actions {{
      display: flex;
      gap: 12px;
      margin-top: 18px;
      flex-wrap: wrap;
    }}
    button {{
      border-radius: 999px;
      padding: 12px 18px;
      cursor: pointer;
      font: 700 16px/1 system-ui, sans-serif;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
    }}
    .ok {{
      background: var(--teal-soft);
      border-color: #9fd4cb;
      color: var(--teal);
    }}
    .bad {{
      background: var(--rose-soft);
      border-color: #f0c0c7;
      color: var(--rose);
    }}
    .meh {{
      background: var(--amber-soft);
      border-color: #efcfb0;
      color: var(--amber);
    }}
    .pager {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 18px;
      font: 600 15px/1.4 system-ui, sans-serif;
      color: var(--muted);
    }}
    .pager a {{
      color: var(--teal);
      text-decoration: none;
    }}
    .empty {{
      padding: 32px;
      border: 1px dashed var(--line);
      border-radius: 22px;
      background: rgba(255,255,255,0.76);
      color: var(--muted);
      font: 500 17px/1.6 system-ui, sans-serif;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    {flash}
    <section class="hero">
      <div class="eyebrow">Embedding Eval</div>
      <h1>Ähnliche Jobs prüfen</h1>
      <p class="lead">Batchweise Review der semantischen Job-Hinweise. Ziel ist noch kein Auto-Merge, sondern zu lernen, wann Similarity wirklich „gleicher Job“ bedeutet.</p>
    </section>
    <section class="stats">
      <div class="stat"><div class="stat-label">Paare gesamt</div><div class="stat-value">{total}</div></div>
      <div class="stat"><div class="stat-label">Entschieden</div><div class="stat-value">{decided}</div></div>
      <div class="stat"><div class="stat-label">Offen</div><div class="stat-value">{pending}</div></div>
      <div class="stat"><div class="stat-label">Batch</div><div class="stat-value">{current_page}/{total_pages}</div></div>
    </section>
    {summary}
    {cards}
    {pager}
  </div>
</body>
</html>"""


def _render_pair_card(pair: dict, page: int, batch_size: int) -> str:
    similarity = float(pair.get("similarity") or 0.0)
    return f"""
    <section class="pair">
      <div class="pair-top">
        <div class="pair-title">Duplicate-Verdacht</div>
        <div class="sim-chip">Similarity {similarity:.2f}</div>
      </div>
      <div class="cols">
        {_render_job_side(pair["left"], label="A")}
        {_render_job_side(pair["right"], label="B")}
      </div>
      <form class="actions" method="post" action="/embedding-eval/action">
        <input type="hidden" name="left_id" value="{html.escape(str(pair['left_id']))}">
        <input type="hidden" name="right_id" value="{html.escape(str(pair['right_id']))}">
        <input type="hidden" name="page" value="{page}">
        <input type="hidden" name="batch_size" value="{batch_size}">
        <button class="ok" type="submit" name="decision" value="merge_ok">Merge OK</button>
        <button class="bad" type="submit" name="decision" value="not_same_job">Not Same Job</button>
        <button class="meh" type="submit" name="decision" value="unclear">Unsicher</button>
      </form>
    </section>
    """


def _render_job_side(job: dict, *, label: str) -> str:
    title = html.escape(str(job.get("title") or ""))
    company = html.escape(str(job.get("company") or "Unbekannt"))
    location = html.escape(str(job.get("location") or ""))
    source = html.escape(str(job.get("source") or ""))
    bucket = html.escape(str(job.get("final_bucket") or ""))
    raw_link = str(job.get("best_link") or job.get("url") or "").strip()
    description = html.escape(str(job.get("description") or "")[:380])
    link_markup = (
        f'<div class="links"><a href="{html.escape(raw_link)}" target="_blank" rel="noopener noreferrer">{html.escape(raw_link)}</a></div>'
        if raw_link
        else '<div class="small">Kein Link hinterlegt.</div>'
    )
    return f"""
      <article class="job">
        <div class="pair-title">Job {label}</div>
        <h2>{title}</h2>
        <div class="meta">{company} · {location} · {source}</div>
        <div class="small">Bucket: {bucket} · Score: {job.get("score", "-")} · Linktyp: {html.escape(str(job.get("best_link_kind") or ""))}</div>
        {link_markup}
        <p class="desc">{description}</p>
      </article>
    """


def _render_summary(rows: list[dict]) -> str:
    body = []
    for row in rows:
        merge_rate = "—" if row["merge_rate"] is None else f"{int(row['merge_rate'] * 100)}%"
        body.append(
            "<tr>"
            f"<td>≥ {row['threshold']:.2f}</td>"
            f"<td>{row['total']}</td>"
            f"<td>{row['merge_ok']}</td>"
            f"<td>{row['not_same_job']}</td>"
            f"<td>{row['unclear']}</td>"
            f"<td>{merge_rate}</td>"
            "</tr>"
        )
    rows_markup = "".join(body)
    return (
        '<section class="summary">'
        '<h2>Was die bisherigen Entscheidungen sagen</h2>'
        '<p>Die Tabelle zeigt nur bereits entschiedene Paare. So sehen wir schnell, ab welchen Similarity-Werten ein späterer Auto-Merge realistisch wäre.</p>'
        '<table>'
        '<thead><tr><th>Threshold</th><th>Entschieden</th><th>Merge OK</th><th>Not Same</th><th>Unsicher</th><th>Merge-Rate</th></tr></thead>'
        f'<tbody>{rows_markup}</tbody>'
        '</table>'
        '</section>'
    )


def _empty_state() -> str:
    return '<div class="empty">Keine offenen Similarity-Paare mehr. Der aktuelle Embedding-Eval-Lauf ist abgearbeitet.</div>'


def _render_pager(page: int, total_pages: int, batch_size: int) -> str:
    prev_link = (
        f'<a href="/embedding-eval?{urlencode({"page": page - 1, "batch_size": batch_size})}">← Vorheriger Batch</a>'
        if page > 1
        else "<span></span>"
    )
    next_link = (
        f'<a href="/embedding-eval?{urlencode({"page": page + 1, "batch_size": batch_size})}">Nächster Batch →</a>'
        if page < total_pages
        else "<span></span>"
    )
    return f'<div class="pager">{prev_link}<span>Seite {page} von {total_pages}</span>{next_link}</div>'
