/**
 * TriageForge — API Client
 * Fetch wrapper for backend API communication.
 */

const API_BASE = import.meta.env.VITE_API_URL || '';

/**
 * Make an API request.
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const config = {
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Incident API
 */
export const incidentApi = {
  /** Create a new incident with optional file attachments */
  create: (formData) =>
    request('/api/incidents', {
      method: 'POST',
      body: formData,
      headers: {}, // Let browser set Content-Type for FormData
    }),

  /** List all incidents with optional filters */
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/api/incidents${query ? `?${query}` : ''}`);
  },

  /** Get single incident with full details */
  get: (id) => request(`/api/incidents/${id}`),

  /** Update incident status/severity */
  update: (id, data) =>
    request(`/api/incidents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

/**
 * WebSocket connection for real-time pipeline updates.
 */
export function connectPipelineWS(incidentId, onMessage) {
  const wsBase = API_BASE.replace(/^http/, 'ws') || `ws://${window.location.host}`;
  const wsUrl = incidentId
    ? `${wsBase}/api/incidents/ws/${incidentId}`
    : `${wsBase}/api/incidents/ws`;

  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error('WebSocket parse error:', e);
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };

  return ws;
}

/**
 * Global WebSocket connection for dashboard-wide updates.
 */
export function connectGlobalWS(onMessage) {
  return connectPipelineWS(null, onMessage);
}

/**
 * Health check
 */
export const healthCheck = () => request('/health');

/**
 * Ticket API (mocked Linear integration)
 */
export const ticketApi = {
  /** List all tickets */
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/api/tickets${query ? `?${query}` : ''}`);
  },

  /** Get single ticket by ID or identifier (e.g. TF-1) */
  get: (id) => request(`/api/tickets/${id}`),

  /** Update ticket status */
  update: (id, data) =>
    request(`/api/tickets/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

/**
 * Notification API
 */
export const notificationApi = {
  /** List all notifications */
  list: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return request(`/api/notifications${query ? `?${query}` : ''}`);
  },
};

/**
 * Mock Integration APIs (Slack channels, Email inboxes)
 */
export const mockApi = {
  /** Slack — list channels */
  slackChannels: () => request('/api/mock/slack/channels'),

  /** Slack — get channel message history */
  slackHistory: (channel) =>
    request(`/api/mock/slack/channels/${encodeURIComponent(channel)}`),

  /** Slack — all messages */
  slackMessages: (limit = 100) => request(`/api/mock/slack/messages?limit=${limit}`),

  /** Email — get inbox (all or by recipient) */
  emailInbox: (recipient = null) =>
    request(recipient
      ? `/api/mock/email/inbox/${encodeURIComponent(recipient)}`
      : '/api/mock/email/inbox'),

  /** Email — list recipients */
  emailRecipients: () => request('/api/mock/email/recipients'),
};
