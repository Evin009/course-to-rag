import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run build` writes into the Python package, where FastAPI serves it.
// `npm run dev` serves on :5173 and forwards /api to `python webapp.py` on :8000.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/aicc_demo/web/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
