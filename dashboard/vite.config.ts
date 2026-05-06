import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /apis to the OpenEMR docker compose stack so the
// React app can call the FHIR + REST endpoints without CORS pain. In
// production the SPA is served from the same host as OpenEMR (or behind a
// reverse proxy) so this config only matters during `npm run dev`.
export default defineConfig({
  // When the dashboard is served by the agent at /dashboard/* (the
  // production embed path used by demographics.php), Vite needs to emit
  // asset URLs prefixed with /dashboard/. In dev (`npm run dev`) we keep
  // the root base so localhost:5173 still works without rewriting.
  base: process.env.VITE_DASHBOARD_BASE ?? "/dashboard/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/apis": {
        target: "https://localhost:9300",
        changeOrigin: true,
        secure: false,
      },
      "/oauth2": {
        target: "https://localhost:9300",
        changeOrigin: true,
        secure: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
  },
});
