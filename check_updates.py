#!/usr/bin/env python3
"""
创业者人物库 - 每日自动更新检测脚本
每天自动检索人物变动，生成待审核清单
"""

import json
import requests
import feedparser
from datetime import datetime, timedelta
import re
import os

# ============ 配置 ============
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/epikhong2007/entrepreneur-db/main"
PEOPLE_JSON_URL = f"{GITHUB_RAW_BASE}/initial-data.json"
PENDING_REVIEW_FILE = "pending-review.json"
NEWS_DAYS_BACK = 3  # 检索最近N天的新闻

# 检测关键词
KEYWORDS_JOIN = ["加入", "出任", "任职", "加盟", "担任", "履新", "新任"]
KEYWORDS_LEAVE = ["离职", "辞职", "卸任", "退出", "离开", "不再担任"]


def load_people():
    """加载人物列表"""
    try:
        # 尝试从仓库加载最新数据
        resp = requests.get(PEOPLE_JSON_URL, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("people", [])
    except:
        pass
    
    # 如果网络失败，使用本地文件
    if os.path.exists("initial-data.json"):
        with open("initial-data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("people", [])
    
    return []


def search_google_news(keyword, days_back=NEWS_DAYS_BACK):
    """
    使用 Google News RSS 搜索新闻（免费，无需API key）
    """
    results = []
    try:
        # Google News RSS API
        query = requests.utils.quote(keyword)
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        
        feed = feedparser.parse(rss_url)
        
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        for entry in feed.entries[:20]:  # 限制最多20条
            # 解析发布时间
            published = entry.get("published_parsed")
            if published:
                pub_date = datetime(*published[:6])
                if pub_date < cutoff_date:
                    continue
            
            results.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": "Google News"
            })
    except Exception as e:
        print(f"    ⚠️  Google News 搜索失败: {e}")
    
    return results


def search_huxiu(person_name, company=None):
    """搜索虎嗅相关文章（RSS）"""
    results = []
    try:
        # 虎嗅RSS（按标签）
        rss_url = f"https://www.huxiu.com/rss/0.xml"
        feed = feedparser.parse(rss_url)
        
        for entry in feed.entries[:30]:
            title = entry.get("title", "")
            if person_name in title:
                results.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": "虎嗅"
                })
    except:
        pass
    
    return results


def detect_event_type(text):
    """检测文本中是否包含入职/离职关键词"""
    text = text.lower()
    
    # 检测离职
    for kw in KEYWORDS_LEAVE:
        if kw in text:
            return "leave"
    
    # 检测入职
    for kw in KEYWORDS_JOIN:
        if kw in text:
            return "join"
    
    return None


def check_person(person):
    """检查单个人物的新闻动态"""
    person_name = person.get("name", "")
    person_company = person.get("company", "")
    
    print(f"  🔍 检查: {person_name}")
    
    detections = []
    
    # 搜索关键词: "姓名 + 离职/加入"
    search_queries = [
        f"{person_name} 离职",
        f"{person_name} 加入",
        f"{person_name} 出任",
    ]
    
    for query in search_queries:
        news_items = search_google_news(query, days_back=NEWS_DAYS_BACK)
        
        for item in news_items:
            # 确认是同一人（简单匹配）
            if person_name not in item["title"]:
                continue
            
            # 检测事件类型
            event_type = detect_event_type(item["title"])
            if not event_type:
                continue
            
            # 提取可能的公司名（简单启发式）
            title = item["title"]
            new_company = ""
            # 尝试从标题中提取公司名（在"加入X"或"离职X"之后）
            match = re.search(r'(加入|离职|辞职|卸任|出任|担任)([^，。,.！!？?\s]{2,20})', title)
            if match:
                new_company = match.group(2).strip()
            
            detections.append({
                "personId": person.get("id", ""),
                "personName": person_name,
                "detectedEvent": "入职" if event_type == "join" else "离职",
                "eventType": event_type,
                "company": new_company,
                "title": item["title"],
                "link": item["link"],
                "date": item["published"],
                "source": item["source"],
                "confidence": "medium",  # low/medium/high
                "reviewed": False
            })
    
    return detections


def main():
    print("=" * 50)
    print("🚀 创业者人物库 - 每日更新检测")
    print(f"⏰ 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 加载人物列表
    print("\n📂 加载人物列表...")
    people = load_people()
    print(f"  ✅ 已加载 {len(people)} 位人物")
    
    if not people:
        print("  ❌ 没有找到人物数据，退出")
        return
    
    # 检查每个人物
    print(f"\n🔍 开始检索最近 {NEWS_DAYS_BACK} 天的新闻...")
    all_detections = []
    
    # 限制检查数量（避免运行超时），优先检查重要人物
    # 这里检查前20个人物作为示例
    people_to_check = people[:20] if len(people) > 20 else people
    
    for person in people_to_check:
        detections = check_person(person)
        if detections:
            all_detections.extend(detections)
            print(f"    ⚡ 发现 {len(detections)} 条可能的变动")
    
    # 生成待审核文件
    print(f"\n📝 生成待审核清单...")
    
    pending_data = {
        "lastCheck": datetime.now().isoformat(),
        "totalDetected": len(all_detections),
        "items": all_detections,
        "message": "请人工审核以下检测到的变动，确认后更新到人物库。"
    }
    
    with open(PENDING_REVIEW_FILE, "w", encoding="utf-8") as f:
        json.dump(pending_data, f, ensure_ascii=False, indent=2)
    
    print(f"  ✅ 已生成 {PENDING_REVIEW_FILE}")
    print(f"  📊 检测到 {len(all_detections)} 条可能的变动")
    
    if all_detections:
        print("\n⚠️  发现待审核变动：")
        for item in all_detections[:5]:  # 显示前5条
            print(f"  - {item['personName']}: {item['detectedEvent']} ({item['source']})")
            print(f"    标题: {item['title']}")
        
        # 设置输出变量供后续步骤使用
        print("\n::set-output name=has_updates::true")
    else:
        print("\n✅ 未发现明显变动")
        print("\n::set-output name=has_updates::false")
    
    print("\n" + "=" * 50)
    print("✅ 检测完成")


if __name__ == "__main__":
    main()
