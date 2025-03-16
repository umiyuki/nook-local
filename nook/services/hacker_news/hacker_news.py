"""Hacker Newsの記事を収集するサービス。"""

import json
from dataclasses import dataclass, field
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
    comments : List[str]
        記事へのコメント。
    story_id : int
        Hacker News記事のID。
    """
    title: str
    score: int
    url: Optional[str] = None
    text: Optional[str] = None
    summary: str = ""
    story_id: int = 0
    comments: List[str] = field(default_factory=list)



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
        self.grok_client = GeminiClient()
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
                story_id=story_id,
                url=item.get("url"),
                text=item.get("text"),
                comments=[]
            )

            # コメントの取得
            if "kids" in item:
                # 上位5件のコメントを取得
                comment_ids = item["kids"][:50]
                for comment_id in comment_ids:
                    try:
                        comment_response = requests.get(f"{self.base_url}/item/{comment_id}.json")
                        comment_data = comment_response.json()
                        if comment_data and "text" in comment_data:
                            story.comments.append(comment_data["text"])
                    except Exception as e:
                        print(f"Error fetching comment {comment_id}: {str(e)}")
            
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
        
        for story in stories:
            self._summarize_story(story)
        
        return stories
    
    def _summarize_story(self, story: Story) -> None:
        """
        Hacker News記事を要約します。

        Parameters
        ----------
        story : Story
            要約する記事。
        """
        if not story.text and not story.comments:
            story.summary = "本文とコメントの情報がないため要約できません。"
            return

        prompt = f"""
        以下のHacker News記事を要約してください。

        タイトル: {story.title}
        本文: {story.text}
        スコア: {story.score}"""
        
        if story.comments:
            prompt += f"""

        記事へのコメント:
        {chr(10).join(f"- {comment}" for comment in story.comments)}"""

        if story.text and story.comments:
            prompt += """

        要約は以下の形式で行い、日本語で回答してください:
        1. 記事の日本語翻訳されたタイトル
        2. 記事の主な内容
        3. 重要なポイント（箇条書き）
        4. この記事が注目を集めた理由
        5. コミュニティの反応
           - コメントから見られる主な意見や議論
           - 記事に対する全体的な評価や感想"""
        elif not story.text and story.comments:
            prompt += """

        要約は以下の形式で行い、日本語で回答してください:
        1. コメントから推測される記事の主題
        2. 主な議論のポイント（箇条書き3-5点）
        3. コミュニティの全体的な反応や評価"""
        else:
            prompt += """

        要約は以下の形式で行い、日本語で回答してください:
        1. 記事の主な内容（1-2文）
        2. 重要なポイント（箇条書き3-5点）
        3. 記事のインパクトや意義"""

        system_instruction = """
        あなたはHacker News記事の要約を行うアシスタントです。
        与えられた記事を分析し、情報量の多い要約を作成してください。
        技術的な内容は正確に、一般的な内容は分かりやすく要約してください。
        回答は必ず日本語で行ってください。専門用語は適切に翻訳し、必要に応じて英語の専門用語を括弧内に残してください。
        コメントの分析では、建設的な議論や重要な洞察を中心に要約してください。
        """

        try:
            summary = self.grok_client.generate_content(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=0.3,
                max_tokens=10000
            )
            story.summary = summary
            # LLM呼び出しをカウント
            counter.increment_llm("hacker_news")
        except Exception as e:
            story.summary = f"要約の生成中にエラーが発生しました: {str(e)}"

    def _translate_to_japanese(self, text: str) -> str:
        """
        テキストを日本語に翻訳します。
        
        Parameters
        ----------
        text : str
            翻訳するテキスト。
            
        Returns
        -------
        str
            翻訳されたテキスト。
        """
        if not text:
            return ""
        
        try:
            # GoogletransのTranslatorインスタンスを作成
            translator = Translator()
            # 英語から日本語に翻訳
            translated = translator.translate(text, src='en', dest='ja')
            # Googletrans呼び出しをカウント
            counter.increment_googletrans("hacker_news")
            return translated.text
        except Exception as e:
            print(f"Error translating text: {str(e)}")
            return text  # 翻訳に失敗した場合は原文を返す

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
            
            # コメントページへのリンクを追加（コメントの数も表示）
            comments_count = len(story.comments)
            comments_text = f"[コメント ({comments_count})]"
            comments_link = f"https://news.ycombinator.com/item?id={story.story_id}"
            
            content += f"## {title_link} - {f'[コメント ({comments_count})]({comments_link})'}\n\n"
            content += f"スコア: {story.score}\n\n"
            
            # 要約があれば表示、なければ本文を表示
            if story.summary:
                content += f"**要約**:\n{story.summary}\n\n"
            elif story.text:
                content += f"{story.text[:500]}{'...' if len(story.text) > 500 else ''}\n\n"
            
            content += "---\n\n"
        
        # 保存
        self.storage.save_markdown(content, "hacker_news", today)
