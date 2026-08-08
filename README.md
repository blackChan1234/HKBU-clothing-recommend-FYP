# Aura Stylist — AI Fashion Stylist

**Final Year Project — BSc (Hons) Computer Science, Hong Kong Baptist University (2025–26)**

A full-stack AI fashion assistant that digitizes your wardrobe, recommends outfits through a **LangGraph multi-agent system**, and generates **virtual try-on** images.

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python, FastAPI, Uvicorn, SQLAlchemy, SQLite |
| AI Agents | LangGraph, LangChain (Google Gemini + OpenAI-compatible APIs) |
| Image Processing | rembg (background removal), Pillow |
| Auth | JWT (python-jose, bcrypt) |
| Frontend | React (Vite), Tailwind CSS |
| External APIs | Rakuten API (real-time product search) |

## System Architecture

```
React (Vite + Tailwind) ──HTTP──▶ FastAPI server ──▶ LangGraph agents
                                      │                    │
                                      │                    └──▶ Gemini / OpenAI LLMs
                                      ├──▶ SQLAlchemy / SQLite (wardrobe, users)
                                      ├──▶ rembg (garment background removal)
                                      └──▶ Try-on job queue (async, IDM-VTON)
```

### Multi-Agent Recommendation System (LangGraph)

Six cooperating agents handle outfit recommendations:

- **ManagerAgent** — orchestrates the conversation/flow between agents
- **UserProfilerAgent** — builds and remembers user style preferences
- **AestheticStylistAgent** — evaluates combinations for aesthetic coherence
- **BudgetPlannerAgent** — filters suggestions by price constraints
- **ContextAdvisorAgent** — considers occasion, weather, and event context
- **RecommendationSynthesizerAgent** — merges agent outputs into a final styling plan

## Features

- **JWT authentication** — register / login / profile management
- **Wardrobe digitization** — upload garment photos; background auto-removed (rembg) and items stored in the wardrobe DB
- **Outfit recommendations** — scenario-driven styling plans ("interview tomorrow") from the multi-agent pipeline, plus a daily recommendation endpoint with a feedback loop
- **Virtual try-on** — async generation pipeline with job status polling (`/api/try-on/*`)
- **Product search** — live clothing data from the Rakuten API

## Quick Start

### Backend

```bash
pip install -r requirements.txt

# set your keys (see apis/api_clients.py)
export GEMINI_API_KEY=...
export HKBU_API_KEY=...        # OpenAI-compatible endpoint
# optional: export NANO_BANANA_API_KEY=...

python server.py                # http://localhost:8000
```

### Frontend

```bash
cd frontend/my-fashion-app
npm install
npm run dev                     # http://localhost:5173
```

## API Overview

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` / `/api/auth/login` | Auth |
| POST | `/api/wardrobe/upload` | Upload garment (bg removed, auto-tagged) |
| GET | `/api/wardrobe/garments` | List wardrobe |
| POST | `/api/recommend/daily` | Daily outfit recommendation |
| POST | `/api/try-on/generate` | Start virtual try-on job (async) |
| GET | `/api/try-on/status/{job_id}` | Poll try-on progress |

## Project Structure

```
agents/         LangGraph agent definitions (6 agents)
apis/           LLM API clients (Gemini, OpenAI-compatible, NanoBanana)
services/       wardrobe agent, RichWear search, sample outfits
server.py       FastAPI application (~940 LOC)
database.py     SQLAlchemy models
auth.py         JWT auth helpers
scripts/        dataset seeding (RichWear)
frontend/       React (Vite + Tailwind) web client
```

## Documentation

- `PROJECT_CONTEXT.md` — full project background & architecture notes
- `PROGRESS_REPORT.md` — development phases & completion log
- `TODO.md` — task breakdown
- `項目管理計劃.md` — project management plan (Chinese)

## Status & Known Limitations

This is a **working FYP prototype**, not production software. Honest caveats:

- **Mobile client**: the React Native (Expo) app is developed in a separate workspace and is not yet included in this repo — the web frontend is the demo UI.
- **Virtual try-on** depends on an external GPU-hosted diffusion model (IDM-VTON); it is triggered via async jobs and is the most environment-sensitive part of the pipeline.
- **Security**: `auth.py` falls back to a hardcoded dev JWT secret if `JWT_SECRET` is not set — set a real secret before any deployment.
- Dataset seeding scripts require the RichWear dataset (see `scripts/`).
