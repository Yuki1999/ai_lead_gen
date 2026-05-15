# Overseas Distributor Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI + Vue demo and a Codex skill for overseas distributor prospecting.

**Architecture:** FastAPI owns persistence and business logic. SQLite stores leads, demo outreach, and reply analyses. Vue presents a single operations dashboard that calls the API.

**Tech Stack:** Python 3.11+, uv, FastAPI, SQLite, pytest, Vue 3, Vite, TypeScript.

---

## File Structure

- Create `README.md` with setup and run steps.
- Create `.env.example` for backend configuration.
- Create `backend/pyproject.toml` for uv-managed Python dependencies.
- Create `backend/app/db.py` for SQLite initialization and queries.
- Create `backend/app/schemas.py` for Pydantic request and response models.
- Create `backend/app/services.py` for lead generation, scoring, email rendering, and reply analysis.
- Create `backend/app/main.py` for FastAPI endpoints.
- Create `backend/tests/test_services.py` and `backend/tests/test_api.py` before implementation.
- Create `frontend/package.json`, `frontend/index.html`, `frontend/src/*`, and `frontend/vite.config.ts`.
- Create `skills/overseas-distributor-prospecting/SKILL.md`.

### Task 1: Backend Service Tests

**Files:**
- Create: `backend/tests/test_services.py`

- [ ] **Step 1: Write failing tests**

Cover lead generation from regions and keywords, region-aware email templates, and reply intent classification.

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && uv run pytest tests/test_services.py -v`

Expected: FAIL because `app.services` does not exist.

### Task 2: Backend Service Implementation

**Files:**
- Create: `backend/app/services.py`
- Create: `backend/app/schemas.py`
- Create: `backend/pyproject.toml`

- [ ] **Step 1: Implement minimal service logic**

Add deterministic candidate generation, scoring, email templates, and reply classification.

- [ ] **Step 2: Run tests to verify pass**

Run: `cd backend && uv run pytest tests/test_services.py -v`

Expected: PASS.

### Task 3: Backend API Tests

**Files:**
- Create: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Cover health, prospecting into DB, listing leads, demo send, reply analysis, and lead update.

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && uv run pytest tests/test_api.py -v`

Expected: FAIL because API/database files do not exist.

### Task 4: Backend API Implementation

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/main.py`
- Create: `backend/app/__init__.py`

- [ ] **Step 1: Implement SQLite and FastAPI endpoints**

Initialize tables, provide CRUD helpers, and wire service functions into endpoints.

- [ ] **Step 2: Run backend test suite**

Run: `cd backend && uv run pytest -v`

Expected: PASS.

### Task 5: Frontend Dashboard

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/styles.css`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`

- [ ] **Step 1: Build Vue app**

Create an operations dashboard with lead search, database table, email send demo, and reply analysis.

- [ ] **Step 2: Verify frontend build**

Run: `cd frontend && npm install && npm run build`

Expected: PASS.

### Task 6: Agent Skill and Docs

**Files:**
- Create: `skills/overseas-distributor-prospecting/SKILL.md`
- Create: `README.md`
- Create: `.env.example`

- [ ] **Step 1: Write the skill**

Include workflow, lead fields, search logic, outreach rules, reply classification, and human handoff criteria.

- [ ] **Step 2: Write setup docs**

Document backend, frontend, test, and demo commands.

### Task 7: Final Verification

- [ ] **Step 1: Run backend tests**

Run: `cd backend && uv run pytest -v`

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`

- [ ] **Step 3: Start backend and frontend dev servers**

Run backend: `cd backend && uv run uvicorn app.main:app --reload --port 8000`

Run frontend: `cd frontend && npm run dev -- --host 0.0.0.0`

