import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          query: ["@tanstack/react-query"],
          antd: ["antd", "@ant-design/icons"],
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
  },
});
