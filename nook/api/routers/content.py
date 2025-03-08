"""コンテンツAPIルーター。"""

from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException

from nook.api.models.schemas import ContentResponse, ContentItem
from nook.common.storage import LocalStorage

router = APIRouter()
storage = LocalStorage("data")

SOURCE_MAPPING = {
    "reddit": "reddit_explorer",
    "hackernews": "hacker_news",
    "github": "github_trending",
    "techfeed": "tech_feed",
    "paper": "paper_summarizer"
    "4chanai": "fourchan_explorer"
}


@router.get("/content/{source}", response_model=ContentResponse)
async def get_content(source: str, date: Optional[str] = None) -> ContentResponse:
    """
    特定のソースのコンテンツを取得します。
    
    Parameters
    ----------
    source : str
        データソース（reddit, hackernews, github, techfeed, paper）。
    date : str, optional
        表示する日付（YYYY-MM-DD形式）。
        
    Returns
    -------
    ContentResponse
        コンテンツレスポンス。
        
    Raises
    ------
    HTTPException
        ソースが無効な場合や、コンテンツが見つからない場合。
    """
    if source not in SOURCE_MAPPING and source != "all":
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
    
    # 特定のソースからコンテンツを取得
    if source != "all":
        service_name = SOURCE_MAPPING[source]
        content = storage.load_markdown(service_name, target_date)
        
        if content:
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
            service_name = SOURCE_MAPPING[source]
            available_dates = storage.list_dates(service_name)
        else:
            for service_name in SOURCE_MAPPING.values():
                dates = storage.list_dates(service_name)
                available_dates.extend(dates)
        
        if not available_dates:
            raise HTTPException(
                status_code=404, 
                detail=f"No content available. Please run the services first."
            )
        else:
            # 最新の利用可能な日付のコンテンツを取得
            latest_date = max(available_dates)
            return await get_content(source, latest_date.strftime("%Y-%m-%d"))
    
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
        "paper": "論文"
        "4chanai": "4chan AI"
    }
    return source_names.get(source, source) 
