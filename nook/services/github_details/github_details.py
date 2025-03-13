"""
GitHubリポジトリの詳細データを取得し要約するサービス。
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dotenv import load_dotenv
import tomli
from github import Github
from nook.common.storage import LocalStorage
from nook.common.gemini_client import GeminiClient

load_dotenv()

class GitHubDetailsService:
    """GitHubリポジトリの詳細情報を取得し要約するサービス。"""
    
    def __init__(self):
        """サービスの初期化。"""
        self.github_token = os.environ.get("GITHUB_TOKEN")
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN environment variable is not set")
        self.client = Github(self.github_token)
        self.storage = LocalStorage("data")
        self.gemini = GeminiClient()

    def load_repos_from_toml(self) -> List[str]:
        """TOMLファイルからリポジトリリストを読み込む。"""
        with open("nook/services/github_details/repos.toml", "rb") as f:
            config = tomli.load(f)
            return config.get("repos", [])

    def get_repo_details(self, repo_full_name: str, days: int = 7) -> Dict[str, Any]:
        """
        指定したリポジトリの詳細情報を取得し要約する。

        Parameters
        ----------
        repo_full_name : str
            リポジトリのフルネーム（例: "owner/repo"）
        days : int
            遡って取得する日数

        Returns
        -------
        Dict[str, Any]
            リポジトリの要約情報
        """
        repo = self.client.get_repo(repo_full_name)
        print(f"Processing {repo_full_name}...")
        since_date = datetime.now() - timedelta(days=days)

        # コミット履歴
        commits = repo.get_commits(since=since_date)
        commit_data = [
            f"{commit.sha[:7]}: {commit.commit.message.split('\n')[0]} by {commit.commit.author.name} ({commit.commit.author.date}) [リンク]({commit.html_url})"
            for commit in commits[:50]
        ]

        # イシュー
        issues = repo.get_issues(state="open", sort="updated", direction="desc")
        issue_data = [
            f"#{issue.number} {issue.title} (更新: {issue.updated_at}, コメント: {issue.comments}) [リンク]({issue.html_url})"
            for issue in issues[:20]
        ]

        # プルリクエスト
        pulls = repo.get_pulls(state="open", sort="updated", direction="desc")
        pull_request_data = [
            f"#{pr.number} {pr.title} "
            f"(作成者: {pr.user.login}, 更新: {pr.updated_at}, "
            f"コメント: {pr.comments}, ファイル変更: {pr.changed_files}) "
            f"[リンク]({pr.html_url})"
            for pr in pulls[:20]
        ]

        # まとめて要約
        summary = self._summarize_with_gemini(repo_full_name, commit_data, issue_data, pull_request_data)
        
        # Markdown形式で保存
        content = self._format_to_markdown(repo_full_name, summary)
        self.storage.save_markdown(content, f"github_details/{repo_full_name.replace('/', '_')}", datetime.now())

        return {
            "repo": repo_full_name,
            "summary": summary
        }

    def _summarize_with_gemini(self, repo_name: str, commits: List[str], issues: List[str], pull_requests: List[str]) -> str:
        """
        コミット、イシュー、プルリクエストをまとめて要約する。

        Parameters
        ----------
        repo_name : str
            リポジトリ名
        commits : List[str]
            コミット情報のリスト
        issues : List[str]
            イシュー情報のリスト
        pull_requests : List[str]
            プルリクエスト情報のリスト

        Returns
        -------
        str
            要約された情報
        """
        prompt = f"""以下のGitHubリポジトリ「{repo_name}」の最近の活動を日本語で詳細に解説してください：

### 最近のコミット
{'\n'.join(commits) if commits else 'コミットなし'}

### 活発なイシュー
{'\n'.join(issues) if issues else 'イシューなし'}

### アクティブなプルリクエスト
{'\n'.join(pull_requests) if pull_requests else 'プルリクエストなし'}

1. 各コミットの主な変更内容
2. 各イシューの議論や進展
3. 進行中のプルリクエストの状況

最後に、特に重要な変更や議論を中心に、技術的な観点から簡潔に要約してください。
"""
        try:
            return self.gemini.generate_content(prompt, temperature=0.7, max_tokens=8000)
        except Exception as e:
            return f"要約に失敗しました: {str(e)}"

    def _format_to_markdown(self, repo_name: str, summary: str) -> str:
        """
        データをMarkdown形式に整形する。

        Parameters
        ----------
        repo_name : str
            リポジトリ名
        summary : str
            要約テキスト

        Returns
        -------
        str
            Markdown形式のテキスト
        """
        return f"""# {repo_name} の最近の活動\n\n{summary}"""

    def run_all_repos(self) -> List[Dict[str, Any]]:
        """
        TOMLに記載された全リポジトリのデータを収集する。

        Returns
        -------
        List[Dict[str, Any]]
            各リポジトリの要約情報のリスト
        """
        print("GitHubリポジトリの詳細情報を収集しています...")
        repos = self.load_repos_from_toml()
        results = []
        for repo in repos:
            try:
                result = self.get_repo_details(repo)
                results.append(result)
            except Exception as e:
                print(f"Warning: {str(e)}")
                print(f"Error processing {repo}: {str(e)}")
        return results

def run_service(repo_full_name: str = None):
    """
    サービスを実行する。

    Parameters
    ----------
    repo_full_name : str, optional
        特定のリポジトリを指定する場合のフルネーム
    """
    service = GitHubDetailsService()
    if repo_full_name:
        service.get_repo_details(repo_full_name)
    else:
        service.run_all_repos()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        run_service(sys.argv[1])
    else:
        run_service()