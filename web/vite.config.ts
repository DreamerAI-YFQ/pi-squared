import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发模式：/api 代理到本地网关（pi-squared serve）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
