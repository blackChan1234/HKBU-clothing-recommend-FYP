# Aura Stylist MVP 任務清單 (TODO.md)

## Phase 1: 最小可行性產品 (MVP) 核心跑通

### 前端任務 (React Native / Expo)
- [x] Task 1.1: 初始化 Expo 專案，將原本的 React (Vite) Web UI (App.jsx) 轉換為 React Native 原生組件 (`<View>`, `<Image>`, `<TouchableOpacity>`)。
- [x] Task 1.2: 安裝並整合 `expo-image-picker`，實作「拍攝/從相簿上傳單件衣服圖片」功能。
- [x] Task 1.3: 實作「拍攝/從相簿上傳全身基準照 (Base Image)」功能。
- [x] Task 1.4: 建立長時間等待的 Loading 動畫組件（例如顯示「AI 正在為您換裝...」），確保等待生圖時 UI 不會卡死。

### 後端任務 (FastAPI)
- [x] Task 1.5: 開發或更新 `/api/wardrobe/upload` 接口，確保能正確接收來自 Expo 手機端的 `multipart/form-data` 格式圖片，並暫存到伺服器本地。
- [x] Task 1.6: 建立 `/api/try-on/generate` 接口，用於接收基準照與衣服照片的請求。
- [ ] Task 1.7: 在 FastAPI 中實作非同步任務 (Async Task)，呼叫 IDM-VTON (Nano Banana) 進行生圖，並將合成結果安全回傳給前端顯示。

## Phase 2: 智能衣櫃與資料庫建設 (Backend & DB)
- [ ] Task 2.1: 建立本地端 SQLite 或 PostgreSQL 資料庫，設計 `Garment` 表格以儲存衣物 Meta Data (ID, 圖片路徑, 標籤等)。
- [ ] Task 2.2: 實作圖片儲存與優化機制：完整原圖存於本地伺服器，並生成縮圖 (Thumbnail) 供手機端快速載入。
- [ ] Task 2.3: 後端整合 `rembg`，實作上傳衣物後的「自動背景去除」功能。

## Phase 3: AI Agent 推薦大腦 (LangGraph)
- [ ] Task 3.1: 完善 LangGraph Agent 邏輯，能從資料庫檢索衣物並輸出搭配清單。
- [ ] Task 3.2: 建立 `/api/recommend/daily` 接口供前端呼叫以獲取每日穿搭推介。