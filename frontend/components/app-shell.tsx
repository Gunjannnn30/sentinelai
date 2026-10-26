"use client";

// Sidebar + top bar shell. Client component: nav highlighting and the auth
// gate both need interactivity.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/hooks/use-auth";
import { SystemStatus } from "@/components/system-status";
import { ThemeToggle } from "@/components/theme-toggle";
import { Skeleton } from "@/components/ui/skeleton";
import { canAdmin, canWrite } from "@/lib/role";

interface NavItem {
  href: string;
  label: string;
  /** Minimum role required to see the entry. */
  min?: "developer" | "admin";
}

const NAV: NavItem[] = [
  { href: "/", label: "Overview" },
  { href: "/playground", label: "Playground" },
  { href: "/requests", label: "Requests" },
  { href: "/policies", label: "Policies", min: "developer" },
  { href: "/models", label: "Models", min: "developer" },
  { href: "/providers", label: "Providers", min: "developer" },
  { href: "/analytics", label: "Analytics" },
  { href: "/evaluations", label: "Evaluations" },
  { href: "/audit", label: "Audit", min: "developer" },
  { href: "/settings", label: "Settings", min: "admin" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { me, loading, logout } = useAuth();

  useEffect(() => {
    if (!loading && !me) router.replace("/login");
  }, [loading, me, router]);

  if (loading) {
    return (
      <div className="flex h-screen">
        <aside className="w-56 border-r p-4">
          <Skeleton className="mb-6 h-6 w-32" />
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="mb-2 h-8 w-full" />
          ))}
        </aside>
        <main className="flex-1 p-8">
          <Skeleton className="mb-4 h-8 w-64" />
          <Skeleton className="h-96 w-full" />
        </main>
      </div>
    );
  }

  if (!me) return null;

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="w-full shrink-0 border-b bg-card md:min-h-screen md:w-56 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between p-4">
          <Link href="/" className="text-lg font-bold tracking-tight">
            Sentinel<span className="text-primary">AI</span>
          </Link>
          <div className="md:hidden">
            <SystemStatus />
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto p-2 md:flex-col md:overflow-visible">
          {NAV.filter(
            (item) =>
              !item.min ||
              (item.min === "admin" ? canAdmin(me.role) : canWrite(me.role)),
          ).map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive(pathname, item.href) ? "page" : undefined}
              className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive(pathname, item.href)
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b bg-card px-4 py-3 md:px-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-muted px-3 py-1 text-sm font-medium">
              {me.org.name}
            </span>
            <span className="hidden text-xs uppercase tracking-wide text-muted-foreground sm:inline">
              {me.role}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="hidden md:inline">
              <SystemStatus />
            </span>
            <ThemeToggle />
            <details className="relative">
              <summary className="inline-flex cursor-pointer list-none items-center gap-2 rounded-md border border-input px-3 py-1.5 text-sm hover:bg-accent">
                {me.user.full_name || me.user.email}
              </summary>
              <div className="absolute right-0 z-40 mt-1 w-48 rounded-md border bg-background p-1 shadow-lg">
                <div className="px-3 py-2 text-xs text-muted-foreground">
                  {me.user.email}
                </div>
                <button
                  type="button"
                  onClick={() => void logout()}
                  className="w-full rounded-sm px-3 py-2 text-left text-sm hover:bg-accent"
                >
                  Sign out
                </button>
              </div>
            </details>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
}
