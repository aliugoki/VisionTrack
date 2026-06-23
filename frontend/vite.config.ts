import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://backend:8000',
        changeOrigin: true,
        ws: true,
      },
      // HLS streams from MediaMTX. The browser hits /hls/<path>/index.m3u8
      // and Vite proxies it to the container. In production this becomes
      // an Nginx location block — frontend code never needs to change.
      '/hls': {
        target: 'http://mediamtx:8888',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/hls/, ''),
      },
    },
  },
});
