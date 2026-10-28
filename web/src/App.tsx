import React from "react";
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
            </Route>

            <Route path="*" element={<Navigate to="/queue" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
