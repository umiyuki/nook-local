"""4chanからのAI関連スレッド収集サービス。"""

import os
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import time

import requests
from bs4 import BeautifulSoup

from nook.common.grok_client import Grok3Client
from nook.common.storage import LocalStorage


@dataclass
class Thread:
    """
    4chanスレッド情報。
    
    Parameters
    ----------
    thread_id : int
        スレッドID。
    title : str
        スレッドタイトル。
    url : str
        スレッドURL。
    board : str
        ボード名。
    posts : List[Dict[str, Any]]
        投稿リスト。
    timestamp : int
        作成タイムスタンプ。
    """
    
    thread_id: int
    title: str
    url: str
    board: str
    posts: List[Dict[str, Any]]
    timestamp: int
    summary: str = field(default="")


class FourChanExplorer:
    """
    4chanからAI関連スレッドを収集するクラス。
    
    Parameters
    ----------
    storage_dir : str, default="data"
        ストレージディレクトリのパス。
    """
    
    def __init__(self, storage_dir: str = "data"):
        """
        FourChanExplorerを初期化します。
        
        Parameters
        ----------
        storage_dir : str, default="data"
            ストレージディレクトリのパス。
        """
        self.storage = LocalStorage(storage_dir)
        self.grok_client = Grok3Client()
        
        # 対象となるボード
        self.target_boards = ["g", "sci", "biz", "pol"]
        
        # AIに関連するキーワード
        self.ai_keywords = [
            "ai", "artificial intelligence", "machine learning", "ml", "deep learning", 
            "neural network", "gpt", "llm", "chatgpt", "claude", "gemini", "grok", 
            "anthropic", "openai", "stable diffusion", "dalle", "midjourney"
        ]
        
        # APIリクエスト間の遅延（4chanのAPI利用規約を遵守するため）
        self.request_delay = 1  # 秒
    
    def run(self, thread_limit: int = 5) -> None:
        """
        4chanからAI関連スレッドを収集して保存します。
        
        Parameters
        ----------
        thread_limit : int, default=5
            各ボードから取得するスレッド数。
        """
        all_threads = []
        
        # 各ボードからスレッドを取得
        for board in self.target_boards:
            try:
                print(f"ボード /{board}/ からのスレッド取得を開始します...")
                threads = self._retrieve_ai_threads(board, thread_limit)
                print(f"ボード /{board}/ から {len(threads)} 件のスレッドを取得しました")
                
                # スレッドを要約
                for thread in threads:
                    self._summarize_thread(thread)
                
                all_threads.extend(threads)
                
                # APIリクエスト間の遅延
                time.sleep(self.request_delay)
            
            except Exception as e:
                print(f"Error processing board /{board}/: {str(e)}")
        
        print(f"合計 {len(all_threads)} 件のスレッドを取得しました")
        
        # 要約を保存
        if all_threads:
            self._store_summaries(all_threads)
            print(f"スレッドの要約を保存しました")
        else:
            print("保存するスレッドがありません")
    
    def _retrieve_ai_threads(self, board: str, limit: int) -> List[Thread]:
        """
        特定のボードからAI関連スレッドを取得します。
        
        Parameters
        ----------
        board : str
            ボード名。
        limit : int
            取得するスレッド数。
            
        Returns
        -------
        List[Thread]
            取得したスレッドのリスト。
        """
        # カタログの取得（すべてのスレッドのリスト）
        catalog_url = f"https://a.4cdn.org/{board}/catalog.json"
        response = requests.get(catalog_url)
        if response.status_code != 200:
            print(f"カタログの取得に失敗しました: {response.status_code}")
            return []
        
        catalog_data = response.json()
        
        # AI関連のスレッドをフィルタリング
        ai_threads = []
        for page in catalog_data:
            for thread in page.get("threads", []):
                # スレッドのタイトル（subject）とコメント（com）を確認
                subject = thread.get("sub", "").lower()
                comment = thread.get("com", "").lower()
                
                # HTMLタグを除去
                if comment:
                    comment = re.sub(r'<[^>]*>', '', comment)
                
                # AIキーワードが含まれているかチェック
                is_ai_related = any(keyword in subject or keyword in comment for keyword in self.ai_keywords)
                
                if is_ai_related:
                    thread_id = thread.get("no")
                    timestamp = thread.get("time", 0)
                    title = thread.get("sub", f"Untitled Thread {thread_id}")
                    
                    # スレッドのURLを構築
                    thread_url = f"https://boards.4chan.org/{board}/thread/{thread_id}"
                    
                    # スレッドの投稿を取得
                    thread_data = self._retrieve_thread_posts(board, thread_id)
                    
                    ai_threads.append(Thread(
                        thread_id=thread_id,
                        title=title,
                        url=thread_url,
                        board=board,
                        posts=thread_data,
                        timestamp=timestamp
                    ))
                    
                    # 指定された数のスレッドを取得したら終了
                    if len(ai_threads) >= limit:
                        break
            
            if len(ai_threads) >= limit:
                break
        
        return ai_threads
    
    def _retrieve_thread_posts(self, board: str, thread_id: int) -> List[Dict[str, Any]]:
        """
        スレッドの投稿を取得します。
        
        Parameters
        ----------
        board : str
            ボード名。
        thread_id : int
            スレッドID。
            
        Returns
        -------
        List[Dict[str, Any]]
            投稿のリスト。
        """
        thread_url = f"https://a.4cdn.org/{board}/thread/{thread_id}.json"
        response = requests.get(thread_url)
        
        if response.status_code != 200:
            print(f"スレッドの取得に失敗しました: {response.status_code}")
            return []
        
        thread_data = response.json()
        posts = thread_data.get("posts", [])
        
        # APIリクエスト間の遅延
        time.sleep(self.request_delay)
        
        return posts
    
    def _summarize_thread(self, thread: Thread) -> None:
        """
        スレッドを要約します。
        
        Parameters
        ----------
        thread : Thread
            要約するスレッド。
        """
        # スレッドのコンテンツを抽出（最初の投稿と、最も反応のある投稿を含む）
        thread_content = ""
        
        # スレッドのタイトルを追加
        thread_content += f"タイトル: {thread.title}\n\n"
        
        # オリジナルポスト（OP）を追加
        if thread.posts and len(thread.posts) > 0:
            op = thread.posts[0]
            op_text = op.get("com", "")
            if op_text:
                # HTMLタグを除去
                op_text = re.sub(r'<[^>]*>', ' ', op_text)
                thread_content += f"OP: {op_text}\n\n"
        
        # 返信を追加（最大5件）
        replies = thread.posts[1:6] if len(thread.posts) > 1 else []
        for i, reply in enumerate(replies):
            reply_text = reply.get("com", "")
            if reply_text:
                # HTMLタグを除去
                reply_text = re.sub(r'<[^>]*>', ' ', reply_text)
                thread_content += f"返信 {i+1}: {reply_text}\n\n"
        
        prompt = f"""
        以下の4chanスレッドを要約してください。

        ボード: /{thread.board}/
        {thread_content}
        
        要約は以下の形式で行い、日本語で回答してください:
        1. スレッドの主な内容（1-2文）
        2. 議論の主要ポイント（箇条書き3-5点）
        3. スレッドの全体的な論調
        
        注意：攻撃的な内容やヘイトスピーチは緩和し、主要な技術的議論に焦点を当ててください。
        """
        
        system_instruction = """
        あなたは4chanスレッドの要約を行うアシスタントです。
        投稿された内容を客観的に分析し、技術的議論や情報に焦点を当てた要約を提供してください。
        過度な攻撃性、ヘイトスピーチ、差別的内容は中和して表現し、有益な情報のみを抽出してください。
        回答は日本語で行い、AIやテクノロジーに関連する情報を優先的に含めてください。
        """
        
        try:
            summary = self.grok_client.generate_content(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=0.3,
                max_tokens=1000
            )
            thread.summary = summary
        except Exception as e:
            thread.summary = f"要約の生成中にエラーが発生しました: {str(e)}"
    
    def _store_summaries(self, threads: List[Thread]) -> None:
        """
        要約を保存します。
        
        Parameters
        ----------
        threads : List[Thread]
            保存するスレッドのリスト。
        """
        today = datetime.now()
        content = f"# 4chan AI関連スレッド ({today.strftime('%Y-%m-%d')})\n\n"
        
        # ボードごとに整理
        boards = {}
        for thread in threads:
            if thread.board not in boards:
                boards[thread.board] = []
            
            boards[thread.board].append(thread)
        
        # Markdownを生成
        for board, board_threads in boards.items():
            content += f"## /{board}/\n\n"
            
            for thread in board_threads:
                formatted_title = thread.title if thread.title else f"無題スレッド #{thread.thread_id}"
                content += f"### [{formatted_title}]({thread.url})\n\n"
                content += f"作成日時: <t:{thread.timestamp}:F>\n\n"
                content += f"**要約**:\n{thread.summary}\n\n"
                
                content += "---\n\n"
        
        # 保存
        self.storage.save_markdown(content, "4chan_explorer", today)
