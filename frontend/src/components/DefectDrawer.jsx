import { useEffect, useState } from 'react';
import { updateTicket, getTicket } from '../api/client';

const COMPASS = (deg) => {
  const dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
  return dirs[Math.round(deg / 22.5) % 16];
};

const fmt = (n, dec = 2) => (n ?? 0).toFixed(dec);

const DEFECT_LABELS = {
  pothole: '🕳️ Pothole',
  road_crack: '⚠️ Road Crack',
  broken_light: '💡 Broken Light',
  drainage_blocked: '🌊 Drainage Blocked',
  sidewalk: '🧱 Broken Sidewalk',
};

const SEV_COLORS = {
  critical: { bg: 'bg-red-600',    text: 'text-red-400',    label: '🔴 CRITICAL' },
  high:     { bg: 'bg-orange-500', text: 'text-orange-400', label: '🟠 HIGH' },
  medium:   { bg: 'bg-yellow-500', text: 'text-yellow-400', label: '🟡 MEDIUM' },
  low:      { bg: 'bg-green-500',  text: 'text-green-400',  label: '🟢 LOW' },
};

const STATUS_FLOW = ['new', 'verified', 'assigned', 'in_progress', 'resolved'];
const STATUS_LABELS = {
  new: '🆕 New', verified: '✅ Verified', assigned: '📋 Assigned',
  in_progress: '🔧 In Progress', resolved: '✔️ Resolved',
};

