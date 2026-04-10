import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { incidentApi, connectGlobalWS } from '../utils/api';
import {
  IconZap, IconCheckCircle, IconAlertTriangle, IconActivity, IconClock, IconShield
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
    <div className="stagger-children" style={{ maxWidth: '1400px', margin: '0 auto', padding: '0 var(--space-xl)' }}>
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

      {/* ERROR */}
      {error && (
        <div className="card animate-in" style={{ borderLeft: '3px solid var(--severity-p1)', margin: 'var(--space-2xl) 0' }}>
          <p style={{ color: 'var(--severity-p1)', fontSize: '14px' }}>{error}</p>
        </div>
      )}

      {/* EPIC HERO SECTION */}
      <div className="animate-in" style={{ padding: 'var(--space-xl) 0 var(--space-3xl) 0', borderBottom: '1px solid var(--border-subtle)', marginBottom: 'var(--space-3xl)' }}>
        
        {/* Top Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4xl)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)' }}>
            <div style={{ padding: '8px', background: 'var(--bg-white)', borderRadius: '12px', boxShadow: 'var(--shadow-inset)' }}>
              <IconActivity size={24} style={{ color: stats.critical > 0 ? 'var(--severity-p1)' : 'var(--text-primary)' }} />
            </div>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 500, letterSpacing: '0.14px', textTransform: 'uppercase', color: 'var(--text-muted)' }}>Platform State</div>
              <div style={{ fontSize: '16px', fontWeight: 400, color: 'var(--text-primary)' }}>
                {stats.critical > 0 ? 'Critical Degradation' : 'All Systems Operational'}
              </div>
            </div>
          </div>
          
          <Link to="/submit" className="btn btn-warm" style={{ padding: '16px 28px 16px 22px', fontSize: '16px' }}>
            <IconAlertTriangle size={18} />
            Report Incident
          </Link>
        </div>

        {/* Ethereal Typography Stats Row */}
        <div style={{ display: 'flex', gap: 'var(--space-4xl)' }}>
          <HeroStat value={stats.total} label="Total Incidents" />
          <HeroStat value={stats.critical} label="Critical (P1)" color={stats.critical > 0 ? 'var(--severity-p1)' : 'var(--text-primary)'} />
          <HeroStat value={stats.active} label="Active Analysis" />
          {timeSinceP1 && (
            <HeroStat value={timeSinceP1} label="Since Last P1" color="var(--text-muted)" isTime />
          )}
        </div>

        {/* Glowing Severity Line instead of blocky bar chart */}
        {stats.total > 0 && (
          <div style={{ marginTop: 'var(--space-4xl)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 'var(--space-md)' }}>
              <div style={{ fontSize: '13px', fontWeight: 500, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
                Intake Distribution
              </div>
              <div className="flex gap-lg">
                {sevCounts.p1 > 0 && <SevLabel label="P1" count={sevCounts.p1} color="var(--severity-p1)" />}
                {sevCounts.p2 > 0 && <SevLabel label="P2" count={sevCounts.p2} color="var(--severity-p2)" />}
                {sevCounts.p3 > 0 && <SevLabel label="P3" count={sevCounts.p3} color="var(--severity-p3)" />}
                {sevCounts.p4 > 0 && <SevLabel label="P4" count={sevCounts.p4} color="var(--severity-p4)" />}
              </div>
            </div>
            
            <div style={{ 
              display: 'flex', 
              height: '3px', 
              borderRadius: '999px',
              background: 'var(--bg-secondary)',
              boxShadow: 'var(--shadow-inset)'
            }}>
              <div className="glow-bar p1" style={{ width: `${(sevCounts.p1 / sevTotal) * 100}%`, background: 'var(--severity-p1)', boxShadow: '0 0 12px var(--severity-p1)' }} />
              <div className="glow-bar p2" style={{ width: `${(sevCounts.p2 / sevTotal) * 100}%`, background: 'var(--severity-p2)', boxShadow: '0 0 8px var(--severity-p2)' }} />
              <div className="glow-bar p3" style={{ width: `${(sevCounts.p3 / sevTotal) * 100}%`, background: 'var(--severity-p3)' }} />
              <div className="glow-bar p4" style={{ width: `${(sevCounts.p4 / sevTotal) * 100}%`, background: 'var(--severity-p4)' }} />
            </div>
          </div>
        )}
      </div>

      {/* INCIDENT QUEUE */}
      <div className="animate-in" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2xl)' }}>
        <h2 style={{ fontSize: '28px' }}>Triage Queue</h2>
      </div>

      {/* Loading */}
      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
          <div className="skeleton" style={{ height: 100, borderRadius: 'var(--radius-lg)' }} />
          <div className="skeleton" style={{ height: 100, borderRadius: 'var(--radius-lg)' }} />
          <div className="skeleton" style={{ height: 100, borderRadius: 'var(--radius-lg)' }} />
        </div>
      )}

      {/* Empty State */}
      {!loading && incidents.length === 0 && (
        <div className="animate-in" style={{ textAlign: 'center', padding: '120px 0' }}>
          <div style={{ marginBottom: 'var(--space-lg)' }}><IconShield size={64} style={{ color: 'var(--border-default)', strokeWidth: 1 }} /></div>
          <h1 style={{ fontSize: '48px', color: 'var(--text-secondary)', marginBottom: 'var(--space-md)' }}>Zero Friction.</h1>
          <p style={{ fontSize: '20px', color: 'var(--text-muted)' }}>There are no active incidents. The system is operating seamlessly.</p>
        </div>
      )}

      {/* Barely-There Floating Rows */}
      {incidents.length > 0 && (
        <div className="animate-in" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)', paddingBottom: '120px' }}>
          {incidents.map((incident) => (
            <Link
              key={incident.id}
              to={`/incident/${incident.id}`}
              className="incident-row-elegant"
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2xl)' }}>
                  
                  {/* Left Visual Indicator */}
                  <div style={{ 
                    width: '4px', 
                    height: '40px', 
                    borderRadius: '2px', 
                    background: incident.severity === 'P1' ? 'var(--severity-p1)' : 
                               incident.severity === 'P2' ? 'var(--severity-p2)' : 
                               incident.severity === 'P3' ? 'var(--severity-p3)' : 
                               incident.severity === 'P4' ? 'var(--severity-p4)' : 'var(--bg-secondary)'
                  }} />
                  
                  {/* Title & Metadata */}
                  <div>
                    <h3 style={{ fontSize: '20px', marginBottom: '4px', fontWeight: 300, color: 'var(--text-primary)' }}>
                      {incident.title}
                    </h3>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)', color: 'var(--text-muted)', fontSize: '13px', letterSpacing: '0.14px' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><IconClock size={12} /> {new Date(incident.created_at).toLocaleTimeString()}</span>
                      <span>—</span>
                      <span>{incident.reporter_name}</span>
                    </div>
                  </div>
                </div>

                {/* Right Badges */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-xl)' }}>
                  <div style={{ display: 'flex', gap: 'var(--space-sm)' }}>
                    <span className={`badge ${SEVERITY_MAP[incident.severity] || 'badge-unknown'}`}>
                      {incident.severity}
                    </span>
                    <span className={`badge ${STATUS_MAP[incident.status] || 'badge-unknown'}`}>
                      {incident.status.replace('_', ' ')}
                    </span>
                  </div>
                  
                  <div style={{ width: '120px', textAlign: 'right', color: 'var(--text-secondary)', fontSize: '14px', fontWeight: 500, letterSpacing: '0.16px' }}>
                    {incident.assigned_team || '—'}
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

// Subcomponents

function HeroStat({ value, label, color, isTime }) {
  return (
    <div>
      <div style={{ 
        fontFamily: 'var(--font-display)', 
        fontSize: isTime ? '48px' : '64px', 
        fontWeight: 300, 
        color: color || 'var(--text-primary)', 
        letterSpacing: '-2px',
        lineHeight: 1
      }}>
        {value}
      </div>
      <div style={{ 
        fontSize: '13px', 
        fontWeight: 500, 
        color: 'var(--text-muted)', 
        textTransform: 'uppercase', 
        letterSpacing: '0.1em', 
        marginTop: 'var(--space-md)' 
      }}>
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
