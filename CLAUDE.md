# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

CS FaceAttend: a face-recognition class attendance system for a Computer Science department. It has a FastAPI + MySQL/MariaDB backend (`backend/`) and a React 19 + Vite + Tailwind v4 frontend (`frontend/`). UI text, code comments and API error messages (`detail`) are written in Thai. Keep that convention when adding code. `backend/README.md` (Thai) is the main setup doc. The root `README.md` is empty.

## Commands

Backend (run from `backend/`; use Python 3.11/3.12 because numpy/dlib have no wheels for 3.14):
```bash
py -3.12 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
# Optional face recognition. Without it, only face endpoints fail (HTTP 503):
pip install dlib-bin && pip install --no-deps face_recognition==1.3.0
pip install git+https://github.com/ageitgey/face_recognition_models && pip install "setuptools<81"
cp .env.example .env            # set DATABASE_URL, SECRET_KEY
uvicorn main:app --reload       # http://127.0.0.1:8000/docs
python seed.py                  # test accounts: teacher01@example.com / Teach123!, student01@example.com / Passw0rd!
python seed_demo.py             # idempotent demo data for teacher T0001 (enrollments, backfilled sessions, random attendance)
pip install -r requirements-dev.txt    # adds pytest
py -3.12 -m pytest                     # unit tests (attendance rules, score formulas); no MySQL/server needed
py -3.12 -m pytest tests/test_scores.py -k per_session   # single file / filter
python tests/e2e_smoke.py [face.jpg]   # API smoke test vs a live server + seeded DB; creates TEST-* rows and deletes them at the end
```

Frontend (run from `frontend/`):
```bash
npm run dev          # http://localhost:5173 (backend URL from VITE_API_URL, default http://127.0.0.1:8000)
npm run build
npm run lint
npm run test:e2e                         # Playwright; needs MySQL + backend running and seed.py applied
npx playwright test e2e/auth.spec.js     # single file
npx playwright test -g "test name"       # single test
```
Playwright starts vite by itself (or reuses a running one). It uses a fake camera, and workers=2 because bcrypt login is slow. Test accounts live in `frontend/e2e/helpers.js`.

## Backend architecture

- **The database schema belongs to phpMyAdmin, not to the code.** The DB `project_face_ai_db` must already exist. There is no Alembic. `app/models.py` must match the real table columns exactly; a mismatch only shows up at query time. The only schema change the code makes is `ensure_columns()` in `main.py`, which runs on startup and does ad-hoc `ALTER TABLE`s plus creates `class_schedules`. New schema changes go there.
- `app/routers/*` holds one router per resource (`/auth`, `/classes`, `/attendance`, `/face`, `/scores`, ...). All are registered in `main.py`.
- Auth: JWT bearer tokens (`app/security.py`) and dependencies in `app/deps.py`: `get_current_user`, `require_student`, `require_teacher`, and `ensure_course_owner` (only the owning teacher may change a course or its classes). `users` is separate from the `students`/`teachers` profile tables (`user.teacher_profile`). `/auth/login` and `/auth/token` share an in-memory failed-login limiter (`app/rate_limit.py`: per IP+username and per IP, 429 with `Retry-After`). It resets when the server restarts and only works with a single uvicorn process.
- Settings are per class, with no global fallback: check-in open/close offsets, `late_threshold_minutes`, `face_confidence_threshold` and `allow_manual_fallback` all come from the `classes` row. `app/config.py` defaults are fallbacks only.
- `app/attendance_utils.py` holds the core attendance rules:
  - `attendance_details` only has rows for students who checked in or were marked manually. Absent, open and upcoming are *inferred* by `effective_status()` from the check-in window: `[start − open_offset, end_time]`, or `start + close_offset` when there is no end time.
  - `sync_scheduled_sessions()` lazily creates `attendance_sessions` from weekly `class_schedules` for classes that have `started_at` set. It backfills from the start date up to today. Attendance read endpoints call it first, so past days with no activity still count as absent.
- `app/face_service.py`: `face_recognition` is an optional import. Embeddings are stored as JSON text in `face_profiles.embedding`. Distance is turned into a 0–100 confidence score using `face_distance_cutoff`. A face profile needs teacher approval (`face_approvals`) before it can be used for check-in.

## Frontend architecture

- `src/lib/api.js`: the single `api(path, {method, body, auth})` fetch wrapper. It sends JSON, or multipart when `body` is a `FormData`, throws `ApiError` with the Thai `detail`, and on a 401 clears the session and redirects to `/login`. The token and user are stored in localStorage ("remember me") or sessionStorage. `apiObjectUrl` loads images that need auth.
- `src/lib/useApi.js`: `useApi(path, initial)` returns `{data, error, loading, reload}`. Pass `path = null` to skip loading.
- `src/App.jsx`: role-gated routes through `RequireRole`. Student pages are at `/dashboard`, `/checkin`, ...; teacher pages are at `/teacher-*`.
- The teacher side (`components/Teacher/`):
  - Pages are wrapped in `TeacherLayout`.
  - Shared data comes from `useTeacherData()`: `/classes/mine` plus `/attendance/records`, which returns one row per session × student, including inferred statuses.
  - i18n (th/en) is in `translations.js` and covers app text only, not data.
  - Theme, font size and language are stored in localStorage through `useAppearanceSettings`.
  - Score formulas (direct vs perSession modes, late-tier deductions) are in `attendanceScoring.js`, shared by the score and export pages.
  - CSV/XLS/PDF export happens entirely in the frontend.
