import { useEffect, useState } from 'react';
import { AreaChart, Area, ResponsiveContainer, Tooltip } from 'recharts';
import { getStats, getCityHealth } from '../api/client';

const GRADE_COLORS = {
  A: 'text-green-400 bg-green-950/50 border-green-700',
  B: 'text-blue-400 bg-blue-950/50 border-blue-700',
  C: 'text-yellow-400 bg-yellow-950/50 border-yellow-700',
  D: 'text-orange-400 bg-orange-950/50 border-orange-700',
  F: 'text-red-400 bg-red-950/50 border-red-700',
};

export default function StatsBar({ wsEvent }) {
  const [stats, setStats] = useState(null);
  const [health, setHealth] = useState(null);

  const load = () => {
    getStats().then(setStats).catch(() => {});
    getCityHealth().then(setHealth).catch(() => {});
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { if (wsEvent) load(); }, [wsEvent]);

  if (!stats) return (
    <div className="h-16 bg-slate-900 border-b border-slate-800 flex items-center justify-center">
      <div className="text-slate-500 text-sm animate-pulse">טוען נתונים...</div>
    </div>
  );

  const grade = health?.health?.grade || '—';
  const gradeStyle = GRADE_COLORS[grade] || 'text-slate-400 bg-slate-900 border-slate-700';

  const cards = [
    {
      label: 'טיקטים פתוחים',
      value: stats.open_tickets ?? stats.total_open ?? 0,
      color: 'text-blue-400',
      icon: '📋',
    },
    {
      label: 'קריטי',
      value: stats.critical_tickets ?? stats.critical_count ?? 0,
      color: 'text-red-400',
      icon: '🚨',
      pulse: (stats.critical_tickets ?? stats.critical_count ?? 0) > 0,
    },
    {
      label: 'בביצוע',
      value: stats.by_status?.in_progress ?? stats.in_progress ?? 0,
      color: 'text-yellow-400',
      icon: '🔧',
    },
    {
      label: 'טופלו היום',
      value: stats.resolved_today ?? 0,
      color: 'text-green-400',
      icon: '✅',
    },
    {
      label: 'הפרת SLA',
      value: stats.sla_breached ?? 0,
      color: (stats.sla_breached ?? 0) > 0 ? 'text-rose-400' : 'text-slate-500',
      icon: '⚠️',
      pulse: (stats.sla_breached ?? 0) > 0,
      alert: (stats.sla_breached ?? 0) > 0,
    },
    {
      label: 'שלבים באיחור',
      value: stats.overdue_steps ?? 0,
      color: (stats.overdue_steps ?? 0) > 0 ? 'text-orange-400' : 'text-slate-500',
      icon: '⏰',
    },
  ];

  return (
    <div className="h-16 bg-slate-900 border-b border-slate-800 flex items-stretch px-4 gap-0 shrink-0 overflow-x-auto">
      {/* City Health Score — first card */}
      {health?.health && (
        <div className={`flex items-center gap-2 px-4 border-r border-slate-800 shrink-0 ${gradeStyle.split(' ').slice(1).join(' ')}`}>
          <div className="text-center">
            <div className={`text-2xl font-black font-mono leading-none ${gradeStyle.split(' ')[0]}`}>
              {grade}
            </div>
            <div className="text-slate-500 text-xs">בריאות</div>
          </div>
          <div className="hidden lg:block">
            <div className="text-white text-sm font-bold font-mono">{health.health.health_score}/100</div>
            <div className="text-slate-500 text-xs">{health.health.metrics?.defect_trend === 'declining' ? '📉 ירידה' : health.health.metrics?.defect_trend === 'rising' ? '📈 עלייה' : '➡️ יציב'}</div>
          </div>
        </div>
      )}

      {cards.map(c => (
        <div
          key={c.label}
          className={`flex items-center gap-2 px-4 border-r border-slate-800 last:border-0 shrink-0 ${
            c.alert ? 'bg-rose-950/30' : ''
          }`}
        >
          <span className={c.pulse ? 'animate-pulse' : ''}>{c.icon}</span>
          <div>
            <div className={`text-xl font-bold font-mono ${c.color} leading-none flex items-center gap-1`}>
              {c.value}
              {c.pulse && c.alert && (
                <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-ping inline-block" />
              )}
            </div>
            <div className="text-slate-500 text-xs">{c.label}</div>
          </div>
        </div>
      ))}

      {/* Sparkline */}
      <div className="flex items-center gap-2 ml-auto pl-4 shrink-0">
        <span className="text-slate-500 text-xs hidden lg:block">זיהויים/שעה</span>
        <div className="w-28 h-10">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={stats.detections_per_hour ?? []}>
              <Area
                type="monotone"
                dataKey="count"
                stroke="#3b82f6"
                fill="#3b82f620"
                strokeWidth={1.5}
                dot={false}
              />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 6, fontSize: 11 }}
                labelStyle={{ color: '#94a3b8' }}
                itemStyle={{ color: '#60a5fa' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
