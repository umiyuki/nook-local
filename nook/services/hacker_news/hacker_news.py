"""Hacker Newsの記事を収集するサービス。"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from nook.common.storage import LocalStorage
from nook.common.gemini_client import GeminiClient
from googletrans import Translator
from nook.common.counters import counter

@dataclass
class Story:
    """
    Hacker News記事情報。
    
    Parameters
    ----------
    title : str
        タイトル。
    score : int
        スコア。
    url : str | None
        URL。
    text : str | None
        本文。
    """
    
    title: str
    score: int
    url: Optional[str] = None
    text: Optional[str] = None


class HackerNewsRetriever:
    """
    Hacker Newsの記事を収集するクラス。
    
    Parameters
    ----------
    storage_dir : str, default="data"
        ストレージディレクトリのパス。
    """
    
    def __init__(self, storage_dir: str = "data"):
        """
        HackerNewsRetrieverを初期化します。
        
        Parameters
        ----------
        storage_dir : str, default="data"
            ストレージディレクトリのパス。
        """
        self.storage = LocalStorage(storage_dir)
        self.base_url = "https://hacker-news.firebaseio.com/v0"
    
    def run(self, limit: int = 30) -> None:
        """
        Hacker Newsの記事を収集して保存します。
        
        Parameters
        ----------
        limit : int, default=30
            取得する記事数。
        """
        stories = self._get_top_stories(limit)
        self._store_summaries(stories)
    
    def _get_top_stories(self, limit: int) -> List[Story]:
        """
        トップ記事を取得します。
        
        Parameters
        ----------
        limit : int
            取得する記事数。
            
        Returns
        -------
        List[Story]
            取得した記事のリスト。
        """
        # トップストーリーのIDを取得
        response = requests.get(f"{self.base_url}/topstories.json")
        story_ids = response.json()[:limit]
        
        stories = []
        for story_id in story_ids:
            # 記事の詳細を取得
            response = requests.get(f"{self.base_url}/item/{story_id}.json")
            item = response.json()
            
            if "title" not in item:
                continue
            
            story = Story(
                title=item.get("title", ""),
                score=item.get("score", 0),
                url=item.get("url"),
                text=item.get("text")
            )
            
            # URLがある場合は記事の内容を取得
            if story.url and not story.text:
                try:
                    # ユーザーエージェントを設定してアクセス制限を回避
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    response = requests.get(story.url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, "html.parser")
                        
                        # メタディスクリプションを取得
                        meta_desc = soup.find("meta", attrs={"name": "description"})
                        if not meta_desc:
                            # Open Graphのdescriptionも試す
                            meta_desc = soup.find("meta", attrs={"property": "og:description"})
                        
                        if meta_desc and meta_desc.get("content"):
                            story.text = meta_desc.get("content")
                        else:
                            # 本文の最初の段落を取得（より多くの段落を試す）
                            paragraphs = soup.find_all("p")
                            if paragraphs:
                                # 最初の3つの段落を結合（短すぎる段落は除外）
                                meaningful_paragraphs = [p.get_text().strip() for p in paragraphs[:5] 
                                                        if len(p.get_text().strip()) > 50]
                                if meaningful_paragraphs:
                                    story.text = " ".join(meaningful_paragraphs[:3])
                                else:
                                    # 意味のある段落がない場合は最初の段落を使用
                                    story.text = paragraphs[0].get_text().strip()
                            
                            # 本文が取得できない場合は、article要素を探す
                            if not story.text:
                                article = soup.find("article")
                                if article:
                                    story.text = article.get_text()[:500]
                except Exception as e:
                    print(f"Error fetching content for {story.url}: {str(e)}")
            
            stories.append(story)
        
        # 日本語に翻訳
        stories = self._translate_stories_to_japanese(stories)
        
        return stories
    
    def _translate_stories_to_japanese(self, stories: List[Story]) -> List[Story]:
        """
        記事を日本語に翻訳します。
        
        Parameters
        ----------
        stories : List[Story]
            翻訳する記事のリスト。
            
        Returns
        -------
        List[Story]
            翻訳された記事のリスト。
        """
        try:
            # GoogletransのTranslatorインスタンスを作成
            translator = Translator()

            for story in stories:
                # タイトルの翻訳
                if story.title:
                    try:
                        # 英語から日本語に翻訳
                        translated = translator.translate(story.title, src='en', dest='ja')
                        # Googletrans呼び出しをカウント
                        counter.increment_googletrans("hacker_news")
                        story.title = translated.text
                    except Exception as e:
                        print(f"Error translating title: {str(e)}")
                
                # 本文の翻訳
                if story.text:
                    try:
                        # 英語から日本語に翻訳
                        translated = translator.translate(story.text, src='en', dest='ja')
                        # Googletrans呼び出しをカウント
                        counter.increment_googletrans("hacker_news")
                        story.text = translated.text
                    except Exception as e:
                        print(f"Error translating text: {str(e)}")
        
        except Exception as e:
            print(f"Error translating stories: {str(e)}")
        
        return stories
    
    def _store_summaries(self, stories: List[Story]) -> None:
        """
        記事情報を保存します。
        
        Parameters
        ----------
        stories : List[Story]
            保存する記事のリスト。
        """
        today = datetime.now()
        content = f"# Hacker News トップ記事 ({today.strftime('%Y-%m-%d')})\n\n"
        
        for story in stories:
            title_link = f"[{story.title}]({story.url})" if story.url else story.title
            content += f"## {title_link}\n\n"
            content += f"スコア: {story.score}\n\n"
            
            if story.text:
                content += f"{story.text[:500]}{'...' if len(story.text) > 500 else ''}\n\n"
            
            content += "---\n\n"
        
        # 保存
        self.storage.save_markdown(content, "hacker_news", today) 