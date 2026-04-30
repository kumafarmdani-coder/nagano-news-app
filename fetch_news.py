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

# ── エリア定義 ──────────────────────────────────────────
# 上伊那地域（優先）
KAMI_INA_AREAS = [
    "伊那市", "伊那", "箕輪町", "箕輪", "南箕輪村", "南箕輪",
    "辰野町", "辰野", "駒ケ根市", "駒ヶ根市", "駒ケ根", "駒ヶ根",
    "中川村", "中川", "宮田村", "宮田", "飯島町", "飯島",
]
# 諏訪地域（最大3件まで）
SUWA_AREAS = [
    "諏訪市", "諏訪", "岡谷市", "岡谷", "茅野市", "茅野",
    "下諏訪町", "下諏訪", "富士見町", "富士見", "原村",
    "霧ケ峰", "霧が峰", "諏訪湖",
]
SUWA_LIMIT = 3

# ── 分類キーワード ────────────────────────────────────────
ADMIN_KEYWORDS   = ["箕輪町", "箕輪村"]
ADMIN_EXTRAS     = ["役場", "議会", "行政", "条例", "予算", "町長", "村長", "定例会", "委員会"]
TOURISM_AREAS    = KAMI_INA_AREAS
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


def is_suwa(title):
    """諏訪地域の記事かどうか判定"""
    return any(k in title for k in SUWA_AREAS)


def is_kami_ina(title):
    """上伊那地域の記事かどうか判定"""
    return any(k in title for k in KAMI_INA_AREAS)


def classify(title):
    """記事タイトルからカテゴリを判定"""
    # 優先1: 箕輪町の行政ニュース
    if any(k in title for k in ADMIN_KEYWORDS):
        return "admin", "🏛行政"

    # 優先2: 上伊那エリアの観光
    if is_kami_ina(title) and any(k in title for k in TOURISM_KEYWORDS):
        return "tourism", "🌿観光"

    # 優先3: 伊那市の教育
    if any(k in title for k in EDUCATION_AREAS) and any(k in title for k in EDUCATION_KEYWORDS):
        return "education", "📚教育"

    # 上伊那エリアの一般（諏訪より優先）
    if is_kami_ina(title):
        return "general", "📰一般"

    # 諏訪・その他の観光
    if any(k in title for k in TOURISM_KEYWORDS):
        return "tourism", "🌿観光"

    return "general", "📰一般"


def prioritize(articles):
    """優先順位でソートして10件選ぶ（諏訪はSUWA_LIMIT件まで）"""
    tagged = []
    for a in articles:
        tag, tag_label = classify(a["title"])
        suwa = is_suwa(a["title"])
        kami = is_kami_ina(a["title"])

        if tag == "admin":
            order = 0
        elif tag == "tourism" and kami:
            order = 1
        elif tag == "education":
            order = 2
        elif tag == "general" and kami:
            order = 3
        elif suwa:
            order = 4   # 諏訪は後回し
        else:
            order = 5

        tagged.append({**a, "tag": tag, "tag_label": tag_label,
                        "_order": order, "_suwa": suwa})

    tagged.sort(key=lambda x: x["_order"])

    result = []
    suwa_count = 0
    for item in tagged:
        if len(result) >= 10:
            break
        if item["_suwa"]:
            if suwa_count >= SUWA_LIMIT:
                continue  # 諏訪は上限を超えたらスキップ
            suwa_count += 1
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
