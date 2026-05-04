import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "light" | "dark";

interface ThemeCtx {
  theme: Theme;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeCtx>({ theme: "dark", toggle: () => {} });

function getDefaultTheme(): Theme {
  const saved = localStorage.getItem("theme") as Theme | null;
  if (saved) return saved;
  const hour = new Date().getHours();
  return hour >= 7 && hour < 20 ? "light" : "dark";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(getDefaultTheme);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

export function useChartColors() {
  const { theme } = useTheme();
  const dark = theme === "dark";
  return {
    grid:          dark ? "#1f2937" : "#e5e7eb",
    tooltipBg:     dark ? "#111827" : "#ffffff",
    tooltipBorder: dark ? "#374151" : "#d1d5db",
    tick:          dark ? "#6b7280" : "#9ca3af",
    label:         dark ? "#e5e7eb" : "#111827",
    legend:        dark ? "#9ca3af" : "#6b7280",
    svgStroke:     dark ? "#111827" : "#ffffff",
  };
}
