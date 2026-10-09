/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Where the browser reaches the FastAPI backend. Set to the Render URL in production;
   *  unset in local dev, it falls back to http://127.0.0.1:8000. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
