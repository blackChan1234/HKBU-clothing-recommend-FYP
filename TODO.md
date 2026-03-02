# Aura Stylist MVP 任務清單 (TODO.md)

## Phase 0: 登入系統與使用者認證 (Authentication)
- [x] Task 0.1: [後端] 在 FastAPI 實作 JWT 登入/註冊機制，並建立 `User` 資料庫表 (包含 id, username, hashed_password)。
- [x] Task 0.2: [前端] 在 Expo 實作 Login / Sign Up 畫面，並使用 AsyncStorage 儲存 JWT Token，設定若未登入則自動導向登入頁。

## Phase 1: 最小可行性產品 (MVP) 核心跑通
- [x] Task 1.1: [前端] 初始化 Expo 專案，將 Web UI 轉換為 React Native 原生組件。
- [x] Task 1.2: [前端] 整合 `expo-image-picker`，實作「拍攝/從相簿上傳單件衣服圖片」功能。
- [x] Task 1.3: [前端] 實作「拍攝/從相簿上傳全身基準照 (Base Image)」功能。
- [x] Task 1.4: [前端] 建立長時間等待的 Loading 動畫組件。
- [x] Task 1.5: [前端] 在上傳「基準照 (Base Image)」時，加入 UI 提示，強烈要求用戶「不要包含頭部 (Headless)」，以符合隱私規範並避免 Nano Banana API 阻擋。
- [x] Task 1.6: [後端] 開發 `/api/wardrobe/upload` 接口，接收圖片並暫存到伺服器。*(註：等 Phase 0 完成後，需更新此接口以綁定 user_id)*。
- [x] Task 1.7: [後端] 建立 `/api/try-on/generate` 接口，接收基準照與衣服照片。
- [x] Task 1.8: [後端] 實作非同步任務 (Async Task)，呼叫 Nano Banana API 進行換裝生圖，並加入圖片違規的錯誤處理機制。

## Phase 2: 智能衣櫃與資料庫建設 (Backend & DB)
- [x] Task 2.1: [後端] 建立本地端 SQLite 資料庫，設計 `Garment` 表格。欄位必須包含：`user_id` (外鍵), 圖片路徑, `category`, `color`, `material` 等 Meta Data。
- [x] Task 2.2: [後端] 實作圖片儲存與優化機制：原圖存於伺服器，並生成縮圖 (Thumbnail)。
- [x] Task 2.3: [後端] 整合 `rembg` 進行「自動背景去除」。
- [x] Task 2.4: [後端] 串接 Vision AI 進行「自動打標籤 (Auto-tagging)」，自動萃取衣物特徵並存入 `Garment` 資料表。

## Phase 3: AI Agent 推薦大腦 (LangGraph)
- [ ] Task 3.1: [後端] 移除舊有 LangGraph 的「無中生有」生圖邏輯。
- [ ] Task 3.2: [後端] 重新設計 LangGraph Agent：根據當前登入的 `user_id`，從資料庫撈取該用戶的 `Garment` 數據，並依據場合/天氣推理出最合適的穿搭組合。
- [ ] Task 3.3: [前後端] 建立 `/api/recommend/daily` 接口，回傳推薦的衣物組合與 Nano Banana 生成的試穿結果，並在前端展示。