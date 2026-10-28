import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  FileText,
  Inbox,
  LayoutDashboard,
  ListOrdered,
  LogOut,
  ShieldCheck,
  UserCheck,
} from "lucide-react";

export function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col text-slate-900">
      <header className="sticky top-0 z-40 bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-8">
            <Link to="/queue" className="flex items-center space-x-3">
              <div className="h-9 w-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-md">
                <FileText className="h-5 w-5" />
              </div>
              <span className="font-bold text-xl tracking-tight bg-gradient-to-r from-indigo-600 to-indigo-900 bg-clip-text text-transparent">
                InvoiceFlow
              </span>
            </Link>

            <nav className="hidden md:flex space-x-1">
              <NavLink
                to="/inbox"
                className={({ isActive }) =>
                  `flex items-center space-x-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700 font-semibold"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                  }`
                }
              >
                <Inbox className="h-4 w-4" />
                <span>Inbox</span>
              </NavLink>

              <NavLink
                to="/queue"
                className={({ isActive }) =>
                  `flex items-center space-x-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700 font-semibold"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                  }`
                }
              >
                <ListOrdered className="h-4 w-4" />
                <span>Review Queue</span>
              </NavLink>

              <NavLink
                to="/dashboard"
                className={({ isActive }) =>
                  `flex items-center space-x-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700 font-semibold"
                      : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                  }`
                }
              >
                <LayoutDashboard className="h-4 w-4" />
                <span>Dashboard</span>
              </NavLink>

              {user?.role === "admin" && (
                <NavLink
                  to="/admin"
                  className={({ isActive }) =>
                    `flex items-center space-x-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-indigo-50 text-indigo-700 font-semibold"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                    }`
                  }
                >
                  <ShieldCheck className="h-4 w-4" />
                  <span>Admin</span>
                </NavLink>
              )}
            </nav>
          </div>

          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 text-sm text-slate-600 bg-slate-100 px-3 py-1.5 rounded-full border border-slate-200">
              <UserCheck className="h-4 w-4 text-indigo-600" />
              <span className="font-medium text-slate-800">{user?.email}</span>
              <span className="text-xs uppercase px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800 font-semibold">
                {user?.role}
              </span>
            </div>

            <button
              onClick={() => logout()}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 border border-slate-300 rounded-md text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 transition-colors"
              title="Log out"
            >
              <LogOut className="h-4 w-4 text-slate-500" />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 flex flex-col">
        <Outlet />
      </main>
    </div>
  );
}
