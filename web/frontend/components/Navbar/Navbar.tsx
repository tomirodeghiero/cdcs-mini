"use client";

import Image from "next/image";

import { GitHubIcon, MoonIcon, SunIcon } from "@/components/icons";
import { API_URL } from "@/lib/api";
import { useTheme } from "@/lib/theme";

export function Navbar() {
  const [theme, toggle] = useTheme();
  const dark = theme === "dark";

  return (
    <header className="border-b border-slate-200/80 bg-white/70 backdrop-blur dark:border-white/5 dark:bg-slate-950/70">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
        <a href="/" className="group flex min-w-0 items-center gap-2 sm:gap-2.5">
          <Image
            src="/cdcs_mini_icon.png"
            alt=""
            width={344}
            height={333}
            priority
            className="h-8 w-8 shrink-0 transition group-hover:scale-105"
          />
          <span className="truncate bg-gradient-to-r from-indigo-700 via-violet-600 to-blue-600 bg-clip-text text-base font-semibold tracking-tight text-transparent dark:from-indigo-200 dark:via-violet-300 dark:to-blue-300">
            CDCS Mini
          </span>
          <span className="hidden sm:inline">
            <VersionBadge>v0.1.0</VersionBadge>
          </span>
        </a>

        <nav className="flex shrink-0 items-center gap-1 text-sm text-slate-600 dark:text-slate-300">
          <span className="hidden sm:contents">
            <NavLink href="/cdcs_mini_tesis_unrc.pdf" external>
              Docs
            </NavLink>
            <NavLink href={`${API_URL}/docs`} external>
              API
            </NavLink>
          </span>
          <a
            href="https://github.com/tomirodeghiero/cdcs-mini"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="GitHub repository"
            className="ml-1 inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 sm:ml-2 sm:px-3 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:shadow-none dark:hover:border-white/20 dark:hover:bg-white/10"
          >
            <GitHubIcon />
            <span className="hidden sm:inline">GitHub</span>
          </a>
          <button
            type="button"
            onClick={toggle}
            aria-label="Toggle theme"
            className="ml-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-slate-300 hover:text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:border-white/20 dark:hover:text-slate-100"
          >
            {dark ? <MoonIcon /> : <SunIcon />}
          </button>
        </nav>
      </div>
    </header>
  );
}

function NavLink({
  href,
  children,
  external = false,
}: {
  href: string;
  children: React.ReactNode;
  external?: boolean;
}) {
  return (
    <a
      href={href}
      target={external ? "_blank" : undefined}
      rel={external ? "noopener noreferrer" : undefined}
      className="rounded-md px-3 py-1.5 transition hover:text-slate-900 dark:hover:text-white"
    >
      {children}
    </a>
  );
}

function VersionBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-500 dark:border-white/10 dark:bg-white/5 dark:text-slate-400">
      {children}
    </span>
  );
}
