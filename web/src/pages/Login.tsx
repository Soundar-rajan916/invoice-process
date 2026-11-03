import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  Lock,
  Mail,
  AlertCircle,
  ArrowRight,
  FileSpreadsheet,
  CheckCircle2,
  ShieldCheck,
  Eye,
  EyeOff,
  Loader2,
  Building2,
  Sparkles,
  FileCheck,
} from "lucide-react";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate("/queue");
    } catch (err: any) {
      setError(err.message || "Invalid corporate credentials. Please verify your email and password.");
    } finally {
      setLoading(false);
    }
  };

  const handleQuickFill = (demoEmail: string, demoPass: string) => {
    setEmail(demoEmail);
    setPassword(demoPass);
    setError(null);
  };

  return (
    <div
      className="min-h-screen flex flex-col font-sans transition-colors duration-150"
      style={{ backgroundColor: "var(--bg-app)" }}
    >
      {/* Top Header Bar */}
      <header className="w-full px-6 py-4 flex items-center justify-between z-10 max-w-7xl mx-auto">
        <div className="flex items-center space-x-3">
          <div
            className="h-10 w-10 rounded-[12px] flex items-center justify-center shadow-xs"
            style={{
              backgroundColor: "var(--ink)",
              color: "#FFFFFF",
            }}
          >
            <FileSpreadsheet className="h-5 w-5 stroke-[2.2]" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-extrabold text-base tracking-tight" style={{ color: "var(--text)" }}>
                InvoiceFlow
              </span>
              <span
                className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider"
                style={{
                  backgroundColor: "var(--accent-soft)",
                  color: "var(--accent-strong)",
                }}
              >
                Enterprise AP
              </span>
            </div>
            <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              Intelligent Invoice Processing & Verification
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <div
            className="flex items-center space-x-2 px-3 py-1.5 rounded-full border text-xs"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
              color: "var(--text-muted)",
            }}
          >
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-medium hidden sm:inline">Universal Human Gate: Active</span>
            <span className="font-medium sm:hidden">Online</span>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <div className="flex-1 flex items-center justify-center p-4 sm:p-6 lg:p-10">
        <div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-14 items-center">
          
          {/* Left Column: Enterprise Product Showcase (Desktop) */}
          <div className="hidden lg:flex lg:col-span-6 flex-col justify-between space-y-6 pr-4">
            <div className="space-y-4">
              <div
                className="inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-semibold border"
                style={{
                  backgroundColor: "var(--accent-soft)",
                  borderColor: "var(--accent)",
                  color: "var(--accent-strong)",
                }}
              >
                <Sparkles className="h-3.5 w-3.5" />
                <span>Next-Gen Accounts Payable Platform</span>
              </div>

              <h1
                className="text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight"
                style={{ color: "var(--text)" }}
              >
                Automated invoice intake with guaranteed ledger integrity.
              </h1>

              <p className="text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                Continuous AI invoice extraction, real-time GSTIN validation, and the Universal Human Gate ensuring zero ledger discrepancies or duplicate payments.
              </p>
            </div>

            {/* Feature Mini Cards */}
            <div className="space-y-3">
              <div
                className="p-4 rounded-card border shadow-xs flex items-start space-x-3 transition-all"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--border)",
                }}
              >
                <div
                  className="p-2.5 rounded-btn shrink-0"
                  style={{
                    backgroundColor: "var(--accent-soft)",
                    color: "var(--accent-strong)",
                  }}
                >
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-xs font-bold" style={{ color: "var(--text)" }}>
                    Universal Human Gate Verification
                  </h2>
                  <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                    Every extracted field requires authenticated verification by the accounts team before sync to downstream ERP books.
                  </p>
                </div>
              </div>

              <div
                className="p-4 rounded-card border shadow-xs flex items-start space-x-3 transition-all"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--border)",
                }}
              >
                <div
                  className="p-2.5 rounded-btn shrink-0"
                  style={{
                    backgroundColor: "var(--success-soft)",
                    color: "var(--success-strong)",
                  }}
                >
                  <CheckCircle2 className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-xs font-bold" style={{ color: "var(--text)" }}>
                    Continuous Ledger Auditing & Reconciliation
                  </h2>
                  <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                    Automated reconciliation sweeps immediately detect phantom entries, missing confirmations, and balance mismatches.
                  </p>
                </div>
              </div>

              {/* Sample Live Verification Preview Card */}
              <div
                className="p-3.5 rounded-card border shadow-xs flex items-center justify-between"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                }}
              >
                <div className="flex items-center space-x-3">
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
                    style={{
                      backgroundColor: "var(--accent-soft)",
                      color: "var(--accent-strong)",
                    }}
                  >
                    <FileCheck className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-bold flex items-center space-x-2">
                      <span style={{ color: "var(--text)" }}>INV-2026-8492</span>
                      <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>27AAPFU0939F1ZV</span>
                    </div>
                    <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                      Acme Industrial Supplies • ₹1,18,500.00
                    </div>
                  </div>
                </div>
                <span
                  className="text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider"
                  style={{
                    backgroundColor: "var(--success)",
                    color: "var(--ink)",
                  }}
                >
                  Verified
                </span>
              </div>
            </div>

            {/* Compliance & Trust Badges */}
            <div className="pt-2 border-t flex items-center space-x-6 text-xs" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
              <div className="flex items-center space-x-1.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span>GSTIN Validated</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <Lock className="h-4 w-4 text-indigo-600" />
                <span>256-bit TLS Encryption</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <Building2 className="h-4 w-4 text-amber-600" />
                <span>SOC2 Aligned</span>
              </div>
            </div>
          </div>

          {/* Right Column: Sign In Card */}
          <div className="lg:col-span-6 w-full max-w-md mx-auto">
            <div
              className="p-8 sm:p-10 rounded-[20px] border shadow-xs transition-all"
              style={{
                backgroundColor: "var(--bg-inset)",
                borderColor: "var(--border)",
              }}
            >
              {/* Form Header */}
              <div className="mb-6">
                <div
                  className="lg:hidden h-10 w-10 rounded-[12px] flex items-center justify-center shadow-xs mb-4"
                  style={{
                    backgroundColor: "var(--ink)",
                    color: "#FFFFFF",
                  }}
                >
                  <FileSpreadsheet className="h-5 w-5 stroke-[2.2]" />
                </div>
                <h2 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
                  Sign in to workspace
                </h2>
                <p className="text-xs mt-1.5" style={{ color: "var(--text-muted)" }}>
                  Enter your corporate credentials to access the invoice review queue.
                </p>
              </div>

              {/* Error Callout */}
              {error && (
                <div
                  className="mb-5 p-3.5 rounded-btn border flex items-start space-x-3 text-xs leading-relaxed"
                  style={{
                    backgroundColor: "var(--danger-soft)",
                    borderColor: "var(--danger)",
                    color: "var(--danger-strong)",
                  }}
                >
                  <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
              )}

              {/* Form */}
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label
                    htmlFor="email"
                    className="block text-xs font-semibold mb-1.5"
                    style={{ color: "var(--text)" }}
                  >
                    Work Email
                  </label>
                  <div className="relative">
                    <div
                      className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <Mail className="h-4 w-4" />
                    </div>
                    <input
                      id="email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="admin@invoiceflow.local"
                      className="w-full pl-9 pr-3 py-2.5 rounded-btn text-xs outline-none transition-all border"
                      style={{
                        backgroundColor: "var(--bg-card)",
                        borderColor: "var(--border)",
                        color: "var(--text)",
                      }}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "var(--ink)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "var(--border)";
                      }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label
                      htmlFor="password"
                      className="block text-xs font-semibold"
                      style={{ color: "var(--text)" }}
                    >
                      Password
                    </label>
                  </div>
                  <div className="relative">
                    <div
                      className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <Lock className="h-4 w-4" />
                    </div>
                    <input
                      id="password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                      className="w-full pl-9 pr-10 py-2.5 rounded-btn text-xs outline-none transition-all border"
                      style={{
                        backgroundColor: "var(--bg-card)",
                        borderColor: "var(--border)",
                        color: "var(--text)",
                      }}
                      onFocus={(e) => {
                        e.currentTarget.style.borderColor = "var(--ink)";
                      }}
                      onBlur={(e) => {
                        e.currentTarget.style.borderColor = "var(--border)";
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center cursor-pointer transition-colors"
                      style={{ color: "var(--text-muted)" }}
                      title={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                {/* Quick-Fill Helper for Testing & Demo */}
                <div
                  className="p-3 rounded-btn border text-xs flex items-center justify-between"
                  style={{
                    backgroundColor: "var(--bg-card)",
                    borderColor: "var(--border)",
                  }}
                >
                  <div className="space-y-0.5">
                    <span className="font-semibold block text-xs" style={{ color: "var(--text)" }}>
                      Demo Account
                    </span>
                    <span className="text-[11px] block font-mono" style={{ color: "var(--text-muted)" }}>
                      admin@invoiceflow.local
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleQuickFill("admin@invoiceflow.local", "AdminPassword123!")}
                    className="px-2.5 py-1 rounded-btn text-[11px] font-semibold border transition-all cursor-pointer"
                    style={{
                      backgroundColor: "var(--bg-inset)",
                      borderColor: "var(--border)",
                      color: "var(--text)",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = "var(--accent-soft)";
                      e.currentTarget.style.color = "var(--accent-strong)";
                      e.currentTarget.style.borderColor = "var(--accent)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = "var(--bg-inset)";
                      e.currentTarget.style.color = "var(--text)";
                      e.currentTarget.style.borderColor = "var(--border)";
                    }}
                  >
                    Quick Fill
                  </button>
                </div>

                {/* Submit Action */}
                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full flex justify-center items-center space-x-2 py-2.5 px-4 rounded-btn text-xs font-bold transition-all cursor-pointer shadow-xs disabled:opacity-50 select-none"
                    style={{
                      backgroundColor: "var(--ink)",
                      color: "#FFFFFF",
                    }}
                  >
                    {loading ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-1" />
                        <span>Authenticating Session...</span>
                      </>
                    ) : (
                      <>
                        <span>Sign In to Workspace</span>
                        <ArrowRight className="h-4 w-4 ml-1" />
                      </>
                    )}
                  </button>
                </div>
              </form>

              {/* Security Footer Note */}
              <div
                className="mt-6 pt-4 border-t text-center text-[11px] flex items-center justify-center space-x-1.5"
                style={{
                  borderColor: "var(--border)",
                  color: "var(--text-muted)",
                }}
              >
                <Lock className="h-3 w-3" />
                <span>Protected by corporate MFA & session encryption.</span>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
