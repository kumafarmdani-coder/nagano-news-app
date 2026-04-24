"""
毎朝長野日報のニュースを取得してnews.jsonを更新するスクリプト
GitHub Actionsから自動実行される
"""
import os
import json
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup
import anthropic

JST = timezone(timedelta(hours=9))

def fetch_article_list():
    """長野日報のニュース一覧から最新記事を取得"""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
    res = requests.get("https://www.nagano-np.co.jp/news/", headers=headers, timeout=15)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    articles = []
    # 記事リンクを探す（nagano-np.co.jpの構造に合わせて調整）
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "news/detail.php?id=" in href:
            title = a.get_text(strip=True)
            if title and len(title) > 4:
                full_url = href if href.startswith("http") else f"https://www.nagano-np.co.jp{href}"
                articles.append({"title": title, "url": full_url})

    # 重複除去
    seen = set()
    unique = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)
    return unique[:30]  # 最新30件


def categorize_with_claude(articles, today_str):
    """Claude APIで記事を分類・優先選択し10件に絞る"""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    articles_text = "\n".join(
        f'{i+1}. {a["title"]} ({a["url"]})'
        for i, a in enumerate(articles)
    )

    prompt = f"""以下は長野日報（nagano-np.co.jp）の最新記事リストです。今日は{today_str}です。

{articles_text}

これらの中から以下の優先順位で10件を選び、各記事に2〜3行の要約をつけてJSON形式で出力してください。

優先順位：
1. 箕輪町の役場・行政・議会・行政関係団体のニュース → tag: "admin", tag_label: "🏛行政"
2. 伊那市・箕輪町・南箕輪村・辰野町の観光・イベント・自然記事 → tag: "tourism", tag_label: "🌿観光"
3. 伊那市の教育・学校・子ども関連記事 → tag: "education", tag_label: "📚教育"
4. その他の地域ニュース → tag: "general", tag_label: "📰一般"

必ずこのJSONフォーマットのみで出力してください（説明文不要）：
{{
  "date": "{today_str}",
  "updated_at": "{datetime.now(JST).isoformat()}",
  "articles": [
    {{
      "number": 1,
      "tag": "admin",
      "tag_label": "🏛行政",
      "title": "記事タイトル",
      "url": "https://www.nagano-np.co.jp/...",
      "summary": "2〜3行の要約"
    }}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    text = message.content[0].text.strip()
    # JSON部分を抽出
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        return json.loads(match.group())
    raise ValueError(f"JSONが取得できませんでした: {text[:200]}")


def main():
    now = datetime.now(JST)
    today_str = now.strftime("%Y年%-m月%-d日（%a）").replace(
        "Mon","月").replace("Tue","火").replace("Wed","水").replace(
        "Thu","木").replace("Fri","金").replace("Sat","土").replace("Sun","日")

    print(f"[{now.isoformat()}] ニュース取得開始: {today_str}")

    articles = fetch_article_list()
    print(f"記事候補: {len(articles)}件")

    if not articles:
        print("記事が取得できませんでした")
        return

    data = categorize_with_claude(articles, today_str)
    data["updated_at"] = now.isoformat()

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"news.json を更新しました（{len(data['articles'])}件）")


if __name__ == "__main__":
    main()
