import { useEffect } from "react";
import { ChatShell } from "@/components/chat/ChatShell";
import { FaqDrawer } from "@/components/faq/FaqDrawer";
import { useClientIP } from "@/hooks/useClientIP";

const THEME_KEY = "kyc.theme";

function applyTheme(theme: "light" | "dark") {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export default function App() {
  // Boot theme from localStorage with system fallback. The toggle in ChatShell
  // updates localStorage; this just hydrates on first paint.
  useEffect(() => {
    const stored = localStorage.getItem(THEME_KEY) as "light" | "dark" | null;
    const sysDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(stored ?? (sysDark ? "dark" : "light"));
  }, []);

  // Discover the user's public IP early so X-Real-IP is available on every
  // backend call from the very first /session/init. Returned ip is exposed
  // to ChatShell via the same hook (re-read from sessionStorage there).
  useClientIP();

  return (
    <div className="app-canvas h-full">
      <ChatShell />
      <FaqDrawer />
    </div>
  );
}
