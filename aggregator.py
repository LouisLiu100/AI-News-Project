#!/usr/bin/env python3
import yaml
import feedparser
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import logging
from googletrans import Translator

# 如果使用 Notion 推送数据，则引入相关模块
try:
    from notion import push_to_notion
except ImportError:
    push_to_notion = None

# 设置日志输出
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 初始化翻译器（翻译成中文）
translator = Translator()

def translate_to_chinese(text):
    try:
        translated = translator.translate(text, dest='zh-cn')
        return translated.text
    except Exception as e:
        logging.error(f"Translation error: {e}")
        return text

def load_config(config_file="config.yaml"):
    with open(config_file, 'r', encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config

def clean_text(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r'\s+', ' ', text)
    return text

def convert_to_iso(date_str):
    try:
        try:
            dt = datetime.fromisoformat(date_str)
        except ValueError:
            dt = parsedate_to_datetime(date_str)
        dt = dt.replace(microsecond=0)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception as e:
        logging.error(f"Date conversion error: {e}")
        return datetime.utcnow().replace(microsecond=0, tzinfo=timezone.utc).isoformat()

def classify_content(title, summary, config):
    category = "趋势新闻"  # 默认类别
    combined = (title + " " + summary).lower()
    for key, keywords in config.get("keywords", {}).items():
        for word in keywords:
            if word.lower() in combined:
                if key == "course":
                    return "课程"
                elif key == "case":
                    return "案例"
                elif key == "trend":
                    return "趋势新闻"
    return category

def process_rss_source(source, config):
    logging.info(f"Processing RSS source: {source['name']}")
    feed = feedparser.parse(source['url'])
    items = []
    for entry in feed.entries:
        title = entry.get("title", "")
        summary = clean_text(entry.get("summary", ""))
        title_cn = translate_to_chinese(title)
        summary_cn = translate_to_chinese(summary)
        raw_published = entry.get("published", datetime.utcnow().isoformat())
        published = convert_to_iso(raw_published)
        link = entry.get("link", "")
        content_type = classify_content(title, summary, config)
        items.append({
            "source": source["name"],
            "title": title_cn,
            "summary": summary_cn,
            "published": published,
            "link": link,
            "type": content_type
        })
    return items

def process_api_source(source, config):
    logging.info(f"Processing API source: {source['name']}")
    headers = source.get("headers", {})
    items = []
    # 针对 Twitter 数据，使用用户时间线接口获取最新 5 篇推文
    if "Twitter" in source["name"]:
        user_id = source.get("user_id")
        if not user_id:
            logging.error("Twitter source requires a 'user_id' in config.")
            return items
        url = f"https://api.twitter.com/2/users/{user_id}/tweets?max_results=5&tweet.fields=created_at"
        response = requests.get(url, headers=headers, timeout=10)
    else:
        response = requests.get(source['url'], headers=headers, timeout=10)
    if response.status_code == 200:
        data = response.json()
        for tweet in data.get("data", []):
            title = tweet.get("text", "")
            summary = clean_text(title)
            title_cn = translate_to_chinese(title)
            summary_cn = translate_to_chinese(summary)
            raw_published = tweet.get("created_at", datetime.utcnow().isoformat())
            published = convert_to_iso(raw_published)
            link = f"https://twitter.com/i/web/status/{tweet.get('id', '')}"
            content_type = classify_content(title, summary, config)
            items.append({
                "source": source["name"],
                "title": title_cn,
                "summary": summary_cn,
                "published": published,
                "link": link,
                "type": content_type
            })
    else:
        logging.error(f"API request failed with status code {response.status_code}")
    return items

def process_deepmind_source(source, config):
    logging.info(f"Processing DeepMind source: {source['name']}")
    response = requests.get(source['url'], timeout=10)
    items = []
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        # 修改正则：查找所有 a 标签，href 包含 "/blog/"（不限制开头）
        links = soup.find_all("a", href=re.compile(r"/blog/"))
        logging.info(f"Found {len(links)} potential blog links on DeepMind.")
        seen = set()
        for a in links:
            href = a.get("href")
            if not href or href in seen:
                continue
            seen.add(href)
            # 如果链接不是绝对 URL，则转换为绝对 URL
            if not href.startswith("http"):
                href = "https://deepmind.com" + href
            title = a.get_text(strip=True)
            if not title:
                title = "DeepMind Blog Post"
            summary = title  # 暂时将标题作为摘要
            title_cn = translate_to_chinese(title)
            summary_cn = translate_to_chinese(summary)
            # 这里默认发布时间为当前时间，如有需要可进一步解析具体发布时间
            published = datetime.utcnow().replace(microsecond=0, tzinfo=timezone.utc).isoformat()
            content_type = classify_content(title, summary, config)
            items.append({
                "source": source["name"],
                "title": title_cn,
                "summary": summary_cn,
                "published": published,
                "link": href,
                "type": content_type
            })
    else:
        logging.error(f"DeepMind request failed with status code {response.status_code}")
    return items

def main():
    config = load_config()
    all_items = []

    for source in config.get("rss_sources", []):
        try:
            items = process_rss_source(source, config)
            all_items.extend(items)
        except Exception as e:
            logging.error(f"Error processing RSS source {source['name']}: {e}")

    for source in config.get("api_sources", []):
        try:
            items = process_api_source(source, config)
            all_items.extend(items)
        except Exception as e:
            logging.error(f"Error processing API source {source['name']}: {e}")

    for source in config.get("crawler_sources", []):
        try:
            if source["name"] == "DeepMind":
                items = process_deepmind_source(source, config)
            else:
                items = process_deepmind_source(source, config)  # 可扩展其他爬虫处理逻辑
            all_items.extend(items)
        except Exception as e:
            logging.error(f"Error processing crawler source {source['name']}: {e}")

    logging.info(f"Total items fetched: {len(all_items)}")

    if config.get("notion", {}).get("enable", False) and push_to_notion:
        for item in all_items:
            try:
                push_to_notion(item, config["notion"])
            except Exception as e:
                logging.error(f"Error pushing item to Notion: {e}")
    else:
        with open("aggregated_data.json", "w", encoding="utf-8") as f:
            import json
            json.dump(all_items, f, ensure_ascii=False, indent=2)
        logging.info("Data saved to aggregated_data.json")

if __name__ == "__main__":
    main()
