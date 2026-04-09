import { BrowserRouter as Router, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import IncidentForm from './components/IncidentForm';
import IncidentDetail from './components/IncidentDetail';
import NotificationFeed from './components/NotificationFeed';
import { IconZap, IconDashboard, IconAlertTriangle, IconBarChart, IconBell } from './components/Icons';

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon"><IconZap size={18} stroke="#fff" /></div>
        <div>
          <h1>TriageForge</h1>
          <span className="version">v1.0</span>
        </div>
      </div>

      <nav>
        <div className="nav-section">
          <div className="nav-section-title">Operations</div>
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <span className="nav-icon"><IconDashboard size={16} /></span>
            Dashboard
          </NavLink>
          <NavLink to="/submit" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <span className="nav-icon"><IconAlertTriangle size={16} /></span>
            Report Incident
          </NavLink>
        </div>

        <div className="nav-section">
          <div className="nav-section-title">Monitoring</div>
          <a href="http://localhost:3001" target="_blank" rel="noopener noreferrer" className="nav-link">
            <span className="nav-icon"><IconBarChart size={16} /></span>
            Grafana
          </a>
        </div>

        <div className="nav-section">
          <div className="nav-section-title">System</div>
          <NavLink to="/notifications" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <span className="nav-icon"><IconBell size={16} /></span>
            Notifications
          </NavLink>
        </div>
      </nav>

      <div style={{ marginTop: 'auto', paddingTop: 'var(--space-xl)', borderTop: '1px solid var(--border-subtle)' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)', letterSpacing: '0.14px' }}>
          SRE Agent • Powered by Gemini
        </div>
      </div>
    </aside>
  );
}

function TopBar() {
  const location = useLocation();
  const titles = {
    '/': 'Incident Dashboard',
    '/submit': 'Report New Incident',
    '/notifications': 'Notifications',
  };

  const title = location.pathname.startsWith('/incident/')
    ? 'Incident Detail'
    : titles[location.pathname] || 'TriageForge';

  return (
    <header className="topbar">
      <h2 className="topbar-title">{title}</h2>
      <div className="topbar-actions">
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)', letterSpacing: '0.14px' }}>
          {new Date().toLocaleString()}
        </span>
        <span style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: 'var(--stage-completed)',
          display: 'inline-block',
          boxShadow: '0 0 8px rgba(34, 197, 94, 0.3)',
        }} />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--stage-completed)', letterSpacing: '0.14px' }}>
          ONLINE
        </span>
      </div>
    </header>
  );
}

export default function App() {
  return (
    <Router>
      <div className="app-layout">
        <Sidebar />
        <TopBar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/submit" element={<IncidentForm />} />
            <Route path="/incident/:id" element={<IncidentDetail />} />
            <Route path="/notifications" element={<NotificationFeed />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}
