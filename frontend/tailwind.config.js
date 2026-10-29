/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0E1417',
        surface: '#151D22',
        'surface-alt': '#1C262C',
        'surface-hi': '#242F36',
        paper: '#ECEAE2',
        muted: '#8C99A0',
        signal: {
          DEFAULT: '#49D6AC',
          dim: '#2C4A42',
        },
        amber: {
          DEFAULT: '#E8A33D',
          dim: '#4A3B23',
        },
        danger: {
          DEFAULT: '#E5584F',
          dim: '#4A2422',
        },
        line: '#263138',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        sans: ['Inter', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      borderRadius: {
        chat: '1rem',
      },
      keyframes: {
        seal: {
          '0%': { transform: 'scale(0.6)', opacity: '0' },
          '60%': { transform: 'scale(1.08)', opacity: '1' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        pulseDot: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
      },
      animation: {
        seal: 'seal 240ms ease-out',
        pulseDot: 'pulseDot 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
