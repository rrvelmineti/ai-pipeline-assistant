import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the API runs on :8000 (python -m claims_platform.cli serve) and Vite proxies /api to it.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { outDir: "dist", sourcemap: false },
  test: { environment: "jsdom", include: ["src/__tests__/**/*.test.{ts,tsx}"] },
});
