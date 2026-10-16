import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { Activity, Inbox, Moon, Plus, Sun } from "lucide-react";
import { HealthBar, useHealth } from "./components/HealthBar";
import { LinkButton } from "./components/ui/button";
import { cn } from "./components/ui/cn";
import { RunsPage } from "./pages/RunsPage";
import { RunPage } from "./pages/RunPage";
import { ReviewPage } from "./pages/ReviewPage";
import { NewRunPage } from "./pages/NewRunPage";
import { DiagnosticsPage } from "./pages/DiagnosticsPage";

function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", dark);
    root.classList.toggle("light", !dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* private mode */
    }
  }, [dark]);
  return (
    <button
      onClick={() => setDark((d) => !d)}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="rounded-md p-2 text-muted hover:bg-surface-2 hover:text-text"
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}

const NAV = [
  { to: "/", label: "Runs", icon: Inbox, end: true },
  { to: "/new", label: "New RFQ", icon: Plus, end: false },
  { to: "/diagnostics", label: "Diagnostics", icon: Activity, end: false },
];

export function App() {
  const health = useHealth();
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border bg-navy px-4 text-white">
        <Link to="/" className="flex items-baseline gap-2">
          <span className="text-lg font-bold tracking-wide">FERGUSON</span>
          <span className="text-sm text-[#b2c7d2]">AutoRFQ</span>
        </Link>
        <div className="ml-auto flex items-center gap-3 [&_span]:border-white/20 [&_.text-muted]:text-[#b2c7d2]">
          <HealthBar health={health} />
        </div>
        <div className="flex items-center gap-2 [&_button]:text-[#e6ecf0]">
          <ThemeToggle />
          <LinkButton href="/new" variant="primary" size="sm" className="!bg-[#00a0dd] !text-[#00263b] hover:!bg-[#33b3e4]">
            <Plus size={16} aria-hidden /> New RFQ
          </LinkButton>
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Main" className="hidden w-48 shrink-0 border-r border-border bg-surface p-3 md:block">
          <ul className="space-y-1">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium",
                      isActive ? "bg-surface-2 text-text" : "text-muted hover:bg-surface-2 hover:text-text",
                    )
                  }
                >
                  <Icon size={16} aria-hidden /> {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl p-4 md:p-6">
            <Routes>
              <Route path="/" element={<RunsPage />} />
              <Route path="/runs/:id" element={<RunPage />} />
              <Route path="/runs/:id/review" element={<ReviewPage />} />
              <Route path="/new" element={<NewRunPage health={health} />} />
              <Route path="/diagnostics" element={<DiagnosticsPage health={health} />} />
              <Route path="*" element={<p className="text-muted">Page not found.</p>} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}
