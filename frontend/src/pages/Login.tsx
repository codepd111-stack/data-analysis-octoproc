import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LoaderCircle } from "lucide-react";
import ErrorBanner from "@/components/ui/ErrorBanner";
import { api, errorMessage } from "@/lib/api";
import { setToken } from "@/lib/auth";

export default function LoginPage() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Local development has no passcode, so there is nothing to sign in to
    api
      .authStatus()
      .then((s) => {
        if (!s.authRequired) navigate("/datasets", { replace: true });
      })
      .catch(() => {});
  }, [navigate]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(code.trim());
      setToken(res.token);
      navigate("/datasets", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="text-3xl font-extrabold leading-none tracking-tight">
            <span className="text-octo-red">OCTO</span>
            <span className="text-octo-green">PROC</span>
          </p>
          <p className="mt-2 text-sm text-slate-500">Data Analysis Agent</p>
        </div>

        <form
          onSubmit={submit}
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <label htmlFor="code" className="text-sm font-medium text-slate-900">
            Access code
          </label>
          <input
            id="code"
            type="password"
            autoFocus
            autoComplete="current-password"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Enter the access code"
            className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-octo-green focus:outline-none focus:ring-2 focus:ring-octo-green/20"
          />

          {error && (
            <div className="mt-4">
              <ErrorBanner message={error} />
            </div>
          )}

          <button
            type="submit"
            disabled={!code.trim() || busy}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-octo-green px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-octo-green-dark disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy && <LoaderCircle className="h-4 w-4 animate-spin" />}
            {busy ? "Signing in…" : "Sign in"}
          </button>
          {busy && (
            <p className="mt-3 text-center text-xs text-slate-400">
              If the server has been idle, this can take up to a minute.
            </p>
          )}
        </form>
      </div>
    </div>
  );
}