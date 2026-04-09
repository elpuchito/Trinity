import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { incidentApi, connectGlobalWS } from '../utils/api';
import {
  IconClipboard, IconAlertCircle, IconZap, IconCheckCircle,
  IconAlertTriangle, IconShield
} from './Icons';

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
  ticket_created: 'badge-ticket',
  in_progress: 'badge-triaging',
  resolved: 'badge-resolved',
  closed: 'badge-unknown',
};

const SEVERITY_ROW_MAP = {
  P1: 'severity-p1',
  P2: 'severity-p2',
  P3: 'severity-p3',
  P4: 'severity-p4',
};

export default function Dashboard() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toasts, setToasts] = useState([]);

  const loadIncidents = useCallback(async () => {
    try {
      const data = await incidentApi.list();
      setIncidents(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadIncidents();
    const interval = setInterval(loadIncidents, 15000);
    return () => clearInterval(interval);
  }, [loadIncidents]);

  // WebSocket live updates
  useEffect(() => {
    let ws;
    try {
      ws = connectGlobalWS((data) => {
        if (data.type === 'incident_triaged' || data.type === 'incident_resolved' || data.type === 'incident_updated') {
          loadIncidents();
          const id = Date.now();
          setToasts(prev => [...prev, {
            id,
            message: data.type === 'incident_resolved'
              ? `Incident resolved (${data.severity || ''})`
              : `Incident triaged → ${data.severity || 'Unknown'}`,
            icon: data.type === 'incident_resolved' ? 'check' : 'zap',
          }]);
          setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
        }
      });
    } catch (e) { /* WebSocket not available */ }
    return () => ws?.close();
  }, [loadIncidents]);

  const stats = {
    total: incidents.length,
    critical: incidents.filter(i => i.severity === 'P1').length,
    active: incidents.filter(i => !['resolved', 'closed'].includes(i.status)).length,
    resolved: incidents.filter(i => i.status === 'resolved').length,
  };

  const sevCounts = {
    p1: incidents.filter(i => i.severity === 'P1').length,
    p2: incidents.filter(i => i.severity === 'P2').length,
    p3: incidents.filter(i => i.severity === 'P3').length,
    p4: incidents.filter(i => i.severity === 'P4').length,
  };
  const sevTotal = Math.max(stats.total, 1);

  const lastP1 = incidents.find(i => i.severity === 'P1');
  const timeSinceP1 = lastP1 ? getTimeSince(new Date(lastP1.created_at)) : null;

  return (
    <div className="stagger-children">
      {/* Toast notifications */}
      {toasts.length > 0 && (
        <div className="toast-container">
          {toasts.map(t => (
            <div key={t.id} className="toast">
              {t.icon === 'check' ? <IconCheckCircle size={16} style={{ color: 'var(--stage-completed)' }} /> : <IconZap size={16} style={{ color: 'var(--status-triaging)' }} />}
              {t.message}
            </div>
          ))}
        </div>
      )}

      {/* Stats Row */}
      <div className="animate-in" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-lg)', marginBottom: 'var(--space-xl)' }}>
        <StatCard label="Total Incidents" value={stats.total} icon={<IconClipboard size={22} style={{ color: 'var(--text-muted)' }} />} />
        <StatCard label="Critical (P1)" value={stats.critical} icon={<IconAlertCircle size={22} style={{ color: 'var(--severity-p1)' }} />} color="var(--severity-p1)" />
        <StatCard label="Active" value={stats.active} icon={<IconZap size={22} style={{ color: 'var(--status-triaging)' }} />} color="var(--status-triaging)" />
        <StatCard label="Resolved" value={stats.resolved} icon={<IconCheckCircle size={22} style={{ color: 'var(--stage-completed)' }} />} color="var(--stage-completed)" />
      </div>

      {/* Severity Bar + P1 Timer */}
      {stats.total > 0 && (
        <div className="card animate-in" style={{ padding: 'var(--space-lg)', marginBottom: 'var(--space-xl)', display: 'flex', alignItems: 'center', gap: 'var(--space-xl)' }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 'var(--space-sm)' }}>
              Severity Distribution
            </div>
            <div className="severity-bar">
              <div className="severity-bar-segment p1" style={{ width: `${(sevCounts.p1 / sevTotal) * 100}%` }} />
              <div className="severity-bar-segment p2" style={{ width: `${(sevCounts.p2 / sevTotal) * 100}%` }} />
              <div className="severity-bar-segment p3" style={{ width: `${(sevCounts.p3 / sevTotal) * 100}%` }} />
              <div className="severity-bar-segment p4" style={{ width: `${(sevCounts.p4 / sevTotal) * 100}%` }} />
            </div>
            <div className="flex gap-lg" style={{ marginTop: 'var(--space-sm)' }}>
              {sevCounts.p1 > 0 && <SevLabel label="P1" count={sevCounts.p1} color="var(--severity-p1)" />}
              {sevCounts.p2 > 0 && <SevLabel label="P2" count={sevCounts.p2} color="var(--severity-p2)" />}
              {sevCounts.p3 > 0 && <SevLabel label="P3" count={sevCounts.p3} color="var(--severity-p3)" />}
              {sevCounts.p4 > 0 && <SevLabel label="P4" count={sevCounts.p4} color="var(--severity-p4)" />}
            </div>
          </div>
          {timeSinceP1 && (
            <div style={{ textAlign: 'center', minWidth: 140, paddingLeft: 'var(--space-xl)', borderLeft: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 'var(--space-xs)' }}>
                Since Last P1
              </div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-2xl)', fontWeight: 300, color: 'var(--severity-p1)', letterSpacing: '-0.5px' }}>
                {timeSinceP1}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Header */}
      <div className="animate-in flex items-center justify-between" style={{ marginBottom: 'var(--space-lg)' }}>
        <h3>Recent Incidents</h3>
        <Link to="/submit" className="btn btn-primary">
          <IconAlertTriangle size={14} />
          Report Incident
        </Link>
      </div>

      {/* Error */}
      {error && (
        <div className="card animate-in" style={{ borderLeft: '3px solid var(--severity-p1)', marginBottom: 'var(--space-lg)' }}>
          <p style={{ color: 'var(--severity-p1)', fontSize: '14px' }}><IconAlertCircle size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} /> {error}</p>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex flex-col gap-sm">
          <div className="skeleton" style={{ height: 80, borderRadius: 'var(--radius-lg)' }} />
          <div className="skeleton" style={{ height: 80, borderRadius: 'var(--radius-lg)' }} />
          <div className="skeleton" style={{ height: 80, borderRadius: 'var(--radius-lg)' }} />
        </div>
      )}

      {/* Empty */}
      {!loading && incidents.length === 0 && (
        <div className="empty-state animate-in">
          <div className="empty-icon"><IconShield size={56} style={{ color: 'var(--text-muted)' }} /></div>
          <h3>All Clear</h3>
          <p>No incidents reported. Your e-commerce platform is running smoothly.</p>
          <Link to="/submit" className="btn btn-primary btn-lg">
            <IconAlertTriangle size={16} />
            Report an Incident
          </Link>
        </div>
      )}

      {/* Incident List */}
      {incidents.length > 0 && (
        <div className="animate-in flex flex-col gap-sm">
          {incidents.map((incident) => (
            <Link
              key={incident.id}
              to={`/incident/${incident.id}`}
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <div className={`card incident-row ${SEVERITY_ROW_MAP[incident.severity] || ''}`} style={{ padding: 'var(--space-lg)', display: 'grid', gridTemplateColumns: '1fr auto auto auto', alignItems: 'center', gap: 'var(--space-xl)' }}>
                <div>
                  <h5 style={{ marginBottom: '2px', fontSize: 'var(--text-base)', fontWeight: 400 }}>{incident.title}</h5>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '11px', letterSpacing: '0.14px' }}>
                    {incident.reporter_name} · {new Date(incident.created_at).toLocaleString()}
                  </span>
                </div>
                <span className={`badge ${SEVERITY_MAP[incident.severity] || 'badge-unknown'}`}>
                  {incident.severity}
                </span>
                <span className={`badge ${STATUS_MAP[incident.status] || 'badge-unknown'}`}>
                  {incident.status.replace('_', ' ')}
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: '13px', fontWeight: 500, letterSpacing: '0.14px' }}>
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
      <div style={{ marginBottom: 'var(--space-sm)', display: 'flex', justifyContent: 'center' }}>{icon}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 300, color: color || 'var(--text-primary)', letterSpacing: '-0.5px' }}>
        {value}
      </div>
      <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 'var(--space-xs)' }}>
        {label}
      </div>
    </div>
  );
}

function SevLabel({ label, count, color }) {
  return (
    <div className="flex items-center gap-xs" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />
      <span style={{ fontFamily: 'var(--font-mono)', letterSpacing: '0.05em' }}>{label}: {count}</span>
    </div>
  );
}

function getTimeSince(date) {
  const now = new Date();
  const diff = now - date;
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  if (hours > 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}
