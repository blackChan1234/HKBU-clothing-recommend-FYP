# Aura Stylist FYP — Progress Report

**Project:** Aura Stylist — AI-Powered Virtual Fashion Try-On & Wardrobe Recommendation App
**Report Date:** 2026-03-03
**Repository Branch:** `main`
**Report Prepared By:** Technical Project Manager

---

## 1. Executive Summary

| Item | Detail |
|---|---|
| **Overall Status** | ✅ All Planned Phases Complete |
| **Current Phase** | Phase 3 — AI Agent Recommendation Brain (DONE) |
| **Completion** | **100% (13 / 13 tasks)** |
| **Last Commit** | `85ca6e0` — Task 3.3 Tinder-mode daily outfit recommendation |
| **Total Commits** | 17 |

All three development phases defined in `TODO.md` have been fully implemented and committed. The application has progressed from a bare Expo scaffold to a full-stack, AI-powered fashion app featuring JWT authentication, a cloud-backed wardrobe, computer-vision auto-tagging, and a LangGraph recommendation engine with a Tinder-style swipe UI.

The immediate technical foundation is stable and demo-ready. No outstanding planned tasks remain. Any future work constitutes post-MVP iteration.

---

## 2. Completed Achievements

### Phase 0 — Authentication (2 / 2 tasks) ✅

| Task | Description | Commit |
|---|---|---|
| **0.1** | FastAPI JWT auth backend — `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`. BCrypt password hashing, 7-day HS256 tokens, SQLite `users` table via SQLAlchemy. | `df20beb` |
| **0.2** | Expo Login / Sign Up screens with `AsyncStorage` token persistence. `AuthProvider` context guards all routes; unauthenticated users are auto-redirected to `/(auth)/login`. | `03de473` |

**Notable technical decision:** Dropped `passlib` (incompatible with `bcrypt` 5.x on Python 3.14) in favour of calling `bcrypt.hashpw()` / `bcrypt.checkpw()` directly.

---

### Phase 1 — MVP Core (8 / 8 tasks) ✅

| Task | Description | Commit |
|---|---|---|
| **1.1** | Expo project initialised; Web UI converted to React Native components (dark theme: `#0a0a0f` bg, `#9333ea` purple accent). | `99b1896` |
| **1.2** | `expo-image-picker` integrated for garment photo capture from camera or gallery. | `5f4b776` |
| **1.3** | Full-body base-image picker implemented for the virtual try-on workflow. | _(part of 1.2 sprint)_ |
| **1.4** | Long-wait `ActivityIndicator` loading screen with contextual copy for Nano Banana processing. | _(part of MVP sprint)_ |
| **1.5** | Headless-photo guidance modal added to the base-image upload flow. Displays ASCII body diagram and rules; user must acknowledge before image picker opens. | `e010762` |
| **1.6** | `POST /api/wardrobe/upload` endpoint built; saves images to `uploads/` and serves them as static files. | `e010762` |
| **1.7** | `POST /api/try-on/generate` endpoint created; accepts `person_image` + `garment_image` file uploads. | `e311bb8` |
| **1.8** | Async job-queue pattern implemented: endpoint returns `{job_id, status:"pending"}` immediately; Nano Banana API called in a background thread; client polls `GET /api/try-on/status/{job_id}`. Content-violation keyword detection included. | `e311bb8` |

---

### Phase 2 — Smart Wardrobe & Database (4 / 4 tasks) ✅

| Task | Description | Commit |
|---|---|---|
| **2.1** | SQLite `garments` table designed with `user_id` FK (cascade delete), plus `image_path`, `thumbnail_path`, `nobg_path`, `category`, `color`, `material`, `label`, `created_at`. Safe `ALTER TABLE` migration in `init_db()` for existing databases. | `335a297` |
| **2.2** | Pillow-based thumbnail generation (300×400 max, JPEG q85, aspect-ratio preserving) on every upload. `/thumbnails/` static mount added. | `3d2e6da` |
| **2.3** | `rembg[cpu]` (v2.0.72 + onnxruntime) integrated. `_remove_background()` helper uses lazy import to avoid slow server startup. Background-removed PNGs saved as `uploads/nobg_<id>.png`; `nobg_url` exposed in all wardrobe API responses. | `46c131c` |
| **2.4** | Gemini Vision (`gemini-2.0-flash`) auto-tagging runs as a `BackgroundTask` after each upload. Extracts `category`, `color`, `material` and writes them back to the `Garment` row using its own `SessionLocal` session (thread-safe). Soft failure — upload always succeeds even if tagging fails. | `2c27077` |

