import requests
import logging

def push_to_notion(item, notion_config):
    token = notion_config["token"]
    database_id = notion_config["database_id"]
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    # 构造页面内容，这里需要预先在Notion数据库中建立相应的属性（如标题、日期、链接、标签等）
    data = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {
                "title": [
                    {
                        "text": {"content": item["title"]}
                    }
                ]
            },
            "Source": {
                "rich_text": [
                    {
                        "text": {"content": item["source"]}
                    }
                ]
            },
            "Published": {
                "date": {"start": item["published"]}
            },
            "Type": {
                "select": {"name": item["type"]}
            },
            "Link": {
                "url": item["link"]
            },
            "Summary": {
                "rich_text": [
                    {
                        "text": {"content": item["summary"]}
                    }
                ]
            }
        }
    }
    response = requests.post(url, headers=headers, json=data, timeout=10)
    if response.status_code != 200:
        logging.error(f"Notion API error: {response.text}")
        raise Exception("Failed to push data to Notion")
    return response.json()
