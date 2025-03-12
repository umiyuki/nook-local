import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ExternalLink } from 'lucide-react';
import { ContentItem } from '../types';

interface ContentCardProps {
  item: ContentItem;
  darkMode: boolean;
}

export const ContentCard: React.FC<ContentCardProps> = ({ item, darkMode }) => {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow w-full">
      <div className="flex items-start justify-between mb-4">
        <h3 className="text-xl font-semibold text-gray-900 dark:text-white flex-1">{item.title}</h3>
        {item.url && (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 ml-2 flex items-center"
          >
            <ExternalLink size={20} />
          </a>
        )}
      </div>
      <div className={`prose prose-lg max-w-none w-full overflow-x-auto ${darkMode ? 'prose-invert' : ''}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.content}</ReactMarkdown>
      </div>
      <div className="mt-4 flex items-center justify-between">
        <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300">
          {item.source}
        </span>
      </div>
    </div>
  );
};