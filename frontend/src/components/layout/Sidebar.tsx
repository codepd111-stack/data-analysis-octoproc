"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut } from "lucide-react";
import { navItems } from "./nav";
import { clearToken, getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

export default function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    setSignedIn(getToken() !== null);
  }, []);

  return (
    <div className="flex h-full flex-col bg-white">
      <div className="px-6 py-6">
        <p className="text-xl font-extrabold leading-none tracking-tight">
          <span className="text-octo-red">OCTO</span>
          <span className="text-octo-green">PROC</span>
        </p>
        <p className="mt-1.5 text-xs text-slate-500">Data Analysis Agent</p>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className={cn(
                "relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-octo-green-soft text-octo-green-dark"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              )}
            >
              {active && (
                <span className="absolute bottom-2 left-0 top-2 w-1 rounded-r-full bg-octo-red" />
              )}
              <Icon
                className={cn("h-[18px] w-[18px]", active ? "text-octo-green" : "text-slate-400")}
              />
              {label}
            </Link>
          );
        })}
      </nav>

      {signedIn && (
        <div className="px-3">
          <button
            onClick={() => {
              clearToken();
              window.location.assign("/login");
            }}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
          >
            <LogOut className="h-[18px] w-[18px] text-slate-400" />
            Sign out
          </button>
        </div>
      )}

      <div className="m-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-octo-green" />
          <p className="text-xs font-medium text-slate-700">Free tier · Groq</p>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">
          Your raw data never leaves the server. The model only sees semantics and query results.
        </p>
      </div>
    </div>
  );
}