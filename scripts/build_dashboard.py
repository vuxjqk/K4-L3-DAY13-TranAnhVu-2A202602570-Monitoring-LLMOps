"""Dựng dashboard 6 panel từ data/logs.jsonl theo contract config/dashboard.yaml.

    python scripts/build_dashboard.py            # ghi data/dashboard.html một lần
    python scripts/build_dashboard.py --watch    # dựng lại mỗi refresh_seconds

Mở file HTML bằng trình duyệt; trang tự reload theo refresh_seconds.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.metrics import percentile

LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
OUT_PATH = REPO_ROOT / "data" / "dashboard.html"

COLORS = ["#2563eb", "#d97706", "#dc2626", "#059669"]


def load_events(path: Path) -> list[dict]:
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
            event["_ts"] = datetime.fromisoformat(event["ts"].replace("Z", "+00:00"))
            events.append(event)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return events


def bucket_by_minute(events: list[dict], start: datetime, minutes: int) -> list[list[dict]]:
    buckets: list[list[dict]] = [[] for _ in range(minutes)]
    for event in events:
        idx = int((event["_ts"] - start).total_seconds() // 60)
        if 0 <= idx < minutes:
            buckets[idx].append(event)
    return buckets


def line_chart(series: list[tuple[str, list[float | None]]], threshold: float | None, unit: str) -> str:
    width, height, pad_l, pad_b, pad_t = 560, 200, 56, 24, 10
    values = [v for _, vals in series for v in vals if v is not None]
    y_max = max(values + ([threshold] if threshold is not None else []) + [1e-9]) * 1.15
    n = max(len(vals) for _, vals in series)
    plot_w, plot_h = width - pad_l - 8, height - pad_b - pad_t

    def x(i: int) -> float:
        return pad_l + (i / max(1, n - 1)) * plot_w

    def y(v: float) -> float:
        return pad_t + plot_h - (v / y_max) * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">']
    for frac in (0, 0.5, 1):
        gy = pad_t + plot_h - frac * plot_h
        parts.append(f'<line x1="{pad_l}" x2="{width - 8}" y1="{gy:.1f}" y2="{gy:.1f}" class="grid"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{gy + 4:.1f}" class="axis" text-anchor="end">{fmt(y_max * frac)}</text>')
    for label, i in (("-60m", 0), ("-30m", n // 2), ("now", n - 1)):
        parts.append(f'<text x="{x(i):.1f}" y="{height - 6}" class="axis" text-anchor="middle">{label}</text>')
    if threshold is not None:
        ty = y(threshold)
        parts.append(f'<line x1="{pad_l}" x2="{width - 8}" y1="{ty:.1f}" y2="{ty:.1f}" class="threshold"/>')
        parts.append(f'<text x="{width - 10}" y="{ty - 4:.1f}" class="threshold-label" text-anchor="end">threshold {fmt(threshold)} {unit}</text>')
    for (name, vals), color in zip(series, COLORS):
        points = [(x(i), y(v)) for i, v in enumerate(vals) if v is not None]
        if len(points) > 1:
            path = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
            parts.append(f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2"/>')
        for px, py in points:
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.5" fill="{color}"/>')
    parts.append("</svg>")
    legend = "".join(
        f'<span class="legend"><i style="background:{c}"></i>{html.escape(name)}</span>'
        for (name, _), c in zip(series, COLORS)
    )
    return legend + "".join(parts)


def fmt(v: float) -> str:
    if v == 0:
        return "0"
    if abs(v) >= 100:
        return f"{v:,.0f}"
    if abs(v) >= 1:
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{v:.4f}".rstrip("0").rstrip(".")


def status(value: float, threshold: dict) -> str:
    ok = value <= threshold["value"] if threshold["operator"] == "lte" else value >= threshold["value"]
    return "ok" if ok else "breach"


def build(config: dict, events: list[dict]) -> str:
    dash = config["dashboard"]
    panels = {p["id"]: p for p in dash["panels"]}
    minutes = dash["time_range_minutes"]
    end = max((e["_ts"] for e in events), default=datetime.now(timezone.utc))
    end = end.replace(second=59, microsecond=999999)
    start = end - timedelta(minutes=minutes) + timedelta(microseconds=1)
    window = [e for e in events if start <= e["_ts"] <= end]
    buckets = bucket_by_minute(window, start, minutes)

    responses = [e for e in window if e.get("event") == "response_sent"]
    received = [e for e in window if e.get("event") == "request_received"]
    failed = [e for e in window if e.get("event") == "request_failed"]
    tool_events = [e for e in window if e.get("tool_success") is not None]

    def per_minute(fn):
        return [fn(b) for b in buckets]

    def resp(b):
        return [e for e in b if e.get("event") == "response_sent"]

    def pct(vals, p):
        return percentile(vals, p) if vals else None

    cards = []

    # 1. Latency
    lat = [e["latency_ms"] for e in responses]
    ttft = [e["ttft_ms"] for e in responses]
    agg = {"p50": pct(lat, 50) or 0, "p95": pct(lat, 95) or 0, "p99": pct(lat, 99) or 0, "ttft_p95": pct(ttft, 95) or 0}
    p = panels["latency"]
    cards.append((p, agg["p95"], [("P50", agg["p50"]), ("P95", agg["p95"]), ("P99", agg["p99"]), ("TTFT P95", agg["ttft_p95"])],
        line_chart([
            ("latency P50", per_minute(lambda b: pct([e["latency_ms"] for e in resp(b)], 50))),
            ("latency P95", per_minute(lambda b: pct([e["latency_ms"] for e in resp(b)], 95))),
            ("latency P99", per_minute(lambda b: pct([e["latency_ms"] for e in resp(b)], 99))),
            ("TTFT P95", per_minute(lambda b: pct([e["ttft_ms"] for e in resp(b)], 95))),
        ], p["threshold"]["value"], p["unit"])))

    # 2. Traffic
    p = panels["traffic"]
    active_minutes = sum(1 for b in buckets if any(e.get("event") == "request_received" for e in b))
    rate = len(received) / active_minutes if active_minutes else 0.0
    cards.append((p, rate, [("count", len(received)), ("avg req/min (active)", rate)],
        line_chart([("requests/min", per_minute(lambda b: sum(1 for e in b if e.get("event") == "request_received") or None))],
                   p["threshold"]["value"], p["unit"])))

    # 3. Errors + retrieval success
    p = panels["errors"]
    err_rate = len(failed) / len(received) * 100 if received else 0.0
    tool_rate = sum(1 for e in tool_events if e["tool_success"]) / len(tool_events) * 100 if tool_events else 100.0
    breakdown = Counter(e.get("error_type", "unknown") for e in failed)
    breakdown_text = ", ".join(f"{k}: {v}" for k, v in breakdown.items()) or "không có lỗi"

    def minute_err(b):
        rec = sum(1 for e in b if e.get("event") == "request_received")
        return sum(1 for e in b if e.get("event") == "request_failed") / rec * 100 if rec else None

    def minute_tool(b):
        t = [e for e in b if e.get("tool_success") is not None]
        return sum(1 for e in t if e["tool_success"]) / len(t) * 100 if t else None

    cards.append((p, err_rate, [("error rate %", err_rate), ("retrieval success %", tool_rate), ("breakdown", breakdown_text)],
        line_chart([("error rate %", per_minute(minute_err)), ("retrieval success %", per_minute(minute_tool))],
                   p["threshold"]["value"], p["unit"])))

    # 4. Cost
    p = panels["cost"]
    total_cost = sum(e["cost_usd"] for e in responses)
    cards.append((p, total_cost, [("total", f"${total_cost:.4f}"), ("avg/request", f"${total_cost / len(responses):.6f}" if responses else "-")],
        line_chart([("cost/min", per_minute(lambda b: sum(e["cost_usd"] for e in resp(b)) or None))], None, p["unit"])
        + f'<p class="note">Threshold {p["threshold"]["value"]} {p["unit"]} áp dụng cho tổng cửa sổ (hiện {total_cost / p["threshold"]["value"] * 100:.2f}% ngưỡng).</p>'))

    # 5. Tokens
    p = panels["tokens"]
    tin, tout = sum(e["tokens_in"] for e in responses), sum(e["tokens_out"] for e in responses)
    cards.append((p, max(tin, tout), [("tokens_in", tin), ("tokens_out", tout)],
        line_chart([
            ("tokens_in/min", per_minute(lambda b: sum(e["tokens_in"] for e in resp(b)) or None)),
            ("tokens_out/min", per_minute(lambda b: sum(e["tokens_out"] for e in resp(b)) or None)),
        ], None, p["unit"])
        + f'<p class="note">Threshold {p["threshold"]["value"]:,} {p["unit"]} cho mỗi field trong cửa sổ.</p>'))

    # 6. Quality
    p = panels["quality"]
    q = [e["quality_score"] for e in responses]
    q_mean = sum(q) / len(q) if q else 0.0
    cards.append((p, q_mean, [("mean", q_mean), ("n", len(q))],
        line_chart([("mean quality", per_minute(lambda b: (sum(e["quality_score"] for e in resp(b)) / len(resp(b))) if resp(b) else None))],
                   p["threshold"]["value"], p["unit"])))

    card_html = []
    for panel, headline, stats, chart in cards:
        th = panel["threshold"]
        st = status(headline, th)
        op = "≤" if th["operator"] == "lte" else "≥"
        stat_html = "".join(
            f'<div class="stat"><span>{html.escape(str(k))}</span><b>{html.escape(fmt(v) if isinstance(v, (int, float)) else str(v))}</b></div>'
            for k, v in stats
        )
        card_html.append(f"""
