"""GitHubのトレンドリポジトリを収集するサービス。"""

import tomli
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from nook.common.storage import LocalStorage
from nook.common.grok_client import Grok3Client


@dataclass
class Repository:
    """
    GitHubリポジトリ情報。
    
    Parameters
    ----------
    name : str
        リポジトリ名。
    description : str | None
        説明。
    link : str
        リポジトリへのリンク。
    stars : int
        スター数。
    """
    
    name: str
    description: Optional[str]
    link: str
    stars: int


class GithubTrending:
    """
    GitHubのトレンドリポジトリを収集するクラス。
    
    Parameters
    ----------
    storage_dir : str, default="data"
        ストレージディレクトリのパス。
    """
    
    def __init__(self, storage_dir: str = "data"):
        """
        GithubTrendingを初期化します。
        
        Parameters
        ----------
        storage_dir : str, default="data"
            ストレージディレクトリのパス。
        """
        self.storage = LocalStorage(storage_dir)
        self.base_url = "https://github.com/trending"
        
        # 言語の設定を読み込む
        script_dir = Path(__file__).parent
        with open(script_dir / "languages.toml", "rb") as f:
            self.languages_config = tomli.load(f)
    
    def run(self, limit: int = 10) -> None:
        """
        GitHubのトレンドリポジトリを収集して保存します。
        
        Parameters
        ----------
        limit : int, default=10
            各言語から取得するリポジトリ数。
        """
        all_repositories = []
        
        # 一般的な言語のリポジトリを取得
        for language in self.languages_config["general"]:
            repositories = self._retrieve_repositories(language, limit)
            all_repositories.append((language or "all", repositories))
        
        # 特定の言語のリポジトリを取得（少なめに）
        for language in self.languages_config["specific"]:
            repositories = self._retrieve_repositories(language, limit // 2)
            all_repositories.append((language, repositories))
        
        # 翻訳処理
        all_repositories = self._translate_repositories(all_repositories)
        
        # 保存
        self._store_summaries(all_repositories)
    
    def _retrieve_repositories(self, language: str, limit: int) -> List[Repository]:
        """
        特定の言語のトレンドリポジトリを取得します。
        
        Parameters
        ----------
        language : str
            言語名（空文字列の場合はすべての言語）。
        limit : int
            取得するリポジトリ数。
            
        Returns
        -------
        List[Repository]
            取得したリポジトリのリスト。
        """
        url = self.base_url
        if language:
            url += f"/{language}"
        
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")
            
            repositories = []
            repo_elements = soup.select("article.Box-row")[:limit]
            
            for repo_element in repo_elements:
                # リポジトリ名を取得
                name_element = repo_element.select_one("h2 a")
                if not name_element:
                    continue
                
                name = name_element.text.strip().replace("\n", "").replace(" ", "")
                link = f"https://github.com{name_element['href']}"
                
                # 説明を取得
                description_element = repo_element.select_one("p")
                description = description_element.text.strip() if description_element else None
                
                # スター数を取得
                stars_element = repo_element.select_one("a.Link--muted")
                stars_text = stars_element.text.strip() if stars_element else "0"
                stars = int(stars_text.replace(",", "")) if stars_text.replace(",", "").isdigit() else 0
                
                repository = Repository(
                    name=name,
                    description=description,
                    link=link,
                    stars=stars
                )
                
                repositories.append(repository)
            
            return repositories
        
        except Exception as e:
            print(f"Error retrieving repositories for language {language}: {str(e)}")
            return []

    def _translate_repositories(self, repositories_by_language: List[tuple[str, List[Repository]]]) -> List[tuple[str, List[Repository]]]:
        """
        リポジトリの説明を日本語に翻訳します。

        Parameters
        ----------
        repositories_by_language : List[tuple[str, List[Repository]]]
            言語ごとのリポジトリリスト。

        Returns
        -------
        List[tuple[str, List[Repository]]]
            翻訳されたリポジトリリスト。
        """
        try:
            # Grok APIクライアントの初期化
            grok_client = Grok3Client()

            for language, repositories in repositories_by_language:
                for repo in repositories:
                    if repo.description:
                        prompt = f"""以下の英語のテキストを詳細かつ情報量の多い日本語に翻訳してください。
                        技術用語や固有名詞は適切に翻訳し、専門的な内容が正確に伝わるようにしてください。
                        必要に応じて、英語の専門用語を括弧内に残しても構いません。
                        単なる直訳ではなく、内容を十分に詳しく説明してください。

                        対象テキスト:
                        {repo.description}
                        """
                        try:
                            repo.description = grok_client.generate_content(
                                prompt=prompt,
                                temperature=0.3,
                                max_tokens=1000  # max_tokensを追加
                            )
                        except Exception as e:
                            print(f"Error translating description for {repo.name}: {str(e)}")

        except Exception as e:
            print(f"Error in translation process: {str(e)}")

        return repositories_by_language
    
    def _store_summaries(self, repositories_by_language: List[tuple[str, List[Repository]]]) -> None:
        """
        リポジトリ情報を保存します。
        
        Parameters
        ----------
        repositories_by_language : List[tuple[str, List[Repository]]]
            言語ごとのリポジトリリスト。
        """
        today = datetime.now()
        content = f"# GitHub トレンドリポジトリ ({today.strftime('%Y-%m-%d')})\n\n"
        
        for language, repositories in repositories_by_language:
            if not repositories:
                continue
            
            language_display = language if language != "all" else "すべての言語"
            content += f"## {language_display.capitalize()}\n\n"
            
            for repo in repositories:
                content += f"### [{repo.name}]({repo.link})\n\n"
                
                if repo.description:
                    content += f"{repo.description}\n\n"
                
                content += f"⭐ スター数: {repo.stars}\n\n"
                content += "---\n\n"
        
        # 保存
        self.storage.save_markdown(content, "github_trending", today) 
