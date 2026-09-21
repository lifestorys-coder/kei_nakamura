#!/usr/bin/env python3
"""沖縄観光新聞を生成する。

毎日 GitHub Actions から実行され、天気(Open-Meteo)とニュース(Yahoo!ニュース
沖縄地域 RSS)を取得し、docs/index.html（最新号）と
docs/archive/YYYY-MM-DD.html（過去号）を書き出す。
"""
from __future__ import annotations

import html
import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ARCHIVE = DOCS / "archive"
SPOTS_FILE = ROOT / "data" / "spots.json"

JST = ZoneInfo("Asia/Tokyo")

# 那覇市の緯度経度
NAHA_LAT = 26.2124
NAHA_LON = 127.6809

WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={NAHA_LAT}&longitude={NAHA_LON}"
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
    "precipitation_probability_max,wind_speed_10m_max"
    "&timezone=Asia%2FTokyo&forecast_days=3"
)

NEWS_RSS_URL = "https://news.yahoo.co.jp/rss/area/47.xml"
NEWS_LIMIT = 8

REQUEST_TIMEOUT = 15
USER_AGENT = "okinawa-tourism-newspaper-bot/1.0 (+https://github.com)"

WEATHER_CODE_MAP = {
    0: ("快晴", "☀️"),
    1: ("晴れ", "🌤️"),
    2: ("晴れ時々曇り", "⛅"),
    3: ("曇り", "☁️"),
    45: ("霧", "🌫️"),
    48: ("霧", "🌫️"),
    51: ("小雨", "🌦️"),
    53: ("小雨", "🌦️"),
    55: ("雨", "🌧️"),
    56: ("みぞれ", "🌧️"),
    57: ("みぞれ", "🌧️"),
    61: ("雨", "🌧️"),
    63: ("雨", "🌧️"),
    65: ("大雨", "⛈️"),
    66: ("みぞれ", "🌧️"),
    67: ("みぞれ", "🌧️"),
    71: ("雪", "🌨️"),
    73: ("雪", "🌨️"),
    75: ("雪", "🌨️"),
    80: ("にわか雨", "🌦️"),
    81: ("にわか雨", "🌦️"),
    82: ("激しいにわか雨", "⛈️"),
    95: ("雷雨", "⛈️"),
    96: ("雷雨", "⛈️"),
    99: ("雷雨", "⛈️"),
}


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()


def fetch_weather() -> list[dict]:
    """Open-Meteo から向こう3日分の那覇の天気を取得する。"""
    try:
        data = fetch_json(WEATHER_URL)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"[warn] 天気取得に失敗しました: {exc}")
        return []

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    codes = daily.get("weather_code", [])
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])
    pop = daily.get("precipitation_probability_max", [])
    wind = daily.get("wind_speed_10m_max", [])

    days = []
    for i, day_str in enumerate(dates):
        code = codes[i] if i < len(codes) else None
        label, icon = WEATHER_CODE_MAP.get(code, ("不明", "🌈"))
        days.append(
            {
                "date": day_str,
                "label": label,
                "icon": icon,
                "tmax": tmax[i] if i < len(tmax) else None,
                "tmin": tmin[i] if i < len(tmin) else None,
                "pop": pop[i] if i < len(pop) else None,
                "wind": wind[i] if i < len(wind) else None,
            }
        )
    return days


