export interface ContentItem {
  title: string;
  content: string;
  url?: string;
  source: string;
}

export interface ContentResponse {
  items: ContentItem[];
}

export interface WeatherResponse {
  temperature: number;
  icon: string;
}