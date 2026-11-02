import { defineConfig } from "vite";

export default defineConfig({
  build: {
    // Into the Python package, which serves it.
    outDir: "../src/glint/static",
    emptyOutDir: true,
  },
});
