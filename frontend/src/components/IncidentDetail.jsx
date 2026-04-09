import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { incidentApi, connectPipelineWS } from '../utils/api';

const PIPELINE_STAGES = [
  { key: 'intake', label: 'Intake', icon: '📥' },
  { key: 'triage', label: 'Triage', icon: '🔍' },
  { key: 'code_analysis', label: 'Code Analysis', icon: '💻' },
  { key: 'doc_analysis', label: 'Doc Analysis', icon: '📚' },
  { key: 'dedup', label: 'Dedup Check', icon: '🔗' },
  { key: 'routing', label: 'Route & Ticket', icon: '🎯' },
  { key: 'notify', label: 'Notify', icon: '🔔' },
];

export default function IncidentDetail() {
  const { id } = useParams();
  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stageStatuses, setStageStatuses] = useState({});

  useEffect(() => {
    loadIncident();
    const interval = setInterval(loadIncident, 5000);
    return () => clearInterval(interval);
  }, [id]);

  useEffect(() => {
    let ws;
    try {
      ws = connectPipelineWS(id, (data) => {
        if (data.stage && data.status) {
          setStageStatuses(prev => ({
            ...prev,
            [data.stage]: data.status,
          }));
        }
        if (data.type === 'incident_updated') {
          loadIncident();
        }
      });
    } catch (e) {
      // WebSocket not available, fall back to polling
    }
    return () => ws?.close();
  }, [id]);

  async function loadIncident() {
    try {
      const data = await incidentApi.get(id);
      setIncident(data);
      setError(null);

      // Infer pipeline stages from incident status
      if (data.status === 'resolved' || data.status === 'closed') {
        const allCompleted = {};
        PIPELINE_STAGES.forEach(s => allCompleted[s.key] = 'completed');
        setStageStatuses(allCompleted);
      } else if (data.triage_report) {
        setStageStatuses({
          intake: 'completed',
          triage: 'completed',
          code_analysis: 'completed',
          doc_analysis: 'completed',
          dedup: 'completed',
          routing: data.tickets?.length > 0 ? 'completed' : 'running',
          notify: data.notifications?.length > 0 ? 'completed' : 'pending',
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleResolve() {
    try {
      await incidentApi.update(id, { status: 'resolved' });
      loadIncident();
    } catch (err) {
      setError(err.message);
    }
  }

  if (loading) {
    return (
      <div className="empty-state animate-in">
        <div className="empty-icon">⏳</div>
        <h3>Loading incident...</h3>
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="empty-state animate-in">
        <div className="empty-icon">❌</div>
        <h3>Error</h3>
        <p>{error || 'Incident not found'}</p>
        <Link to="/" className="btn btn-secondary">← Back to Dashboard</Link>
      </div>
    );
  }

  return (
    <div className="stagger-children">
      {/* Back link + Actions */}
      <div className="animate-in flex items-center justify-between" style={{ marginBottom: 'var(--space-xl)' }}>
        <Link to="/" style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>← Back to Dashboard</Link>
        <div className="flex gap-md">
          {incident.status !== 'resolved' && incident.status !== 'closed' && (
            <button className="btn btn-primary" onClick={handleResolve}>
              ✅ Mark Resolved
            </button>
          )}
        </div>
      </div>

      {/* Title Card */}
      <div className="card animate-in" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-md)' }}>
          <h2>{incident.title}</h2>
          <div className="flex gap-md">
            <span className={`badge badge-${incident.severity?.toLowerCase() || 'unknown'}`}>
              {incident.severity}
            </span>
            <span className={`badge badge-${incident.status?.split('_')[0] || 'unknown'}`}>
              {incident.status?.replace('_', ' ')}
            </span>
          </div>
        </div>
        <p className="text-muted" style={{ fontSize: 'var(--text-sm)', marginBottom: 'var(--space-md)' }}>
          Reported by <strong>{incident.reporter_name}</strong> ({incident.reporter_email}) · {new Date(incident.created_at).toLocaleString()}
        </p>
        <p style={{ lineHeight: 1.7 }}>{incident.description}</p>

        {/* Attachments */}
        {incident.attachments?.length > 0 && (
          <div style={{ marginTop: 'var(--space-lg)' }}>
            <h5 style={{ fontSize: 'var(--text-sm)', marginBottom: 'var(--space-sm)' }}>📎 Attachments</h5>
            <div className="flex gap-sm" style={{ flexWrap: 'wrap' }}>
              {incident.attachments.map((att, i) => (
                <div key={i} style={{
                  padding: 'var(--space-sm) var(--space-md)',
                  background: 'var(--bg-secondary)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 'var(--text-xs)',
                  fontFamily: 'var(--font-mono)',
                }}>
                  {att.original_name || att}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Pipeline Visualization */}
      <div className="card animate-in" style={{ marginBottom: 'var(--space-lg)' }}>
        <h4 style={{ marginBottom: 'var(--space-lg)' }}>🔄 Triage Pipeline</h4>
        <div className="pipeline-track">
          {PIPELINE_STAGES.map((stage, i) => (
            <PipelineStageNode
              key={stage.key}
              stage={stage}
              status={stageStatuses[stage.key] || 'pending'}
              isLast={i === PIPELINE_STAGES.length - 1}
              prevCompleted={i === 0 || stageStatuses[PIPELINE_STAGES[i - 1].key] === 'completed'}
            />
          ))}
        </div>
      </div>

      {/* Triage Report */}
      {incident.triage_report && (
        <div className="card animate-in" style={{ marginBottom: 'var(--space-lg)' }}>
          <h4 style={{ marginBottom: 'var(--space-lg)' }}>🧠 AI Triage Report</h4>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-lg)' }}>
            {incident.affected_service && (
              <InfoBlock label="Affected Service" value={incident.affected_service} />
            )}
            {incident.assigned_team && (
              <InfoBlock label="Assigned Team" value={incident.assigned_team} />
            )}
          </div>

          {incident.root_cause_hypothesis && (
            <div style={{ marginTop: 'var(--space-lg)' }}>
              <div className="form-label">Root Cause Hypothesis</div>
              <div style={{
                padding: 'var(--space-md)',
                background: 'var(--bg-secondary)',
                borderRadius: 'var(--radius-md)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-sm)',
                lineHeight: 1.7,
                borderLeft: '3px solid var(--cyan)',
              }}>
                {incident.root_cause_hypothesis}
              </div>
            </div>
          )}

          {incident.suggested_runbook && (
            <div style={{ marginTop: 'var(--space-lg)' }}>
              <div className="form-label">Suggested Runbook</div>
              <div style={{
                padding: 'var(--space-md)',
                background: 'var(--bg-secondary)',
                borderRadius: 'var(--radius-md)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-sm)',
                lineHeight: 1.7,
                borderLeft: '3px solid var(--green)',
                whiteSpace: 'pre-wrap',
              }}>
                {incident.suggested_runbook}
              </div>
            </div>
          )}

          {incident.related_code_files?.length > 0 && (
            <div style={{ marginTop: 'var(--space-lg)' }}>
              <div className="form-label">Related Code Files</div>
              <div className="flex gap-sm" style={{ flexWrap: 'wrap' }}>
                {incident.related_code_files.map((file, i) => (
                  <span key={i} style={{
                    padding: 'var(--space-xs) var(--space-md)',
                    background: 'var(--purple-dim)',
                    color: 'var(--purple)',
                    borderRadius: 'var(--radius-full)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-xs)',
                  }}>
                    {file}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tickets */}
      {incident.tickets?.length > 0 && (
        <div className="card animate-in" style={{ marginBottom: 'var(--space-lg)' }}>
          <h4 style={{ marginBottom: 'var(--space-lg)' }}>🎫 Tickets</h4>
          {incident.tickets.map(ticket => (
            <div key={ticket.id} style={{
              padding: 'var(--space-md)',
              background: 'var(--bg-secondary)',
              borderRadius: 'var(--radius-md)',
              marginBottom: 'var(--space-sm)',
            }}>
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-mono" style={{ color: 'var(--cyan)', fontSize: 'var(--text-sm)' }}>
                    {ticket.external_id}
                  </span>
                  <span style={{ margin: '0 var(--space-sm)', color: 'var(--text-muted)' }}>·</span>
                  <span style={{ fontSize: 'var(--text-sm)' }}>{ticket.title}</span>
                </div>
                <span className={`badge badge-${ticket.status === 'open' ? 'submitted' : ticket.status === 'resolved' ? 'resolved' : 'triaging'}`}>
                  {ticket.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Notifications */}
      {incident.notifications?.length > 0 && (
        <div className="card animate-in">
          <h4 style={{ marginBottom: 'var(--space-lg)' }}>🔔 Notifications</h4>
          {incident.notifications.map(notif => (
            <div key={notif.id} style={{
              padding: 'var(--space-md)',
              background: 'var(--bg-secondary)',
              borderRadius: 'var(--radius-md)',
              marginBottom: 'var(--space-sm)',
              fontSize: 'var(--text-sm)',
            }}>
              <div className="flex items-center gap-md">
                <span>{notif.channel === 'email' ? '📧' : '💬'}</span>
                <span className="text-mono" style={{ fontSize: 'var(--text-xs)' }}>{notif.recipient}</span>
                <span style={{ color: notif.is_sent ? 'var(--green)' : 'var(--amber)' }}>
                  {notif.is_sent ? '✓ Sent' : '⏳ Pending'}
                </span>
                {notif.sent_at && (
                  <span className="text-muted text-mono" style={{ fontSize: 'var(--text-xs)' }}>
                    {new Date(notif.sent_at).toLocaleString()}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PipelineStageNode({ stage, status, isLast, prevCompleted }) {
  return (
    <>
      <div className={`pipeline-node ${status}`}>
        <div className="pipeline-node-dot">
          {status === 'completed' ? '✓' :
           status === 'running' ? stage.icon :
           status === 'error' ? '✕' :
           stage.icon}
        </div>
        <div className="pipeline-node-label">{stage.label}</div>
      </div>
      {!isLast && (
        <div className={`pipeline-connector ${status === 'completed' ? 'active' : ''}`} />
      )}
    </>
  );
}

function InfoBlock({ label, value }) {
  return (
    <div>
      <div className="form-label">{label}</div>
      <div style={{ fontSize: 'var(--text-md)', fontWeight: 600 }}>{value}</div>
    </div>
  );
}
