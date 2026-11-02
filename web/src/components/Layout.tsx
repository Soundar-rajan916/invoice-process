import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  Inbox,
  LayoutDashboard,
  ListOrdered,
  LogOut,
  ShieldCheck,
  Building2,
  FileSpreadsheet,
  AlertTriangle,
  Scale,
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
    if (location.pathname === "/admin") return "Master Data";
    if (location.pathname === "/admin/dead-letters") return "Dead Letters";
    if (location.pathname === "/admin/reconciliation") return "Reconciliation";
    return "Workspace";
  };

  const userInitials = user?.email ? user.email.slice(0, 2).toUpperCase() : "AD";
  const userDisplayName = user?.email ? user.email.split("@")[0] : "Reviewer";

  return (
    <div
      className="min-h-screen flex font-sans antialiased"
      style={{
        backgroundColor: "var(--bg-app)",
        color: "var(--text)",
      }}
    >
      {/* Fixed Left Sidebar (240px wide) on --bg-card */}
      <aside
        className="w-60 shrink-0 border-r flex flex-col justify-between p-4 select-none min-h-screen sticky top-0 h-screen overflow-y-auto"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        <div className="space-y-6">
          {/* Brand Logo Header: rounded square in --ink with white glyph */}
          <Link to="/queue" className="flex items-center space-x-2.5 px-2 pt-1">
            <div
              className="h-8 w-8 rounded-[10px] flex items-center justify-center shadow-xs"
              style={{
                backgroundColor: "var(--ink)",
                color: "#FFFFFF",
              }}
            >
              <FileSpreadsheet className="h-4 w-4 stroke-[2.2]" />
            </div>
            <span className="font-semibold text-lg tracking-tight" style={{ color: "var(--text)" }}>
              InvoiceFlow
            </span>
          </Link>

          {/* Navigation Groups */}
          <div className="space-y-5">
            {/* Group 1: WORKSPACE */}
            <div className="space-y-1">
              <div
                className="px-3 text-[11px] font-semibold uppercase tracking-wider mb-1.5"
                style={{ color: "var(--text-muted)" }}
              >
                Workspace
              </div>

              <NavLink
                to="/queue"
                className={({ isActive }) =>
                  `flex items-center justify-between px-3 py-2 rounded-[10px] text-sm font-medium transition-all ${
                    isActive
                      ? "shadow-2xs font-semibold"
                      : "hover:bg-white/60"
                  }`
                }
                style={({ isActive }) => ({
                  backgroundColor: isActive ? "var(--bg-inset)" : "transparent",
                  color: isActive ? "var(--text)" : "var(--text-secondary)",
                  border: isActive ? "1px solid var(--border)" : "1px solid transparent",
                })}
              >
                {({ isActive }) => (
                  <div className="flex items-center space-x-2.5">
                    {isActive ? (
                      <div
                        className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 shadow-2xs"
                        style={{
                          backgroundColor: "var(--accent)",
                          color: "var(--ink)",
                        }}
                      >
                        <ListOrdered className="h-3 w-3 stroke-[2.5]" />
                      </div>
                    ) : (
                      <ListOrdered className="h-[18px] w-[18px] shrink-0" style={{ color: "var(--text-muted)" }} />
                    )}
                    <span>Review Queue</span>
                  </div>
                )}
              </NavLink>

              <NavLink
                to="/inbox"
                className={({ isActive }) =>
                  `flex items-center justify-between px-3 py-2 rounded-[10px] text-sm font-medium transition-all ${
                    isActive
                      ? "shadow-2xs font-semibold"
                      : "hover:bg-white/60"
                  }`
                }
                style={({ isActive }) => ({
                  backgroundColor: isActive ? "var(--bg-inset)" : "transparent",
                  color: isActive ? "var(--text)" : "var(--text-secondary)",
                  border: isActive ? "1px solid var(--border)" : "1px solid transparent",
                })}
              >
                {({ isActive }) => (
                  <div className="flex items-center space-x-2.5">
                    {isActive ? (
                      <div
                        className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 shadow-2xs"
                        style={{
                          backgroundColor: "var(--accent)",
                          color: "var(--ink)",
                        }}
                      >
                        <Inbox className="h-3 w-3 stroke-[2.5]" />
                      </div>
                    ) : (
                      <Inbox className="h-[18px] w-[18px] shrink-0" style={{ color: "var(--text-muted)" }} />
                    )}
                    <span>Inbox</span>
                  </div>
                )}
              </NavLink>
            </div>

            {/* Group 2: OPERATIONS */}
            <div className="space-y-1">
              <div
                className="px-3 text-[11px] font-semibold uppercase tracking-wider mb-1.5"
                style={{ color: "var(--text-muted)" }}
              >
                Operations
              </div>

              <NavLink
                to="/dashboard"
                className={({ isActive }) =>
                  `flex items-center justify-between px-3 py-2 rounded-[10px] text-sm font-medium transition-all ${
                    isActive
                      ? "shadow-2xs font-semibold"
                      : "hover:bg-white/60"
                  }`
                }
                style={({ isActive }) => ({
                  backgroundColor: isActive ? "var(--bg-inset)" : "transparent",
                  color: isActive ? "var(--text)" : "var(--text-secondary)",
                  border: isActive ? "1px solid var(--border)" : "1px solid transparent",
                })}
              >
                {({ isActive }) => (
                  <div className="flex items-center space-x-2.5">
                    {isActive ? (
                      <div
                        className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 shadow-2xs"
                        style={{
                          backgroundColor: "var(--accent)",
                          color: "var(--ink)",
                        }}
                      >
                        <LayoutDashboard className="h-3 w-3 stroke-[2.5]" />
                      </div>
                    ) : (
                      <LayoutDashboard className="h-[18px] w-[18px] shrink-0" style={{ color: "var(--text-muted)" }} />
                    )}
                    <span>Dashboard</span>
                  </div>
                )}
              </NavLink>

              {user?.role === "admin" && (
                <>
                  <NavLink
                    to="/admin"
                    end
                    className={({ isActive }) =>
                      `flex items-center justify-between px-3 py-2 rounded-[10px] text-sm font-medium transition-all ${
                        isActive
                          ? "shadow-2xs font-semibold"
                          : "hover:bg-white/60"
                      }`
                    }
                    style={({ isActive }) => ({
                      backgroundColor: isActive ? "var(--bg-inset)" : "transparent",
                      color: isActive ? "var(--text)" : "var(--text-secondary)",
                      border: isActive ? "1px solid var(--border)" : "1px solid transparent",
                    })}
                  >
                    {({ isActive }) => (
                      <div className="flex items-center space-x-2.5">
                        {isActive ? (
                          <div
                            className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 shadow-2xs"
                            style={{
                              backgroundColor: "var(--accent)",
                              color: "var(--ink)",
                            }}
                          >
                            <ShieldCheck className="h-3 w-3 stroke-[2.5]" />
                          </div>
                        ) : (
                          <ShieldCheck className="h-[18px] w-[18px] shrink-0" style={{ color: "var(--text-muted)" }} />
                        )}
                        <span>Master Data</span>
                      </div>
                    )}
                  </NavLink>

                  <NavLink
                    to="/admin/dead-letters"
                    className={({ isActive }) =>
                      `flex items-center justify-between px-3 py-2 rounded-[10px] text-sm font-medium transition-all ${
                        isActive
                          ? "shadow-2xs font-semibold"
                          : "hover:bg-white/60"
                      }`
                    }
                    style={({ isActive }) => ({
                      backgroundColor: isActive ? "var(--bg-inset)" : "transparent",
                      color: isActive ? "var(--text)" : "var(--text-secondary)",
                      border: isActive ? "1px solid var(--border)" : "1px solid transparent",
                    })}
                  >
                    {({ isActive }) => (
                      <div className="flex items-center space-x-2.5">
                        {isActive ? (
                          <div
                            className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 shadow-2xs"
                            style={{
                              backgroundColor: "var(--danger)",
                              color: "var(--ink)",
                            }}
                          >
                            <AlertTriangle className="h-3 w-3 stroke-[2.5]" />
                          </div>
                        ) : (
                          <AlertTriangle className="h-[18px] w-[18px] shrink-0" style={{ color: "var(--text-muted)" }} />
                        )}
                        <span>Dead Letters</span>
                      </div>
                    )}
                  </NavLink>

                  <NavLink
                    to="/admin/reconciliation"
                    className={({ isActive }) =>
                      `flex items-center justify-between px-3 py-2 rounded-[10px] text-sm font-medium transition-all ${
                        isActive
                          ? "shadow-2xs font-semibold"
                          : "hover:bg-white/60"
                      }`
                    }
                    style={({ isActive }) => ({
                      backgroundColor: isActive ? "var(--bg-inset)" : "transparent",
                      color: isActive ? "var(--text)" : "var(--text-secondary)",
                      border: isActive ? "1px solid var(--border)" : "1px solid transparent",
                    })}
                  >
                    {({ isActive }) => (
                      <div className="flex items-center space-x-2.5">
                        {isActive ? (
                          <div
                            className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 shadow-2xs"
                            style={{
                              backgroundColor: "var(--warning)",
                              color: "var(--ink)",
                            }}
                          >
                            <Scale className="h-3 w-3 stroke-[2.5]" />
                          </div>
                        ) : (
                          <Scale className="h-[18px] w-[18px] shrink-0" style={{ color: "var(--text-muted)" }} />
                        )}
                        <span>Reconciliation</span>
                      </div>
                    )}
                  </NavLink>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar Footer: User Card and Logout */}
        <div
          className="pt-4 border-t space-y-2.5"
          style={{ borderColor: "var(--border)" }}
        >
          {/* User Card */}
          <div
            className="border rounded-2xl p-3 flex items-center justify-between shadow-xs hover:shadow-sm transition-all"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
            }}
          >
            <div className="flex items-center space-x-3 min-w-0">
              <div
                className="h-9 w-9 rounded-full flex items-center justify-center font-bold text-xs shrink-0 shadow-[0_2px_8px_rgba(155,161,249,0.35)]"
                style={{
                  backgroundColor: "var(--accent)",
                  color: "var(--ink)",
                }}
              >
                {userInitials}
              </div>
              <div className="min-w-0 text-left">
                <div className="text-xs font-bold truncate" style={{ color: "var(--text)" }}>
                  {userDisplayName}
                </div>
                <div className="text-[11px] font-medium truncate mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {user?.role === "admin" ? "Administrator" : "Reviewer"}
                </div>
              </div>
            </div>
          </div>

          {/* Logout Action */}
          <button
            onClick={() => logout()}
            className="flex items-center space-x-2.5 px-3 py-2 rounded-xl text-xs font-semibold w-full transition-all cursor-pointer border border-transparent"
            style={{ color: "var(--text-muted)" }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = "var(--danger-soft)";
              e.currentTarget.style.color = "var(--danger-strong)";
              e.currentTarget.style.borderColor = "rgba(254, 130, 135, 0.25)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "transparent";
              e.currentTarget.style.color = "var(--text-muted)";
              e.currentTarget.style.borderColor = "transparent";
            }}
            title="Log out"
          >
            <LogOut className="h-4 w-4 stroke-[2.2]" />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      {/* Main Viewport Content Area on --bg-app */}
      <div
        className="flex-1 min-w-0 flex flex-col min-h-screen"
        style={{ backgroundColor: "var(--bg-app)" }}
      >
        {/* Top Header / Breadcrumbs Bar on --bg-card */}
        <header
          className="px-6 sm:px-8 py-3.5 border-b flex items-center justify-between shrink-0"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          {/* Breadcrumb */}
          <div className="flex items-center space-x-2 text-xs">
            <span style={{ color: "var(--text-muted)" }}>InvoiceFlow</span>
            <span style={{ color: "var(--text-muted)", opacity: 0.6 }}>/</span>
            <span className="font-semibold" style={{ color: "var(--text)" }}>{getPageTitle()}</span>
          </div>

          {/* Right Workspace Chip */}
          <div className="flex items-center space-x-3 text-xs" style={{ color: "var(--text-muted)" }}>
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
