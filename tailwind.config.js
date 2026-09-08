/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./templates/**/*.js"],
  theme: {
    extend: {
      boxShadow: {
        xs: "0 1px 2px 0 rgb(15 45 37 / 0.06)",
        panel: "0 1px 2px 0 rgb(15 45 37 / 0.04), 0 12px 32px -16px rgb(15 45 37 / 0.18)",
        knob: "0 1px 2px 0 rgb(15 45 37 / 0.10), 0 1px 1px 0 rgb(15 45 37 / 0.04)",
        pop: "0 8px 24px -8px rgb(15 45 37 / 0.24)",
      },
      borderRadius: {
        panel: "20px",
      },
      colors: {
        mint: {
          DEFAULT: "#0F4C3A",
          hover: "#083025",
          ink: "#0F2D25",
          muted: "#4A6B62",
          line: "#DCE5E4",
          hair: "#EDF2F1",
          wash: "#F0F4F4",
          rose: "#F43F5E",
        },
      },
      fontFamily: {
        sans: [
          "Hiragino Sans",
          "Hiragino Kaku Gothic ProN",
          "Yu Gothic",
          "YuGothic",
          "sans-serif",
        ],
      },
    },
  },
};
