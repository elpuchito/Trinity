import { useState, useEffect } from 'react';
import { notificationApi, mockApi } from '../utils/api';
import {
  IconBell, IconMessageSquare, IconMail, IconCheck, IconAlertCircle
} from './Icons';

export default function NotificationFeed() {
  const [activeTab, setActiveTab] = useState('all');
  const [notifications, setNotifications] = useState([]);
  const [slackMessages, setSlackMessages] = useState([]);
  const [emails, setEmails] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  async function loadData() {
    try {
      const [notifData, slackData, emailData] = await Promise.allSettled([
        notificationApi.list(),
        mockApi.slackMessages(100),
        mockApi.emailInbox(),
      ]);
      if (notifData.status === 'fulfilled') setNotifications(notifData.value.notifications || []);
      if (slackData.status === 'fulfilled') setSlackMessages(slackData.value.messages || []);
      if (emailData.status === 'fulfilled') setEmails(emailData.value.emails || []);
    } catch (e) { /* swallow */ }
    setLoading(false);
  }

  const displayItems = activeTab === 'slack' ? slackMessages :
                       activeTab === 'email' ? emails :
                       notifications;

  return (
    <div className="stagger-children">
      <div className="animate-in" style={{ marginBottom: 'var(--space-xl)' }}>
        <h2>Notifications</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '14px', letterSpacing: '0.14px', marginTop: 'var(--space-sm)' }}>
          Real-time delivery log from the triage pipeline's integrations.
        </p>
      </div>

      {/* Tab Bar */}
      <div className="tab-bar animate-in" style={{ marginBottom: 'var(--space-xl)' }}>
        <button className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`} onClick={() => setActiveTab('all')}>
          All ({notifications.length})
        </button>
        <button className={`tab-btn ${activeTab === 'slack' ? 'active' : ''}`} onClick={() => setActiveTab('slack')}>
          <IconMessageSquare size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
          Slack ({slackMessages.length})
        </button>
        <button className={`tab-btn ${activeTab === 'email' ? 'active' : ''}`} onClick={() => setActiveTab('email')}>
          <IconMail size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
          Email ({emails.length})
        </button>
      </div>

      {loading && (
        <div className="flex flex-col gap-md">
          <div className="skeleton" style={{ height: 80, borderRadius: 'var(--radius-lg)' }} />
          <div className="skeleton" style={{ height: 80, borderRadius: 'var(--radius-lg)' }} />
          <div className="skeleton" style={{ height: 80, borderRadius: 'var(--radius-lg)' }} />
        </div>
      )}

      {!loading && displayItems.length === 0 && (
        <div className="empty-state animate-in">
          <div className="empty-icon">
            {activeTab === 'slack' ? <IconMessageSquare size={56} style={{ color: 'var(--text-muted)' }} /> :
             activeTab === 'email' ? <IconMail size={56} style={{ color: 'var(--text-muted)' }} /> :
             <IconBell size={56} style={{ color: 'var(--text-muted)' }} />}
          </div>
          <h3>No {activeTab === 'all' ? 'notifications' : `${activeTab} messages`} yet</h3>
          <p>Submit an incident to see notifications appear here in real-time.</p>
        </div>
      )}

      {/* All Notifications */}
      {!loading && activeTab === 'all' && notifications.length > 0 && (
        <div className="flex flex-col gap-sm animate-in">
          {notifications.map(notif => (
            <div key={notif.id} className="card" style={{ padding: 'var(--space-lg)', display: 'grid', gridTemplateColumns: '36px 1fr auto', alignItems: 'center', gap: 'var(--space-md)' }}>
              <span style={{ display: 'flex', justifyContent: 'center', color: 'var(--text-muted)' }}>
                {notif.channel === 'email' ? <IconMail size={18} /> : <IconMessageSquare size={18} />}
              </span>
              <div>
                <div style={{ fontSize: '14px', fontWeight: 500, marginBottom: '2px', letterSpacing: '0.14px' }}>
                  {notif.subject}
                </div>
                <div style={{ fontSize: '13px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {notif.recipient}
                </div>
              </div>
              <div className="flex flex-col items-center gap-xs" style={{ textAlign: 'right' }}>
                <span className="flex items-center gap-xs" style={{ color: notif.is_sent ? 'var(--stage-completed)' : 'var(--status-triaged)', fontSize: '12px', fontWeight: 500 }}>
                  {notif.is_sent ? <><IconCheck size={12} /> Sent</> : 'Pending'}
                </span>
                {notif.sent_at && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                    {new Date(notif.sent_at).toLocaleTimeString()}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Slack Messages */}
      {!loading && activeTab === 'slack' && slackMessages.length > 0 && (
        <div className="flex flex-col gap-sm animate-in">
          {slackMessages.map((msg, i) => (
            <div key={i} className="card" style={{ padding: 'var(--space-lg)' }}>
              <div className="flex items-center gap-md" style={{ marginBottom: 'var(--space-sm)' }}>
                <IconMessageSquare size={16} style={{ color: 'var(--text-muted)' }} />
                <span style={{ fontWeight: 500, fontSize: '14px' }}>{msg.channel || '#incidents'}</span>
                <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                  {msg.ts ? new Date(parseFloat(msg.ts) * 1000).toLocaleTimeString() : ''}
                </span>
              </div>
              <div style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: 1.6, letterSpacing: '0.14px' }}>
                {msg.message?.text || msg.text || 'Slack message'}
              </div>
              {msg._metadata?.urgency && (
                <span style={{
                  marginTop: 'var(--space-sm)',
                  display: 'inline-block',
                  padding: '2px 8px',
                  background: msg._metadata.urgency === 'immediate' ? 'var(--severity-p1-bg)' : msg._metadata.urgency === 'resolution' ? 'var(--status-resolved-bg)' : 'var(--bg-secondary)',
                  color: msg._metadata.urgency === 'immediate' ? 'var(--severity-p1)' : msg._metadata.urgency === 'resolution' ? 'var(--status-resolved)' : 'var(--text-muted)',
                  borderRadius: 'var(--radius-pill)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                }}>
                  {msg._metadata.urgency}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Emails */}
      {!loading && activeTab === 'email' && emails.length > 0 && (
        <div className="flex flex-col gap-sm animate-in">
          {emails.map((email, i) => (
            <div key={i} className="card" style={{ padding: 'var(--space-lg)' }}>
              <div className="flex items-center gap-md" style={{ marginBottom: 'var(--space-sm)' }}>
                <IconMail size={16} style={{ color: 'var(--text-muted)' }} />
                <span style={{ fontWeight: 500, fontSize: '14px' }}>{email.to || email.recipient}</span>
                <span className="flex items-center gap-xs" style={{ marginLeft: 'auto', color: 'var(--stage-completed)', fontSize: '12px', fontWeight: 500 }}>
                  <IconCheck size={12} /> Delivered
                </span>
              </div>
              <div style={{ fontWeight: 500, fontSize: '14px', marginBottom: '4px', letterSpacing: '0.14px' }}>
                {email.subject}
              </div>
              <div className="flex gap-sm items-center" style={{ marginTop: 'var(--space-sm)' }}>
                <span style={{
                  padding: '2px 8px',
                  background: email.email_type === 'oncall_alert' ? 'var(--severity-p1-bg)' : email.email_type === 'resolution' ? 'var(--status-resolved-bg)' : 'var(--status-submitted-bg)',
                  color: email.email_type === 'oncall_alert' ? 'var(--severity-p1)' : email.email_type === 'resolution' ? 'var(--status-resolved)' : 'var(--status-submitted)',
                  borderRadius: 'var(--radius-pill)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                }}>
                  {email.email_type || 'notification'}
                </span>
                {email.sent_at && (
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                    {new Date(email.sent_at).toLocaleTimeString()}
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
