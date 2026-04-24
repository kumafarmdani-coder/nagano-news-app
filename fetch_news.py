"""
長野日報ニュース自動取得スクリプト（APIキー不要版）
キーワードマッチングで記事を分類してnews.jsonを更新する
"""
import json
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))

# 分類キーワード
ADMIN_KEYWORDS   = ["箕輪町", "箕輪村"]
ADMIN_EXTRAS     = ["役場", "議会", "行政", "条例", "予算", "町長", "村長", "定例会", "委員会"]
TOURISM_AREAS    = ["伊那市", "伊那", "箕輪", "南箕輪", "辰野", "駒ケ根", "駒ヶ根", "中川村", "中川"]
TOURISM_KEYWORDS = ["観光", "イベント", "祭り", "まつり", "フェス", "キャンプ", "登山", "山", "花",
                    "桜", "紅葉", "開山", "オープン", "公園", "名所", "温泉", "体験", "ハイキング"]
EDUCATION_AREAS  = ["伊那市", "伊那"]
EDUCATION_KEYWORDS = ["教育", "学校", "小学", "中学", "高校", "高等学校", "児童", "生徒", "先生",
                      "授業", "入学", "卒業", "部活", "クラブ", "PTA", "教委", "図書"]

WEEKDAYS = ["月","火","水","木","金","土","日"]


def get_today_str():
    now = datetime.now(JST)
    wd = WEEKDAYS[now.weekday()]
    return now.strftime(f"%Y年%-m月%-d日（{wd}）")


def fetch_articles():
    """長野日報ニュース一覧から最新記事を取得"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    res = requests.get("https://www.nagano-np.co.jp/news/", headers=headers, timeout=20)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    articles = []
    seen = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "news/detail.php?id=" not in href:
            continue
        title = a_tag.get_text(strip=True)
        # 日付タイトル（「2026年4月24日付」など）はスキップ
        if re.search(r"\d{4}年\d+月\d+日付", title):
            continue
        if not title or len(title) < 5:
            continue
        url = href if href.startswith("http") else f"https://www.nagano-np.co.jp{href}"
        if url not in seen:
            seen.add(url)
            articles.append({"title": title, "url": url})

    return articles[:40]


def classify(title):
    """記事タイトルからカテゴリを判定"""
    # 優先1: 箕輪町の行政ニュース
    if any(k in title for k in ADMIN_KEYWORDS):
        if any(k in title for k in ADMIN_EXTRAS + TOURISM_KEYWORDS + EDUCATION_KEYWORDS):
            return "admin", "🏛行政"
        return "admin", "🏛行政"  # 箕輪町というだけで行政扱い

    # 優先2: 対象エリアの観光
    if any(k in title for k in TOURISM_AREAS) and any(k in title for k in TOURISM_KEYWORDS):
        return "tourism", "🌿観光"

    # 優先3: 伊那市の教育
    if any(k in title for k in EDUCATION_AREAS) and any(k in title for k in EDUCATION_KEYWORDS):
        return "education", "📚教育"

    # 観光キーワードだけでも観光扱い（エリア問わず）
    if any(k in title for k in TOURISM_KEYWORDS):
        return "tourism", "🌿観光"

    return "general", "📰一般"


def prioritize(articles):
    """優先順位でソートして10件選ぶ"""
    ORDER = {"admin": 0, "tourism": 1, "education": 2, "general": 3}
    tagged = []
    for a in articles:
        tag, tag_label = classify(a["title"])
        tagged.append({**a, "tag": tag, "tag_label": tag_label, "_order": ORDER[tag]})

    tagged.sort(key=lambda x: x["_order"])

    # 各カテゴリから重複なく選ぶ（adminを優先しつつ計10件）
    result = []
    for item in tagged:
        if len(result) >= 10:
            break
        result.append(item)

    # 10件に満たない場合は残りで補完
    for item in tagged:
        if len(result) >= 10:
            break
        if item not in result:
            result.append(item)

    return result[:10]


def main():
    now = datetime.now(JST)
    today_str = get_today_str()
    print(f"[{now.isoformat()}] ニュース取得開始: {today_str}")

    articles = fetch_articles()
    print(f"記事候補: {len(articles)}件")

    selected = prioritize(articles)

    output = {
        "date": today_str,
        "updated_at": now.isoformat(),
        "articles": [
            {
                "number": i + 1,
                "tag": a["tag"],
                "tag_label": a["tag_label"],
                "title": a["title"],
                "url": a["url"],
                "summary": f"長野日報の記事です。タイトルをタップして全文をご覧ください。",
            }
            for i, a in enumerate(selected)
        ]
    }

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"news.json 更新完了（{len(output['articles'])}件）")
    for a in output["articles"]:
        print(f"  {a['number']}. {a['tag_label']} {a['title']}")


if __name__ == "__main__":
    main()
