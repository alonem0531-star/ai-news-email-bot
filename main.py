import json
import os
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

import feedparser
import requests
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / "news_cache.json"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

DEFAULT_RSS_FEEDS = [
    "https://news.google.com/rss/search?q=AI%20OR%20%22artificial%20intelligence%22%20OR%20ChatGPT&hl=ja&gl=JP&ceid=JP:ja",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
]

IMPORTANT_KEYWORDS = {
    "openai": 8,
    "chatgpt": 8,
    "gpt": 7,
    "anthropic": 7,
    "claude": 7,
    "google": 6,
    "gemini": 7,
    "microsoft": 6,
    "copilot": 6,
    "meta": 5,
    "llama": 6,
    "nvidia": 6,
    "生成ai": 8,
    "人工知能": 5,
    "aiエージェント": 8,
    "agent": 5,
    "model": 4,
    "llm": 6,
    "規制": 5,
    "security": 4,
    "安全性": 4,
    "research": 3,
    "release": 4,
    "launch": 4,
}


def load_cache() -> set[str]:
    if not CACHE_FILE.exists():
        return set()

    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()

    if isinstance(data, list):
        return set(str(url) for url in data)
    if isinstance(data, dict):
        return set(str(url) for url in data.get("sent_urls", []))
    return set()


def save_cache(sent_urls: set[str]) -> None:
    CACHE_FILE.write_text(
        json.dumps({"sent_urls": sorted(sent_urls)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clean_text(value: str, max_length: int = 180) -> str:
    text = re.sub(r"<[^>]+>", "", value or "")
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "..."


def parse_datetime(entry) -> datetime:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (TypeError, ValueError):
            continue
    return datetime.now(timezone.utc)


def normalize_url(entry) -> str:
    return str(entry.get("link") or entry.get("id") or "").strip()


def importance_score(title: str, summary: str, published_at: datetime) -> int:
    text = f"{title} {summary}".lower()
    score = 0
    for keyword, weight in IMPORTANT_KEYWORDS.items():
        if keyword.lower() in text:
            score += weight

    age_hours = max(
        0,
        (datetime.now(timezone.utc) - published_at.astimezone(timezone.utc)).total_seconds()
        / 3600,
    )
    if age_hours <= 24:
        score += 8
    elif age_hours <= 72:
        score += 4
    elif age_hours <= 168:
        score += 1

    return score


def get_rss_feeds() -> list[str]:
    configured = os.getenv("RSS_FEEDS", "").strip()
    if not configured:
        return DEFAULT_RSS_FEEDS
    return [feed.strip() for feed in configured.split(",") if feed.strip()]


def fetch_news(sent_urls: set[str], limit: int = 5) -> list[dict]:
    items = []
    seen_now = set()

    for feed_url in get_rss_feeds():
        try:
            response = requests.get(
                feed_url,
                headers={"User-Agent": "ai-news-line-bot/1.0"},
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"Failed to fetch RSS feed: {feed_url} ({error})")
            continue

        feed = feedparser.parse(response.content)
        for entry in feed.entries:
            url = normalize_url(entry)
            if not url or url in sent_urls or url in seen_now:
                continue

            title = clean_text(entry.get("title", ""), max_length=120)
            summary = clean_text(
                entry.get("summary") or entry.get("description") or title,
                max_length=180,
            )
            published_at = parse_datetime(entry)
            score = importance_score(title, summary, published_at)

            items.append(
                {
                    "title": title,
                    "summary": summary,
                    "url": url,
                    "published_at": published_at,
                    "score": score,
                }
            )
            seen_now.add(url)

    items.sort(key=lambda item: (item["score"], item["published_at"]), reverse=True)
    return items[:limit]


def build_line_message(news_items: list[dict]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"AIニュース TOP {len(news_items)} ({today})"]

    for index, item in enumerate(news_items, start=1):
        lines.extend(
            [
                "",
                f"{index}. {item['title']}",
                f"要約: {item['summary']}",
                f"URL: {item['url']}",
            ]
        )

    return "\n".join(lines)


def build_email_message(news_items: list[dict]) -> tuple[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"本日のAIニュース TOP {len(news_items)} ({today})"
    lines = [
        f"本日のピックアップAIニュース {len(news_items)}選",
        "",
    ]

    for index, item in enumerate(news_items, start=1):
        lines.extend(
            [
                f"{index}. {item['title']}",
                f"要約: {item['summary']}",
                f"URL: {item['url']}",
                "",
            ]
        )

    return subject, "\n".join(lines).strip()


def send_line_message(message: str) -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    to_id = os.getenv("LINE_USER_ID", "").strip()

    if not token:
        raise RuntimeError(".env に LINE_CHANNEL_ACCESS_TOKEN を設定してください。")
    if not to_id:
        raise RuntimeError(".env に LINE_USER_ID を設定してください。")

    response = requests.post(
        LINE_PUSH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "to": to_id,
            "messages": [{"type": "text", "text": message[:4900]}],
        },
        timeout=20,
    )
    response.raise_for_status()


def send_email_message(subject: str, body: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    email_from = os.getenv("EMAIL_FROM", smtp_username).strip()
    email_to = os.getenv("EMAIL_TO", "").strip()

    if not smtp_username:
        raise RuntimeError("SMTP_USERNAME を設定してください。")
    if not smtp_password:
        raise RuntimeError("SMTP_PASSWORD を設定してください。")
    if not email_from:
        raise RuntimeError("EMAIL_FROM または SMTP_USERNAME を設定してください。")
    if not email_to:
        raise RuntimeError("EMAIL_TO を設定してください。")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = email_from
    message["To"] = email_to
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


def main() -> None:
    load_dotenv(BASE_DIR / ".env")

    sent_urls = load_cache()
    news_items = fetch_news(sent_urls)

    if not news_items:
        print("No new AI news found.")
        return

    delivery_channel = os.getenv("DELIVERY_CHANNEL", "line").strip().lower()
    if delivery_channel == "email":
        subject, body = build_email_message(news_items)
        send_email_message(subject, body)
        print(f"Sent {len(news_items)} news items by email.")
    else:
        message = build_line_message(news_items)
        send_line_message(message)
        print(f"Sent {len(news_items)} news items to LINE.")

    sent_urls.update(item["url"] for item in news_items)
    save_cache(sent_urls)


if __name__ == "__main__":
    main()
