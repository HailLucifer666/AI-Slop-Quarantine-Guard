import type { Config } from 'tailwindcss'

/**
 * Aurora-on-Black theme. Token VALUES live as CSS custom properties in
 * app/globals.css (single source of truth); Tailwind just names them so
 * `bg-bg`, `text-text-muted`, `border-border`, `text-sev-certain` etc. work.
 * Mirrors web/DESIGN.md.
 */
const config: Config = {
  darkMode: 'class',
  content: [
    './pages/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
    './app/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // rgb(var(--x-rgb) / <alpha-value>) so Tailwind opacity modifiers work.
        bg: 'rgb(var(--bg-rgb) / <alpha-value>)',
        surface: 'rgb(var(--surface-rgb) / <alpha-value>)',
        'surface-elevated': 'rgb(var(--surface-elevated-rgb) / <alpha-value>)',
        border: 'var(--border)', // already rgba
        'border-strong': 'var(--border-strong)',
        'brand-indigo': 'rgb(var(--brand-indigo-rgb) / <alpha-value>)',
        'brand-teal': 'rgb(var(--brand-teal-rgb) / <alpha-value>)',
        'brand-emerald': 'rgb(var(--brand-emerald-rgb) / <alpha-value>)',
        scan: 'rgb(var(--scan-rgb) / <alpha-value>)',
        'sev-certain': 'rgb(var(--sev-certain-rgb) / <alpha-value>)',
        'sev-high': 'rgb(var(--sev-high-rgb) / <alpha-value>)',
        'sev-medium': 'rgb(var(--sev-medium-rgb) / <alpha-value>)',
        'sev-clean': 'rgb(var(--sev-clean-rgb) / <alpha-value>)',
        text: 'rgb(var(--text-rgb) / <alpha-value>)',
        'text-muted': 'rgb(var(--text-muted-rgb) / <alpha-value>)',
        'text-faint': 'rgb(var(--text-faint-rgb) / <alpha-value>)',
      },
      backgroundImage: {
        'brand-gradient': 'var(--brand-gradient)',
      },
      borderRadius: {
        sm: '10px',
        md: '16px',
        lg: '22px',
      },
      fontFamily: {
        display: ['var(--font-display)', 'sans-serif'],
        sans: ['var(--font-sans)', 'sans-serif'],
        mono: ['var(--font-mono)', 'monospace'],
      },
      fontSize: {
        // 12/14/16/20/28/40/56 scale from DESIGN.md
        xs: '0.75rem',
        sm: '0.875rem',
        base: '1rem',
        lg: '1.25rem',
        xl: '1.75rem',
        '2xl': '2.5rem',
        '3xl': '3.5rem',
      },
      boxShadow: {
        glass: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 40px -12px rgba(0,0,0,0.6)',
        glow: '0 0 60px -10px rgba(74,91,255,0.35)',
      },
      keyframes: {
        'scan-pulse': {
          '0%, 100%': { opacity: '0.35' },
          '50%': { opacity: '1' },
        },
        'aurora-drift': {
          '0%': { transform: 'translate3d(0,0,0) scale(1)' },
          '50%': { transform: 'translate3d(2%,-3%,0) scale(1.05)' },
          '100%': { transform: 'translate3d(0,0,0) scale(1)' },
        },
        'orbit-spin': {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
        'orbit-pulse': {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '1' },
        },
        'dot-reveal': {
          '0%': { opacity: '0', transform: 'scale(0.5)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'lollipop-grow': {
          '0%': { transform: 'scaleX(0)' },
          '100%': { transform: 'scaleX(1)' },
        },
      },
      animation: {
        'scan-pulse': 'scan-pulse 1.8s ease-in-out infinite',
        'aurora-drift': 'aurora-drift 24s ease-in-out infinite',
        'orbit-spin': 'orbit-spin 40s linear infinite',
        'orbit-pulse': 'orbit-pulse 2s ease-in-out infinite',
        'dot-reveal': 'dot-reveal 0.4s ease-out both',
        'lollipop-grow': 'lollipop-grow 0.6s ease-out both',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
export default config
