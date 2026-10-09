/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // The brand palette. Blue is the core thread and purple works beside
        // it — "generously", per the house style guide — so purple carries
        // accents and active states rather than sitting unused. A deployment
        // overrides these at build time; see src/brand.config.js for the
        // name and logo half of white-labeling.
        brand: '#1A1F71',
        'brand-deep': '#0F1450',
        'brand-ink': '#0A0A23',
        'accent-2': '#963CBD',
        success: '#26D07C',
        'success-deep': '#0FA862',
        surface: '#FFFFFF',
        subtle: '#F4F4F6',
        'subtle-2': '#E8E8EE',
        muted: '#6B6B7B',
      },
      fontFamily: {
        // Roboto FIRST. It sat fifth behind Inter and Segoe UI, so it never won.
        sans: ['Roboto', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
      },
      boxShadow: {
        tile: '0 1px 2px rgba(10, 10, 35, 0.05), 0 1px 3px rgba(10, 10, 35, 0.08)',
      },
    },
  },
  plugins: [],
};