function PotholeSection({ d }) {
  const L = d.defect_length_cm || 0;
  const W = d.defect_width_cm || 0;
  const D = d.defect_depth_cm || 0;

  // SVG cross-section
  const mid = 100;
  const halfW = Math.min(60, W * 0.5);
  const depth = Math.min(35, D * 1.5);

  return (
    <div className="bg-slate-900 border border-slate-600 rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2 text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest">
        <span>📐</span><span>Defect Geometry</span>
        <span className="ml-auto text-slate-500 font-normal normal-case">Estimated by sensor</span>
      </div>

      {/* Table */}
      <table className="w-full text-sm font-mono">
        <tbody>
          {[
            ['Length',         fmt(L, 1), 'cm'],
            ['Width',          fmt(W, 1), 'cm'],
            ['Depth',          fmt(D, 1), 'cm'],
            ['Surface Area',   fmt(d.surface_area_m2, 4), 'm²'],
            ['Volume',         fmt(d.defect_volume_m3, 6), 'm³'],
            ['Repair Material',fmt(d.repair_material_m3, 6), 'm³'],
          ].map(([label, val, unit]) => (
            <tr key={label} className="border-b border-slate-800">
              <td className="py-1.5 text-slate-400 pr-4">{label}</td>
              <td className="py-1.5 text-white text-right font-bold tabular-nums">{val}</td>
              <td className="py-1.5 text-slate-500 pl-2">{unit}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* SVG Cross-section */}
      <div className="pt-2">
        <div className="text-xs text-slate-500 font-mono mb-1">Cross-section view</div>
        <svg viewBox="0 0 200 70" className="w-full h-16 rounded bg-slate-950">
          {/* Road surface */}
          <rect x="0" y="15" width="200" height="8" fill="#555" rx="1"/>
          <text x="5" y="11" fill="#888" fontSize="7" fontFamily="monospace">ROAD SURFACE</text>
          {/* Pothole */}
          <path
            d={`M ${mid - halfW},23 Q ${mid - halfW * 0.3},${23 + depth} ${mid},${23 + depth} Q ${mid + halfW * 0.3},${23 + depth} ${mid + halfW},23`}
            stroke="#ef4444" strokeWidth="1.5" fill="#1e1e1e"
          />
          {/* Depth arrow */}
          <line x1={mid} y1="24" x2={mid} y2={22 + depth} stroke="#ef4444" strokeWidth="0.8" strokeDasharray="2,2"/>
          <text x={mid + 3} y={24 + depth * 0.5} fill="#ef4444" fontSize="6" fontFamily="monospace">
            ~{fmt(D, 0)}cm
          </text>
          {/* Width arrow */}
          <line x1={mid - halfW} y1="60" x2={mid + halfW} y2="60" stroke="#3b82f6" strokeWidth="0.8" markerEnd="url(#arr)"/>
          <text x={mid - 12} y="68" fill="#3b82f6" fontSize="6" fontFamily="monospace">{fmt(W, 0)}cm</text>
        </svg>
      </div>
    </div>
  );
}

function EnvSection({ d }) {
  const hotAsphalt = (d.asphalt_temp_c || 0) > 30;
  const conditionEmoji = {
    Clear: '☀️', Cloudy: '☁️', Rain: '🌧️',
    Fog: '🌫️', 'Partly Cloudy': '⛅',
  }[d.weather_condition] || '🌤️';

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 space-y-3">
      <div className="text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest">
        🌡️ Environmental Conditions
      </div>
      <div className="grid grid-cols-2 gap-y-2 text-sm">
        {[
          ['Air Temp',   `${fmt(d.ambient_temp_c, 1)}°C`, ''],
          ['Asphalt',    `${fmt(d.asphalt_temp_c, 1)}°C`, hotAsphalt ? '⚠️' : ''],
          ['Weather',    `${conditionEmoji} ${d.weather_condition}`, ''],
          ['Wind',       `${fmt(d.wind_speed_kmh, 1)} km/h`, ''],
          ['Humidity',   `${fmt(d.humidity_pct, 1)}%`, ''],
          ['Visibility', `${(d.visibility_m || 0).toLocaleString()} m`, ''],
        ].map(([label, val, warn]) => (
          <div key={label} className="flex flex-col">
            <span className="text-slate-500 text-xs font-mono">{label}</span>
            <span className={`font-semibold ${warn ? 'text-orange-400' : 'text-white'}`}>
              {val} {warn}
            </span>
          </div>
        ))}
      </div>
      {hotAsphalt && (
        <div className="text-xs text-orange-400 bg-orange-950 border border-orange-800 rounded-lg px-3 py-2 font-mono">
          ⚠️ Asphalt temp above 30°C may accelerate defect growth
        </div>
      )}
    </div>
  );
}

export default function DefectDrawer({ ticket, onClose, onStatusChange }) {
  const [fullTicket, setFullTicket] = useState(ticket);
  const [loading, setLoading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);

  useEffect(() => {
    if (!ticket) return;
    setLoading(true);
    getTicket(ticket.id)
      .then(setFullTicket)
      .catch(() => setFullTicket(ticket))
      .finally(() => setLoading(false));
  }, [ticket?.id]);

  if (!ticket) return null;

  const t = fullTicket;
  const d = t.detections?.[0] || {};
  const sev = SEV_COLORS[t.severity] || SEV_COLORS.low;

  const handleStatus = async (newStatus) => {
    setStatusLoading(true);
    try {
      const updated = await updateTicket(t.id, newStatus);
      setFullTicket({ ...t, status: newStatus });
      onStatusChange?.(updated);
    } finally {
      setStatusLoading(false);
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '—';
    const dt = new Date(iso);
    return dt.toLocaleString('en-GB', {
      weekday: 'long', day: '2-digit', month: 'short',
      year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  };

  const nextStatus = STATUS_FLOW[STATUS_FLOW.indexOf(t.status) + 1];
  const currentIdx = STATUS_FLOW.indexOf(t.status);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 z-[9998] backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed top-0 right-0 h-full w-full max-w-[480px] bg-slate-950 border-l border-slate-700 z-[9999] flex flex-col shadow-2xl overflow-hidden"
           style={{ animation: 'slideIn 0.25s ease-out' }}>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 bg-slate-900 shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{DEFECT_LABELS[t.defect_type]?.split(' ')[0]}</span>
            <div>
              <div className="text-white font-bold text-sm">Ticket #{t.id}</div>
              <div className="text-slate-400 text-xs font-mono">{t.address}</div>
            </div>
          </div>
          <button onClick={onClose}
            className="text-slate-400 hover:text-white w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-700 text-xl transition-colors">
            ✕
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">

          {loading && (
            <div className="flex items-center justify-center h-24 text-slate-400">
              <div className="animate-spin text-2xl">⚙️</div>
            </div>
          )}

          {/* Photo */}
          {d.image_url && (
            <div className="rounded-xl overflow-hidden border border-slate-700">
              <img
                src={d.image_url}
                alt={d.image_caption || 'Defect photo'}
                className="w-full h-48 object-cover"
                onError={e => { e.target.style.display = 'none'; }}
              />
              {d.image_caption && (
                <div className="px-3 py-1.5 bg-slate-900 text-slate-400 text-xs italic">
                  {d.image_caption}
                </div>
              )}
            </div>
          )}

          {/* Severity + type badges */}
          <div className="flex gap-2 flex-wrap">
            <span className={`${sev.bg} text-white text-xs font-bold px-3 py-1 rounded-full`}>
              {sev.label}
            </span>
            <span className="bg-slate-700 text-white text-xs font-bold px-3 py-1 rounded-full">
              {DEFECT_LABELS[t.defect_type] || t.defect_type}
            </span>
            <span className="bg-slate-800 text-slate-300 text-xs px-3 py-1 rounded-full border border-slate-600">
              {STATUS_LABELS[t.status] || t.status}
            </span>
            {t.detection_count > 1 && (
              <span className="bg-purple-900 text-purple-300 text-xs px-3 py-1 rounded-full border border-purple-700">
                📡 {t.detection_count} reports
              </span>
            )}
          </div>

          {/* Time & Location */}
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 space-y-2">
            <div className="text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest mb-2">
              📍 Location & Time
            </div>
            <div className="text-sm space-y-1.5">
              <div className="flex items-start gap-2">
                <span className="text-slate-500 w-20 shrink-0">Date</span>
                <span className="text-white">{formatDate(d.detected_at || t.created_at)}</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-slate-500 w-20 shrink-0">Address</span>
                <span className="text-white">{t.address}</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-slate-500 w-20 shrink-0">GPS</span>
                <span className="text-slate-300 font-mono text-xs">
                  {fmt(t.lat, 6)}, {fmt(t.lng, 6)}
                </span>
                <button
                  onClick={() => navigator.clipboard.writeText(`${t.lat},${t.lng}`)}
                  className="text-xs text-blue-400 hover:text-blue-300 ml-auto"
                >📋</button>
              </div>
            </div>
          </div>

          {/* Vehicle & System */}
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
            <div className="text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest mb-3">
              🚗 Vehicle & System
            </div>
            <div className="grid grid-cols-2 gap-y-2 text-sm">
              {[
                ['Vehicle ID',   d.vehicle_id || '—'],
                ['Model',        d.vehicle_model || '—'],
                ['Speed',        `${fmt(d.vehicle_speed_kmh, 1)} km/h`],
                ['Heading',      `${fmt(d.vehicle_heading_deg, 0)}° (${COMPASS(d.vehicle_heading_deg || 0)})`],
                ['Sensor',       d.vehicle_sensor_version || '—'],
                ['Reported by',  d.reported_by || 'simulator'],
              ].map(([label, val]) => (
                <div key={label} className="flex flex-col">
                  <span className="text-slate-500 text-xs font-mono">{label}</span>
                  <span className="text-white font-medium text-xs">{val}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Engineering Geometry */}
          <PotholeSection d={d} />

          {/* Environmental */}
          <EnvSection d={d} />

          {/* Notes */}
          {d.notes && (
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
              <div className="text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest mb-2">
                📝 Field Notes
              </div>
              <p className="text-slate-300 text-sm italic">"{d.notes}"</p>
            </div>
          )}

          {/* Status Progress */}
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
            <div className="text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest mb-3">
              📊 Status Progress
            </div>
            <div className="flex items-center gap-1">
              {STATUS_FLOW.map((s, i) => (
                <div key={s} className="flex items-center gap-1 flex-1">
                  <div className={`h-2 rounded-full flex-1 transition-colors ${i <= currentIdx ? 'bg-blue-500' : 'bg-slate-700'}`} />
                  {i === currentIdx && (
                    <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                  )}
                </div>
              ))}
            </div>
            <div className="flex justify-between mt-1">
              {STATUS_FLOW.map((s, i) => (
                <span key={s} className={`text-xs font-mono ${i <= currentIdx ? 'text-blue-400' : 'text-slate-600'}`}>
                  {s.replace('_', ' ')}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Action bar */}
        <div className="border-t border-slate-800 px-5 py-4 bg-slate-900 shrink-0">
          {nextStatus ? (
            <button
              onClick={() => handleStatus(nextStatus)}
              disabled={statusLoading}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold py-3 rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              {statusLoading ? '⏳ Updating...' : `→ Move to: ${STATUS_LABELS[nextStatus]}`}
            </button>
          ) : (
            <div className="text-center text-green-400 font-mono text-sm py-2">
              ✔️ Ticket Resolved
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>
    </>
  );
}