<section class="card {st}">
  <header><h2>{html.escape(panel['title'])}</h2><span class="badge {st}">{'OK' if st == 'ok' else 'BREACH'}</span></header>
  <p class="meta">unit: <code>{html.escape(panel['unit'])}</code> · threshold: {th['aggregation']} {op} {fmt(th['value'])}</p>
  <div class="stats">{stat_html}</div>
  {chart}
</section>""")

    local = timezone(timedelta(hours=7))
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{dash['refresh_seconds']}">
<title>{html.escape(dash['title'])}</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --fg:#111827; --muted:#6b7280; --grid:#e5e7eb; --ok:#059669; --bad:#dc2626; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1115; --card:#181b21; --fg:#e5e7eb; --muted:#9ca3af; --grid:#2a2f38; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:16px; background:var(--bg); color:var(--fg); font:14px/1.4 system-ui,-apple-system,Segoe UI,sans-serif; }}
h1 {{ font-size:20px; margin:0 0 4px; }}
.sub {{ color:var(--muted); margin:0 0 16px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr)); gap:16px; }}
.card {{ background:var(--card); border-radius:10px; padding:14px 16px; border-top:4px solid var(--ok); }}
.card.breach {{ border-top-color:var(--bad); }}
.card header {{ display:flex; justify-content:space-between; align-items:center; }}
.card h2 {{ font-size:16px; margin:0; }}
.badge {{ font-size:11px; font-weight:700; padding:2px 8px; border-radius:99px; color:#fff; background:var(--ok); }}
.badge.breach {{ background:var(--bad); }}
.meta,.note {{ color:var(--muted); font-size:12px; margin:4px 0 8px; }}
.stats {{ display:flex; flex-wrap:wrap; gap:8px 20px; margin-bottom:6px; }}
.stat span {{ display:block; color:var(--muted); font-size:11px; }}
.stat b {{ font-size:18px; font-variant-numeric:tabular-nums; }}
.chart {{ width:100%; height:auto; display:block; }}
.chart .grid {{ stroke:var(--grid); stroke-width:1; }}
.chart .axis {{ fill:var(--muted); font-size:10px; }}
.chart .threshold {{ stroke:var(--bad); stroke-dasharray:5 4; stroke-width:1.5; }}
.chart .threshold-label {{ fill:var(--bad); font-size:10px; }}
.legend {{ display:inline-flex; align-items:center; gap:4px; margin-right:12px; font-size:12px; color:var(--muted); }}
.legend i {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}
</style></head><body>
<h1>{html.escape(dash['title'])}</h1>
<p class="sub">Nguồn: <code>data/logs.jsonl</code> · Time range: {minutes} phút
({start.astimezone(local):%H:%M} → {end.astimezone(local):%H:%M} UTC+7) · refresh {dash['refresh_seconds']}s ·
{len(received)} requests · build lúc {datetime.now(local):%Y-%m-%d %H:%M:%S}</p>
<div class="grid">{''.join(card_html)}</div>
</body></html>"""


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    while True:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(build(config, load_events(LOG_PATH)), encoding="utf-8")
        print(f"Đã ghi {args.out}")
        if not args.watch:
            break
        time.sleep(config["dashboard"]["refresh_seconds"])


if __name__ == "__main__":
    main()
