import axios from 'axios';

const api = axios.create({ baseURL: '' });

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token');
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

export const login = (username, password) =>
  api.post('/api/auth/login', { username, password }).then(r => r.data);

export const getMe = () =>
  api.get('/api/auth/me').then(r => r.data);

export const getTickets = (params = {}) =>
  api.get('/api/tickets', { params }).then(r => r.data);

export const getTicket = (id) =>
  api.get(`/api/tickets/${id}`).then(r => r.data);

export const updateTicket = (id, status) =>
  api.patch(`/api/tickets/${id}`, { status }).then(r => r.data);

export const postDetection = (data) =>
  api.post('/api/detections', data).then(r => r.data);

export const getStats = () =>
  api.get('/api/stats/summary').then(r => r.data);

export const getWorkOrders = () =>
  api.get('/api/work-orders').then(r => r.data);
