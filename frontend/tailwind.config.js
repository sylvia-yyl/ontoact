/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  // Tailwind's default blue-600 (#2563eb) is the brand color; see --brand in src/index.css.
  theme: { extend: {} },
  plugins: [],
}
