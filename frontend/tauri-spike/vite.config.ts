import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("@xyflow")) {
            return "vendor-xyflow";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true,
    watch: {
      ignored: [
        "**/src-tauri/target/**",
        "**/src-tauri/backend-build/**",
        "**/src-tauri/backend-dist/**",
        "**/src-tauri/binaries/**",
      ],
    },
  },
});
