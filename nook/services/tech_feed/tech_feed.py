"""技術ブログのRSSフィードを監視・収集・要約するサービス。"""

import tomli
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import feedparser
import requests
from bs4 import BeautifulSoup

from nook.common.grok_client import Grok3Client
from nook.common.storage import LocalStorage


@dataclass
class Article:
    """
    技術ブログの記事情報。
    
    Parameters
    ----------
    feed_name : str
        フィード名。
    title : str
        タイトル。
    url : str
        URL。
    text : str
        本文。
    soup : BeautifulSoup
        BeautifulSoupオブジェクト。
    category : str | None
        カテゴリ。
    """
    
    feed_name: str
    title: str
    url: str
    text: str
    soup: BeautifulSoup
    category: Optional[str] = None
    summary: str = field(default="")


class TechFeed:
    """
    技術ブログのRSSフィードを監視・収集・要約するクラス。
    
    Parameters
    ----------
    storage_dir : str, default="data"
        ストレージディレクトリのパス。
    """
    
    def __init__(self, storage_dir: str = "data"):
        """
        TechFeedを初期化します。
        
        Parameters
        ----------
        storage_dir : str, default="data"
            ストレージディレクトリのパス。
        """
        self.storage = LocalStorage(storage_dir)
        self.grok_client = Grok3Client()
        
        # フィードの設定を読み込む
        script_dir = Path(__file__).parent
        with open(script_dir / "feed.toml", "rb") as f:
            self.feed_config = tomli.load(f)
    
    def run(self, days: int = 1, limit: int = 3) -> None:
        """
        技術ブログのRSSフィードを監視・収集・要約して保存します。
        
        Parameters
        ----------
        days : int, default=1
            何日前までの記事を取得するか。
        limit : int, default=3
            各フィードから取得する記事数。
        """
        all_articles = []
        
        # 各カテゴリのフィードから記事を取得
        for category, feeds in self.feed_config.items():
            print(f"カテゴリ {category} の処理を開始します...")
            for feed_url in feeds:
                try:
                    # フィードを解析
                    print(f"フィード {feed_url} を解析しています...")
                    feed = feedparser.parse(feed_url)
                    feed_name = feed.feed.title if hasattr(feed, "feed") and hasattr(feed.feed, "title") else feed_url
                    
                    # 新しいエントリをフィルタリング
                    entries = self._filter_entries(feed.entries, days, limit)
                    print(f"フィード {feed_name} から {len(entries)} 件のエントリを取得しました")
                    
                    for entry in entries:
                        # 記事を取得
                        article = self._retrieve_article(entry, feed_name, category)
                        if article:
                            # 記事を要約
                            self._summarize_article(article)
                            all_articles.append(article)
                
                except Exception as e:
                    print(f"Error processing feed {feed_url}: {str(e)}")
        
        print(f"合計 {len(all_articles)} 件の記事を取得しました")
        
        # 要約を保存
        if all_articles:
            self._store_summaries(all_articles)
            print(f"記事の要約を保存しました")
        else:
            print("保存する記事がありません")
    
    def _filter_entries(self, entries: List[dict], days: int, limit: int) -> List[dict]:
        """
        新しいエントリをフィルタリングします。
        
        Parameters
        ----------
        entries : List[dict]
            エントリのリスト。
        days : int
            何日前までの記事を取得するか。
        limit : int
            取得する記事数。
            
        Returns
        -------
        List[dict]
            フィルタリングされたエントリのリスト。
        """
        print(f"エントリのフィルタリングを開始します（{len(entries)}件）...")
        
        # 日付でフィルタリング
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_entries = []
        
        for entry in entries:
            entry_date = None
            
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                entry_date = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                entry_date = datetime(*entry.updated_parsed[:6])
            
            if entry_date:
                print(f"エントリ日付: {entry_date}, カットオフ日付: {cutoff_date}")
                if entry_date >= cutoff_date:
                    recent_entries.append(entry)
            else:
                # 日付が取得できない場合は含める
                print("エントリに日付情報がありません。含めます。")
                recent_entries.append(entry)
        
        print(f"フィルタリング後のエントリ数: {len(recent_entries)}")
        
        # 最新の記事を取得
        return recent_entries[:limit]


    def _retrieve_article(self, entry: dict, feed_name: str, category: str) -> Optional[Article]:
        """
        記事を取得します。
    
        Parameters
        ----------
        entry : dict
            エントリ情報。
        feed_name : str
            フィード名。
        category : str
            カテゴリ。
    
        Returns
        -------
        Article or None
            取得した記事。取得に失敗した場合はNone。
        """
        try:
            # URLを取得
            url = entry.link if hasattr(entry, "link") else None
            if not url:
                return None
    
            # ドメインをチェックして日本語ソースかどうかを判断
            is_japanese_source = "zenn.dev" in url or "qiita.com" in url
    
            # タイトルを取得
            title = entry.title if hasattr(entry, "title") else "無題"
    
            # 記事の内容を取得
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return None
    
            soup = BeautifulSoup(response.text, "html.parser")
    
            # 本文を抽出
            text = ""
    
            # まずはエントリの要約を使用
            if hasattr(entry, "summary"):
                text = entry.summary
    
            # 次に記事の本文を抽出
            if not text:
                # メタディスクリプションを取得
                meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_desc and meta_desc.get("content"):
                    text = meta_desc.get("content")
                else:
                    # 本文の最初の段落を取得
                    paragraphs = soup.find_all("p")
                    if paragraphs:
                        text = "\n".join([p.get_text() for p in paragraphs[:5]])
    
            # タイトルは原文のまま
            # 本文は日本語ソースのものは翻訳せず、英語のものは翻訳
            text_ja = self._translate_to_japanese(text, is_japanese_source)
    
            return Article(
                feed_name=feed_name,
                title=title,  # タイトルは原文のまま
                url=url,
                text=text_ja,
                soup=soup,
                category=category
            )
    
        except Exception as e:
            print(f"Error retrieving article {entry.get('link', 'unknown')}: {str(e)}")
            return None
        
    def _translate_to_japanese(self, text: str, is_japanese_source: bool = False) -> str:
        """
        テキストを日本語に翻訳します。

        Parameters
        ----------
        text : str
            翻訳するテキスト。
        is_japanese_source : bool, default=False
            ソースが日本語かどうか。

        Returns
        -------
        str
            翻訳されたテキスト。
        """
        # 日本語ソースの場合は翻訳せずにそのまま返す
        if is_japanese_source or not text:
            return text

        try:
            prompt = f"以下の英語のテキストを自然な日本語に翻訳してください。技術用語は適切に翻訳し、必要に応じて英語の専門用語を括弧内に残してください。\n\n{text}"

            translated_text = self.grok_client.generate_content(
                prompt=prompt,
                temperature=0.3,
                max_tokens=1000
            )

            return translated_text
        except Exception as e:
            print(f"Error translating text: {str(e)}")
            return text  # 翻訳に失敗した場合は原文を返す

    def _summarize_article(self, article: Article) -> None:
        """
        記事を要約します。

        Parameters
        ----------
        article : Article
            要約する記事。
        """
        # 日本語ソースかどうかを判断
        is_japanese_source = "zenn.dev" in article.url or "qiita.com" in article.url

        if is_japanese_source:
            prompt = f"""
            以下の技術ブログの記事を要約してください。

            タイトル: {article.title}
            本文: {article.text[:2000]}

            要約は以下の形式で行い、日本語で回答してください:
            1. 記事の主な内容（1-2文）
            2. 重要なポイント（箇条書き3-5点）
            3. 技術的な洞察
            """
        else:
            prompt = f"""
            以下の技術ブログの記事を要約してください。

            タイトル: {article.title}
            本文: {article.text[:2000]}

            要約は以下の形式で行い、日本語で回答してください:
            1. 記事の主な内容（1-2文）
            2. 重要なポイント（箇条書き3-5点）
            3. 技術的な洞察
            """

        system_instruction = """
        あなたは技術ブログの記事の要約を行うアシスタントです。
        与えられた記事を分析し、簡潔で情報量の多い要約を作成してください。
        技術的な内容は正確に、一般的な内容は分かりやすく要約してください。
        回答は必ず日本語で行ってください。専門用語は適切に翻訳し、必要に応じて英語の専門用語を括弧内に残してください。
        """

        try:
            summary = self.grok_client.generate_content(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=0.3,
                max_tokens=1000
            )
            article.summary = summary
        except Exception as e:
            article.summary = f"要約の生成中にエラーが発生しました: {str(e)}"

    def _store_summaries(self, articles: List[Article]) -> None:
        """
        要約を保存します。
    
        Parameters
        ----------
        articles : List[Article]
            保存する記事のリスト。
        """
        if not articles:
            print("保存する記事がありません")
            return
    
        today = datetime.now()
        content = f"# 技術ブログ記事 ({today.strftime('%Y-%m-%d')})\n\n"
    
        # カテゴリごとに整理
        categories = {}
        for article in articles:
            if article.category not in categories:
                categories[article.category] = []
    
            categories[article.category].append(article)
    
        # Markdownを生成
        for category, category_articles in categories.items():
            content += f"## {category.replace('_', ' ').capitalize()}\n\n"
    
            for article in category_articles:
                content += f"### [{article.title}]({article.url})\n\n"
                content += f"**フィード**: {article.feed_name}\n\n"
                content += f"**要約**:\n{article.summary}\n\n"
    
                content += "---\n\n"
    
        # 保存
        print(f"tech_feed ディレクトリに保存します: {today.strftime('%Y-%m-%d')}.md")
        try:
            self.storage.save_markdown(content, "tech_feed", today)
            print("保存が完了しました")
        except Exception as e:
            print(f"保存中にエラーが発生しました: {str(e)}")
            # ディレクトリを作成して再試行
            try:
                tech_feed_dir = Path(self.storage.base_dir) / "tech_feed"
                tech_feed_dir.mkdir(parents=True, exist_ok=True)
    
                file_path = tech_feed_dir / f"{today.strftime('%Y-%m-%d')}.md"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"再試行で保存に成功しました: {file_path}")
            except Exception as e2:
                print(f"再試行でも保存に失敗しました: {str(e2)}")
    
