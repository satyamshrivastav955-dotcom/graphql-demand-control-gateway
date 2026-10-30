import { Suspense, lazy } from 'react';
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom';
import Landing from './pages/Landing';

// The dashboard is a separate chunk: visitors of the landing page never download it.
const AuthGate = lazy(() => import('./components/AuthGate'));
const AppShell = lazy(() => import('./components/AppShell'));
const Overview = lazy(() => import('./pages/app/Overview'));
const Analyze = lazy(() => import('./pages/app/Analyze'));
const Events = lazy(() => import('./pages/app/Events'));
const EventDetail = lazy(() => import('./pages/app/EventDetail'));
const Policies = lazy(() => import('./pages/app/Policies'));
const EvaluationPage = lazy(() => import('./pages/app/Evaluation'));

function Fallback() {
  return (
    <div role="status" className="flex min-h-screen items-center justify-center bg-ink-950 text-sm text-ink-300">
      Loading…
    </div>
  );
}

function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 text-center">
      <p className="text-5xl font-semibold text-ink-50">404</p>
      <p className="text-ink-300">That page does not exist.</p>
      <Link to="/" className="btn-secondary mt-2">
        Back to home
      </Link>
    </div>
  );
}

export function AppRoutes() {
  return (
    <Suspense fallback={<Fallback />}>
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app" element={<AuthGate><AppShell /></AuthGate>}>
        <Route index element={<Overview />} />
        <Route path="analyze" element={<Analyze />} />
        <Route path="events" element={<Events />} />
        <Route path="events/:id" element={<EventDetail />} />
        <Route path="policies" element={<Policies />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="*" element={<Navigate to="/app" replace />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
