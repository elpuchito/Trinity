import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { incidentApi } from '../utils/api';

const SEVERITY_MAP = {
  P1: 'badge-p1',
  P2: 'badge-p2',
  P3: 'badge-p3',
  P4: 'badge-p4',
  UNKNOWN: 'badge-unknown',
};

const STATUS_MAP = {
  submitted: 'badge-submitted',
  triaging: 'badge-triaging',
  triaged: 'badge-triaged',
  ticket_created: 'badge-triaged',
  in_progress: 'badge-triaging',
  resolved: 'badge-resolved',
  closed: 'badge-unknown',
};

export default function Dashboard() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadIncidents();
    const interval = setInterval(loadIncidents, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, []);

  async function loadIncidents() {
    try {
      const data = await incidentApi.list();
      setIncidents(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const stats = {
    total: incidents.length,
    critical: incidents.filter(i => i.severity === 'P1').length,
    active: incidents.filter(i => !['resolved', 'closed'].includes(i.status)).length,
    resolved: incidents.filter(i => i.status === 'resolved').length,
  };

  return (
    <div className="stagger-children">
      {/* Stats Row */}
      <div className="animate-in" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-lg)', marginBottom: 'var(--space-2xl)' }}>
        <StatCard label="Total Incidents" value={stats.total} icon="📋" />
        <StatCard label="Critical (P1)" value={stats.critical} icon="🔴" color="var(--red)" />
        <StatCard label="Active" value={stats.active} icon="⚡" color="var(--cyan)" />
        <StatCard label="Resolved" value={stats.resolved} icon="✅" color="var(--green)" />
      </div>

      {/* Header */}
      <div className="animate-in flex items-center justify-between" style={{ marginBottom: 'var(--space-lg)' }}>
        <h3>Recent Incidents</h3>
        <Link to="/submit" className="btn btn-primary">
          🚨 Report Incident
        </Link>
      </div>

      {/* Error State */}
      {error && (
        <div className="card animate-in" style={{ borderColor: 'var(--red)', marginBottom: 'var(--space-lg)' }}>
          <p style={{ color: 'var(--red)' }}>⚠️ {error}</p>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="empty-state animate-in">
          <div className="empty-icon">⏳</div>
          <h3>Loading incidents...</h3>
        </div>
      )}

      {/* Empty State */}
      {!loading && incidents.length === 0 && (
        <div className="empty-state animate-in">
          <div className="empty-icon">🛡️</div>
          <h3>All Clear</h3>
          <p>No incidents reported. Your e-commerce platform is running smoothly.</p>
          <Link to="/submit" className="btn btn-primary btn-lg">
            🚨 Report an Incident
          </Link>
        </div>
      )}

      {/* Incident List */}
      {incidents.length > 0 && (
        <div className="animate-in" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
          {incidents.map((incident) => (
            <Link
              key={incident.id}
              to={`/incident/${incident.id}`}
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <div className="card" style={{ padding: 'var(--space-lg)', display: 'grid', gridTemplateColumns: '1fr auto auto auto', alignItems: 'center', gap: 'var(--space-xl)' }}>
                <div>
                  <h5 style={{ marginBottom: 'var(--space-xs)', fontSize: 'var(--text-base)' }}>{incident.title}</h5>
                  <span className="text-muted text-mono" style={{ fontSize: 'var(--text-xs)' }}>
                    {incident.reporter_name} · {new Date(incident.created_at).toLocaleString()}
                  </span>
                </div>
                <span className={`badge ${SEVERITY_MAP[incident.severity] || 'badge-unknown'}`}>
                  {incident.severity}
                </span>
                <span className={`badge ${STATUS_MAP[incident.status] || 'badge-unknown'}`}>
                  {incident.status.replace('_', ' ')}
                </span>
                <span className="text-muted" style={{ fontSize: 'var(--text-sm)' }}>
                  {incident.assigned_team || '—'}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, icon, color }) {
  return (
    <div className="card" style={{ textAlign: 'center', padding: 'var(--space-lg)' }}>
      <div style={{ fontSize: 'var(--text-2xl)', marginBottom: 'var(--space-sm)' }}>{icon}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 800, color: color || 'var(--text-primary)' }}>
        {value}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 'var(--space-xs)' }}>
        {label}
      </div>
    </div>
  );
}
