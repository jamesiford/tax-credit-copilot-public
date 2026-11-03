/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Bridged to the semantic tokens (styles/tokens/semantic.css) so the
        // Tailwind utilities still left in ChatPanel follow the active theme.
        // A `var()` colour cannot take an alpha modifier, so `/40` is a no-op.
        brand: 'var(--tw-brand)',
        'brand-deep': 'var(--tw-brand-deep)',
        'brand-ink': 'var(--tw-brand-ink)',
        'accent-2': 'var(--tw-accent-2)',
        success: 'var(--tw-success)',
        'success-deep': 'var(--tw-success-deep)',
        surface: 'var(--tw-surface)',
        subtle: 'var(--tw-subtle)',
        'subtle-2': 'var(--tw-subtle-2)',
        muted: 'var(--tw-muted)',
      },
      fontFamily: {
        sans: ['var(--font-sans)'],
      },
      boxShadow: {
        tile: 'var(--shadow-1)',
      },
    },
  },
  plugins: [],
};
