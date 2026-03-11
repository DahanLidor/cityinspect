import { useEffect, useState } from 'react';
import { AreaChart, Area, ResponsiveContainer, Tooltip } from 'recharts';
import { getStats } from '../api/client';

export default function StatsBar({ wsEvent }) {
  const [stats, setStats] = useState(null);

  const load = () => getStats().then(setStats).catch(() => {});

  useEffect(() => { load(); }, []);
  useEffect(() => { if (wsEvent) load(); }, [wsEvent]);

  if (!stats) return (
    <div className="h-16 bg-slate-900 border-b border-slate-800 flex items-center justify-center">
      <div className="text-slate-500 text-sm animate-pulse">Loading stats...</div>
    </div>
  );

  const cards = [
    { label: 'Open Tickets',    value: stats.total_open,        color: 'text-blue-400',   icon: '📋' },
    { label: 'Critical',        value: stats.critical_count,    color: 'text-red-400',    icon: '🚨' },
    { label: 'In Progress',     value: stats.in_progress,       color: 'text-yellow-400', icon: '🔧' },
    { label: 'Resolved Today',  value: stats.resolved_today,    color: 'text-green-400',  icon: '✅' },
    { label: 'Last Hour',       value: stats.detections_last_hour, color: 'text-purple-400', icon: '📡' },
  ];

  return (
    <div className="h-16 bg-slate-900 border-b border-slate-800 flex items-stretch px-4 gap-1 shrink-0">
      {cards.map(c => (
        <div key={c.label} className="flex items-center gap-2 px-4 border-r border-slate-800 last:border-0">
          <span>{c.icon}</span>
          <div>
            <div className={`text-xl font-bold font-mono ${c.color} leading-none`}>{c.value}</div>
            <div className="text-slate-500 text-xs">{c.label}</div>
          </div>
        </div>
      ))}

      {/* Sparkline */}
      <div className="flex items-center gap-2 ml-auto pl-4">
        <span className="text-slate-500 text-xs">Detections/hr</span>
        <div className="w-28 h-10">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={stats.detections_per_hour}>
              <Area type="monotone" dataKey="count" stroke="#3b82f6" fill="#3b82f620" strokeWidth={1.5} dot={false} />
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
