import { useEffect, useState } from 'react';
import { getPeople } from '../api/client';

const ROLE_META = {
  city_manager:          { icon: '🏙️', label: 'מנהל עיר',      color: 'text-purple-300 bg-purple-950 border-purple-700' },
  infrastructure_manager:{ icon: '🏗️', label: 'מנהל תשתיות',   color: 'text-blue-300 bg-blue-950 border-blue-700' },
  work_manager:          { icon: '👷', label: 'מנהל עבודה',     color: 'text-cyan-300 bg-cyan-950 border-cyan-700' },
  inspector:             { icon: '🔍', label: 'מפקח',           color: 'text-yellow-300 bg-yellow-950 border-yellow-700' },
  contractor:            { icon: '🔨', label: 'קבלן',           color: 'text-orange-300 bg-orange-950 border-orange-700' },
  field_worker:          { icon: '⛏️', label: 'פועל שטח',       color: 'text-green-300 bg-green-950 border-green-700' },
};

const ROLE_ORDER = ['city_manager','infrastructure_manager','work_manager','inspector','contractor','field_worker'];

function WorkloadBar({ value, max = 10 }) {
  const pct = Math.min(100, (value / max) * 100);
  const color = pct > 75 ? 'bg-red-500' : pct > 50 ? 'bg-orange-500' : 'bg-green-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-slate-400 w-4 text-right">{value}</span>
    </div>
  );
}

function PersonCard({ person }) {
  const meta = ROLE_META[person.role] || { icon: '👤', label: person.role, color: 'text-slate-300 bg-slate-800 border-slate-600' };

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-3 hover:border-slate-500 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-lg shrink-0">{meta.icon}</span>
          <div className="min-w-0">
            <div className="text-white text-sm font-semibold truncate">{person.name}</div>
            <span className={`text-xs px-1.5 py-0.5 rounded border ${meta.color} font-mono`}>
              {meta.label}
            </span>
          </div>
        </div>
        <div className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${person.is_active ? 'bg-green-400' : 'bg-slate-600'}`} />
      </div>

      <div className="mt-2 space-y-1">
        <WorkloadBar value={person.current_workload} />
        <div className="text-xs text-slate-500 font-mono">עומס: {person.current_workload} טיקטים</div>
      </div>

      {person.specialties?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {person.specialties.map(s => (
            <span key={s} className="text-xs bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded font-mono">
              {s}
            </span>
          ))}
        </div>
      )}

      <div className="mt-2 flex gap-3 text-xs text-slate-500">
        {person.phone && <span>📞 {person.phone}</span>}
        {person.whatsapp_id && <span>💬 {person.whatsapp_id}</span>}
      </div>
    </div>
  );
}

export default function PeoplePanel({ cityId = 'tel-aviv' }) {
  const [people, setPeople] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');

  useEffect(() => {
    setLoading(true);
    getPeople({ city_id: cityId })
      .then(setPeople)
      .catch(() => setPeople([]))
      .finally(() => setLoading(false));
  }, [cityId]);

  const filtered = people.filter(p => {
    const matchRole = roleFilter === 'all' || p.role === roleFilter;
    const matchText = !filter ||
      p.name.includes(filter) ||
      p.role.includes(filter) ||
      p.specialties?.some(s => s.includes(filter));
    return matchRole && matchText;
  });

  const grouped = ROLE_ORDER.reduce((acc, role) => {
    const group = filtered.filter(p => p.role === role);
    if (group.length) acc[role] = group;
    return acc;
  }, {});

  const totalLoad = people.reduce((s, p) => s + p.current_workload, 0);
  const overloaded = people.filter(p => p.current_workload >= 5).length;

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-800 bg-slate-900 shrink-0">
        <div className="flex items-center justify-between mb-2">
          <div className="text-white font-semibold text-sm">👥 אנשי קשר — {cityId}</div>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span>{people.length} אנשים</span>
            <span className="text-orange-400">{overloaded} עמוסים</span>
            <span>עומס כולל: {totalLoad}</span>
          </div>
        </div>

        {/* Filters */}
        <div className="flex gap-2">
          <input
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="חפש שם / תפקיד / מומחיות..."
            className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-xs placeholder-slate-500 focus:outline-none focus:border-blue-500"
            style={{ direction: 'rtl' }}
          />
          <select
            value={roleFilter}
            onChange={e => setRoleFilter(e.target.value)}
            className="bg-slate-800 border border-slate-600 rounded-lg px-2 py-1.5 text-white text-xs focus:outline-none"
          >
            <option value="all">כל התפקידים</option>
            {ROLE_ORDER.map(r => (
              <option key={r} value={r}>{ROLE_META[r]?.label || r}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {loading && (
          <div className="flex items-center justify-center h-32 text-slate-400">
            <div className="animate-spin text-2xl">⚙️</div>
          </div>
        )}

        {!loading && people.length === 0 && (
          <div className="text-center py-8 text-slate-500">
            <div className="text-3xl mb-2">👥</div>
            <div className="text-sm">לא נמצאו אנשי קשר</div>
            <div className="text-xs mt-1">
              ודא שה-contacts.yaml הוטען (/api/v1/people/sync)
            </div>
          </div>
        )}

        {Object.entries(grouped).map(([role, members]) => {
          const meta = ROLE_META[role] || { label: role, icon: '👤' };
          return (
            <div key={role}>
              <div className="flex items-center gap-2 mb-2">
                <span>{meta.icon}</span>
                <span className="text-slate-400 text-xs font-mono uppercase tracking-wider">{meta.label}</span>
                <span className="text-slate-600 text-xs">({members.length})</span>
              </div>
              <div className="space-y-2 mr-4">
                {members.map(p => <PersonCard key={p.id} person={p} />)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
