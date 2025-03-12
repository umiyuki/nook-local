import axios from 'axios';
import { ContentResponse, WeatherResponse } from './types';

const api = axios.create({
  baseURL: 'http://localhost:8000/api'
});

export const getContent = async (source: string, date?: string) => {
  const { data } = await api.get<ContentResponse>(`/content/${source}`, {
    params: { date }
  });
  return data;
};

export const getWeather = async () => {
  const { data } = await api.get<WeatherResponse>('/weather');
  return data;
};
