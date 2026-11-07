import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
  // Vercel serves the build from frontend/dist/app (see vercel.json).
  build: { outDir: "dist/app", emptyOutDir: true },
  // `uvicorn backend.server:app --port 8000` during local development.
  server: { proxy: { "/api": "http://localhost:8000" } },
});
