import { defineConfig } from "vite";

export default defineConfig({
  base: "/chat/", // where the server mounts the page
  build: {
    // Into the Python package, which serves it.
    outDir: "../src/glint/static",
    emptyOutDir: true,
  },
});