---

### Phase 3 — AI Agent Recommendation Brain (3 / 3 tasks) ✅

| Task | Description | Commit |
|---|---|---|
| **3.1** | Removed all hallucinated-image generation logic: deleted `services/appearance_service.py`, removed `generate_ootd_diagram()` and `_generate_stub_diagram()` from `NanoBananaClient`, dropped legacy `POST /api/generate-plan` and `POST /api/generate-visuals` endpoints. Net: −279 lines. | `185a1ab` |
| **3.2** | New LangGraph agent (`services/wardrobe_agent.py`) with 3-node linear graph: `load_wardrobe` (SQLite) → `get_weather` (HKO API) → `recommend_outfit` (Gemini via `HKBUAPIClient`). `_parse_json_safe()` helper strips markdown fences before `json.loads()`. Returns full garment objects with all image URLs. | `2fb6264` |
| **3.3** | Tinder-mode recommendation screen fully implemented (frontend + backend). See details below. | `85ca6e0` |

**Task 3.3 detail — Tinder-Mode Outfit Recommendation:**

*Backend additions:*
- `POST /api/recommend/daily` — Synchronous FastAPI endpoint (runs in thread pool); invokes LangGraph to generate **3 distinct outfit combinations** and returns pure JSON + image URLs. Zero Nano Banana calls in this path (prevents 90-second timeout crashes).
- `POST /api/recommend/feedback` — Receives `{"garment_ids": [...], "liked": bool}` per swipe; logs preference data for future AI tuning.
- `POST /api/try-on/from-wardrobe` — On-demand try-on: accepts `person_image` upload + `garment_id` form field; reads garment bytes from disk server-side (no client re-upload); queues a Nano Banana background job; returns `job_id` for polling.

*Frontend additions (`new front end/wardrobe-app`):*
- **Daily tab** added to tab bar (sparkles icon).
- **`recommend.tsx`** — Full Tinder swipe card UI:
  - `PanResponder` + `Animated.ValueXY` (React Native built-in; no additional dependencies).
  - 3 cards stacked with −4% scale and 10px `translateY` depth effect per layer.
  - LIKE 💚 / PASS ❌ overlay stamps fade in when drag exceeds 120px threshold.
  - Card flies off screen (280ms) on release past threshold; springs back if released early.
  - ❌ / 💚 icon action buttons below the stack for tap-based interaction.
  - **"✨ Virtual Try-On"** button inside each front card → triggers image picker for headless base photo → polls `/api/try-on/from-wardrobe` every 4 seconds → displays result in a bottom-sheet modal.
  - Per-swipe feedback fires `POST /api/recommend/feedback` with that card's exact `garment_ids`.
  - Summary screen after all cards are swiped ("Liked X / 3 outfits").

---

## 3. Current Focus & Next Steps

All tasks in `TODO.md` are complete. The following are **recommended post-MVP priorities** based on the current codebase state:

### High Priority (Demo Polish)
1. **Persistent Feedback Storage** — `POST /api/recommend/feedback` currently logs to the server logger only. Adding a `Feedback` table to SQLite would enable data-driven model improvement and make a stronger FYP demonstration.
2. **Wardrobe Screen Auth Upgrade** — `wardrobe.tsx` still uses a local `useState<string[]>` for garments and does not call `GET /api/wardrobe/garments`. It should be updated to load the authenticated user's garments from the backend on mount, matching the pattern established in Phase 2.
3. **Frontend Try-On Wiring (Home Screen)** — `index.tsx` `handleGenerate()` contains a `TODO` comment (`setTimeout(() => setAppState('result'), 3000)`) instead of the real `POST /api/try-on/generate` + polling flow.

