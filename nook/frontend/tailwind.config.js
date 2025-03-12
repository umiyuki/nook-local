/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      typography: {
        DEFAULT: {
          css: {
            maxWidth: '100%',
            width: '100%',
            fontSize: '1.25rem',
            p: {
              fontSize: '1.25rem',
            },
            li: {
              fontSize: '1.25rem',
            },
            h1: {
              fontSize: '2.25rem',
            },
            h2: {
              fontSize: '1.875rem',
            },
            h3: {
              fontSize: '1.5rem',
            },
            img: {
              maxWidth: '100%',
            },
            pre: {
              fontSize: '1.125rem',
              overflowX: 'auto',
            },
            code: {
              fontSize: '1.125rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            },
          },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
};
