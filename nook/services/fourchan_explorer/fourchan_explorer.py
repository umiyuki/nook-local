"""4chanからのAI関連スレッド収集サービス。"""

import os
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
import time

import requests
from bs4 import BeautifulSoup

from nook.common.gemini_client import GeminiClient
from nook.common.storage import LocalStorage
from nook.common.tracked_thread import TrackedThread
from nook.common.counters import counter


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
        self.grok_client = GeminiClient()

        # 追跡対象スレッドの読み込み
        script_dir = Path(__file__).parent
        self.tracked_threads = TrackedThread.load_tracked_threads(script_dir / "tracked_threads.json")
        
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

        try:
            print("4chanからのスレッド収集を開始...")

            # 追跡対象スレッドを処理
            for thread_name, tracked_thread in self.tracked_threads.items():
                try:
                    print(f"追跡対象スレッド「{thread_name}」の処理を開始します...")
                    catalog = self._fetch_catalog(tracked_thread.board)
                    thread_info = self._find_thread_by_name(catalog, thread_name)

                    if not thread_info:
                        print(f"スレッド「{thread_name}」は見つかりませんでした")
                        continue

                    thread_id, title = thread_info
                    print(f"スレッド「{thread_name}」(ID: {thread_id})を処理中...")

                    # スレッドの投稿を取得
                    thread_data = self._retrieve_thread_posts(tracked_thread.board, thread_id)
                    
                    if thread_data:
                        # 差分を計算
                        new_posts = [post for post in thread_data
                                    if not tracked_thread.last_post_no 
                                    or post.get("no", 0) > tracked_thread.last_post_no]
                    
                        if new_posts:
                            print(f"スレッド「{thread_name}」に {len(new_posts)} 件の新規投稿があります")
                            thread = Thread(
                                thread_id=thread_id,
                                title=title,
                                url=f"https://boards.4chan.org/{tracked_thread.board}/thread/{thread_id}",
                                board=tracked_thread.board,
                                posts=new_posts,
                                timestamp=int(datetime.now().timestamp())
                            )
                            self._summarize_thread(thread)
                            all_threads.append(thread)
                            print(f"スレッド「{thread_name}」から {len(new_posts)} 件の新規投稿を取得しました")
                        else:
                            print(f"スレッド「{thread_name}」に新規投稿はありません")
                            
                        # 追跡情報を更新
                        max_post_no = max(post.get("no", 0) for post in thread_data)
                        tracked_thread.update(
                            thread_id=thread_id,
                            url=f"https://boards.4chan.org/{tracked_thread.board}/thread/{thread_id}",
                            last_post_no=max_post_no
                        )
                    else:
                        print(f"スレッド「{thread_name}」のデータ取得に失敗しました")

                except Exception as e:
                    print(f"追跡対象スレッド「{thread_name}」の処理中にエラーが発生しました: {str(e)}")
                    continue

            # 各ボードからスレッドを取得
            ai_threads = self._collect_ai_threads(thread_limit)
            all_threads.extend(ai_threads)
            
            print(f"合計 {len(all_threads)} 件のスレッドを取得しました")
            
            # 要約を保存
            if all_threads:
                self._store_summaries(all_threads)
                print(f"スレッドの要約を保存しました")
            else:
                print("保存するスレッドがありません")
            
            # 追跡情報を保存
            script_dir = Path(__file__).parent
            TrackedThread.save_tracked_threads(self.tracked_threads, script_dir / "tracked_threads.json")

        except Exception as e:
            print(f"スレッド収集処理中にエラーが発生しました: {str(e)}")
    
    def _fetch_catalog(self, board: str) -> List[Dict[str, Any]]:
        """
        指定された板のカタログを取得します。

        Parameters
        ----------
        board : str
            板名。

        Returns
        -------
        List[Dict[str, Any]]
            カタログデータ。
        """
        catalog_url = f"https://a.4cdn.org/{board}/catalog.json"
        response = requests.get(catalog_url)
        if response.status_code != 200:
            print(f"カタログの取得に失敗しました: {response.status_code}")
            return []
        
        return response.json()
    
    def _find_thread_by_name(self, catalog: List[Dict[str, Any]], thread_name: str) -> Optional[tuple[int, str]]:
        """
        カタログから指定された名前のスレッドを検索します。

        Parameters
        ----------
        catalog : List[Dict[str, Any]]
            カタログデータ。
        thread_name : str
            検索するスレッド名。

        Returns
        -------
        Optional[tuple[int, str]]
            見つかった場合は (スレッドID, スレッドタイトル) のタプル、
            見つからなかった場合は None。
        """
        for page in catalog:
            for thread in page.get("threads", []):
                subject = thread.get("sub", "").strip()
                if thread_name.lower() in subject.lower():
                    return thread.get("no"), subject
        return None
    
    def _collect_ai_threads(self, thread_limit: int) -> List[Thread]:
        """AIに関連するスレッドを収集します。"""
        print("AIキーワードを含むスレッドの収集を開始...")
        collected_threads = []  # ここで collected_threads を初期化
        tracked_names = {thread.name.lower() for thread in self.tracked_threads.values()}
        
        for board in self.target_boards:
            try:
                # 残りの収集数を計算
                remaining = thread_limit - len(collected_threads)
                if remaining <= 0:
                    break
                
                print(f"ボード /{board}/ からのスレッド取得を開始します...")
                threads = self._retrieve_ai_threads(board, remaining)
                print(f"ボード /{board}/ から {len(threads)} 件のスレッドを取得しました")
                
                # 追跡対象スレッドのタイトルを小文字で保持
                tracked_titles = {name.lower() for name in tracked_names}
                
                filtered_threads = []
                for thread in threads:  # すでに取得済みのスレッドを除外
                    if not any(title in thread.title.lower() for title in tracked_titles):
                        self._summarize_thread(thread)
                        filtered_threads.append(thread)
                
                collected_threads.extend(filtered_threads[:remaining])  # 残り数だけ追加
                if len(collected_threads) >= thread_limit:
                    break

                # APIリクエスト間の遅延
                time.sleep(self.request_delay * 2)  # スレッド取得後は少し長めに待機
                
            except Exception as e:
                print(f"Error processing board /{board}/: {str(e)}")
        
        print(f"合計 {len(collected_threads)} 件のAI関連スレッドを収集しました")
        return collected_threads  # 修正: collected_threads を返す
    
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
        # カタログの取得
        catalog_data = self._fetch_catalog(board)
        
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
                    try:
                        thread_data = self._retrieve_thread_posts(board, thread_id)
                        if not thread_data:
                            print(f"スレッド {thread_id} の投稿の取得に失敗しました")
                            continue
                    except Exception as e:
                        print(f"スレッド {thread_id} の投稿取得中にエラーが発生しました: {str(e)}")
                        continue
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
        try:
            print(f"スレッド {thread_id} の投稿を取得しています...")
            thread_url = f"https://a.4cdn.org/{board}/thread/{thread_id}.json"
            response = requests.get(thread_url)
            
            if response.status_code != 200:
                print(f"スレッド {thread_id} の取得に失敗しました: {response.status_code}")
                return []
            
            thread_data = response.json()
            posts = thread_data.get("posts", [])
            print(f"スレッド {thread_id} から {len(posts)} 件の投稿を取得しました")
            
            # APIリクエスト間の遅延
            time.sleep(self.request_delay)
            return posts
        except Exception as e:
            print(f"スレッド {thread_id} の取得中にエラーが発生しました: {str(e)}")
            return []
    
    def _summarize_thread(self, thread: Thread) -> None:
        """
        スレッドを要約します。
        
        Parameters
        ----------
        thread : Thread
            要約するスレッド。
        """
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
            if summary is None:
                thread.summary = "要約の生成に失敗しました"
                print(f"スレッド {thread.title} の要約生成に失敗しました: 生成結果がNoneでした")
            else:
                thread.summary = summary
        except Exception as e:
            thread.summary = f"要約の生成中にエラーが発生しました: {str(e)}"
            print(f"スレッド {thread.title} の要約生成中にエラーが発生しました: {str(e)}")
    
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
        total_threads = 0
        for thread in threads:
            if thread.board not in boards:
                boards[thread.board] = []
            
            boards[thread.board].append(thread)
            total_threads += 1
        
        if total_threads == 0:
            print("保存するスレッドがありません")
            return
        
        print(f"合計 {total_threads} 件のスレッドを保存します")
        # Markdownを生成
        for board, board_threads in boards.items():
            content += f"## /{board}/\n\n"
            
            for thread in board_threads:
                content += f"### {thread.title}\n[4chan Link]({thread.url})\n\n"
                date_str = datetime.fromtimestamp(thread.timestamp).strftime('%Y-%m-%d %H:%M:%S')
                content += f"作成日時: {date_str}\n\n"
                content += f"**要約**:\n{thread.summary}\n\n"
                
                content += "---\n\n"
        
        # 保存
        self.storage.save_markdown(content, "fourchan_explorer", today)


if __name__ == "__main__":
    explorer = FourChanExplorer()
    explorer.run()