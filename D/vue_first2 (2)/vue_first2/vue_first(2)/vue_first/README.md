# Vue 3 + FastAPI 数据分析项目

项目按前后端分目录组织：

- `frontend/`：Vue 3 + TypeScript + Vite 前端
- `backend/`：FastAPI 后端

前端开发：

```bash
cd frontend
npm install
npm run dev
```

后端依赖和启动方式见 `backend/requirements.txt` 及后端代码。

前端使用 Vue 3、TypeScript 和 Vite；组件采用 Vue 3 `<script setup>` 语法。

## 更新记录

### 2026-08-07

- 重构前端应用壳层：新增 Oripio 深色动态入口首页、统一侧边导航、状态头部和响应式布局。
- 重设计总览页：保留数据概览、业务信号和快捷入口，新增可交互的 embedding 向量空间演示。
- 新增 `frontend/src/components/AuroraField.vue`、`frontend/src/components/VectorSpace.vue` 和 `frontend/src/pages/LandingPage.vue`，用于动态背景、向量散点检索交互和网站入口页。
- Tailwind、TypeScript、Vite 相关配置统一归档在 `frontend/`，未与后端文件混放。
- 当前向量空间使用演示点位；后续接入 embedding 服务后，可将 `VectorSpace` 的点位数据替换为真实 RAG API 返回的 PCA/UMAP 坐标。
- 首页升级为 Canvas 数据粒子场、分段文字揭示和指针视差，并加入 `home → charging → portal → workspace` 门户状态机；重复点击在转场期间会被锁定，返回首页使用短反向淡化。
- 首次进入序列通过 `sessionStorage` 仅在当前会话完整播放一次，再次返回采用缩短版本；用户可跳过，辅助功能不会被动画阻塞。
- 总览、智能问析、数据资源、业务知识和系统设置统一为石墨黑玻璃面板、青紫光晕与分层舞台体系，同时暗色化弹窗、知识图谱和向量空间；原有请求路径、载荷及表单操作保持不变。
- 使用本地 npm 依赖打包 Manrope 可变字体，中文回退到系统字体栈，不依赖外部字体 CDN。
- `prefers-reduced-motion` 下停用粒子运动、磁吸和复杂门户扩张，只保留约 180ms 的轻量淡入淡出；小屏布局收敛为底部导航与单列工作区。
