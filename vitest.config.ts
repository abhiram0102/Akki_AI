import { defineConfig } from "vite";
import path from "path";

// Minimal standalone Vitest config — deliberately NOT reusing the root
// vite.config.ts (that one sets `root: "client"`, a dev-only Replit plugin
// pipeline, and an API proxy, none of which unit tests need or want).
// Scoped to client/src so it only ever picks up our own *.test.ts files.
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "client", "src"),
      "@shared": path.resolve(import.meta.dirname, "shared"),
    },
  },
  test: {
    environment: "node",
    include: ["client/src/**/*.test.ts"],
  },
});
