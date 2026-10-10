# OCTOPROC Data Analysis Agent

Chat with your spreadsheets. Upload CSV, Excel or Parquet files, review the AI-drafted
description of the data, then ask questions in plain language and get answers with charts.

```
upload files ──> profile + Parquet ──> AI drafts semantic layer ──> you review & approve
                                       (meanings, metrics, filters)         │
   answer + chart <── LLM narrates <── graded for trust <── DuckDB runs SQL <── LLM writes SQL <┘
   + trust badge                       (verified / governed / ad-hoc)                      (chat)
   + evidence
```

- **Backend** ([`backend/`](backend/)): FastAPI, SQLAlchemy + Alembic on Postgres (Neon),
  DuckDB for queries, sqlglot for SQL validation, Groq (`openai/gpt-oss-*`) as the LLM, files on
  local disk or any S3-compatible bucket.
- **Frontend** ([`frontend/`](frontend/)): Vite, React 19, React Router 7, Tailwind 4, recharts
  (the same stack as the MRO platform frontend).

## Run locally

Prerequisites: Python 3.13, Node 20+, a Postgres database (Neon works; SQLite also works for a
quick look: `DATABASE_URL=sqlite:///./dev.db`), a [Groq](https://console.groq.com) API key.

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                                  # fill in DATABASE_URL and GROQ_API_KEY
alembic upgrade head
uvicorn app.main:app --reload                         # http://127.0.0.1:8000/docs

# frontend (second terminal)
cd frontend
cp .env.example .env.local
npm install && npm run dev                            # http://localhost:3000
```

With `ACCESS_CODE` empty, sign-in is off; the backend logs a warning to make that obvious.

## Tests

```bash
cd backend
pytest
```

The suite runs against a temporary SQLite file and local storage, with the AI stubbed out,
so it needs no network or keys. It covers the SQL validator and DuckDB sandbox, chart building,
sign-in tokens and throttling, ingestion (column cleaning, dates, Excel sheets), semantic layer
generation and merging of model output, governed definitions (validation and the check against
the data), grounding and trust badges, the chat pipeline with a scripted model (the default-filter
guardrail, the verified short-circuit), the thumbs-up → verified library → reuse flow over the
API, and the upload → review flow end to end.

The scripts next to it (`test_engine.py`, `test_storage.py`, `check_db.py`, `make_*.py`) are
manual helpers that talk to your real configuration; they are not part of the suite.

## Configuration

All backend settings are environment variables, documented in
[`backend/.env.example`](backend/.env.example). The ones that matter most:

| Variable | Notes |
| --- | --- |
| `DATABASE_URL` | Required. For Neon use the pooled `postgresql+psycopg://...` string. |
| `GROQ_API_KEY` | Without it, datasets still ingest with heuristic descriptions; chat does not work. |
| `STORAGE_BACKEND` | `local` for development. **Production must use `s3`**: Render's disk is wiped on every deploy. |
| `S3_*` | Endpoint, bucket and credentials for Supabase Storage, Cloudflare R2, Backblaze B2 or AWS S3. |
| `CORS_ORIGINS` | Comma-separated frontend origins. |
| `ACCESS_CODE` / `AUTH_SECRET` | The shared sign-in code and the key that signs session tokens (16+ random chars). |
| `TRUST_PROXY_HEADERS` | `true` only behind a reverse proxy such as Render, so the login throttle sees real client IPs. |

Frontend: `VITE_API_BASE_URL` in [`frontend/.env.example`](frontend/.env.example).

## Deploy

- **API on Render**: [`render.yaml`](render.yaml) is a Blueprint for the Docker service. Create
  it from the Render dashboard ("New → Blueprint"), then fill in the `sync: false` secrets.
  The container runs `alembic upgrade head` on every start, so schema changes ship with the code.
- **Database on Neon**: create a project, copy the pooled connection string into `DATABASE_URL`.
- **Files**: create a bucket on any S3-compatible provider and set the `S3_*` variables.
- **Frontend on Vercel** (or similar): import `frontend/` (its `vercel.json` selects the Vite
  preset and the SPA rewrite), set `VITE_API_BASE_URL` to the Render URL, and add the Vercel
  URL to the API's `CORS_ORIGINS`.

Cold starts: Neon scales to zero and Render's free tier sleeps, so the frontend shows a
"waking up the server" banner and polls `/api/health` for up to 90 seconds.

## How it works

**Ingestion** (`backend/app/services/ingestion.py`) runs as a FastAPI background task:
cleans column names to `snake_case`, parses date-like columns, writes one Parquet file per
table (Excel sheets become tables), profiles each column, builds a heuristic semantic layer
(roles, relationships from shared key columns) and asks the LLM to improve descriptions and to
draft **governed definitions**: metrics (`Revenue = SUM(amount)`), default filters
(`status <> 'test'`) and business rules. Suggested definitions survive only if they parse, refer
to real columns of one table and (for metrics) aggregate; the reviewer edits the rest.
Columns with sensitive-sounding names (email, phone, salary, ...) never have sample values
stored or sent to the model. The job runs inside the API process, so if the server restarts
mid-way the dataset is marked failed with a clear message and a **Retry** button.

**Semantic layer** (`semantic_generator.py`, `semantic_store.py`, `definitions.py`) is
versioned: every edit saves a new version, approval is per version, and chat uses the latest
approved one. A layer with a broken metric or filter cannot be saved or approved (the API
answers 422/409 naming the problem), and `POST .../semantic/check` runs every definition
against the data so the reviewer sees real numbers ("Revenue: 1,234,567", "keeps 980 of 1,000
rows") before approving.

**Chat** (`chat_orchestrator.py`) is a fixed text-to-SQL pipeline, not a tool-using agent:

1. A fresh question that a person already verified (see below) is answered from the stored SQL
   without calling the model, unless a default filter was added since.
2. Otherwise the main model returns `{answerable, sql, chart, assumptions, skipped_filters}`
   as JSON, given the schema with its governed metrics, default filters and rules, up to three
   similar verified examples, the last three turns and today's date.
3. `validate_select` accepts exactly one `SELECT`/`UNION` over known tables, rejects table
   functions and adds a `LIMIT`. `run_query` loads only the needed Parquet tables into an
   in-memory DuckDB, disables external access, and enforces a 15 second timeout.
4. A failing query is fed back to the model for up to two more attempts; zero rows trigger one
   "loosen the filters" retry; a default filter left out without the user asking is sent back
   once (if it is still missing, the answer is kept but flagged).
5. `grounding.py` grades the answer structurally (sqlglot, never the model's say-so): which
   governed metrics the SQL really uses, which default filters are applied, skipped or missing,
   and which aggregates are not governed. That gives the **trust badge**: *verified* (matches a
   confirmed calculation), *governed* (only governed metrics, every default filter applied) or
   *ad-hoc* (anything else), plus the evidence shown under every answer: the reason, definitions
   used, tables read, the first rows and the SQL.
6. The fast model turns the rows into prose; `chart_builder` turns them into a bar, line or pie
   spec for recharts.
7. Rate limits surface as HTTP 429 with `Retry-After`.

**Verified answers** (`verified_store.py`): a thumbs-up on an answer saves its question and SQL
for the dataset; taking the thumbs-up back removes it, and the review page lists and retires
them. Entries are reused as worked examples for similar questions and, when a fresh chat asks
the same question, answered directly. A thumbs-up on a follow-up question is kept as an example
only, since its SQL depends on the earlier turns.

Every attempt is written to `query_logs` with its trust badge, which powers the **Insights**
page (failures, retries, thumbs up/down, share of governed or verified answers, an "Ad-hoc
answers" filter that shows where definitions are missing, CSV export).

**Sign-in** is a single shared access code. Login returns an HMAC-signed token that the frontend
keeps in `localStorage`; every other route requires it as a Bearer header. Failed logins are
throttled per client IP (8 per 5 minutes, in memory).

## Known limitations

- One shared access code; no per-user accounts, so all datasets and chats are visible to anyone
  who signs in.
- Ingestion is in-process. Uploads are capped at `MAX_UPLOAD_MB` and read fully into memory;
  each query loads the whole Parquet table into DuckDB before running.
- The login throttle is per process; run a single uvicorn worker (the default).
- No frontend tests yet; `npm run lint` is the only check there.
