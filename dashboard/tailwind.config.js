/** @type {import('tailwindcss').Config} */
// One system for the landing page and the dashboard: neutral near-black surfaces that step up by lightness only,
// 1px hairlines, radius <= 8px, white as the primary action colour, and no brand hue. Colour is reserved for data
// (the semantic decision colours) so it always means something.
module.exports = {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    borderRadius: {
      none: '0',
      sm: '3px',
      DEFAULT: '4px',
      md: '6px',
      lg: '8px',
      xl: '8px',
      '2xl': '8px',
      '3xl': '8px',
      full: '9999px',
    },
    extend: {
      colors: {
        ink: {
          950: '#08090a', // canvas
          900: '#0d0e10', // surface 1
          850: '#111214',
          800: '#16171a', // surface 2 (hover, inputs)
          700: '#1f2023', // solid hairline / skeleton
          600: '#2e3035',
          500: '#4a4d54',
          400: '#7f838c', // tertiary text (>= 4.5:1 on canvas)
          300: '#a4a7ae', // secondary text
          200: '#c9cbd0',
          100: '#e7e8ea',
          50: '#f6f6f7', // primary text
        },
        line: { DEFAULT: 'rgba(255,255,255,0.08)', strong: 'rgba(255,255,255,0.14)', faint: 'rgba(255,255,255,0.05)' },
        // "accent" is white: primary actions are white-on-black. Kept as a token so components read semantically.
        accent: { DEFAULT: '#ffffff', soft: '#e7e8ea', dim: '#2e3035' },
        // decisions: the only chromatic colours in the product
        allow: '#3ecf8e',
        throttle: '#f5a524',
        block: '#f5594e',
        fault: '#a4a7ae',
        low: '#a4d65e',
        high: '#f08a3b',
      },
      fontFamily: {
        sans: ['"Geist Variable"', 'Geist', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        display: ['"Geist Variable"', 'Geist', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Geist Mono Variable"', '"Geist Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      letterSpacing: { tightest: '-0.045em', tighter: '-0.035em' },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        // Above-the-fold entrance: transform only, so the text is painted (and counted for LCP) immediately.
        rise: { '0%': { transform: 'translateY(10px)' }, '100%': { transform: 'translateY(0)' } },
        'fade-in': { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        'live-ping': {
          '0%': { transform: 'scale(1)', opacity: '0.55' },
          '100%': { transform: 'scale(2.4)', opacity: '0' },
        },
        stamp: {
          '0%': { opacity: '0', transform: 'scale(1.08)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        grow: {
          '0%': { opacity: '0', transform: 'translateX(-4px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
        'node-in': { '0%': { opacity: '0', transform: 'scale(0.4)' }, '100%': { opacity: '1', transform: 'scale(1)' } },
        'edge-in': { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        draw: { '0%': { strokeDashoffset: '1' }, '100%': { strokeDashoffset: '0' } },
        travel: { '0%': { transform: 'translateX(0)', opacity: '0' }, '12%': { opacity: '1' }, '100%': { transform: 'translateX(var(--travel, 54px))', opacity: '1' } },
        blink: { '0%, 49%': { opacity: '1' }, '50%, 100%': { opacity: '0' } },
      },
      animation: {
        'fade-up': 'fade-up 0.55s cubic-bezier(0.22, 1, 0.36, 1) both',
        rise: 'rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) both',
        'fade-in': 'fade-in 0.3s ease-out both',
        'live-ping': 'live-ping 1.8s cubic-bezier(0, 0, 0.2, 1) infinite',
        stamp: 'stamp 0.28s cubic-bezier(0.2, 0.9, 0.3, 1) both',
        grow: 'grow 0.3s cubic-bezier(0.22, 1, 0.36, 1) both',
        shimmer: 'shimmer 1.6s linear infinite',
        'node-in': 'node-in 0.32s cubic-bezier(0.22, 1, 0.36, 1) both',
        'edge-in': 'edge-in 0.3s ease-out both',
        draw: 'draw 0.7s cubic-bezier(0.4, 0, 0.2, 1) both',
        travel: 'travel 0.9s cubic-bezier(0.4, 0, 0.2, 1) both',
        blink: 'blink 1.1s steps(1) infinite',
      },
    },
  },
  plugins: [],
};
