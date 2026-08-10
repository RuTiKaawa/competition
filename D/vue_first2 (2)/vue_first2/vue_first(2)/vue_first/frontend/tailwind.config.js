/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sidebar: "#f7fafb",
        "sidebar-hover": "#e5f8f3",
        contentbg: "#f4f7fa",
        primary: "#1a9a89",
        "primary-dark": "#11766e",
        success: "#22b889",
        danger: "#ef5c6f",
        ink: "#1e3045",
        mist: "#e9f0f4",
      },
    },
  },
  plugins: [],
}
