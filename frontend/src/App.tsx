import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/authStore";
import Layout from "@/components/Layout";

const LoginPage = React.lazy(() => import("@/pages/login/LoginPage"));
const WorkshopListPage = React.lazy(() => import("@/pages/workshop/WorkshopListPage"));
const WorkshopAppPage = React.lazy(() => import("@/pages/workshop/WorkshopAppPage"));
const QueryLibraryPage = React.lazy(() => import("@/pages/queries/QueryLibraryPage"));

class AppErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; message?: string }
> {
  state = { hasError: false, message: "" };
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, message: error.message };
  }
  render() {
    if (this.state.hasError)
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
          <div className="bg-white border rounded-xl p-6 max-w-lg">
            <h2 className="font-semibold">This page could not load</h2>
            <p className="text-sm text-gray-600 mt-2">{this.state.message || "Something went wrong. Reload to try again."}</p>
            <button onClick={() => window.location.reload()} className="wb-button-primary mt-4">Reload</button>
          </div>
        </div>
      );
    return this.props.children;
  }
}

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

// VITE_AUTH_MODE=local_single_user skips sign-in for a one-person local setup.
const LOCAL_SINGLE_USER = import.meta.env.VITE_AUTH_MODE === "local_single_user";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  return LOCAL_SINGLE_USER || token ? <Layout>{children}</Layout> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AppErrorBoundary>
          <React.Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading…</div>}>
            <Routes>
              <Route path="/login" element={LOCAL_SINGLE_USER ? <Navigate to="/apps/workshop" replace /> : <LoginPage />} />
              <Route path="/" element={<Navigate to="/apps/workshop" replace />} />
              <Route path="/apps/workshop" element={<ProtectedRoute><WorkshopListPage /></ProtectedRoute>} />
              <Route path="/apps/workshop/:appId" element={<ProtectedRoute><WorkshopAppPage /></ProtectedRoute>} />
              <Route path="/apps/queries" element={<ProtectedRoute><QueryLibraryPage /></ProtectedRoute>} />
              <Route path="*" element={<Navigate to="/apps/workshop" replace />} />
            </Routes>
          </React.Suspense>
        </AppErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
