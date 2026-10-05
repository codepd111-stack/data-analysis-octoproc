# OCTOPROC Data Analysis Agent: frontend

Next.js 16 (App Router), React 19, Tailwind 4 and recharts. All data comes from the FastAPI
backend in [`../backend`](../backend); see the [root README](../README.md) for the full picture.

## Run locally

```bash
cp .env.example .env.local   # NEXT_PUBLIC_API_URL, defaults to http://127.0.0.1:8000
npm install
npm run dev                  # http://localhost:3000
```

## Layout

| Path | What it is |
| --- | --- |
| `src/app/` | One folder per page: `login`, `datasets`, `review/[id]`, `chat`, `history`, `insights` |
| `src/components/` | UI grouped by feature (`chat/`, `datasets/`, `semantic/`, `insights/`) plus `layout/` and `ui/` |
| `src/lib/api.ts` | The only place that calls the backend: adds the Bearer token, redirects to `/login` on 401 |
| `src/lib/auth.ts` | Sign-in token storage (`localStorage`, key `octoproc_token`) |
| `src/lib/types.ts` | TypeScript mirrors of the backend's camelCase JSON |

## Notes

- `AGENTS.md` / `CLAUDE.md` are written by `next dev`: this Next.js version differs from older
  ones, so read `node_modules/next/dist/docs/` before changing framework-level code.
- `npm run lint` runs ESLint; there is no frontend test suite yet.
