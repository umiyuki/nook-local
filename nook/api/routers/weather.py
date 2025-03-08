"""天気APIルーター。"""

import os
import json
from typing import Dict, Any
from dotenv import load_dotenv

import requests
from fastapi import APIRouter, HTTPException

from nook.api.models.schemas import WeatherResponse

# 環境変数の読み込み
load_dotenv()

router = APIRouter()


@router.get("/weather", response_model=WeatherResponse)
async def get_weather_data() -> WeatherResponse:
    """
    天気データを取得します。
    
    Returns
    -------
    WeatherResponse
        天気レスポンス。
        
    Raises
    ------
    HTTPException
        天気データの取得に失敗した場合。
    """
    try:
        # OpenWeatherMap APIを使用して天気データを取得
        api_key = os.environ.get("OPENWEATHERMAP_API_KEY")
        if not api_key:
            # デモ用のダミーデータを返す
            return WeatherResponse(temperature=20.5, icon="01d")
        
        # 神奈川の天気を取得
        city = "Kanagawa"
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
        
        response = requests.get(url)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch weather data")
        
        data = response.json()
        
        temperature = data["main"]["temp"]
        icon = data["weather"][0]["icon"]
        
        return WeatherResponse(temperature=temperature, icon=icon)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching weather data: {str(e)}") 
