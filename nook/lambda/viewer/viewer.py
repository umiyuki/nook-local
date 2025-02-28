import datetime
import os
import re

import boto3
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from gemini_client import create_client
from mangum import Mangum

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# S3バケット名は環境変数から取得
BUCKET_NAME = os.environ.get("BUCKET_NAME")
s3_client = boto3.client("s3")
gemini_model = "gemini-2.0-flash"

# 対象のアプリ名リスト
app_names = [
    "github_trending",
    "hacker_news",
    "paper_summarizer",
    "reddit_explorer",
    "tech_feed",
]

# 天気アイコンの対応表
WEATHER_ICONS = {
    "100": "☀️",  # 晴れ
    "101": "🌤️",  # 晴れ時々くもり
    "200": "☁️",  # くもり
    "201": "⛅",  # くもり時々晴れ
    "202": "🌧️",  # くもり一時雨
    "300": "🌧️",  # 雨
    "301": "🌦️",  # 雨時々晴れ
    "400": "🌨️",  # 雪
}


def get_weather_data():
    """
    気象庁のAPIから東京の天気データを取得する

    Returns
    -------
    dict
        天気データ（気温と天気コード）
    """
    try:
        response = requests.get(
            "https://www.jma.go.jp/bosai/forecast/data/forecast/130000.json", timeout=5
        )
        response.raise_for_status()
        data = response.json()

        # 東京地方のデータを取得
        tokyo = next(
            (
                area
                for area in data[0]["timeSeries"][2]["areas"]
                if area["area"]["name"] == "東京"
            ),
            None,
        )
        tokyo_weather = next(
            (
                area
                for area in data[0]["timeSeries"][0]["areas"]
                if area["area"]["code"] == "130010"
            ),
            None,
        )

        if tokyo and tokyo_weather:
            # 現在の気温（temps[0]が最低気温、temps[1]が最高気温）
            temps = tokyo["temps"]
            weather_code = tokyo_weather["weatherCodes"][0]
            weather_icon = WEATHER_ICONS.get(weather_code, "")

            return {
                "temp": temps[0],
                "weather_code": weather_code,
                "weather_icon": weather_icon,
            }
    except Exception as e:
        print(f"Error fetching weather data: {e}")

    # エラー時やデータが取得できない場合はデフォルト値を返す
    return {
        "temp": "--",
        "weather_code": "100",  # デフォルトは晴れ
        "weather_icon": WEATHER_ICONS.get("100", "☀️"),
    }


def extract_links(text: str) -> list[str]:
    """Markdownテキストからリンクを抽出する"""
    # Markdown形式のリンク [text](url) を抽出
    markdown_links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)
    # もし[text]の部分が[Image]または[Video]の場合は、その部分を除外
    markdown_links = [
        (text, url)
        for text, url in markdown_links
        if not text.startswith("[Image]") and not text.startswith("[Video]")
    ]
    # 通常のURLも抽出
    urls = re.findall(r"(?<![\(\[])(https?://[^\s\)]+)", text)

    return [url for _, url in markdown_links] + urls


def fetch_url_content(url: str) -> str | None:
    """URLの内容を取得してテキストに変換する"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # スクリプト、スタイル、ナビゲーション要素を削除
        for element in soup(["script", "style", "nav", "header", "footer"]):
            element.decompose()

        # メインコンテンツを抽出（article, main, または本文要素）
        main_content = soup.find("article") or soup.find("main") or soup.find("body")
        if main_content:
            # テキストを抽出し、余分な空白を削除
            text = " ".join(main_content.get_text(separator=" ").split())
            # 長すぎる場合は最初の1000文字に制限
            return text[:1000] + "..." if len(text) > 1000 else text

        return None
    except Exception as e:
        print(f"Error fetching URL {url}: {e}")
        return None


def fetch_markdown(app_name: str, date_str: str) -> str:
    """
    指定されたアプリ名と日付のS3上のMarkdownファイルを取得し、
    MarkdownをHTMLに変換して返す。
    """
    key = f"{app_name}/{date_str}.md"
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        md_content = response["Body"].read().decode("utf-8")
        # デバッグ用にMarkdownの内容をログに出力
        print(f"Fetched markdown for {key}:")
        print(md_content[:500])  # 最初の500文字だけ表示
        return md_content
    except Exception as e:
        return f"Error fetching {key}: {e}"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, date: str = None):
    if date is None:
        date = datetime.date.today().strftime("%Y-%m-%d")
    contents = {name: fetch_markdown(name, date) for name in app_names}

    # 天気データを取得
    weather_data = get_weather_data()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "contents": contents,
            "date": date,
            "app_names": app_names,
            "weather_data": weather_data,
        },
    )


@app.get("/api/weather", response_class=JSONResponse)
async def get_weather():
    """天気データを取得するAPIエンドポイント"""
    return get_weather_data()


_MESSAGE = """
以下の記事に関連して、検索エンジンを用いて事実を確認しながら、ユーザーからの質問に対してできるだけ詳細に答えてください。
なお、回答はMarkdown形式で記述してください。

[記事]

{markdown}

{additional_context}

[チャット履歴]

'''
{chat_history}
'''

[ユーザーからの新しい質問]

'''
{message}
'''

それでは、回答をお願いします。
"""


@app.post("/chat/{topic_id}")
async def chat(topic_id: str, request: Request):
    data = await request.json()
    message = data.get("message")
    markdown = data.get("markdown")
    chat_history = data.get("chat_history", "なし")  # チャット履歴を受け取る

    # markdownとメッセージからリンクを抽出
    links = extract_links(markdown) + extract_links(message)

    # リンクの内容を取得
    additional_context = []
    for url in links:
        if content := fetch_url_content(url):
            additional_context.append(f"- Content from {url}:\n\n'''{content}'''\n\n")

    # 追加コンテキストがある場合、markdownに追加
    if additional_context:
        additional_context = (
            "\n\n[記事またはユーザーからの質問に含まれるリンクの内容](うまく取得できていない可能性があります)\n\n"
            + "\n\n".join(additional_context)
        )
    else:
        additional_context = ""

    formatted_message = _MESSAGE.format(
        markdown=markdown,
        additional_context=additional_context,
        chat_history=chat_history,
        message=message,
    )

    gemini_client = create_client(use_search=True)
    response_text = gemini_client.chat_with_search(formatted_message)

    return {"response": response_text}


# AWS Lambda上でFastAPIを実行するためのハンドラ
lambda_handler = Mangum(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
