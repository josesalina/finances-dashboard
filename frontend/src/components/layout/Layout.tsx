import { Outlet, NavLink } from "react-router-dom";

const navItems = [
  { to: "/dashboard",       label: "Dashboard",        icon: "📊" },
  { to: "/dividends",       label: "Dividendos",       icon: "💵" },
  { to: "/semaforos",       label: "Semáforos",        icon: "🚦" },
  { to: "/dividend-config", label: "Config Dividendos", icon: "⚙️" },
  { to: "/pipeline",        label: "Pipeline",         icon: "🔧" },
];

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="px-5 py-5 border-b border-gray-800">
          <p className="text-xs text-gray-500 uppercase tracking-widest">Portfolio</p>
          <h1 className="text-lg font-semibold text-white mt-0.5">Finances</h1>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-green-900/40 text-green-400 font-medium"
                    : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
                }`
              }
            >
              <span>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-5 py-4 border-t border-gray-800">
          <p className="text-xs text-gray-600">Jose Salina</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto bg-gray-950">
        <Outlet />
      </main>
    </div>
  );
}
