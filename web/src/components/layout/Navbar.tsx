"use client";
import { useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { ThemeToggle } from "./ThemeToggle";
import { cn } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const NAV_LINKS = [
  { href: "/",                  label: "Dashboard"    },
  { href: "/review",            label: "Code Review"  },
  { href: "/merge",             label: "Merge Review" },
  { href: "/history",           label: "History"      },
  { href: "/settings?tab=info", label: "Info"         },
  { href: "/settings",          label: "Settings"     },
];

function NavbarInner() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [userId, setUserId] = useState("anon");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setUserId(localStorage.getItem("jessie_user_id") ?? "anon");
  }, []);

  const { data: req } = useQuery({
    queryKey: ["request-count", userId],
    queryFn:  () => api.getRequestCount(userId),
    refetchInterval: 30_000,
    retry: false,
    enabled: mounted,
  });

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    if (href.startsWith("/settings")) {
      const tab = searchParams.get("tab");
      if (href.includes("tab=info")) return pathname === "/settings" && tab === "info";
      return pathname === "/settings" && tab !== "info";
    }
    return pathname.startsWith(href);
  }

  return (
    <header className="sticky top-0 z-40 border-b bg-white/80 dark:bg-gray-900/80 backdrop-blur supports-[backdrop-filter]:bg-white/60">
      <div className="flex items-center h-14 px-4 gap-6 max-w-screen-2xl mx-auto">
        <Link href="/" prefetch className="flex items-center gap-2 font-bold text-indigo-600 dark:text-indigo-400 shrink-0">
          <span className="text-lg">✦</span>
          <span>Jessie AI</span>
        </Link>

        <nav className="hidden md:flex items-center gap-1">
          {NAV_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              prefetch
              className={cn(
                "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                isActive(href)
                  ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300"
                  : "text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800",
              )}
            >
              {label}
            </Link>
          ))}
        </nav>

        <div className="flex-1" />

        <div className="flex items-center gap-3">
          {req && (
            <span className="hidden sm:block text-xs text-gray-500 dark:text-gray-400">
              {req.requests_today} reqs today
            </span>
          )}
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300" suppressHydrationWarning>
            {userId}
          </span>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

export function Navbar() {
  return (
    <Suspense fallback={<header className="h-14 border-b" />}>
      <NavbarInner />
    </Suspense>
  );
}
