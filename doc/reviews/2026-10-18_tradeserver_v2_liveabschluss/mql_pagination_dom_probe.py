"""At most two authorized light GETs, existing browser cookies in RAM only.

No WebDriver navigation, no cookie/header publication, no retry on a block.
Raw HTML stays exclusively in the ignored private live-run directory.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.parse

import psutil
import requests
from bs4 import BeautifulSoup
from mqlkiscanner.mql5.ratelimit import RateLimiter
import mql_pagination_watch as watch

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[3]
REVIEW = Path(__file__).resolve().parent
PRIVATE = ROOT / "data/runs/liveabschluss_20261018/mql_dom_probe"
PRIVATE.mkdir(parents=True, exist_ok=True)
LIMITER = RateLimiter(min_interval_s=20, jitter_s=1)


def summary(response, label):
    html = response.text
    private = PRIVATE / (label + ".html")
    assert not private.exists(), "Never overwrite a previous source observation"
    private.write_bytes(response.content)
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select(".signal a[href*='/signals/']")
    rows = []
    for link in links:
        identifier = re.search(r"/signals/(\d+)(?:[?#/]|$)", link.get("href", ""))
        if not identifier:
            continue
        row = link.find_parent(lambda tag: tag.name == "tr" or (tag.name == "div" and "row" in " ".join(tag.get("class", [])) and "signal" in " ".join(tag.get("class", []))))
        raw, parsed = None, None
        if row:
            for selector in (".col-subscribers", "td.col-subscribers", "div.col-subscribers", '[class*="subscribers"]', "td:nth-child(5)"):
                cell = row.select_one(selector)
                if cell:
                    text = cell.get_text(" ", strip=True)
                    digits = re.sub(r"[^0-9]", "", text)
                    if digits:
                        raw, parsed = text, int(digits)
                        break
        rows.append({"signal_id": int(identifier[1]), "subscriber_text": raw, "parsed_subscribers": parsed})
    paginator = []
    for link in soup.select("a[href]"):
        href = link["href"]
        if re.search(r"/page\d+(?:[?#]|$)|[?&]page=\d+", href):
            url = urllib.parse.urljoin(response.url, href)
            if urllib.parse.urlsplit(url).hostname == "www.mql5.com":
                paginator.append({"text": link.get_text(" ", strip=True), "href": href, "absolute_url": url})
    value = {"observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "requested_url": response.request.url,
             "response_url": response.url, "http_status": response.status_code,
             "title": soup.title.get_text(" ", strip=True) if soup.title else None,
             "html_sha256": hashlib.sha256(response.content).hexdigest(),
             "provider_anchor_count": len(links), "numeric_provider_count": len(rows),
             "positive_subscribers": sum((row["parsed_subscribers"] or 0) > 0 for row in rows),
             "explicit_zero_subscribers": sum(row["parsed_subscribers"] == 0 for row in rows),
             "unknown_subscribers": sum(row["parsed_subscribers"] is None for row in rows),
             "provider_samples": rows[:8], "paginator_links": paginator}
    (REVIEW / f"mql_pagination_dom_{label}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)
    return value


process = psutil.Process(watch.PID)
drivers = watch.drivers(process)
assert len(drivers) == 1
driver_pid, port, session_id = drivers[0]
cookies = watch.get(f"http://127.0.0.1:{port}/session/{session_id}/cookie", timeout=5)["value"]
user_agent = None
for child in process.children(recursive=True):
    if child.name().lower() != "chrome.exe":
        continue
    for arg in child.cmdline():
        if arg.startswith("--user-agent="):
            user_agent = arg.split("=", 1)[1]
            break
    if user_agent:
        break
assert user_agent, "No verified current browser user agent"
session = requests.Session()
session.headers.update({"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"})
for cookie in cookies:
    if cookie.get("domain", "").lstrip(".").endswith("mql5.com"):
        session.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie.get("path", "/"))
del cookies
LIMITER.wait()
first_response = session.get("https://www.mql5.com/en/signals/mt4/list?orderby=subscribers", timeout=30)
first = summary(first_response, "first")
assert first_response.status_code == 200 and first["numeric_provider_count"] > 0, "No valid page; stop without retry"
next_urls = [link["absolute_url"] for link in first["paginator_links"] if re.search(r"/page2(?:[?#]|$)|[?&]page=2(?:&|$)", link["absolute_url"])]
assert next_urls, "No original paginator href for page 2"
next_url = next_urls[0]
assert urllib.parse.urlsplit(next_url).hostname == "www.mql5.com" and "/signals/mt4/" in urllib.parse.urlsplit(next_url).path
LIMITER.wait()
second_response = session.get(next_url, timeout=30)
second = summary(second_response, "original_page2")
assert second_response.status_code == 200, "Original follow-up did not return 200; no retry"
