import axios from 'axios';

const api = axios.create({ baseURL: '' });

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token');
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

// ── Auth ──────────────────────────────────────────────────────────────────────
export const login = (username, password) =>
  api.post('/api/v1/login', { username, password }).then(r => r.data);

export const getMe = () =>
  api.get('/api/v1/me').then(r => r.data);

// ── Tickets ───────────────────────────────────────────────────────────────────
export const getTickets = (params = {}) =>
  api.get('/api/v1/tickets', { params }).then(r => r.data);

export const getTicket = (id) =>
  api.get(`/api/v1/tickets/${id}`).then(r => r.data);

export const updateTicket = (id, status) =>
  api.patch(`/api/v1/tickets/${id}`, { status }).then(r => r.data);

// ── Detections ────────────────────────────────────────────────────────────────
export const postDetection = (formData) =>
  api.post('/api/v1/incident/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);

// ── Stats ─────────────────────────────────────────────────────────────────────
export const getStats = () =>
  api.get('/api/v1/stats/summary').then(r => r.data);

// ── Work Orders ───────────────────────────────────────────────────────────────
export const getWorkOrders = () =>
  api.get('/api/v1/work-orders').then(r => r.data);

// ── Workflow ──────────────────────────────────────────────────────────────────
export const getTicketSteps = (ticketId) =>
  api.get(`/api/v1/workflow/tickets/${ticketId}/steps`).then(r => r.data);

export const getTicketAudit = (ticketId) =>
  api.get(`/api/v1/workflow/tickets/${ticketId}/audit`).then(r => r.data);

export const performWorkflowAction = (ticketId, body) =>
  api.post(`/api/v1/workflow/tickets/${ticketId}/action`, body).then(r => r.data);

export const openTicketWorkflow = (ticketId) =>
  api.post(`/api/v1/workflow/tickets/${ticketId}/open`).then(r => r.data);

// ── People ────────────────────────────────────────────────────────────────────
export const getPeople = (params = {}) =>
  api.get('/api/v1/people', { params }).then(r => r.data);

export const getPerson = (id) =>
  api.get(`/api/v1/people/${id}`).then(r => r.data);

// ── Daily Plans ──────────────────────────────────────────────────────────────
export const getDailyPlanWorkers = (params = {}) =>
  api.get('/api/v1/daily-plans/workers', { params }).then(r => r.data);

export const generateDailyPlan = (body) =>
  api.post('/api/v1/daily-plans/generate', body).then(r => r.data);

export const getDailyPlans = (params = {}) =>
  api.get('/api/v1/daily-plans', { params }).then(r => r.data);

export const getDailyPlan = (id) =>
  api.get(`/api/v1/daily-plans/${id}`).then(r => r.data);

// ── Admin Chat (SSE) ──────────────────────────────────────────────────────────
export const streamAdminChat = async (messages, cityId = 'tel-aviv', onChunk, onDone) => {
  const token = localStorage.getItem('token');
  const response = await fetch('/api/v1/admin/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ messages, city_id: cityId }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Chat error');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6);
      if (raw === '[DONE]') { onDone?.(); return; }
      try {
        const parsed = JSON.parse(raw);
        if (parsed.text) onChunk(parsed.text);
        if (parsed.error) throw new Error(parsed.error);
      } catch {}
    }
  }
  onDone?.();
};
