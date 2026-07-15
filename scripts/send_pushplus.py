#!/usr/bin/env python3
"""Send the rendered HTML report to PushPlus without exposing its token in logs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")


def main() -> None:
    if not TOKEN:
        raise SystemExit("PUSHPLUS_TOKEN is not configured. Add it in GitHub Actions secrets.")
    report = json.loads((ROOT / "reports" / "latest.json").read_text(encoding="utf-8"))
    title = f"纳指100申购额度日报 · {report['checked_at'][:10]}"
    body = urlencode({"token": TOKEN, "title": title, "content": (ROOT / "reports" / "latest.html").read_text(encoding="utf-8"), "template": "html"}).encode("utf-8")
    request = Request("https://www.pushplus.plus/send", data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code") != 200:
        raise SystemExit(f"PushPlus rejected the message: {result.get('msg', 'unknown error')}")
    print("PushPlus accepted the report.")


if __name__ == "__main__":
    main()
