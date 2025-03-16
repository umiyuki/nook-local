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

from nook.common.gemini_client import GeminiClient
from nook.common.storage import LocalStorage
from nook.common.tracked_thread import TrackedThread


@dataclass
class Thread:
    """
    5chanスレッド情報。
    
    Parameters
    ----------
    thread_id : int
        スレッドID。
    title : str
        スレッドタイトル。
    url : str
        スレッドURL。
    board : str
        板名。
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


class FiveChanExplorer:
    """
    5chan（旧2ちゃんねる）から情報を収集するクラス。
    
    Parameters
    ----------
    storage_dir : str, default="data"
        ストレージディレクトリのパス。
    """
    
    def __init__(self, storage_dir: str = "data"):
        """
        FiveChanExplorerを初期化します。
        
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
        
        # 対象となる板
        self.target_boards = self._load_boards()
        
        # 試すサブドメインのリスト（すべての板で試す）
        self.subdomains = [
            "mevius.5ch.net", 
            "egg.5ch.net", 
            "medaka.5ch.net", 
            "hayabusa9.5ch.net", 
            "mi.5ch.net",
            "lavender.5ch.net",
            "eagle.5ch.net",
            "rosie.5ch.net",
            "fate.5ch.net",
            "mercury.bbspink.com"  # BBSPinkのドメインを追加
        ]
        
        # AIに関連するキーワード
        self.ai_keywords = [
            "ai", "人工知能", "機械学習", "ディープラーニング", 
            "ニューラルネットワーク", "gpt", "llm", "chatgpt", "claude", "gemini", "grok", 
            "anthropic", "openai", "stable diffusion", "dalle", "midjourney",
            "自然言語処理", "大規模言語モデル", "チャットボット", "対話型ai",
            "生成ai", "画像生成", "alphaゴー", "alphago", "deepmind",
            "強化学習", "自己学習", "強い人工知能", "弱い人工知能", "特化型人工知能", 
            "pixai", "comfyui", "stablediffusion", "ai画像", "ai動画"
        ]
        
        # リクエスト間の遅延（サーバー負荷軽減のため）
        self.request_delay = 2  # 秒
    
    def _load_boards(self) -> Dict[str, str]:
        """
        対象となる板の設定を読み込みます。
        
        Returns
        -------
        Dict[str, str]
            板のID: 板の名前のディクショナリ
        """
        script_dir = Path(__file__).parent
        with open(script_dir / "boards.toml", "rb") as f:
            import tomli
            config = tomli.load(f)
            return config.get("boards", {})
    
    def run(self, thread_limit: int = 5) -> None:
        """
        5chanからAI関連スレッドを収集して保存します。
        
        Parameters
        ----------
        thread_limit : int, default=5
            各板から取得するスレッド数。
        """
        all_threads = []
        
        # まず追跡対象スレッドを処理
        for thread_name, tracked_thread in self.tracked_threads.items():
            try:
                print(f"追跡対象スレッド「{thread_name}」の処理を開始します...")
                
                # 板一覧とスレッド一覧を取得
                thread_info = self._find_latest_thread(tracked_thread.board, thread_name)
                
                if thread_info:
                    thread_id, title, url = thread_info
                    if tracked_thread.board == "onatech":  # BBSPinkの場合
                        posts, timestamp = self._retrieve_thread_posts_fromBBSPink(url)
                    else:  # 5chの場合
                        posts, timestamp = self._retrieve_thread_posts(url)
                    
                    if posts:
                        # 差分を計算
                        new_posts = []
                        for post in posts:
                            if not tracked_thread.last_post_no or post["no"] > tracked_thread.last_post_no:
                                new_posts.append(post)
                        
                        if new_posts:
                            thread = Thread(
                                thread_id=thread_id,
                                title=title,
                                url=url,
                                board=tracked_thread.board,
                                posts=new_posts,
                                timestamp=timestamp
                            )
                            self._summarize_thread(thread)
                            all_threads.append(thread)
                        
                        # 追跡情報を更新
                        max_post_no = max(post["no"] for post in posts)
                        tracked_thread.update(
                            thread_id=thread_id,
                            url=url,
                            last_post_no=max_post_no
                        )
            except Exception as e:
                print(f"追跡対象スレッド「{thread_name}」の処理中にエラーが発生しました: {str(e)}")
        
        # AIキーワードを含むスレッドを収集
        all_threads.extend(self._collect_ai_threads(thread_limit))
        
        # 要約を保存
        if all_threads:
            self._store_summaries(all_threads)
            print(f"スレッドの要約を保存しました")
        else:
            print("保存するスレッドがありません")
        
        # 追跡情報を保存
        script_dir = Path(__file__).parent
        TrackedThread.save_tracked_threads(self.tracked_threads, script_dir / "tracked_threads.json")
    
    def _collect_ai_threads(self, thread_limit: int) -> List[Thread]:
        """AIに関連するスレッドを収集します。"""
        ai_threads = []
        
        # 各板からAIキーワードを含むスレッドを取得
        for board_id, board_name in self.target_boards.items():
            try:
                print(f"板 /{board_id}/({board_name}) からのスレッド取得を開始します...")
                threads = self._retrieve_ai_threads(board_id, thread_limit)
                print(f"板 /{board_id}/({board_name}) から {len(threads)} 件のスレッドを取得しました")
                
                # スレッドを要約と追加（追跡対象と重複しないものだけ）
                tracked_names = {t.name.lower() for t in self.tracked_threads.values()}
                for thread in threads:
                    if thread.title.lower() not in tracked_names:
                        self._summarize_thread(thread)
                        ai_threads.append(thread)
                
                # リクエスト間の遅延
                time.sleep(self.request_delay)
            except Exception as e:
                print(f"板 /{board_id}/({board_name}) の処理中にエラーが発生しました: {str(e)}")
        
        return ai_threads
    
    def _find_latest_thread(self, board: str, thread_name: str) -> Optional[tuple[int, str, str]]:
        """
        特定の名前のスレッドの最新版を見つけます。

        Parameters
        ----------
        board : str
            板名（例: "onatech"）。
        thread_name : str
            検索するスレッド名（例: "なんJLLM部 避難所"）。

        Returns
        -------
        Optional[tuple[int, str, str]]
            見つかった場合は (スレッドID, スレッドタイトル, URL) のタプル。
            見つからなかった場合は None。
        """
        # BBSPinkか5chかを板名で判断
        if board in ["onatech"]:  # BBSPinkの場合
            base_domain = "mercury.bbspink.com"
            base_url = f"https://{base_domain}/{board}/subback.html"
        else:  # 5chの場合（既存のロジックを保持）
            base_url = f"https://{self.subdomains[0]}/{board}/"

        try:
            print(f"アクセス中: {base_url}")
            response = requests.get(base_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }, timeout=15)
            response.encoding = 'shift_jis'  # Shift_JIS を明示的に設定
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # BBSPinkの場合、スレッド一覧を <div><small id="trad"> から取得
            thread_list = soup.find("small", id="trad")
            if not thread_list:
                print(f"スレッド一覧が見つかりませんでした: {base_url}")
                return None

            for thread_link in thread_list.find_all('a', href=True):
                href = thread_link['href']  # 例: "1739448962/l50"
                title = thread_link.text.strip()  # 例: "19: なんJLLM部 避難所 ★6 	 (728)"

                # スレッド名がタイトルに含まれているか確認
                if thread_name.lower() in title.lower():
                    # スレッドIDを抽出
                    match = re.search(r'^(\d+)/', href)
                    if match:
                        thread_id = int(match.group(1))
                        # <base> タグを考慮した完全なURLを構築
                        full_url = f"https://{base_domain}/test/read.cgi/{board}/{thread_id}/"
                        print(f"スレッド発見: {title} -> {full_url}")
                        return thread_id, title, full_url

            print(f"スレッド「{thread_name}」が見つかりませんでした: {base_url}")
            return None

        except Exception as e:
            print(f"スレッド検索エラー: {str(e)}")
            return None
    
    def _retrieve_ai_threads(self, board_id: str, limit: int) -> List[Thread]:
        """
        特定の板からAI関連スレッドを取得します。
        
        Parameters
        ----------
        board_id : str
            板のID。
        limit : int
            取得するスレッド数。
            
        Returns
        -------
        List[Thread]
            取得したスレッドのリスト。
        """
        # 5chの板URLを構築
        board_url = f"https://menu.5ch.net/bbsmenu.html"
        
        try:
            print(f"板一覧ページ {board_url} にアクセスしています...")
            
            # 板一覧ページにアクセス
            response = requests.get(board_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }, timeout=15)
            response.raise_for_status()
            
            # 板のURLを探す
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 特定の板へのリンクを検索
            board_links = soup.find_all('a')
            actual_board_url = None
            
            for link in board_links:
                href = link.get('href', '')
                if f"/{board_id}/" in href and not href.endswith('.html'):
                    actual_board_url = href
                    print(f"板 {board_id} のURL: {actual_board_url}")
                    break
            
            if not actual_board_url:
                print(f"板 {board_id} のURLが見つかりませんでした")
                # 直接URLを構築してみる
                actual_board_url = f"https://menu.5ch.net/test/read.cgi/{board_id}/"
                print(f"推測した板URL: {actual_board_url}")
            
            # 板のページにアクセス
            print(f"板 {board_id} のページにアクセスしています...")
            response = requests.get(actual_board_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }, timeout=15)
            response.raise_for_status()
            
            # スレッド一覧を解析
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 5chのスレッド一覧を取得（pタグ内のaタグを探す）
            thread_elements = []
            p_elements = soup.find_all('p')
            
            for p in p_elements:
                a_tag = p.find('a')
                if a_tag and '/test/read.cgi/' in a_tag.get('href', ''):
                    thread_elements.append(a_tag)
            
            if not thread_elements:
                # 別の方法で試す
                thread_elements = soup.select('a[href*="/test/read.cgi/"]')
            
            print(f"見つかったスレッド数: {len(thread_elements)}")
            
            ai_threads = []
            
            for element in thread_elements[:50]:  # 最初の50スレッドだけ確認
                try:
                    # スレッドタイトルとURLを取得
                    title = element.text.strip()
                    thread_url = element.get('href', '')
                    
                    # 相対URLの場合は絶対URLに変換
                    if thread_url.startswith('/'):
                        thread_url = f"https://menu.5ch.net{thread_url}"
                    
                    # スレッドIDを抽出
                    thread_id_match = re.search(r'/([0-9]+)', thread_url)
                    if not thread_id_match:
                        continue
                    
                    thread_id = int(thread_id_match.group(1))
                    
                    # AIキーワードがタイトルに含まれているかチェック（大文字小文字を区別しない）
                    title_lower = title.lower()
                    is_ai_related = any(keyword.lower() in title_lower for keyword in self.ai_keywords)
                    
                    print(f"スレッド: {title}, AI関連: {is_ai_related}")
                    
                    if is_ai_related:
                        # 投稿を取得
                        print(f"AI関連スレッド見つかりました: {title}")
                        # Fix: Pass None as the initial working_subdomain
                        posts, timestamp = self._retrieve_thread_posts(thread_url, None)
                        
                        if posts:  # 投稿が取得できた場合のみ追加
                            thread = Thread(
                                thread_id=thread_id,
                                title=title,
                                url=thread_url,
                                board=board_id,
                                posts=posts,
                                timestamp=timestamp or int(datetime.now().timestamp())
                            )
                            ai_threads.append(thread)
                            if len(ai_threads) >= limit:
                                break
                        
                        # リクエスト間の遅延
                        time.sleep(self.request_delay)
                except Exception as e:
                    print(f"スレッド処理エラー: {str(e)}")
                    continue

            # リクエスト間の遅延
            time.sleep(self.request_delay)
            
            return ai_threads
            
        except Exception as e:
            print(f"板 {board_id} からのスレッド取得エラー: {str(e)}")
            return []

    def _retrieve_thread_posts_fromBBSPink(self, thread_url: str, working_subdomain: Optional[str] = None) -> tuple[List[Dict[str, Any]], int]:
        """
        スレッドの投稿を取得します。
        
        Parameters
        ----------
        thread_url : str
            スレッドのURL。
        working_subdomain : Optional[str], default=None
            動作しているサブドメイン。
            
        Returns
        -------
        tuple[List[Dict[str, Any]], int]
            投稿のリストとスレッド作成タイムスタンプのタプル。
        """
        # 全件取得のために /l50 を削除（必要に応じて /l1000 に変更可能）
        if thread_url.endswith('/l50'):
            thread_url = thread_url.rstrip('/l50')
        thread_url = thread_url.rstrip('/')  # /l50 を付けない場合

        try:
            print(f"スレッド {thread_url} にアクセスしています...")
            response = requests.get(thread_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Referer': 'https://mercury.bbspink.com/onatech/subback.html'
            }, timeout=15)
            response.encoding = 'shift_jis'  # BBSPinkはShift_JISを使用
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            posts = []
            timestamp = int(datetime.now().timestamp())

            # BBSPinkの投稿を取得
            post_elements = soup.select('article.post')  # 投稿は <article class="post"> 内に格納
            if not post_elements:
                print(f"警告: 投稿が見つかりませんでした。HTML構造を確認してください: {soup.prettify()[:500]}...")
                return [], timestamp

            for i, post in enumerate(post_elements):  # 最初の10投稿を取得
                post_id_elem = post.find('span', class_='postid')
                date_elem = post.find('span', class_='date')
                uid_elem = post.find('span', class_='uid')
                content_elem = post.find('section', class_='post-content')

                post_number = int(post_id_elem.text) if post_id_elem else i + 1
                date_str = date_elem.text.strip() if date_elem else ""
                uid = uid_elem.text.strip() if uid_elem else "ID:???"
                content = content_elem.text.strip() if content_elem else ""

                if i == 0 and date_str:
                    try:
                        # 小数点の有無に対応
                        date_clean = date_str.split('.')[0] if '.' in date_str else date_str
                        dt = datetime.strptime(date_clean, '%Y/%m/%d(%a) %H:%M:%S')
                        timestamp = int(dt.timestamp())
                    except Exception as e:
                        print(f"タイムスタンプ解析エラー: {str(e)}, 使用された日付: {date_str}")
                        # フォールバックとして別の形式を試す
                        try:
                            dt = datetime.strptime(date_clean, '%Y/%m/%d %H:%M:%S')
                            timestamp = int(dt.timestamp())
                        except Exception as e2:
                            print(f"代替形式でも解析失敗: {str(e2)}")

                posts.append({
                    "no": post_number,
                    "com": content,
                    "time": date_str,
                    "uid": uid
                })

            print(f"取得した投稿数: {len(posts)}")
            if not posts:
                print(f"警告: 投稿内容が空です。HTMLを確認してください: {soup.prettify()[:500]}...")

            return posts, timestamp

        except Exception as e:
            print(f"スレッド {thread_url} からの投稿取得エラー: {str(e)}")
            return [], int(datetime.now().timestamp())
    
    def _retrieve_thread_posts(self, thread_url: str, working_subdomain: Optional[str] = None) -> tuple[List[Dict[str, Any]], int]:
        """
        スレッドの投稿を取得します。
        
        Parameters
        ----------
        thread_url : str
            スレッドのURL。
        working_subdomain : Optional[str], default=None
            動作しているサブドメイン。指定されない場合は自動的に検出を試みます。
            
        Returns
        -------
        tuple[List[Dict[str, Any]], int]
            投稿のリストとスレッド作成タイムスタンプのタプル。
        """
        try:
            print(f"スレッド {thread_url} にアクセスしています...")
            
            # まず提供されたURLで試す
            try:
                response = requests.get(thread_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }, timeout=15)
                
                # エラーの場合は他のサブドメインを試す
                if response.status_code != 200:
                    raise requests.RequestException(f"応答コード {response.status_code}")
                
            except requests.RequestException as e:
                print(f"元のURLでのアクセスエラー: {str(e)}")
                
                # URLからパスを抽出し、別のサブドメインで試す
                parsed_url = thread_url.split('/', 3)
                if len(parsed_url) >= 4:
                    path = '/' + parsed_url[3]
                    
                    # 他のサブドメインを試す
                    success = False
                    for subdomain in self.subdomains:
                        # Skip if it's the same as working_subdomain
                        if working_subdomain is not None and subdomain == working_subdomain:
                            continue  # 既に試したサブドメインはスキップ
                            
                        try:
                            new_url = f"https://{subdomain}{path}"
                            print(f"代替URLを試しています: {new_url}")
                            
                            response = requests.get(new_url, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                            }, timeout=15)
                            
                            if response.status_code == 200:
                                thread_url = new_url  # 動作するURLに更新
                                success = True
                                break
                        except requests.RequestException:
                            continue
                    
                    if not success:
                        return [], int(datetime.now().timestamp())
                else:
                    return [], int(datetime.now().timestamp())
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # スレッドの投稿を取得（divタグ内のdtタグとddタグを探す）
            # 5chのレイアウトは変わることがあるため、複数の方法を試す
            
            # まず、一般的なレイアウトを試す
            posts = []
            timestamp = int(datetime.now().timestamp())  # デフォルトタイムスタンプ
            
            # 方法1: div.reshead と div.resbody を探す
            dt_elements = soup.select('div.reshead')
            dd_elements = soup.select('div.resbody')
            
            if dt_elements and dd_elements and len(dt_elements) == len(dd_elements):
                for i, (dt, dd) in enumerate(zip(dt_elements[:10], dd_elements[:10])):
                    post_number = i + 1
                    date_str = ""
                    
                    # 投稿番号と日時を抽出
                    header_text = dt.text.strip()
                    post_match = re.search(r'(\d+)', header_text)
                    if post_match:
                        post_number = int(post_match.group(1))
                    
                    date_match = re.search(r'(\d{4}/\d{2}/\d{2}(?:\(\w+\))? \d{2}:\d{2}:\d{2})', header_text)
                    if date_match:
                        date_str = date_match.group(1)
                        
                        # 最初の投稿からタイムスタンプを取得
                        if i == 0:
                            try:
                                # 様々な日付形式に対応
                                date_formats = [
                                    "%Y/%m/%d(%a) %H:%M:%S",
                                    "%Y/%m/%d %H:%M:%S"
                                ]
                                for fmt in date_formats:
                                    try:
                                        cleaned_date = re.sub(r'\(\w+\)', '', date_str)
                                        dt = datetime.strptime(cleaned_date, fmt)
                                        timestamp = int(dt.timestamp())
                                        break
                                    except:
                                        continue
                            except:
                                pass
                    
                    # 投稿内容
                    content = dd.text.strip()
                    
                    posts.append({
                        "no": post_number,
                        "com": content,
                        "time": date_str
                    })
            
            # 方法2: divタグのclass属性に"post"を含むものを探す
            if not posts:
                post_elements = soup.select('div[class*="post"]')
                if post_elements:
                    for i, element in enumerate(post_elements[:10]):
                        post_number = i + 1
                        content = element.text.strip()
                        
                        # 番号と内容を分離する試み
                        number_match = re.search(r'^(\d+)', content)
                        if number_match:
                            post_number = int(number_match.group(1))
                            content = content[len(number_match.group(0)):].strip()
                        
                        # 日付を抽出する試み
                        date_str = ""
                        date_match = re.search(r'(\d{4}/\d{2}/\d{2}(?:\(\w+\))? \d{2}:\d{2}:\d{2})', content)
                        if date_match:
                            date_str = date_match.group(1)
                        
                        posts.append({
                            "no": post_number,
                            "com": content,
                            "time": date_str
                        })
            
            # 方法3: 添付されたHTMLのようなパターン
            if not posts:
                p_elements = soup.find_all('p')
                current_post = {}
                post_count = 0
                
                for p in p_elements[:20]:
                    text = p.text.strip()
                    
                    if re.match(r'^\d+:', text):  # 番号から始まる行はレス
                        # 前の投稿を保存
                        if current_post and 'com' in current_post:
                            posts.append(current_post)
                            post_count += 1
                            if post_count >= 10:  # 最初の10投稿まで
                                break
                        
                        # 新しい投稿
                        post_parts = text.split(':', 1)
                        post_number = int(post_parts[0])
                        content = post_parts[1].strip() if len(post_parts) > 1 else ""
                        
                        current_post = {
                            "no": post_number,
                            "com": content,
                            "time": ""
                        }
                
                # 最後の投稿を追加
                if current_post and 'com' in current_post and len(posts) < 10:
                    posts.append(current_post)
            
            # もし投稿が見つからなければ、別の方法を試す
            if not posts:
                # すべてのテキストを取得し、正規表現で投稿を抽出する
                all_text = soup.get_text()
                post_pattern = re.compile(r'(\d+)[:：](.+?)(?=\d+[:：]|$)', re.DOTALL)
                matches = post_pattern.findall(all_text)
                
                for i, (num, content) in enumerate(matches[:10]):
                    posts.append({
                        "no": int(num),
                        "com": content.strip(),
                        "time": ""
                    })
            
            print(f"取得した投稿数: {len(posts)}")
            
            # 投稿が見つからなければ、エラーログを表示
            if not posts:
                print(f"警告: スレッド {thread_url} から投稿を取得できませんでした")
                print(f"HTML構造: {soup.prettify()[:500]}...")
            
            return posts, timestamp
            
        except Exception as e:
            print(f"スレッド {thread_url} からの投稿取得エラー: {str(e)}")
            return [], int(datetime.now().timestamp())
    
    def _summarize_thread(self, thread: Thread) -> None:
        """
        スレッドを要約します。
        
        Parameters
        ----------
        thread : Thread
            要約するスレッド。
        """
        # スレッドのコンテンツを抽出
        thread_content = ""
        
        # スレッドのタイトルを追加
        thread_content += f"タイトル: {thread.title}\n\n"
        
        # オリジナルポスト（OP）を追加
        if thread.posts and len(thread.posts) > 0:
            op = thread.posts[0]
            op_text = op.get("com", "")
            if op_text:
                thread_content += f">>1: {op_text}\n\n"
        
        # 返信を追加（最大5件）
        replies = thread.posts[1:6] if len(thread.posts) > 1 else []
        for i, reply in enumerate(replies):
            reply_text = reply.get("com", "")
            if reply_text:
                post_number = reply.get("no", i+2)
                thread_content += f">>{post_number}: {reply_text}\n\n"
        
        prompt = f"""
        以下の5chan（旧2ちゃんねる）スレッドを詳しくまとめてください。

        板: /{thread.board}/
        {thread_content}
        
        解説は以下の形式で行い、日本語で回答してください:
        1. スレッドの流れを詳細に説明
        2. 主要な投稿を抜粋
        3. 議論の主要ポイント
        4. スレッドの全体的な論調
        5. 共有されてる情報を抽出
        
        """
        
        system_instruction = """
        あなたは5chan（旧2ちゃんねる）スレッドの解説を行うアシスタントです。
        投稿された内容を客観的に分析してください。
        回答は日本語で行います。
        """
        
        try:
            summary = self.grok_client.generate_content(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=0.3,
                max_tokens=10000
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
        content = f"# 5chan AI関連スレッド ({today.strftime('%Y-%m-%d')})\n\n"
        
        # 板ごとに整理
        boards = {}
        for thread in threads:
            if thread.board not in boards:
                boards[thread.board] = []
            
            boards[thread.board].append(thread)
        
        # Markdownを生成
        for board, board_threads in boards.items():
            board_name = self.target_boards.get(board, board)
            content += f"## {board_name} (/{board}/)\n\n"
            
            for thread in board_threads:
                formatted_title = thread.title if thread.title else f"無題スレッド #{thread.thread_id}"
                content += f"### [{formatted_title}]({thread.url})\n\n"
                
                # 投稿日時
                date_str = datetime.fromtimestamp(thread.timestamp).strftime('%Y-%m-%d %H:%M:%S')
                content += f"作成日時: {date_str}\n\n"
                
                content += f"**要約**:\n{thread.summary}\n\n"
                
                content += "---\n\n"
        
        # 保存
        self.storage.save_markdown(content, "fivechan_explorer", today)
