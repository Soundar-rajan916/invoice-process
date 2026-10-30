import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  Inbox,
  LayoutDashboard,
  ListOrdered,
  LogOut,
  ShieldCheck,
  Building2,
  ChevronDown,
  Plus,
} from "lucide-react";

export function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();

  // Clean breadcrumb text based on current route
  const getPageTitle = () => {
    if (location.pathname.startsWith("/invoices/")) return "Invoice Review";
    if (location.pathname === "/queue") return "Review Queue";
    if (location.pathname === "/inbox") return "Inbox";
    if (location.pathname === "/dashboard") return "Dashboard";
    if (location.pathname === "/admin") return "Admin";
    return "Workspace";
  };

  const userInitials = user?.email ? user.email.slice(0, 2).toUpperCase() : "IF";
  const userDisplayName = user?.email ? user.email.split("@")[0] : "Reviewer";

  return (
    <div className="min-h-screen bg-findeck-app flex font-sans antialiased text-findeck-text">
      {/* Fixed Left Sidebar (240px wide) */}
      <aside className="w-60 shrink-0 bg-findeck-sidebar border-r border-findeck flex flex-col justify-between p-4 select-none min-h-screen sticky top-0 h-screen overflow-y-auto">
        <div className="space-y-6">
          {/* Brand Logo Header */}
          <Link to="/queue" className="flex items-center space-x-2.5 px-2 pt-2">
            <div className="h-8 w-8 rounded-[10px] bg-findeck-accent flex items-center justify-center text-white shadow-2xs">
              <Plus className="h-5 w-5 stroke-[3]" />
            </div>
            <span className="font-semibold text-lg tracking-tight text-findeck-text">
              InvoiceFlow
            </span>
          </Link>

          {/* Navigation Groups */}
          <div className="space-y-5">
            {/* Group 1: WORKSPACE */}
            <div className="space-y-1">
              <div className="px-3 text-[11px] font-semibold text-findeck-muted uppercase tracking-wider mb-1.5">
                Workspace
              </div>

              <NavLink
                to="/queue"
                className={({ isActive }) =>
                  `flex items-center justify-between px-3 py-2 rounded-btn text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-white text-findeck-text font-semibold shadow-2xs border border-findeck/50"
                      : "text-findeck-muted hover:text-findeck-text hover:bg-white/50"
                  }`
                }
              >
                <div className="flex items-center space-x-2.5">
                  <ListOrdered className="h-4 w-4" />
                  <span>Review Queue</span>
                </div>
              </NavLink>

              <NavLink
                to="/inbox"
                className={({ isActive }) =>
                  `flex items-center justify-between px-3 py-2 rounded-btn text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-white text-findeck-text font-semibold shadow-2xs border border-findeck/50"
                      : "text-findeck-muted hover:text-findeck-text hover:bg-white/50"
                  }`
                }
              >
                <div className="flex items-center space-x-2.5">
                  <Inbox className="h-4 w-4" />
                  <span>Inbox</span>
                </div>
              </NavLink>
            </div>

            {/* Group 2: OPERATIONS */}
            <div className="space-y-1">
              <div className="px-3 text-[11px] font-semibold text-findeck-muted uppercase tracking-wider mb-1.5">
                Operations
              </div>

              <NavLink
                to="/dashboard"
                className={({ isActive }) =>
                  `flex items-center space-x-2.5 px-3 py-2 rounded-btn text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-white text-findeck-text font-semibold shadow-2xs border border-findeck/50"
                      : "text-findeck-muted hover:text-findeck-text hover:bg-white/50"
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
                    `flex items-center space-x-2.5 px-3 py-2 rounded-btn text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-white text-findeck-text font-semibold shadow-2xs border border-findeck/50"
                        : "text-findeck-muted hover:text-findeck-text hover:bg-white/50"
                    }`
                  }
                >
                  <ShieldCheck className="h-4 w-4" />
                  <span>Admin</span>
                </NavLink>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar Footer: User Card and Logout */}
        <div className="pt-4 border-t border-findeck space-y-2">
          {/* User Card */}
          <div className="bg-white border border-findeck rounded-btn p-2 px-2.5 flex items-center justify-between shadow-2xs">
            <div className="flex items-center space-x-2.5 min-w-0">
              <div className="h-7 w-7 rounded-[8px] bg-findeck-accent text-white flex items-center justify-center font-bold text-xs shrink-0 shadow-2xs">
                {userInitials}
              </div>
              <div className="min-w-0 text-left">
                <div className="text-xs font-semibold text-findeck-text truncate">
                  {userDisplayName}
                </div>
                <div className="text-[10px] text-findeck-muted truncate">
                  {user?.role === "admin" ? "Administrator" : "Reviewer"}
                </div>
              </div>
            </div>
            <ChevronDown className="h-3.5 w-3.5 text-findeck-muted shrink-0" />
          </div>

          {/* Logout Action */}
          <button
            onClick={() => logout()}
            className="flex items-center space-x-2 px-2.5 py-1.5 rounded-btn text-xs font-medium text-findeck-muted hover:text-findeck-danger hover:bg-findeck-danger-soft w-full transition-colors cursor-pointer"
            title="Log out"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      {/* Main Viewport Content Area */}
      <div className="flex-1 min-w-0 flex flex-col bg-findeck-app min-h-screen">
        {/* Top Header / Breadcrumbs Bar */}
        <header className="px-6 sm:px-8 py-3.5 bg-findeck-card border-b border-findeck flex items-center justify-between shrink-0">
          {/* Breadcrumb */}
          <div className="flex items-center space-x-2 text-xs">
            <span className="text-findeck-muted">InvoiceFlow</span>
            <span className="text-findeck-muted/60">/</span>
            <span className="font-semibold text-findeck-text">{getPageTitle()}</span>
          </div>

          {/* Right User Email Chip */}
          <div className="flex items-center space-x-3 text-xs text-findeck-muted">
            <div className="flex items-center space-x-1.5">
              <Building2 className="h-3.5 w-3.5" />
              <span>Accounts Review Workspace</span>
            </div>
          </div>
        </header>

        {/* Dynamic Route Content */}
        <main className="flex-1 min-h-0 p-6 sm:p-8 flex flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
