import { useState, useEffect, useCallback } from 'react';
import MapView from './components/MapView';
import DefectDrawer from './components/DefectDrawer';
import StatsBar from './components/StatsBar';
import SensorSimulator from './components/SensorSimulator';
import { useWebSocket } from './hooks/useWebSocket';
import { login as apiLogin, getMe } from './api/client';

function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await apiLogin(username, password);
      localStorage.setItem('token', res.access_token);
      onLogin(res.user);
    } catch {
      setError('Invalid credentials. Try admin / admin123');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🏗️</div>
          <h1 className="text-2xl font-bold text-white">CityInspect</h1>
          <p className="text-slate-400 text-sm mt-1">Urban Infrastructure Detection System</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-700 rounded-2xl p-6 space-y-4">
          <div>
            <label className="text-slate-400 text-xs font-mono uppercase tracking-wider block mb-1">Username</label>
            <input
              className="w-full bg-slate-800 border border-slate-600 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500 transition-colors"
              value={username} onChange={e => setUsername(e.target.value)}
              placeholder="admin"
            />
          </div>
          <div>
            <label className="text-slate-400 text-xs font-mono uppercase tracking-wider block mb-1">Password</label>
            <input
              type="password"
              className="w-full bg-slate-800 border border-slate-600 rounded-xl px-4 py-2.5 text-white focus:outline-none focus:border-blue-500 transition-colors"
              value={password} onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold py-3 rounded-xl transition-colors"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
          <p className="text-slate-500 text-xs text-center">
            Demo: admin/admin123 · viewer/demo123
          </p>
        </form>
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [wsEvent, setWsEvent] = useState(null);
  const [showSimulator, setShowSimulator] = useState(true);

  // Auto-login if token exists
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      getMe().then(setUser).catch(() => localStorage.removeItem('token')).finally(() => setAuthChecked(true));
    } else {
      setAuthChecked(true);
    }
  }, []);

  const handleWsMessage = useCallback((msg) => {
    setWsEvent(msg);
  }, []);

  useWebSocket(handleWsMessage);

  if (!authChecked) return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="text-slate-400 animate-pulse">Loading...</div>
    </div>
  );

  if (!user) return <LoginScreen onLogin={setUser} />;

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-white overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-2.5 bg-slate-900 border-b border-slate-800 shrink-0 z-10">
        <div className="flex items-center gap-3">
          <span className="text-xl">🏗️</span>
          <span className="font-bold text-white">CityInspect</span>
          <span className="text-slate-500 text-xs font-mono">v2.0</span>
          <div className="flex items-center gap-1 bg-green-950 border border-green-800 rounded-full px-2.5 py-0.5 text-xs text-green-400">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            Live
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowSimulator(p => !p)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-colors font-mono ${
              showSimulator
                ? 'bg-blue-950 border-blue-700 text-blue-400'
                : 'bg-slate-800 border-slate-600 text-slate-400'
            }`}
          >
            📡 Simulator
          </button>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center text-xs font-bold">
              {user.full_name?.[0] || 'U'}
            </div>
            <span className="text-sm text-slate-300">{user.full_name}</span>
            <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded-full capitalize">{user.role}</span>
          </div>
          <button
            onClick={() => { localStorage.removeItem('token'); setUser(null); }}
            className="text-xs text-slate-500 hover:text-red-400 transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <StatsBar wsEvent={wsEvent} />

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Simulator sidebar */}
        {showSimulator && (
          <div className="w-64 shrink-0 overflow-hidden">
            <SensorSimulator onDetection={() => {}} />
          </div>
        )}

        {/* Map */}
        <div className="flex-1 relative">
          <MapView
            onSelectTicket={setSelectedTicket}
            wsEvent={wsEvent}
          />
        </div>
      </div>

      {/* Defect Drawer */}
      {selectedTicket && (
        <DefectDrawer
          ticket={selectedTicket}
          onClose={() => setSelectedTicket(null)}
          onStatusChange={(updated) => {
            setSelectedTicket(prev => ({ ...prev, status: updated.status }));
          }}
        />
      )}
    </div>
  );
}
