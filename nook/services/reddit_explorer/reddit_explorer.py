"""Redditの人気投稿を収集・要約するサービス。"""

import os
import tomli
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional

import praw
from praw.models import Submission

from nook.common.grok_client import Grok3Client
from nook.common.storage import LocalStorage


@dataclass
class RedditPost:
    """
    Reddit投稿情報。
    
    Parameters
    ----------
    type : Literal["image", "gallery", "video", "poll", "crosspost", "text", "link"]
        投稿タイプ。
    id : str
        投稿ID。
    title : str
        タイトル。
    url : str | None
        URL。
    upvotes : int
        アップボート数。
    text : str
        本文。
    permalink : str
        投稿へのパーマリンク。
    thumbnail : str
        サムネイルURL。
    """
    
    type: Literal["image", "gallery", "video", "poll", "crosspost", "text", "link"]
    id: str
    title: str
    url: str | None
    upvotes: int
    text: str
    permalink: str = ""
    comments: List[Dict[str, str | int]] = field(default_factory=list)
    summary: str = field(init=False)
    thumbnail: str = "self"


class RedditExplorer:
    """
    Redditの人気投稿を収集・要約するクラス。
    
    Parameters
    ----------
    client_id : str, optional
        Reddit APIのクライアントID。指定しない場合は環境変数から取得。
    client_secret : str, optional
        Reddit APIのクライアントシークレット。指定しない場合は環境変数から取得。
    user_agent : str, optional
        Reddit APIのユーザーエージェント。指定しない場合は環境変数から取得。
    storage_dir : str, default="data"
        ストレージディレクトリのパス。
    """
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_agent: Optional[str] = None,
        storage_dir: str = "data"
    ):
        """
        RedditExplorerを初期化します。
        
        Parameters
        ----------
        client_id : str, optional
            Reddit APIのクライアントID。指定しない場合は環境変数から取得。
        client_secret : str, optional
            Reddit APIのクライアントシークレット。指定しない場合は環境変数から取得。
        user_agent : str, optional
            Reddit APIのユーザーエージェント。指定しない場合は環境変数から取得。
        storage_dir : str, default="data"
            ストレージディレクトリのパス。
        """
        self.client_id = client_id or os.environ.get("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("REDDIT_CLIENT_SECRET")
        self.user_agent = user_agent or os.environ.get("REDDIT_USER_AGENT")
        
        if not all([self.client_id, self.client_secret, self.user_agent]):
            raise ValueError("Reddit API credentials must be provided or set as environment variables")
        
        self.reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent
        )
        
        self.grok_client = Grok3Client()
        self.storage = LocalStorage(storage_dir)
        
        # サブレディットの設定を読み込む
        script_dir = Path(__file__).parent
        with open(script_dir / "subreddits.toml", "rb") as f:
            self.subreddits_config = tomli.load(f)
    
    def run(self, limit: int = 3) -> None:
        """
        Redditの人気投稿を収集・要約して保存します。
        
        Parameters
        ----------
        limit : int, default=3
            各サブレディットから取得する投稿数。
        """
        all_posts = []
        
        # 各カテゴリのサブレディットから投稿を取得
        for category, subreddits in self.subreddits_config.items():
            for subreddit_name in subreddits:
                posts = self._retrieve_hot_posts(subreddit_name, limit)
                
                for post in posts:
                    # トップコメントを取得
                    comments = self._retrieve_top_comments_of_post(post, limit=5)
                    post.comments = comments
                    
                    # 投稿を要約
                    self._summarize_reddit_post(post)
                    
                    all_posts.append((category, subreddit_name, post))
        
        # 要約を保存
        self._store_summaries(all_posts)
    
    def _retrieve_hot_posts(self, subreddit_name: str, limit: int) -> List[RedditPost]:
        """
        サブレディットの人気投稿を取得します。
        
        Parameters
        ----------
        subreddit_name : str
            サブレディット名。
        limit : int
            取得する投稿数。
            
        Returns
        -------
        List[RedditPost]
            取得した投稿のリスト。
        """
        subreddit = self.reddit.subreddit(subreddit_name)
        posts = []
        
        for submission in subreddit.hot(limit=limit):
            if submission.stickied:
                continue
            
            # 投稿タイプを判定
            post_type = "text"
            if hasattr(submission, "is_video") and submission.is_video:
                post_type = "video"
            elif hasattr(submission, "is_gallery") and submission.is_gallery:
                post_type = "gallery"
            elif hasattr(submission, "poll_data") and submission.poll_data:
                post_type = "poll"
            elif hasattr(submission, "crosspost_parent") and submission.crosspost_parent:
                post_type = "crosspost"
            elif submission.is_self:
                post_type = "text"
            elif any(submission.url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif"]):
                post_type = "image"
            else:
                post_type = "link"
            
            # タイトルと本文を日本語に翻訳
            title = submission.title
            text_ja = self._translate_to_japanese(submission.selftext) if submission.selftext else ""
            
            post = RedditPost(
                type=post_type,
                id=submission.id,
                title=title,
                url=submission.url if not submission.is_self else None,
                upvotes=submission.score,
                text=text_ja,
                permalink=f"https://www.reddit.com{submission.permalink}",
                thumbnail=submission.thumbnail if hasattr(submission, "thumbnail") else "self"
            )
            
            posts.append(post)
        
        return posts
    
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
            prompt = f"以下の英語のテキストを自然な日本語に翻訳してください。専門用語や固有名詞は適切に翻訳し、必要に応じて英語の原語を括弧内に残してください。\n\n{text}"
            
            translated_text = self.grok_client.generate_content(
                prompt=prompt,
                temperature=0.3,
                max_tokens=1000
            )
            
            return translated_text
        except Exception as e:
            print(f"Error translating text: {str(e)}")
            return text  # 翻訳に失敗した場合は原文を返す
    
    def _retrieve_top_comments_of_post(self, post: RedditPost, limit: int = 5) -> List[Dict[str, str | int]]:
        """
        投稿のトップコメントを取得します。
        
        Parameters
        ----------
        post : RedditPost
            投稿情報。
        limit : int, default=5
            取得するコメント数。
            
        Returns
        -------
        List[Dict[str, str | int]]
            取得したコメントのリスト。
        """
        submission = self.reddit.submission(id=post.id)
        submission.comment_sort = "top"
        submission.comment_limit = limit
        
        comments = []
        for comment in submission.comments[:limit]:
            if hasattr(comment, "body"):
                # コメントを日本語に翻訳
                comment_text_ja = self._translate_to_japanese(comment.body)
                
                comments.append({
                    "text": comment_text_ja,
                    "score": comment.score if hasattr(comment, "score") else 0
                })
        
        return comments
    
    def _summarize_reddit_post(self, post: RedditPost) -> None:
        """
        Reddit投稿を要約します。
        
        Parameters
        ----------
        post : RedditPost
            要約する投稿。
        """
        prompt = f"""
        以下のReddit投稿を要約してください。

        タイトル: {post.title}
        本文: {post.text if post.text else '(本文なし)'}
        URL: {post.url if post.url else '(URLなし)'}
        
        トップコメント:
        {chr(10).join([f"- {comment['text']}" for comment in post.comments])}
        
        要約は以下の形式で行い、日本語で回答してください:
        1. 投稿の主な内容（1-2文）
        2. 重要なポイント（箇条書き3-5点）
        3. 議論の傾向（コメントから）
        """
        
        system_instruction = """
        あなたはReddit投稿の要約を行うアシスタントです。
        与えられた投稿とコメントを分析し、簡潔で情報量の多い要約を作成してください。
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
            post.summary = summary
        except Exception as e:
            post.summary = f"要約の生成中にエラーが発生しました: {str(e)}"
    
    def _store_summaries(self, posts: List[tuple[str, str, RedditPost]]) -> None:
        """
        要約を保存します。
        
        Parameters
        ----------
        posts : List[tuple[str, str, RedditPost]]
            保存する投稿のリスト（カテゴリ、サブレディット名、投稿）。
        """
        today = datetime.now()
        content = f"# Reddit 人気投稿 ({today.strftime('%Y-%m-%d')})\n\n"
        
        # カテゴリごとに整理
        categories = {}
        for category, subreddit, post in posts:
            if category not in categories:
                categories[category] = {}
            
            if subreddit not in categories[category]:
                categories[category][subreddit] = []
            
            categories[category][subreddit].append(post)
        
        # Markdownを生成
        for category, subreddits in categories.items():
            content += f"## {category.capitalize()}\n\n"
            
            for subreddit, subreddit_posts in subreddits.items():
                content += f"### r/{subreddit}\n\n"
                
                for post in subreddit_posts:
                    content += f"#### [{post.title}]({post.permalink})\n\n"
                    
                    if post.url and post.url != post.permalink:
                        content += f"リンク: {post.url}\n\n"
                    
                    if post.text:
                        content += f"本文: {post.text[:200]}{'...' if len(post.text) > 200 else ''}\n\n"
                    
                    content += f"アップボート: {post.upvotes}\n\n"
                    content += f"**要約**:\n{post.summary}\n\n"
                    content += "---\n\n"
        
        # 保存
        self.storage.save_markdown(content, "reddit_explorer", today)
