import React, { Component, ErrorInfo, ReactNode } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Layout } from "@/components/Layout";
import { Login } from "@/pages/Login";
import { Inbox } from "@/pages/Inbox";
import { ReviewQueue } from "@/pages/ReviewQueue";
import { ReviewDetail } from "@/pages/ReviewDetail";
import { Dashboard } from "@/pages/Dashboard";
import { Admin } from "@/pages/Admin";
import { DeadLetters } from "@/pages/DeadLetters";
import { Reconciliation } from "@/pages/Reconciliation";

class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error: Error | null }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
          <div className="max-w-md w-full bg-white rounded-2xl shadow-xl border border-red-200 p-6 text-center space-y-4">
            <div className="inline-flex p-3 rounded-full bg-red-100 text-red-600 font-bold text-xl">⚠️</div>
            <h2 className="text-lg font-bold text-slate-900">Something went wrong</h2>
            <p className="text-xs text-red-600 font-mono bg-red-50 p-3 rounded-lg overflow-x-auto text-left">
              {this.state.error?.message || "An unexpected error occurred"}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  this.setState({ hasError: false, error: null });
                  window.location.href = "/queue";
                }}
                className="flex-1 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs rounded-lg transition"
              >
                Return to Queue
              </button>
              <button
                onClick={() => {
                  this.setState({ hasError: false, error: null });
                  window.location.reload();
                }}
                className="flex-1 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs rounded-lg transition"
              >
                Reload Page
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-500">
        Loading session...
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="p-8 text-center text-slate-500">Loading session...</div>;
  }

  if (!user || user.role !== "admin") {
    return <Navigate to="/queue" replace />;
  }

  return <>{children}</>;
}

export function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />

              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route index element={<Navigate to="/queue" replace />} />
                <Route path="inbox" element={<Inbox />} />
                <Route path="queue" element={<ReviewQueue />} />
                <Route path="invoices/:id" element={<ReviewDetail />} />
                <Route path="dashboard" element={<Dashboard />} />
                <Route
                  path="admin"
                  element={
                    <AdminRoute>
                      <Admin />
                    </AdminRoute>
                  }
                />
                <Route
                  path="admin/dead-letters"
                  element={
                    <AdminRoute>
                      <DeadLetters />
                    </AdminRoute>
                  }
                />
                <Route
                  path="admin/reconciliation"
                  element={
                    <AdminRoute>
                      <Reconciliation />
                    </AdminRoute>
                  }
                />
              </Route>

              <Route path="*" element={<Navigate to="/queue" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
