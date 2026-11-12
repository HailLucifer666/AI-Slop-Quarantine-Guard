import type { Config } from 'tailwindcss'

/**
 * Command Wall theme (merged Aurora + Wall system — see web/DESIGN.md).
 * Token VALUES live as CSS custom properties in app/dashboard/wall.css
 * (`:root` block, single source of truth); the `--*-rgb` channel triples those
 * opacity-modifier names need live in app/globals.css. Tailwind only NAMES
 * tokens so `bg-bg`, `text-text-muted`, `border-line`, `text-sev-certain`,
 * `text-accent-cyan` etc. work. The Aurora names (brand-indigo, brand-teal,
 * scan, border, border-strong) are retired.
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
        line: 'var(--line)', // already rgba
        'line-strong': 'var(--line-strong)',
        'accent-cyan': 'rgb(var(--accent-cyan-rgb) / <alpha-value>)',
        'accent-magenta': 'rgb(var(--accent-magenta-rgb) / <alpha-value>)',
        'accent-violet': 'rgb(var(--accent-violet-rgb) / <alpha-value>)',
        'accent-green': 'rgb(var(--accent-green-rgb) / <alpha-value>)',
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
        xs: '4px',
        sm: '6px',
        md: '8px',
        lg: '12px',
        xl: '16px',
        full: '9999px',
      },
      fontFamily: {
        display: ['var(--font-display)', 'sans-serif'],
        sans: ['var(--font-sans)', 'sans-serif'],
        mono: ['var(--font-mono)', 'monospace'],
      },
      fontSize: {
        // Floor-safe scale from DESIGN.md — 12px absolute minimum, nothing below.
        xs: ['0.75rem', { lineHeight: '1.33' }], // 12/16
        sm: ['0.8125rem', { lineHeight: '1.47' }], // 13/19
        base: ['0.875rem', { lineHeight: '1.5' }], // 14/21
        md: ['1rem', { lineHeight: '1.5' }], // 16/24
        lg: ['1.125rem', { lineHeight: '1.34' }], // 18/24
        xl: ['1.25rem', { lineHeight: '1.3' }], // 20/26
        '2xl': ['1.5rem', { lineHeight: '1.25' }], // 24/30
        '3xl': ['2rem', { lineHeight: '1.2' }], // 32/38
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
export default config
