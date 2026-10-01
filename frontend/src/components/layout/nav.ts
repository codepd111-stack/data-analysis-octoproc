import {
  Activity,
  Database,
  History,
  MessageSquare,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export const navItems: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/review", label: "Semantic Review", icon: ShieldCheck },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/history", label: "History", icon: History },
  { href: "/insights", label: "Insights", icon: Activity },
];