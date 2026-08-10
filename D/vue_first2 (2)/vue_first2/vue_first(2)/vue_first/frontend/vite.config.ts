import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path' // <---【第 1 步】必须引入 path

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  // <---【第 2 步】添加 resolve 配置，告诉 Vite "@" 代表 "src"
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})