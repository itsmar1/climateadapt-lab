import { useCallback, useEffect, useState } from 'react';
import type { ScenarioDetail } from './api/client';
import { API_BASE_URL } from './api/client';
import DemoView from './components/DemoView';
import HistoryView from './components/HistoryView';
import JobProgress from './components/JobProgress';
import ResultsView from './components/ResultsView';
import ScenarioForm from './components/ScenarioForm';

type Route =
  | { view: 'form' }
  | { view: 'history' }
  | { view: 'demo'; key: string | null }
  | { view: 'scenario'; id: string };

function routeFromHash(): Route {
  if (window.location.hash === '#/scenarios') {
    return { view: 'history' };
  }
  if (window.location.hash === '#/demo') {
    return { view: 'demo', key: null };
  }
  const demoMatch = /^#\/demo\/([A-Za-z0-9_-]+)$/.exec(window.location.hash);
  if (demoMatch?.[1]) {
    return { view: 'demo', key: demoMatch[1] };
  }
  const match = /^#\/scenarios\/([A-Za-z0-9_-]+)$/.exec(window.location.hash);
  if (match?.[1]) {
    return { view: 'scenario', id: match[1] };
  }
  return { view: 'form' };
}

function ScenarioRun({ id, onBack }: { id: string; onBack: () => void }) {
  const [detail, setDetail] = useState<ScenarioDetail | null>(null);

  const handleDone = useCallback((loaded: ScenarioDetail) => {
    setDetail(loaded);
  }, []);

  if (detail) {
    return <ResultsView detail={detail} onNew={onBack} />;
  }
  return <JobProgress key={id} scenarioId={id} onDone={handleDone} onStop={onBack} />;
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => routeFromHash());

  useEffect(() => {
    function onHashChange(): void {
      setRoute(routeFromHash());
    }
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  function openScenario(id: string): void {
    window.location.hash = `#/scenarios/${id}`;
    setRoute({ view: 'scenario', id });
  }

  function openForm(): void {
    window.location.hash = '';
    setRoute({ view: 'form' });
  }

  function openDemo(key: string | null): void {
    window.location.hash = key === null ? '#/demo' : `#/demo/${key}`;
    setRoute({ view: 'demo', key });
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>ClimateAdapt Lab</h1>
        <p>Evidence-grounded agricultural drought adaptation (demo)</p>
        <nav className="app-nav" aria-label="Sections">
          <a href="#">New analysis</a>
          <a href="#/scenarios">History</a>
          <a href="#/demo">Demo</a>
        </nav>
      </header>
      <main>
        {route.view === 'form' ? (
          <div className="card">
            <h2>New analysis</h2>
            <p className="subtle">
              Pick a location and window. The backend computes environmental
              indicators deterministically; values are never estimated.
            </p>
            <ScenarioForm onCreated={openScenario} />
          </div>
        ) : route.view === 'history' ? (
          <HistoryView onOpen={openScenario} />
        ) : route.view === 'demo' ? (
          <DemoView snapshotKey={route.key} onOpen={openDemo} />
        ) : (
          <ScenarioRun id={route.id} onBack={openForm} />
        )}
      </main>
      <footer className="app-footer">
        Backend: <code className="inline">{API_BASE_URL}</code> · No severity
        scores are shown anywhere in this app; indicator values stand on their
        own with sources and limitations.
      </footer>
    </div>
  );
}
