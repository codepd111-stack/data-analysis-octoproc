# OCTOPROC Data Analysis Agent: frontend

Vite, React 19, React Router 7, Tailwind 4 and recharts, the same stack as the MRO platform
frontend. All data comes from the FastAPI backend in [`../backend`](../backend); see the
[root README](../README.md) for the full picture.

## Run locally

```bash
cp .env.example .env.local   # VITE_API_BASE_URL, defaults to http://127.0.0.1:8000
npm install
npm run dev                  # http://localhost:3000
```

The dev server keeps port 3000 because the backend's default `CORS_ORIGINS` allows that origin.

## Layout

| Path | What it is |
| --- | --- |
| `src/App.tsx` | The route table: `login`, `datasets`, `review`, `review/:id`, `chat`, `history`, `insights` |
| `src/pages/` | One file per route |
| `src/components/` | UI grouped by feature (`chat/`, `datasets/`, `semantic/`, `insights/`) plus `layout/` and `ui/` |
| `src/components/layout/AppShell.tsx` | Layout route (sidebar, mobile drawer, server wake banner) for every page but sign-in |
| `src/lib/api.ts` | The only place that calls the backend: adds the Bearer token, redirects to `/login` on 401 |
| `src/lib/auth.ts` | Sign-in token storage (`localStorage`, key `octoproc_token`) |
| `src/lib/types.ts` | TypeScript mirrors of the backend's camelCase JSON |

## Notes

- `npm run build` type-checks (`tsc -b`) and bundles into `dist/`; `npm run lint` runs oxlint.
  There is no frontend test suite yet.
- `vercel.json` sets the Vite preset and the SPA rewrite so deep links such as `/chat` load on
  refresh. On Vercel, set `VITE_API_BASE_URL` to the Render URL.
