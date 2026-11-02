import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "/chat/", // where the server mounts the page
  build: {
    // Into the Python package, which serves it.
    outDir: "../src/glint/static",
    emptyOutDir: true,
  },
});
