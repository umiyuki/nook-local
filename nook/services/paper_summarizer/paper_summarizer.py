"""arXiv論文を収集・要約するサービス。"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import arxiv
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from nook.common.grok_client import Grok3Client
from nook.common.storage import LocalStorage


@dataclass
class PaperInfo:
    """
    arXiv論文情報。
    
    Parameters
    ----------
    title : str
        論文タイトル。
    abstract : str
        要約。
    url : str
        URL。
    contents : str
        論文の内容。
    """
    
    title: str
    abstract: str
    url: str
    contents: str
    summary: str = field(init=False)


class PaperSummarizer:
    """
    arXiv論文を収集・要約するクラス。
    
    Parameters
    ----------
    storage_dir : str, default="data"
        ストレージディレクトリのパス。
    """
    
    def __init__(self, storage_dir: str = "data"):
        """
        PaperSummarizerを初期化します。
        
        Parameters
        ----------
        storage_dir : str, default="data"
            ストレージディレクトリのパス。
        """
        self.storage = LocalStorage(storage_dir)
        self.grok_client = Grok3Client()
    
    def run(self, limit: int = 5) -> None:
        """
        arXiv論文を収集・要約して保存します。
        
        Parameters
        ----------
        limit : int, default=5
            取得する論文数。
        """
        # Hugging Faceでキュレーションされた論文IDを取得
        paper_ids = self._get_curated_paper_ids(limit)
        
        # 論文情報を取得
        papers = []
        for paper_id in tqdm(paper_ids, desc="論文を処理中"):
            paper_info = self._retrieve_paper_info(paper_id)
            if paper_info:
                # 論文を要約
                self._summarize_paper_info(paper_info)
                papers.append(paper_info)
        
        # 要約を保存
        self._store_summaries(papers)
        
        # 処理済みの論文IDを保存
        self._save_processed_ids(paper_ids)
    
    def _get_curated_paper_ids(self, limit: int) -> List[str]:
        """
        Hugging Faceでキュレーションされた論文IDを取得します。
        
        Parameters
        ----------
        limit : int
            取得する論文数。
            
        Returns
        -------
        List[str]
            論文IDのリスト。
        """
        # Hugging Faceの論文ページから最新の論文IDを取得
        url = "https://huggingface.co/papers"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        
        paper_ids = []
        paper_links = soup.select("a[href^='/papers/']")
        
        for link in paper_links:
            href = link.get("href", "")
            if "/papers/" in href:
                paper_id_match = re.search(r"/papers/(\d+\.\d+)", href)
                if paper_id_match:
                    paper_id = paper_id_match.group(1)
                    if paper_id not in paper_ids:
                        paper_ids.append(paper_id)
                        if len(paper_ids) >= limit:
                            break
        
        # 既に処理済みの論文IDを除外
        processed_ids = self._get_processed_ids()
        paper_ids = [pid for pid in paper_ids if pid not in processed_ids]
        
        return paper_ids[:limit]
    
    def _get_processed_ids(self) -> List[str]:
        """
        既に処理済みの論文IDを取得します。
        
        Returns
        -------
        List[str]
            処理済みの論文IDのリスト。
        """
        today = datetime.now()
        date_str = today.strftime("%Y-%m-%d")
        file_path = Path(self.storage.base_dir) / "paper_summarizer" / f"arxiv_ids-{date_str}.txt"
        
        if not file_path.exists():
            return []
        
        with open(file_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    
    def _save_processed_ids(self, paper_ids: List[str]) -> None:
        """
        処理済みの論文IDを保存します。
        
        Parameters
        ----------
        paper_ids : List[str]
            処理済みの論文IDのリスト。
        """
        today = datetime.now()
        date_str = today.strftime("%Y-%m-%d")
        dir_path = Path(self.storage.base_dir) / "paper_summarizer"
        dir_path.mkdir(parents=True, exist_ok=True)
        
        file_path = dir_path / f"arxiv_ids-{date_str}.txt"
        
        # 既存のIDを読み込む
        existing_ids = []
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                existing_ids = [line.strip() for line in f if line.strip()]
        
        # 新しいIDを追加
        all_ids = existing_ids + paper_ids
        all_ids = list(dict.fromkeys(all_ids))  # 重複を削除
        
        with open(file_path, "w", encoding="utf-8") as f:
            for paper_id in all_ids:
                f.write(f"{paper_id}\n")
    
    def _retrieve_paper_info(self, paper_id: str) -> Optional[PaperInfo]:
        """
        論文情報を取得します。
        
        Parameters
        ----------
        paper_id : str
            論文ID。
            
        Returns
        -------
        PaperInfo or None
            取得した論文情報。取得に失敗した場合はNone。
        """
        try:
            client = arxiv.Client()
            search = arxiv.Search(id_list=[paper_id])
            results = list(client.results(search))
            
            if not results:
                return None
            
            paper = results[0]
            
            # PDFから本文を抽出
            contents = self._extract_body_text(paper)
            
            # タイトルとアブストラクトを日本語に翻訳
            title = paper.title
            abstract_ja = self._translate_to_japanese(paper.summary)
            
            return PaperInfo(
                title=title,
                abstract=abstract_ja,
                url=paper.entry_id,
                contents=contents
            )
        
        except Exception as e:
            print(f"Error retrieving paper {paper_id}: {str(e)}")
            return None
    
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
        try:
            prompt = f"以下の英語の学術論文のテキストを自然な日本語に翻訳してください。専門用語は適切に翻訳し、必要に応じて英語の専門用語を括弧内に残してください。\n\n{text}"
            
            translated_text = self.grok_client.generate_content(
                prompt=prompt,
                temperature=0.3,
                max_tokens=1000
            )
            
            return translated_text
        except Exception as e:
            print(f"Error translating text: {str(e)}")
            return text  # 翻訳に失敗した場合は原文を返す
    
    def _extract_body_text(self, paper: arxiv.Result) -> str:
        """
        論文本文を抽出します。
        
        Parameters
        ----------
        paper : arxiv.Result
            論文情報。
            
        Returns
        -------
        str
            抽出した本文。
        """
        # 簡易的な実装として、要約を返す
        # 実際のPDF解析は複雑なため、ここでは省略
        return paper.summary
    
    def _summarize_paper_info(self, paper_info: PaperInfo) -> None:
        """
        論文を要約します。
        
        Parameters
        ----------
        paper_info : PaperInfo
            要約する論文情報。
        """
        prompt = f"""
        以下の論文を要約してください。

        タイトル: {paper_info.title}
        アブストラクト: {paper_info.abstract}
        
        要約は以下の形式で行い、日本語で回答してください:
        1. 研究の目的と背景
        2. 提案手法の概要
        3. 主な結果と貢献
        4. 将来の研究への示唆
        """
        
        system_instruction = """
        あなたは論文の要約を行うアシスタントです。
        与えられた論文を分析し、簡潔で情報量の多い要約を作成してください。
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
            paper_info.summary = summary
        except Exception as e:
            paper_info.summary = f"要約の生成中にエラーが発生しました: {str(e)}"
    
    def _store_summaries(self, papers: List[PaperInfo]) -> None:
        """
        要約を保存します。
        
        Parameters
        ----------
        papers : List[PaperInfo]
            保存する論文のリスト。
        """
        if not papers:
            return
        
        today = datetime.now()
        content = f"# arXiv 論文要約 ({today.strftime('%Y-%m-%d')})\n\n"
        
        for paper in papers:
            content += f"## [{paper.title}]({paper.url})\n\n"
            content += f"**アブストラクト**:\n{paper.abstract}\n\n"
            content += f"**要約**:\n{paper.summary}\n\n"
            content += "---\n\n"
        
        # 保存
        self.storage.save_markdown(content, "paper_summarizer", today) 
