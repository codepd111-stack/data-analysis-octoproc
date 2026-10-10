import { CircleCheck, ShieldCheck, Sparkles } from "lucide-react";
import type { Trust } from "@/lib/types";
import { cn } from "@/lib/utils";

const TRUST: Record<
  Trust,
  { label: string; hint: string; classes: string; Icon: typeof CircleCheck }
> = {
  verified: {
    label: "Verified",
    hint: "A person confirmed this exact calculation before.",
    classes: "bg-octo-green-soft text-octo-green-dark ring-octo-green/30",
    Icon: CircleCheck,
  },
  governed: {
    label: "Governed",
    hint: "Built only from approved metrics, with every default filter applied.",
    classes: "bg-sky-50 text-sky-700 ring-sky-200",
    Icon: ShieldCheck,
  },
  ad_hoc: {
    label: "Ad-hoc",
    hint: "The AI's own calculation. Check the evidence before relying on it.",
    classes: "bg-slate-100 text-slate-600 ring-slate-200",
    Icon: Sparkles,
  },
};

export default function TrustBadge({ trust, size = "sm" }: { trust: Trust; size?: "sm" | "xs" }) {
  const t = TRUST[trust];
  return (
    <span
      title={t.hint}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full font-medium ring-1 ring-inset",
        size === "xs" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
        t.classes
      )}
    >
      <t.Icon className={size === "xs" ? "h-3 w-3" : "h-3.5 w-3.5"} />
      {t.label}
    </span>
  );
}
