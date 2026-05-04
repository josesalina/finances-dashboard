import { Outlet, NavLink } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext";

const navItems = [
  { to: "/dashboard",       label: "Dashboard",        icon: "📊" },
  { to: "/dividends",       label: "Dividendos",       icon: "💵" },
  { to: "/semaforos",       label: "Semáforos",        icon: "🚦" },
  { to: "/dividend-config", label: "Config Dividendos", icon: "⚙️" },
  { to: "/stock-search",    label: "Buscador",         icon: "🔍" },
  { to: "/pipeline",        label: "Pipeline",         icon: "🔧" },
];

export default function Layout() {
  const { theme, toggle } = useTheme();

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col">
        <div className="px-5 py-5 border-b border-gray-200 dark:border-gray-800">
          <p className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-widest">Portfolio</p>
          <h1 className="text-lg font-semibold text-gray-900 dark:text-white mt-0.5">Finances</h1>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-green-900/40 text-green-600 dark:text-green-400 font-medium"
                    : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200"
                }`
              }
            >
              <span>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-5 py-4 border-t border-gray-200 dark:border-gray-800">
          <p className="text-xs text-gray-400 dark:text-gray-600">Jose Salina</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-white dark:bg-gray-950 relative">
        {/* Theme toggle — top-right */}
        <button
          onClick={toggle}
          className="fixed top-4 right-4 z-50 p-2 rounded-lg bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors shadow-sm"
          title={theme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
        >
          {theme === "dark" ? "☀️" : "🌙"}
        </button>
        <Outlet />
      </main>
    </div>
  );
}
