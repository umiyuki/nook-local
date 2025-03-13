"""スレッド追跡用の共通クラスを提供します。"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json
from datetime import datetime
from pathlib import Path


@dataclass
class TrackedThread:
    """
    追跡対象のスレッド情報。

    Parameters
    ----------
    name : str
        スレッド名（例: "/ldg/ - Local Diffusion General"）。
    board : str
        板名（例: "g"）。
    thread_id : Optional[int]
        現在のスレッドID。
    url : Optional[str]
        現在のスレッドURL。
    last_post_no : Optional[int]
        最後に取得した投稿番号。
    last_update : Optional[datetime]
        最後の更新日時。
    """

    name: str
    board: str
    thread_id: Optional[int] = None
    url: Optional[str] = None
    last_post_no: Optional[int] = None
    last_update: Optional[datetime] = None

    @staticmethod
    def load_tracked_threads(file_path: Path) -> Dict[str, "TrackedThread"]:
        """
        追跡対象スレッドの情報を読み込みます。

        Parameters
        ----------
        file_path : Path
            設定ファイルのパス。

        Returns
        -------
        Dict[str, TrackedThread]
            スレッド名をキーとする TrackedThread オブジェクトの辞書。
        """
        if not file_path.exists():
            return {}

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        threads = {}
        for thread_data in data.get("threads", []):
            last_update = None
            if thread_data.get("last_update"):
                last_update = datetime.fromisoformat(thread_data["last_update"])

            thread = TrackedThread(
                name=thread_data["name"],
                board=thread_data["board"],
                thread_id=thread_data.get("thread_id"),
                url=thread_data.get("url"),
                last_post_no=thread_data.get("last_post_no"),
                last_update=last_update
            )
            threads[thread.name] = thread

        return threads

    @staticmethod
    def save_tracked_threads(threads: Dict[str, "TrackedThread"], file_path: Path) -> None:
        """
        追跡対象スレッドの情報を保存します。

        Parameters
        ----------
        threads : Dict[str, TrackedThread]
            保存するスレッド情報。
        file_path : Path
            保存先のファイルパス。
        """
        data = {
            "threads": [
                {
                    "name": thread.name,
                    "board": thread.board,
                    "thread_id": thread.thread_id,
                    "url": thread.url,
                    "last_post_no": thread.last_post_no,
                    "last_update": thread.last_update.isoformat() if thread.last_update else None
                }
                for thread in threads.values()
            ]
        }

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def update(self, thread_id: int, url: str, last_post_no: int) -> None:
        """
        スレッド情報を更新します。

        Parameters
        ----------
        thread_id : int
            新しいスレッドID。
        url : str
            新しいスレッドURL。
        last_post_no : int
            最新の投稿番号。
        """
        self.thread_id = thread_id
        self.url = url
        self.last_post_no = last_post_no
        self.last_update = datetime.now()