def fetch_news(limit: int = NEWS_LIMIT) -> list[dict]:
    """Yahoo!ニュース 沖縄地域面の RSS からニュース一覧を取得する。"""
    try:
        raw = fetch_bytes(NEWS_RSS_URL)
        root = ET.fromstring(raw)
    except (urllib.error.URLError, TimeoutError, ET.ParseError) as exc:
        print(f"[warn] ニュース取得に失敗しました: {exc}")
        return []

    items = []
    for item in root.findall("./channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "pub_date": pub_date})
    return items


def load_spots() -> list[dict]:
    with SPOTS_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def pick_spots_of_day(spots: list[dict], today: date, count: int = 3) -> list[dict]:
    """日付を元に決定的に（同じ日は同じ結果になるように）スポットを選ぶ。"""
    if not spots:
        return []
    start = today.toordinal() % len(spots)
    picked = []
    for offset in range(count):
        picked.append(spots[(start + offset) % len(spots)])
    return picked


def format_pub_date(pub_date: str) -> str:
    if not pub_date:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            dt = datetime.strptime(pub_date, fmt)
            return dt.astimezone(JST).strftime("%m/%d %H:%M")
        except ValueError:
            continue
    return pub_date


def render_weather_html(days: list[dict]) -> str:
    if not days:
        return "<p class=\"notice\">天気情報を取得できませんでした。</p>"

    cards = []
    day_labels = ["今日", "明日", "明後日"]
    for i, d in enumerate(days[:3]):
        label = day_labels[i] if i < len(day_labels) else d["date"]
        tmax = f'{d["tmax"]:.0f}' if d["tmax"] is not None else "-"
        tmin = f'{d["tmin"]:.0f}' if d["tmin"] is not None else "-"
        pop = f'{d["pop"]:.0f}' if d["pop"] is not None else "-"
        wind = f'{d["wind"]:.0f}' if d["wind"] is not None else "-"
        cards.append(
            f"""
        <div class="weather-card">
          <div class="weather-day">{html.escape(label)}<span class="weather-date">({html.escape(d["date"][5:])})</span></div>
          <div class="weather-icon">{d["icon"]}</div>
          <div class="weather-label">{html.escape(d["label"])}</div>
          <div class="weather-temp"><span class="tmax">{tmax}℃</span> / <span class="tmin">{tmin}℃</span></div>
          <div class="weather-sub">降水確率 {pop}% ・ 風速 {wind}m/s</div>
        </div>"""
        )
    return f'<div class="weather-grid">{"".join(cards)}</div>'


def render_spots_html(spots: list[dict]) -> str:
    if not spots:
        return "<p class=\"notice\">本日のおすすめスポットは準備中です。</p>"
    cards = []
    for spot in spots:
        cards.append(
            f"""
        <div class="spot-card">
          <div class="spot-header">
            <span class="spot-name">{html.escape(spot["name"])}</span>
            <span class="spot-category">{html.escape(spot["category"])}</span>
          </div>
          <div class="spot-area">📍 {html.escape(spot["area"])}</div>
          <p class="spot-desc">{html.escape(spot["description"])}</p>
        </div>"""
        )
    return f'<div class="spot-grid">{"".join(cards)}</div>'


def render_news_html(news: list[dict]) -> str:
    if not news:
        return "<p class=\"notice\">本日のニュースを取得できませんでした。</p>"
    rows = []
    for item in news:
        pub = format_pub_date(item["pub_date"])
        rows.append(
            f"""
        <li class="news-item">
          <a href="{html.escape(item["link"])}" target="_blank" rel="noopener noreferrer">{html.escape(item["title"])}</a>
          <span class="news-date">{html.escape(pub)}</span>
        </li>"""
        )
    return f'<ul class="news-list">{"".join(rows)}</ul>'


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>沖縄観光新聞 - {date_jp}</title>
<meta name="description" content="{date_jp}付の沖縄観光新聞。那覇の天気、本日のおすすめ観光スポット、沖縄の最新ニュースをお届けします。">
<link rel="stylesheet" href="{style_href}">
</head>
<body>
<header class="masthead">
  <div class="masthead-inner">
    <p class="masthead-eyebrow">DAILY OKINAWA TOURISM PRESS</p>
    <h1 class="masthead-title">沖縄観光新聞</h1>
    <p class="masthead-date">{date_jp}（{weekday_jp}曜日）　第{issue_no}号</p>
  </div>
</header>

<nav class="topnav">
  <a href="{index_href}">最新号</a>
  <a href="{archive_href}">バックナンバー</a>
</nav>

<main class="paper">
  <section class="section">
    <h2 class="section-title">🌤️ 今日の沖縄（那覇）の天気</h2>
    {weather_html}
  </section>

  <section class="section">
    <h2 class="section-title">📌 本日のおすすめ観光スポット</h2>
    {spots_html}
  </section>

  <section class="section">
    <h2 class="section-title">📰 沖縄ニュース</h2>
    {news_html}
    <p class="source-note">ニュース提供: Yahoo!ニュース 沖縄地域面 RSS</p>
  </section>
</main>

<footer class="site-footer">
  <p>沖縄観光新聞は GitHub Actions により毎朝自動生成されています。</p>
  <p class="generated-at">生成日時: {generated_at}</p>
</footer>
</body>
</html>
"""

WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]


def build_html(*, today: date, issue_no: int, style_href: str, index_href: str, archive_href: str) -> str:
    weather_days = fetch_weather()
    news_items = fetch_news()
    spots = load_spots()
    todays_spots = pick_spots_of_day(spots, today)

    date_jp = f"{today.year}年{today.month}月{today.day}日"
    weekday_jp = WEEKDAY_JP[today.weekday()]
    generated_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")

    return PAGE_TEMPLATE.format(
        date_jp=date_jp,
        weekday_jp=weekday_jp,
        issue_no=issue_no,
        style_href=style_href,
        index_href=index_href,
        archive_href=archive_href,
        weather_html=render_weather_html(weather_days),
        spots_html=render_spots_html(todays_spots),
        news_html=render_news_html(news_items),
        generated_at=generated_at,
    )


def compute_issue_no(today: date) -> int:
    """通巻号数として、創刊日(2025-01-01)からの経過日数+1を使う。"""
    epoch = date(2025, 1, 1)
    return max(1, (today - epoch).days + 1)


def update_archive_index() -> None:
    files = sorted(ARCHIVE.glob("????-??-??.html"), reverse=True)
    items = []
    for f in files:
        day_str = f.stem
        items.append(f'    <li><a href="{f.name}">{day_str}</a></li>')
    body = "\n".join(items) if items else "    <li>バックナンバーはまだありません。</li>"

    content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>バックナンバー - 沖縄観光新聞</title>
<link rel="stylesheet" href="../style.css">
</head>
<body>
<header class="masthead">
  <div class="masthead-inner">
    <p class="masthead-eyebrow">DAILY OKINAWA TOURISM PRESS</p>
    <h1 class="masthead-title">沖縄観光新聞</h1>
    <p class="masthead-date">バックナンバー</p>
  </div>
</header>
<nav class="topnav">
  <a href="../index.html">最新号</a>
  <a href="index.html">バックナンバー</a>
</nav>
<main class="paper">
  <section class="section">
    <h2 class="section-title">🗂️ バックナンバー一覧</h2>
    <ul class="archive-list">
{body}
    </ul>
  </section>
</main>
<footer class="site-footer">
  <p>沖縄観光新聞は GitHub Actions により毎朝自動生成されています。</p>
</footer>
</body>
</html>
"""
    (ARCHIVE / "index.html").write_text(content, encoding="utf-8")


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    today = datetime.now(JST).date()
    issue_no = compute_issue_no(today)

    index_html = build_html(
        today=today,
        issue_no=issue_no,
        style_href="style.css",
        index_href="index.html",
        archive_href="archive/index.html",
    )
    (DOCS / "index.html").write_text(index_html, encoding="utf-8")

    archive_html = build_html(
        today=today,
        issue_no=issue_no,
        style_href="../style.css",
        index_href="../index.html",
        archive_href="index.html",
    )
    (ARCHIVE / f"{today.isoformat()}.html").write_text(archive_html, encoding="utf-8")

    update_archive_index()
    print(f"沖縄観光新聞 第{issue_no}号（{today.isoformat()}）を生成しました。")


if __name__ == "__main__":
    main()
