import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const AGENT = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: AGENT, changeOrigin: true },
      "/media": { target: AGENT, changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
    },
  },
  build: {
    outDir: "../server/gate_studio/static",
    emptyOutDir: true,
  },
});
