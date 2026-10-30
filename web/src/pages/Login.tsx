import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Lock, Mail, AlertCircle, ArrowRight, FileSpreadsheet } from "lucide-react";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
      setError(err.message || "Failed to log in. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 font-sans"
      style={{ backgroundColor: "var(--bg-app)" }}
    >
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <div
            className="h-12 w-12 rounded-[14px] flex items-center justify-center shadow-xs"
            style={{
              backgroundColor: "var(--ink)",
              color: "#FFFFFF",
            }}
          >
            <FileSpreadsheet className="h-6 w-6 stroke-[2.2]" />
          </div>
        </div>
        <h2
          aria-label="Sign in to your account"
          className="mt-5 text-center text-24 font-bold tracking-tight"
          style={{ color: "var(--text)" }}
        >
          Sign in to InvoiceFlow
        </h2>
        <p className="mt-1.5 text-center text-sm" style={{ color: "var(--text-muted)" }}>
          Production AI Invoice Processing & Verification
        </p>
      </div>

      <div className="mt-7 sm:mx-auto sm:w-full sm:max-w-md">
        <div
          className="py-8 px-6 shadow-xs rounded-card sm:px-10 border"
          style={{
            backgroundColor: "var(--bg-inset)",
            borderColor: "var(--border)",
          }}
        >
          {error && (
            <div
              className="mb-6 p-3.5 rounded-btn border flex items-start space-x-3 text-sm"
              style={{
                backgroundColor: "var(--danger-soft)",
                borderColor: "var(--danger)",
                color: "var(--danger-strong)",
              }}
            >
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" style={{ color: "var(--danger-strong)" }} />
              <span>{error}</span>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label
                htmlFor="email"
                className="block text-xs font-semibold uppercase tracking-wide"
                style={{ color: "var(--text)" }}
              >
                Work Email
              </label>
              <div className="mt-1.5 relative rounded-btn">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" style={{ color: "var(--text-muted)" }}>
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
                  className="block w-full pl-9 pr-3 py-2 h-10 border rounded-btn text-sm outline-none transition-all"
                  style={{
                    backgroundColor: "var(--bg-inset)",
                    borderColor: "var(--border)",
                    color: "var(--text)",
                  }}
                  placeholder="reviewer@invoiceflow.internal"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-xs font-semibold uppercase tracking-wide"
                style={{ color: "var(--text)" }}
              >
                Password
              </label>
              <div className="mt-1.5 relative rounded-btn">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none" style={{ color: "var(--text-muted)" }}>
                  <Lock className="h-4 w-4" />
                </div>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full pl-9 pr-3 py-2 h-10 border rounded-btn text-sm outline-none transition-all"
                  style={{
                    backgroundColor: "var(--bg-inset)",
                    borderColor: "var(--border)",
                    color: "var(--text)",
                  }}
                  placeholder="••••••••••••"
                />
              </div>
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center items-center space-x-2 py-2.5 px-4 rounded-btn text-sm font-semibold transition-all cursor-pointer shadow-xs disabled:opacity-50"
                style={{
                  backgroundColor: "var(--ink)",
                  color: "#FFFFFF",
                }}
              >
                <span>{loading ? "Authenticating..." : "Sign in"}</span>
                {!loading && <ArrowRight className="h-4 w-4" />}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
