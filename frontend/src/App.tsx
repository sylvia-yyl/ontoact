import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Layout from "@/components/Layout";

const WorkshopListPage = React.lazy(() => import("@/pages/workshop/WorkshopListPage"));
const WorkshopAppPage = React.lazy(() => import("@/pages/workshop/WorkshopAppPage"));
const QueryLibraryPage = React.lazy(() => import("@/pages/queries/QueryLibraryPage"));
const OntologyOverviewPage = React.lazy(() => import("@/pages/ontology/OntologyOverviewPage"));

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

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AppErrorBoundary>
          <React.Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading…</div>}>
            <Routes>
              <Route path="/" element={<Navigate to="/ontology" replace />} />
              <Route path="/apps/workshop" element={<Layout><WorkshopListPage /></Layout>} />
              <Route path="/apps/workshop/:appId" element={<Layout><WorkshopAppPage /></Layout>} />
              <Route path="/apps/queries" element={<Layout><QueryLibraryPage /></Layout>} />
              <Route path="/ontology" element={<Layout><OntologyOverviewPage /></Layout>} />
              <Route path="*" element={<Navigate to="/ontology" replace />} />
            </Routes>
          </React.Suspense>
        </AppErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
