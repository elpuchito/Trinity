import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { incidentApi, connectPipelineWS, ticketApi, mockApi } from '../utils/api';
import {
  IconInbox, IconSearch, IconCode, IconFileText, IconLink, IconTarget, IconSend,
  IconCheck, IconCheckCircle, IconX, IconLoader, IconClock, IconRefreshCw,
  IconBrain, IconPlug, IconClipboard, IconChevronRight,
  IconMessageSquare, IconMail, IconTicket, IconPaperclip, IconAlertCircle
} from './Icons';

const PIPELINE_STAGES = [
  { key: 'intake', label: 'Intake', icon: <IconInbox size={16} /> },
  { key: 'triage', label: 'Triage', icon: <IconSearch size={16} /> },
  { key: 'code_analysis', label: 'Code Analysis', icon: <IconCode size={16} /> },
  { key: 'doc_analysis', label: 'Doc Analysis', icon: <IconFileText size={16} /> },
  { key: 'dedup', label: 'Dedup Check', icon: <IconLink size={16} /> },
  { key: 'routing', label: 'Route & Ticket', icon: <IconTarget size={16} /> },
  { key: 'notify', label: 'Notify', icon: <IconSend size={16} /> },
];

export default function IncidentDetail() {
  const { id } = useParams();
  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stageStatuses, setStageStatuses] = useState({});
  const [stageMessages, setStageMessages] = useState({});
  const [pipelineElapsed, setPipelineElapsed] = useState(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [activeTab, setActiveTab] = useState('slack');
  const [slackMessages, setSlackMessages] = useState([]);
  const [emails, setEmails] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [jsonExpanded, setJsonExpanded] = useState(false);

  const loadIncident = useCallback(async () => {
    try {
      const data = await incidentApi.get(id);
      setIncident(data);
      setError(null);

      if (data.status === 'resolved' || data.status === 'closed') {
        const allCompleted = {};
        PIPELINE_STAGES.forEach(s => allCompleted[s.key] = 'completed');
        setStageStatuses(allCompleted);
        setPipelineRunning(false);
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
        setPipelineRunning(false);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadIntegrations = useCallback(async () => {
    try {
      const [slackData, emailData, ticketData] = await Promise.allSettled([
        mockApi.slackMessages(50),
        mockApi.emailInbox(),
        ticketApi.list(),
      ]);
      if (slackData.status === 'fulfilled') setSlackMessages(slackData.value.messages || []);
      if (emailData.status === 'fulfilled') setEmails(emailData.value.emails || []);
      if (ticketData.status === 'fulfilled') {
        const all = [...(ticketData.value.linear_issues || []), ...(ticketData.value.db_tickets || [])];
        setTickets(all);
      }
    } catch (e) { /* swallow */ }
  }, []);

  useEffect(() => {
    loadIncident();
    loadIntegrations();
    const interval = setInterval(() => {
      loadIncident();
      loadIntegrations();
    }, 5000);
    return () => clearInterval(interval);
  }, [loadIncident, loadIntegrations]);

  useEffect(() => {
    let ws;
    try {
      ws = connectPipelineWS(id, (data) => {
        if (data.stage && data.status) {
          setStageStatuses(prev => ({ ...prev, [data.stage]: data.status }));
          if (data.message) setStageMessages(prev => ({ ...prev, [data.stage]: data.message }));
        }
        if (data.type === 'pipeline_started') setPipelineRunning(true);
        if (data.type === 'pipeline_completed' || data.type === 'incident_updated' || data.type === 'incident_resolved') {
          setPipelineRunning(false);
          loadIncident();
          loadIntegrations();
        }
      });
    } catch (e) { /* fallback to polling */ }
    return () => ws?.close();
  }, [id, loadIncident, loadIntegrations]);

  useEffect(() => {
    if (!pipelineRunning) return;
    const start = Date.now();
    const timer = setInterval(() => setPipelineElapsed(((Date.now() - start) / 1000).toFixed(1)), 100);
    return () => clearInterval(timer);
  }, [pipelineRunning]);

  async function handleResolve() {
    try {
      await incidentApi.update(id, { status: 'resolved' });
      loadIncident();
      loadIntegrations();
    } catch (err) {
      setError(err.message);
    }
  }

  if (loading) {
    return (
      <div className="animate-in" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
        <div className="skeleton" style={{ height: 200, borderRadius: 'var(--radius-lg)' }} />
        <div className="skeleton" style={{ height: 120, borderRadius: 'var(--radius-lg)' }} />
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="empty-state animate-in">
        <div className="empty-icon"><IconAlertCircle size={56} style={{ color: 'var(--text-muted)' }} /></div>
        <h3>Error</h3>
        <p>{error || 'Incident not found'}</p>
        <Link to="/" className="btn btn-secondary">← Back to Dashboard</Link>
      </div>
    );
  }

  const report = incident.triage_report || {};
  const incidentSlack = slackMessages.filter(m => m._metadata?.incident_id === id || m.incident_id === id);
  const incidentEmails = emails.filter(e => e.incident_id === id);

  return (
    <div className="stagger-children">
      {/* Back + Actions */}
      <div className="animate-in flex items-center justify-between" style={{ marginBottom: 'var(--space-xl)' }}>
        <Link to="/" style={{ color: 'var(--text-muted)', fontSize: '14px', letterSpacing: '0.14px' }}>← Back to Dashboard</Link>
        <div className="flex gap-md">
          {incident.status !== 'resolved' && incident.status !== 'closed' && (
            <button className="btn btn-primary" onClick={handleResolve}>
              <IconCheckCircle size={14} />
              Mark Resolved
            </button>
          )}
        </div>
      </div>

      {/* Title Card */}
      <div className="card animate-in" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-md)' }}>
          <h2 style={{ flex: 1, marginRight: 'var(--space-lg)' }}>{incident.title}</h2>
          <div className="flex gap-sm">
            <span className={`badge badge-${incident.severity?.toLowerCase() || 'unknown'}`}>{incident.severity}</span>
            <span className={`badge badge-${incident.status?.split('_')[0] || 'unknown'}`}>{incident.status?.replace('_', ' ')}</span>
          </div>
        </div>
        <p style={{ fontSize: '14px', color: 'var(--text-muted)', marginBottom: 'var(--space-md)', letterSpacing: '0.14px' }}>
          Reported by <strong style={{ color: 'var(--text-primary)' }}>{incident.reporter_name}</strong> ({incident.reporter_email}) · {new Date(incident.created_at).toLocaleString()}
        </p>
        <p style={{ lineHeight: 1.7, letterSpacing: '0.16px', color: 'var(--text-secondary)' }}>{incident.description}</p>

        {incident.attachments?.length > 0 && (
          <div style={{ marginTop: 'var(--space-lg)' }}>
            <div className="form-label flex items-center gap-xs"><IconPaperclip size={12} /> Attachments</div>
            <div className="flex gap-sm" style={{ flexWrap: 'wrap' }}>
              {incident.attachments.map((att, i) => (
                <span key={i} style={{ padding: '4px 12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-pill)', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                  {att.original_name || att}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Pipeline Visualization */}
      <div className="card animate-in" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 'var(--space-lg)' }}>
          <h4 className="flex items-center gap-sm"><IconRefreshCw size={18} /> Triage Pipeline</h4>
          {pipelineRunning && pipelineElapsed && (
            <span className="flex items-center gap-xs" style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--status-triaging)' }}>
              <IconClock size={13} /> {pipelineElapsed}s
            </span>
          )}
        </div>
        <div className="pipeline-track">
          {PIPELINE_STAGES.map((stage, i) => (
            <PipelineStageNode
              key={stage.key}
              stage={stage}
              status={stageStatuses[stage.key] || 'pending'}
              message={stageMessages[stage.key]}
              isLast={i === PIPELINE_STAGES.length - 1}
            />
          ))}
        </div>
      </div>

      {/* Triage Report */}
      {incident.triage_report && (
        <div className="card animate-in" style={{ marginBottom: 'var(--space-lg)' }}>
          <h4 className="flex items-center gap-sm" style={{ marginBottom: 'var(--space-lg)' }}><IconBrain size={18} /> AI Triage Report</h4>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--space-lg)', marginBottom: 'var(--space-lg)' }}>
            {incident.affected_service && <InfoBlock label="Affected Service" value={incident.affected_service} />}
            {incident.assigned_team && <InfoBlock label="Assigned Team" value={incident.assigned_team} />}
            {report.code_confidence > 0 && (
              <div>
                <div className="form-label">Confidence</div>
                <div className="flex items-center gap-md">
                  <ConfidenceGauge value={Math.round(report.code_confidence * 100)} />
                  <span style={{ fontSize: '14px', fontWeight: 500 }}>{Math.round(report.code_confidence * 100)}%</span>
                </div>
              </div>
            )}
          </div>

          {incident.root_cause_hypothesis && (
            <div style={{ marginBottom: 'var(--space-lg)' }}>
              <div className="form-label">Root Cause Hypothesis</div>
              <div style={{ padding: 'var(--space-md) var(--space-lg)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', fontSize: '14px', lineHeight: 1.7, letterSpacing: '0.14px', borderLeft: '3px solid var(--text-primary)', color: 'var(--text-secondary)' }}>
                {incident.root_cause_hypothesis}
              </div>
            </div>
          )}

          {incident.suggested_runbook && (
            <div style={{ marginBottom: 'var(--space-lg)' }}>
              <div className="form-label">Suggested Runbook</div>
              <div style={{ padding: 'var(--space-md) var(--space-lg)', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)', fontSize: '13px', lineHeight: 1.85, borderLeft: '3px solid var(--stage-completed)', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
                {incident.suggested_runbook}
              </div>
            </div>
          )}

          {report.recommended_actions?.length > 0 && (
            <div style={{ marginBottom: 'var(--space-lg)' }}>
              <div className="form-label">Recommended Actions</div>
              {report.recommended_actions.map((action, i) => (
                <div key={i} className="flex items-center gap-md" style={{ padding: '8px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '14px', letterSpacing: '0.14px', color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '12px', minWidth: 24 }}>{i + 1}.</span>
                  {action}
                </div>
              ))}
            </div>
          )}

          {report.known_issues?.length > 0 && (
            <div style={{ marginBottom: 'var(--space-lg)' }}>
              <div className="form-label">Known Issues</div>
              <div className="flex gap-sm" style={{ flexWrap: 'wrap' }}>
                {report.known_issues.map((issue, i) => (
                  <span key={i} style={{ padding: '4px 12px', background: 'var(--status-triaged-bg)', color: 'var(--status-triaged)', borderRadius: 'var(--radius-pill)', fontSize: '13px', fontWeight: 500 }}>
                    {issue}
                  </span>
                ))}
              </div>
            </div>
          )}

          {incident.related_code_files?.length > 0 && (
            <div style={{ marginBottom: 'var(--space-lg)' }}>
              <div className="form-label">Related Code Files</div>
              <div className="flex gap-sm" style={{ flexWrap: 'wrap' }}>
                {incident.related_code_files.map((file, i) => (
                  <span key={i} style={{ padding: '4px 12px', background: 'var(--status-submitted-bg)', color: 'var(--status-submitted)', borderRadius: 'var(--radius-pill)', fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                    {file}
                  </span>
                ))}
              </div>
            </div>
          )}

          <button className={`collapsible-trigger ${jsonExpanded ? 'open' : ''}`} onClick={() => setJsonExpanded(!jsonExpanded)}>
            <span className="chevron"><IconChevronRight size={12} /></span>
            Raw Triage JSON
          </button>
          {jsonExpanded && (
            <div className="json-viewer animate-in">
              {JSON.stringify(incident.triage_report, null, 2)}
            </div>
          )}
        </div>
      )}

      {/* Integrations Panel */}
      {(incidentSlack.length > 0 || incidentEmails.length > 0 || incident.tickets?.length > 0) && (
        <div className="card animate-in" style={{ marginBottom: 'var(--space-lg)' }}>
          <h4 className="flex items-center gap-sm" style={{ marginBottom: 'var(--space-lg)' }}><IconPlug size={18} /> Integrations</h4>

          <div className="tab-bar">
            <button className={`tab-btn ${activeTab === 'slack' ? 'active' : ''}`} onClick={() => setActiveTab('slack')}>
              <IconMessageSquare size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
              Slack {incidentSlack.length > 0 && `(${incidentSlack.length})`}
            </button>
            <button className={`tab-btn ${activeTab === 'email' ? 'active' : ''}`} onClick={() => setActiveTab('email')}>
              <IconMail size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
              Email {incidentEmails.length > 0 && `(${incidentEmails.length})`}
            </button>
            <button className={`tab-btn ${activeTab === 'linear' ? 'active' : ''}`} onClick={() => setActiveTab('linear')}>
              <IconTicket size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
              Linear {incident.tickets?.length > 0 && `(${incident.tickets.length})`}
            </button>
          </div>

          {activeTab === 'slack' && (
            <div className="flex flex-col gap-md animate-in">
              {incidentSlack.length > 0 ? incidentSlack.map((msg, i) => (
                <div key={i} className="integration-card">
                  <div className="integration-card-header">
                    <span className="icon"><IconMessageSquare size={16} /></span>
                    <span>{msg.channel || msg._metadata?.channel || '#incidents'}</span>
                    <span style={{ marginLeft: 'auto', fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                      {msg.ts ? new Date(parseFloat(msg.ts) * 1000).toLocaleString() : ''}
                    </span>
                  </div>
                  <div style={{ fontSize: '14px', color: 'var(--text-secondary)', letterSpacing: '0.14px', lineHeight: 1.6 }}>
                    {msg.message?.text || msg.text || 'Slack message delivered'}
                  </div>
                </div>
              )) : <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>No Slack messages yet for this incident.</p>}
            </div>
          )}

          {activeTab === 'email' && (
            <div className="flex flex-col gap-md animate-in">
              {incidentEmails.length > 0 ? incidentEmails.map((email, i) => (
                <div key={i} className="integration-card">
                  <div className="integration-card-header">
                    <span className="icon"><IconMail size={16} /></span>
                    <span>{email.to || email.recipient}</span>
                    <span style={{ marginLeft: 'auto', color: 'var(--stage-completed)', fontSize: '12px', fontWeight: 500 }} className="flex items-center gap-xs">
                      <IconCheck size={12} /> Delivered
                    </span>
                  </div>
                  <div style={{ fontWeight: 500, fontSize: '14px', marginBottom: '4px' }}>{email.subject}</div>
                  <div style={{ fontSize: '13px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{email.email_type || 'notification'}</div>
                </div>
              )) : <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>No emails yet for this incident.</p>}
            </div>
          )}

          {activeTab === 'linear' && (
            <div className="flex flex-col gap-md animate-in">
              {incident.tickets?.length > 0 ? incident.tickets.map(ticket => (
                <div key={ticket.id} className="integration-card">
                  <div className="integration-card-header">
                    <span className="icon"><IconTicket size={16} /></span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-primary)' }}>{ticket.external_id}</span>
                    <span className={`badge badge-${ticket.status === 'open' ? 'submitted' : ticket.status === 'resolved' ? 'resolved' : 'triaging'}`} style={{ marginLeft: 'auto' }}>
                      {ticket.status}
                    </span>
                  </div>
                  <div style={{ fontSize: '14px', fontWeight: 500, marginBottom: '8px' }}>{ticket.title}</div>
                  <div className="flex gap-sm items-center" style={{ flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Team: {ticket.assignee}</span>
                    {ticket.labels?.map((label, i) => (
                      <span key={i} style={{ padding: '2px 8px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-pill)', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                        {label}
                      </span>
                    ))}
                  </div>
                </div>
              )) : <p style={{ color: 'var(--text-muted)', fontSize: '14px' }}>No tickets yet for this incident.</p>}
            </div>
          )}
        </div>
      )}

      {/* Timeline */}
      {report.pipeline_stages?.length > 0 && (
        <div className="card animate-in">
          <h4 className="flex items-center gap-sm" style={{ marginBottom: 'var(--space-lg)' }}><IconClipboard size={18} /> Event Timeline</h4>
          <div className="timeline">
            <TimelineEvent time={incident.created_at} title="Incident Submitted" desc={`Reported by ${incident.reporter_name}`} status="completed" />
            {report.pipeline_stages.map((stage, i) => (
              <TimelineEvent key={i} time={stage.timestamp} title={`${stage.stage} — ${stage.status}`} desc={stage.message} status={stage.status === 'completed' ? 'completed' : stage.status === 'error' ? 'error' : 'running'} />
            ))}
            {incident.resolved_at && (
              <TimelineEvent time={incident.resolved_at} title="Incident Resolved" desc="Resolution notifications sent" status="completed" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function PipelineStageNode({ stage, status, message, isLast }) {
  return (
    <>
      <div className={`pipeline-node ${status}`}>
        <div className="pipeline-node-dot">
          {status === 'completed' ? <IconCheck size={16} /> :
           status === 'running' ? <IconLoader size={16} /> :
           status === 'error' ? <IconX size={16} /> :
           stage.icon}
        </div>
        <div className="pipeline-node-label">{stage.label}</div>
        {message && (
          <div style={{ position: 'absolute', top: '100%', marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center', maxWidth: '120px', lineHeight: 1.3 }}>
            {message.length > 60 ? message.slice(0, 60) + '…' : message}
          </div>
        )}
      </div>
      {!isLast && <div className={`pipeline-connector ${status === 'completed' ? 'active' : ''}`} />}
    </>
  );
}

function InfoBlock({ label, value }) {
  return (
    <div>
      <div className="form-label">{label}</div>
      <div style={{ fontSize: 'var(--text-md)', fontWeight: 500 }}>{value}</div>
    </div>
  );
}

function ConfidenceGauge({ value }) {
  const circumference = 2 * Math.PI * 18;
  const offset = circumference - (value / 100) * circumference;
  return (
    <svg width="48" height="48" viewBox="0 0 48 48" className="gauge-ring">
      <circle className="gauge-bg" cx="24" cy="24" r="18" />
      <circle className="gauge-fill" cx="24" cy="24" r="18" strokeDasharray={circumference} strokeDashoffset={offset} />
    </svg>
  );
}

function TimelineEvent({ time, title, desc, status }) {
  return (
    <div className={`timeline-item ${status}`}>
      <div className="timeline-dot" />
      {time && <div className="timeline-time">{new Date(time).toLocaleTimeString()}</div>}
      <div className="timeline-title">{title}</div>
      {desc && <div className="timeline-desc">{desc}</div>}
    </div>
  );
}