### Medium Priority (Robustness)
4. **JWT Refresh / Expiry Handling** — Tokens are 7-day HS256 with no refresh mechanism. Expired tokens currently produce an unhandled 401 on the frontend.
5. **`BACKEND_URL` Centralisation** — The IP `http://192.168.50.218:8000` is hardcoded in three separate files (`wardrobe.tsx`, `auth-context.tsx`, `recommend.tsx`). A single shared constant or environment variable would simplify device testing.
6. **Garment Deletion Endpoint** — No `DELETE /api/wardrobe/garments/{id}` endpoint exists; orphaned files in `uploads/` and `thumbnails/` cannot be cleaned up through the app.

### Low Priority (Future Enhancement)
7. **Feedback-Driven Personalisation** — Wire the `liked/passed` preference log into the LangGraph `recommend_outfit` prompt as context to bias future recommendations.
8. **Nano Banana Try-On Result Persistence** — Try-on results are in-memory only (`_jobs` dict). Saving the result URL to a `TryOnResult` DB table would allow a history view.
9. **Production Security Hardening** — `JWT_SECRET` should be rotated from the development default; CORS `allow_origins=["*"]` should be restricted before any public deployment.

---

## 4. Known Blockers & Technical Constraints

| Constraint | Details |
|---|---|
| **Headless base images required** | Nano Banana's content policy blocks photos containing human faces. All try-on workflows require the person's base photo to exclude the head (neck-and-below). This is enforced via a mandatory UI modal on the frontend before the image picker opens. |
| **Nano Banana is async-only** | The Nano Banana API call can take 30–240 seconds. All try-on endpoints return a `job_id` immediately and require client polling of `GET /api/try-on/status/{job_id}`. No try-on generation is triggered inside `/api/recommend/daily` to prevent request timeouts. |
| **Python 3.14 environment** | The server runs on Python 3.14 (`C:/Users/chan/AppData/Local/Programs/Python/Python314/`). `passlib` is incompatible with this version (fails to read `bcrypt.__about__.__version__`); `bcrypt` is called directly instead. |
| **rembg model weights** | `rembg` downloads ONNX model weights (~170 MB) on first call. The import is lazy (inside `_remove_background()`) to avoid slowing server startup on machines where the cache is cold. |
| **Dual git repositories** | The frontend lives at `new front end/wardrobe-app/` which contains its own `.git` repo (`master` branch). Frontend changes must be committed to **both** the wardrobe-app repo and the parent FYP repo. |
| **In-memory job store** | Try-on jobs are stored in the `_jobs` dict in `server.py`. All job state is lost on server restart. This is acceptable for MVP/demo but not for production. |
| **Gemini auto-tagging quality** | Tags (`category`, `color`, `material`) are generated by `gemini-2.0-flash` with a zero-shot prompt. Results on garments with unusual lighting or backgrounds may be inaccurate. Tagging failure is soft — the upload succeeds and fields remain `null`. |

---

## 5. Technology Stack Summary

| Layer | Technology |
|---|---|
| **Frontend** | React Native (Expo SDK), Expo Router v6, TypeScript, AsyncStorage, PanResponder + Animated |
| **Backend** | Python 3.14, FastAPI, Uvicorn, SQLAlchemy 2.0 (SQLite) |
| **Authentication** | BCrypt + python-jose (JWT HS256, 7-day expiry) |
| **AI / Vision** | Google Gemini (`gemini-2.0-flash`) for auto-tagging, Nano Banana API (`gemini-3-pro-image-preview`) for virtual try-on |
| **AI Agent** | LangGraph + HKBUAPIClient (Qwen3-max via HKBU GenAI) + HKO Weather API |
| **Image Processing** | Pillow (thumbnails), rembg + onnxruntime (background removal) |
| **State Management** | React `useState` / `useContext` / `useRef`; FastAPI `BackgroundTasks` for async jobs |

---

*Report generated from `TODO.md` and `git log` as of commit `85ca6e0` (2026-03-03).*
