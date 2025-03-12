import React from 'react';
import { useQuery } from 'react-query';
import { Cloud, Sun, CloudRain } from 'lucide-react';
import { getWeather } from '../api';

const getWeatherIcon = (icon: string) => {
  switch (icon) {
    case 'sunny':
      return <Sun className="w-8 h-8 text-yellow-500" />;
    case 'cloudy':
      return <Cloud className="w-8 h-8 text-gray-500" />;
    case 'rainy':
      return <CloudRain className="w-8 h-8 text-blue-500" />;
    default:
      return <Sun className="w-8 h-8 text-yellow-500" />;
  }
};

export const WeatherWidget: React.FC = () => {
  const { data, isLoading } = useQuery('weather', getWeather);

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow-md p-4 animate-pulse">
        <div className="h-8 bg-gray-200 rounded w-24 mb-2"></div>
        <div className="h-6 bg-gray-200 rounded w-16"></div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="bg-white rounded-lg shadow-md p-4">
      <div className="flex items-center space-x-4">
        {getWeatherIcon(data.icon)}
        <div>
          <div className="text-2xl font-bold">{data.temperature}°C</div>
          <div className="text-gray-500">Current Weather</div>
        </div>
      </div>
    </div>
  );
};
