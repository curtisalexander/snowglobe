import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/healthz": "http://127.0.0.1:8000",
      "/v1": "http://127.0.0.1:8000",
    },
  },
  build: {
    sourcemap: false,
  },
});
