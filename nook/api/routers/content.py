"""コンテンツAPIルーター。"""

from datetime import datetime
import logging
from urllib.parse import unquote
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query

from nook.api.models.schemas import ContentResponse, ContentItem
from nook.common.storage import LocalStorage

router = APIRouter()
storage = LocalStorage("data")

logger = logging.getLogger(__name__)

SOURCE_MAPPING = {
    "paper": "paper_summarizer",
    "github": "github_trending",
    "hacker news": "hacker_news",
    "tech news": "tech_feed",
    "business news": "business_feed",
    "zenn": "zenn_explorer",
    "qiita": "qiita_explorer",
    "note": "note_explorer",
    "reddit": "reddit_explorer",
    "4chan": "fourchan_explorer",
    "5chan": "fivechan_explorer",
    "github_details": "github_details"
}


@router.get("/content/{source}", response_model=ContentResponse)
async def get_content(
    source: str,
    date: Optional[str] = None
) -> ContentResponse:
    """
    特定のソースのコンテンツを取得します。
    
    Parameters
    ----------
    source : str
        データソース（reddit, hackernews, github, techfeed, paper）。
    date : str, optional
        表示する日付（YYYY-MM-DD形式）。
    repo : str, optional
        GitHub詳細を取得する場合のリポジトリ名。
        
    Returns
    -------
    ContentResponse
        コンテンツレスポンス。
        
    Raises
    ------
    HTTPException
        ソースが無効な場合や、コンテンツが見つからない場合。
    """
    # URLデコードしてソースを取得
    source = unquote(source)
    logger.info(f"Requested source (decoded): {source}")
    
    if source not in SOURCE_MAPPING and source != "all":
        logger.error(f"Invalid source: {source} not in {list(SOURCE_MAPPING.keys())}")
        raise HTTPException(status_code=404, detail=f"Source '{source}' not found")
     # 日付の処理
    target_date = None
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {date}")
    else:
        target_date = datetime.now()
    
    items = []
    
    # GitHub詳細の処理
    if source.strip() == "github_details":
        logger.info("Processing github_details source")
        # TOMLファイルから全リポジトリのデータを取得
        from nook.services.github_details.github_details import GitHubDetailsService
        service = GitHubDetailsService()
        logger.info("Loading repos from TOML file")
        repos = service.load_repos_from_toml()
        logger.info(f"Found repos: {repos}")

        # 各リポジトリのデータを個別に取得
        for repo_name in repos:
            service_name = f"github_details/{repo_name.replace('/', '_')}"
            content = storage.load_markdown(f"github_details/{repo_name.replace('/', '_')}", target_date)
            
            if not content:
                logger.info(f"No content found for {repo_name}, running service...")
                service.get_repo_details(repo_name)
                content = storage.load_markdown(service_name, target_date)
                logger.info(f"Content loaded for {repo_name}: {bool(content)}")
            
            if content:
                items.append(ContentItem(
                    title=f"GitHub Details - {repo_name}",
                    content=content,
                    source=source
                ))
                logger.info(f"Data path: data/github_details/{repo_name.replace('/', '_')}/{target_date.strftime('%Y-%m-%d')}.md")
                logger.info(f"Added content item for {repo_name}")
        logger.info(f"Added {len(items)} github_details items")
        
    # 特定のソースからコンテンツを取得
    elif source != "all":  # github_details以外の場合のみ実行
        service_name = SOURCE_MAPPING[source]
        content = storage.load_markdown(service_name, target_date)
        
        logger.info(f"Loading content for {source} from {service_name}")
        if content:
            logger.info(f"Content found for {source}")
            # マークダウンからContentItemを作成
            items.append(ContentItem(
                title=f"{_get_source_display_name(source)} - {target_date.strftime('%Y-%m-%d')}",
                content=content,
                source=source
            ))
    else:
        # すべてのソースからコンテンツを取得
        for src, service_name in SOURCE_MAPPING.items():
            content = storage.load_markdown(service_name, target_date)
            if content:
                items.append(ContentItem(
                    title=f"{_get_source_display_name(src)} - {target_date.strftime('%Y-%m-%d')}",
                    content=content,
                    source=src
                ))
    
    if not items:
        # 利用可能な日付を確認
        available_dates = []
        if source != "all":
            service_name = f"github_details/{repos[0].replace('/', '_')}" if source == "github_details" else SOURCE_MAPPING[source]
            available_dates = storage.list_dates(service_name)
        else:
            for service_name in SOURCE_MAPPING.values():
                dates = storage.list_dates(service_name)
                available_dates.extend(dates)
        
        if not available_dates:
            logger.warning(f"No content available for source: {source}")
            raise HTTPException(
                status_code=404,
                headers={"x-debug-path": f"data/{service_name}/"},
                detail=f"No content available. Please run the services first."
            )
        else:
            # 最新の利用可能な日付のコンテンツを取得
            latest_date = max(available_dates)
            return await get_content(source, latest_date.strftime("%Y-%m-%d"))
    
    logger.info(f"Returning {len(items)} items")
    return ContentResponse(items=items)

def _get_source_display_name(source: str) -> str:
    """
    ソースの表示名を取得します。
    
    Parameters
    ----------
    source : str
        データソース
        
    Returns
    -------
    str
        表示名
    """
    source_names = {
        "reddit": "Reddit",
        "hackernews": "Hacker News",
        "github": "GitHub Trending",
        "techfeed": "Tech Feed",
        "businessfeed": "Business Feed",
        "paper": "論文",
        "4chan": "4chan",
        "5chan": "5ちゃんねる",
        "github_details": "GitHub Details"
    }
    return source_names.get(source, source) 
