import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/pages/**/*.{js,ts,jsx,tsx,mdx}", "./src/components/**/*.{js,ts,jsx,tsx,mdx}", "./src/app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f4faf4",
          100: "#dcedd7",
          500: "#2f7d32",
          700: "#1d4d20",
          900: "#123014"
        }
      }
    }
  },
  plugins: []
};

export default config;
