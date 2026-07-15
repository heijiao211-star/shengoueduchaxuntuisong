#!/usr/bin/env python3
"""Build a daily subscription-limit report for the configured OTC Nasdaq-100 funds."""

from __future__ import annotations

import csv
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "funds.json"
REPORTS_DIR = ROOT / "reports"
DATA_DIR = ROOT / "data"
USER_AGENT = "Mozilla/5.0 (compatible; Nasdaq100QuotaMonitor/1.0; +https://github.com/)"


def plain(value: str) -> str:
    value = re.sub(r"<[^>]*>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def amount(value: str | None) -> int | None:
    if not value:
        return None
    return int(float(value.replace(",", "")))


def fund_url(code: str) -> str:
    return f"https://fundf10.eastmoney.com/jjjz_{code}.html"


def fetch_fund(fund: dict) -> dict:
    url = fund_url(fund["code"])
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
        with urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", errors="replace")

        status_match = re.search(r"交易状态：\s*<span>(.*?)</span>", page, flags=re.S)
        raw_status = plain(status_match.group(1)) if status_match else "状态未识别"
        cap_match = re.search(r"单日累计购买上限\s*([\d,.]+)元", plain(page))
        cap = amount(cap_match.group(1)) if cap_match else None
        sip_match = re.search(r"定投\s*([\d,.]+元起)", plain(page))
        sip_status = f"支持（{sip_match.group(1)}）" if sip_match else "未识别"

        if "暂停申购" in raw_status or "封闭" in raw_status:
            subscription_status = "暂停申购"
            subscription_amount = 0
        elif cap is not None:
            subscription_status = "限大额申购"
            subscription_amount = cap
        elif "开放" in raw_status or "申购" in raw_status:
            subscription_status = "开放申购"
            subscription_amount = None
        else:
            subscription_status = "待人工确认"
            subscription_amount = 0

        return {
            **fund,
            "source_url": url,
            "raw_status": raw_status,
            "subscription_status": subscription_status,
            "daily_limit": cap,
            "subscription_amount": subscription_amount,
            "sip_status": sip_status,
            "error": "",
        }
    except Exception as exc:  # Keep the remaining funds visible if one source is unavailable.
        return {
            **fund,
            "source_url": url,
            "raw_status": "获取失败",
            "subscription_status": "获取失败",
            "daily_limit": None,
            "subscription_amount": 0,
            "sip_status": "待确认",
            "error": type(exc).__name__,
        }


def money(value: int | None) -> str:
    return "—" if value is None else f"¥{value:,}"


def invested(value: bool) -> str:
    return "已定投" if value else "未定投"


def status_class(status: str) -> str:
    if status == "开放申购":
        return "ok"
    if status == "限大额申购":
        return "warn"
    return "stop"


def build_markdown(rows: list[dict], checked_at: str) -> str:
    available = [row for row in rows if row["subscription_status"] in {"开放申购", "限大额申购"}]
    total = sum(row["subscription_amount"] or 0 for row in rows)
    lines = [
        "# 纳指100场外申购额度日报",
        "",
        f"> 更新：{checked_at}（北京时间）  ",
        f"> 可申购：**{len(available)}/{len(rows)}** 只 ｜ 公告披露额度合计：**¥{total:,}**",
        "",
        "| 代码 | 基金 | 基金公司 | 定投标记 | 今日状态 | 公告单日上限 | 今日申购金额 | 定投状态 |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['code']} | {row['name']} | {row['manager']} | {invested(row['invested'])} | "
            f"{row['subscription_status']} | {money(row['daily_limit'])} | {money(row['subscription_amount'])} | {row['sip_status']} |"
        )
    lines += [
        "",
        "说明：今日申购金额直接采用公告披露的单日上限；未披露具体上限的开放基金显示“—”。支付宝最终下单结果以支付宝页面为准。",
    ]
    return "\n".join(lines) + "\n"


def build_html(rows: list[dict], checked_at: str) -> str:
    available = [row for row in rows if row["subscription_status"] in {"开放申购", "限大额申购"}]
    total = sum(row["subscription_amount"] or 0 for row in rows)
    table_rows = []
    for row in rows:
        table_rows.append(
            "<tr>"
            f"<td><strong>{html.escape(row['code'])}</strong><br><span class='muted'>{html.escape(row['manager'])}</span></td>"
            f"<td>{html.escape(row['name'])}<br><span class='tag'>{invested(row['invested'])}</span></td>"
            f"<td><span class='state {status_class(row['subscription_status'])}'>{html.escape(row['subscription_status'])}</span><br><span class='muted'>{html.escape(row['raw_status'])}</span></td>"
            f"<td>{money(row['daily_limit'])}</td>"
            f"<td class='amount'>{money(row['subscription_amount'])}</td>"
            f"<td>{html.escape(row['sip_status'])}</td>"
            "</tr>"
        )
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
body{{margin:0;background:#f4f7fb;color:#172033;font:14px -apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}}
.wrap{{max-width:980px;margin:0 auto;padding:22px 12px}}.hero{{padding:22px 24px;border-radius:16px;background:linear-gradient(135deg,#132b50,#245994);color:#fff}}
.hero h1{{margin:0 0 8px;font-size:22px}}.hero p{{margin:0;color:#dbeafe}}.stats{{display:flex;gap:12px;margin:16px 0}}.stat{{flex:1;background:#fff;border-radius:12px;padding:14px;box-shadow:0 2px 12px #1e3a5f12}}.stat b{{display:block;font-size:23px;color:#134e9b}}.stat span,.muted{{color:#738097;font-size:12px}}
.table{{overflow-x:auto;background:#fff;border-radius:14px;box-shadow:0 2px 12px #1e3a5f12}}table{{width:100%;border-collapse:collapse;min-width:860px}}th{{background:#eef5ff;color:#46627f;text-align:left;font-size:12px}}td,th{{padding:12px;border-bottom:1px solid #edf1f6;vertical-align:top}}tr:last-child td{{border-bottom:0}}.tag{{font-size:11px;color:#245994;background:#e9f2ff;border-radius:99px;padding:2px 6px}}.state{{display:inline-block;padding:3px 7px;border-radius:6px;font-size:12px;font-weight:600}}.ok{{color:#18794e;background:#e6f6ec}}.warn{{color:#a35f00;background:#fff4d6}}.stop{{color:#b42318;background:#feeceb}}.amount{{font-weight:700;color:#134e9b}}.foot{{margin:14px 2px;color:#738097;font-size:12px}}
</style></head><body><div class='wrap'><section class='hero'><h1>纳指100 · 场外申购额度日报</h1><p>{html.escape(checked_at)}（北京时间）｜公开基金状态监控</p></section><section class='stats'><div class='stat'><span>可申购基金</span><b>{len(available)} / {len(rows)}</b></div><div class='stat'><span>公告披露额度合计</span><b>¥{total:,}</b></div></section><section class='table'><table><thead><tr><th>代码 / 公司</th><th>基金 / 标记</th><th>今日状态</th><th>单日上限</th><th>今日申购金额</th><th>定投状态</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></section><p class='foot'>“今日申购金额”直接采用公告披露的单日上限；支付宝最终下单结果以支付宝页面为准。</p></div></body></html>"""


def write_history(rows: list[dict], checked_at: str) -> None:
    path = DATA_DIR / "history.csv"
    new_file = not path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["checked_at", "code", "name", "status", "daily_limit", "subscription_amount", "sip_status", "source_url", "error"])
        if new_file:
            writer.writeheader()
        for row in rows:
            writer.writerow({"checked_at": checked_at, "code": row["code"], "name": row["name"], "status": row["subscription_status"], "daily_limit": row["daily_limit"], "subscription_amount": row["subscription_amount"], "sip_status": row["sip_status"], "source_url": row["source_url"], "error": row["error"]})


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    now = datetime.now(ZoneInfo(config["timezone"]))
    checked_at = now.strftime("%Y-%m-%d %H:%M")
    REPORTS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    # The public pages can be slow. Parallel reads keep a daily run short while
    # preserving the configured display order.
    with ThreadPoolExecutor(max_workers=5) as executor:
        rows = list(executor.map(fetch_fund, config["funds"]))
    report = {"checked_at": checked_at, "timezone": config["timezone"], "funds": rows}
    (REPORTS_DIR / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORTS_DIR / "latest.md").write_text(build_markdown(rows, checked_at), encoding="utf-8")
    (REPORTS_DIR / "latest.html").write_text(build_html(rows, checked_at), encoding="utf-8")
    write_history(rows, checked_at)
    print(f"Built report for {len(rows)} funds at {checked_at}.")


if __name__ == "__main__":
    main()
