import { useEffect, useState } from 'react';
import { updateTicket, getTicket } from '../api/client';
import WorkflowTimeline from './WorkflowTimeline';

const COMPASS = (deg) => {
  const dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
  return dirs[Math.round(deg / 22.5) % 16];
};

const fmt = (n, dec = 2) => (n ?? 0).toFixed(dec);

const DEFECT_LABELS = {
  pothole:          '🕳️ בור בכביש',
  road_crack:       '⚠️ סדק בכביש',
  broken_light:     '💡 פנס תקול',
  drainage_blocked: '🌊 ביוב חסום',
  sidewalk:         '🧱 מדרכה שבורה',
};

const SEV_COLORS = {
  critical: { bg: 'bg-red-600',    text: 'text-red-400',    label: '🔴 קריטי' },
  high:     { bg: 'bg-orange-500', text: 'text-orange-400', label: '🟠 גבוה' },
  medium:   { bg: 'bg-yellow-500', text: 'text-yellow-400', label: '🟡 בינוני' },
  low:      { bg: 'bg-green-500',  text: 'text-green-400',  label: '🟢 נמוך' },
};

const STATUS_FLOW   = ['new', 'verified', 'assigned', 'in_progress', 'resolved'];
const STATUS_LABELS = {
  new: '🆕 חדש', verified: '✅ אומת', assigned: '📋 שויך',
  in_progress: '🔧 בביצוע', resolved: '✔️ טופל',
};

// ── AI Pipeline notes parser (10-agent) ──────────────────────────────────────
function RiskBadge({ level }) {
  const cfg = { critical: 'bg-red-600 text-white', high: 'bg-orange-500 text-white', medium: 'bg-yellow-500 text-black', low: 'bg-green-600 text-white' };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${cfg[level] || 'bg-slate-600 text-white'}`}>{level}</span>;
}

function GradeBadge({ grade }) {
  const cfg = { A: 'bg-green-600', B: 'bg-blue-600', C: 'bg-yellow-500', D: 'bg-red-600' };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-bold text-white ${cfg[grade] || 'bg-slate-600'}`}>{grade}</span>;
}

function RiskCard({ risk }) {
  if (!risk || !risk.risk_score) return null;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-3">
      <div className="text-red-400 font-mono text-xs font-bold uppercase tracking-wider mb-2">⚠️ חיזוי סיכון</div>
      <div className="flex items-center justify-between mb-2">
        <div className="text-2xl font-bold text-white">{risk.risk_score}<span className="text-xs text-slate-400">/100</span></div>
        <RiskBadge level={risk.risk_level} />
      </div>
      {risk.liability_exposure_nis_monthly > 0 && (
        <div className="text-xs text-orange-300 bg-orange-950/50 rounded-lg px-2 py-1 mb-2">
          💰 חשיפת תביעות: ₪{risk.liability_exposure_nis_monthly?.toLocaleString()}/חודש
        </div>
      )}
      {risk.recommendation && <div className="text-xs text-slate-300">{risk.recommendation}</div>}
    </div>
  );
}

function RepairCard({ repair }) {
  if (!repair || repair.method === 'manual_assessment') return null;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-3">
      <div className="text-green-400 font-mono text-xs font-bold uppercase tracking-wider mb-2">🔧 המלצת תיקון</div>
      <div className="flex items-center justify-between mb-2">
        <div className="text-white text-sm font-semibold">{repair.method_he || repair.method}</div>
        <div className="text-green-400 font-bold text-sm">₪{repair.estimated_cost_nis?.toLocaleString()}</div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-slate-400 mb-2">
        <div>⏱️ {repair.estimated_hours} שעות</div>
        <div>👥 {repair.team_size} עובדים</div>
      </div>
      {repair.materials?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {repair.materials.map((m, i) => (
            <span key={i} className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded-full">
              {m.name || m} {m.quantity ? `(${m.quantity} ${m.unit || ''})` : ''}
            </span>
          ))}
        </div>
      )}
      {repair.equipment_needed?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {repair.equipment_needed.map((e, i) => (
            <span key={i} className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">🔧 {e}</span>
          ))}
        </div>
      )}
      {!repair.can_repair_today && repair.weather_warning && (
        <div className="text-xs text-orange-300 bg-orange-950/50 rounded-lg px-2 py-1 mt-2">🌧️ {repair.weather_warning}</div>
      )}
    </div>
  );
}

function GeometryCard({ geo }) {
  if (!geo || geo.confidence === 0) return null;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-3">
      <div className="text-purple-400 font-mono text-xs font-bold uppercase tracking-wider mb-2">📐 מידות משוערות</div>
      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <div className="text-lg font-bold text-white">{geo.estimated_width_cm?.toFixed(0)}</div>
          <div className="text-xs text-slate-500">רוחב (ס"מ)</div>
        </div>
        <div>
          <div className="text-lg font-bold text-white">{geo.estimated_length_cm?.toFixed(0)}</div>
          <div className="text-xs text-slate-500">אורך (ס"מ)</div>
        </div>
        <div>
          <div className="text-lg font-bold text-white">{geo.estimated_depth_cm?.toFixed(0)}</div>
          <div className="text-xs text-slate-500">עומק (ס"מ)</div>
        </div>
      </div>
      <div className="flex items-center justify-between mt-2 text-xs text-slate-400">
        <span>שטח: {geo.estimated_area_m2?.toFixed(2)} מ"ר</span>
        <span>שיטה: {geo.method === 'camera_intrinsics' ? '📷 עדשה' : geo.method === 'lidar' ? '📡 LiDAR' : '📏 הערכה'}</span>
      </div>
    </div>
  );
}

function TemporalCard({ temporal }) {
  if (!temporal || temporal.tracking === 'first_observation') return null;
  const trendIcon = temporal.trend === 'worsening' ? '📈' : temporal.trend === 'improving' ? '📉' : '➡️';
  const trendColor = temporal.trend === 'worsening' ? 'text-red-400' : temporal.trend === 'improving' ? 'text-green-400' : 'text-slate-400';
  const trendLabel = temporal.trend === 'worsening' ? 'מחמיר' : temporal.trend === 'improving' ? 'משתפר' : 'יציב';
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-3">
      <div className="text-blue-400 font-mono text-xs font-bold uppercase tracking-wider mb-2">📊 מעקב זמני</div>
      <div className="flex items-center justify-between">
        <div className={`text-sm font-bold ${trendColor}`}>{trendIcon} {trendLabel}</div>
        <div className="text-xs text-slate-400">{temporal.observations} תצפיות · {temporal.days_open} ימים</div>
      </div>
      {temporal.alert && (
        <div className="text-xs text-red-300 bg-red-950/50 rounded-lg px-2 py-1 mt-2">🚨 מפגע מחמיר ללא טיפול!</div>
      )}
    </div>
  );
}

function FusionCard({ fusion }) {
  if (!fusion || !fusion.overall_confidence) return null;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-3">
      <div className="text-cyan-400 font-mono text-xs font-bold uppercase tracking-wider mb-2">🎯 איכות צילום</div>
      <div className="flex items-center justify-between mb-2">
        <div className="text-white text-sm">ציון כולל: <span className="font-bold">{(fusion.overall_confidence * 100).toFixed(0)}%</span></div>
        <GradeBadge grade={fusion.capture_grade} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs text-center">
        <div><div className="text-slate-400">מיקום</div><div className="text-white font-mono">{(fusion.location_confidence * 100).toFixed(0)}%</div></div>
        <div><div className="text-slate-400">תמונה</div><div className="text-white font-mono">{(fusion.image_confidence * 100).toFixed(0)}%</div></div>
        <div><div className="text-slate-400">גיאומטריה</div><div className="text-white font-mono">{(fusion.geometry_confidence * 100).toFixed(0)}%</div></div>
      </div>
      {fusion.warnings?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {fusion.warnings.map((w, i) => (
            <span key={i} className="text-xs bg-yellow-950/50 text-yellow-300 px-2 py-0.5 rounded-full">⚠️ {w}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function AIPipelineSection({ notes }) {
  let data = null;
  try { data = JSON.parse(notes); } catch { return null; }
  if (!data || typeof data !== 'object') return null;

  // Rich cards for new agents
  const hasRich = data.risk || data.repair || data.geometry || data.temporal || data.fusion;

  // Fallback generic sections for VLM, environment, dedup, scorer
  const genericSections = [
    { key: 'vlm',         icon: '🔍', title: 'VLM Agent' },
    { key: 'environment', icon: '🌍', title: 'סביבה' },
    { key: 'dedup',       icon: '🔄', title: 'כפילויות' },
    { key: 'scorer',      icon: '📊', title: 'ציון סופי' },
  ];

  return (
    <div className="space-y-2">
      {/* Rich cards first */}
      {data.fusion && <FusionCard fusion={data.fusion} />}
      {data.geometry && <GeometryCard geo={data.geometry} />}
      {data.risk && <RiskCard risk={data.risk} />}
      {data.repair && <RepairCard repair={data.repair} />}
      {data.temporal && <TemporalCard temporal={data.temporal} />}

      {/* Generic sections */}
      {genericSections.map(({ key, icon, title }) => {
        const d = data[key];
        if (!d) return null;
        return (
          <div key={key} className="bg-slate-900 border border-slate-700 rounded-xl p-3">
            <div className="text-cyan-400 font-mono text-xs font-bold uppercase tracking-wider mb-2">
              {icon} {title}
            </div>
            <div className="space-y-1">
              {Object.entries(d).map(([k, v]) => (
                <div key={k} className="flex items-start gap-2 text-xs">
                  <span className="text-slate-500 font-mono min-w-[100px] shrink-0">{k}</span>
                  <span className="text-white break-all">
                    {typeof v === 'object' ? JSON.stringify(v, null, 0).slice(0, 120) : String(v)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* Validator badge */}
      {data.validator && (
        <div className={`text-xs text-center py-1 rounded-lg font-mono ${data.validator.valid ? 'bg-green-950/50 text-green-400' : 'bg-red-950/50 text-red-400'}`}>
          {data.validator.valid ? `✅ צילום תקין (${data.validator.quality_score}/100)` : `⚠️ בעיות בצילום: ${data.validator.issues?.map(i => i.type).join(', ')}`}
        </div>
      )}
    </div>
  );
}

// ── Environment section ───────────────────────────────────────────────────────
function EnvironmentSection({ d }) {
  let env = null;
  try { env = d.notes ? JSON.parse(d.notes)?.environment : null; } catch {}

  const weather = env?.weather || {};
  const address = env?.address || {};
  const pois    = env?.nearby_places || [];
  const risks   = env?.risk_factors  || [];
  const envScore = env?.environment_score;

  // Fallback to detection columns if no pipeline data yet
  const temp    = weather.temperature_c  ?? d.ambient_temp_c;
  const wLabel  = weather.weather_label  ?? d.weather_condition;
  const wind    = weather.wind_speed_kmh ?? d.wind_speed_kmh;
  const hum     = weather.humidity_pct   ?? d.humidity_pct;
  const precip  = weather.precipitation_mm;

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest">🌍 סביבה ומזג אוויר</div>
        {envScore != null && (
          <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded-full border ${
            envScore >= 60 ? 'bg-red-950 text-red-300 border-red-700' :
            envScore >= 30 ? 'bg-orange-950 text-orange-300 border-orange-700' :
            'bg-slate-800 text-slate-300 border-slate-600'
          }`}>סיכון סביבתי {envScore}/100</span>
        )}
      </div>

      {/* Address from OSM */}
      {address.road && (
        <div className="text-xs text-slate-300 bg-slate-800 rounded-lg px-3 py-2">
          📍 {[address.road, address.suburb, address.city].filter(Boolean).join(', ')}
        </div>
      )}

      {/* Weather grid */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        {[
          ['🌡️', 'טמפ׳', temp != null ? `${fmt(temp, 1)}°C` : '—'],
          ['🌬️', 'רוח',  wind != null ? `${fmt(wind, 0)} קמ"ש` : '—'],
          ['💧', 'לחות', hum  != null ? `${fmt(hum, 0)}%` : '—'],
          ['☁️', 'מזג',  wLabel || '—'],
          ...(precip != null ? [['🌧️', 'משקעים', `${fmt(precip, 1)} מ"מ`]] : []),
          ...(d.visibility_m ? [['👁️', 'ראות', `${(d.visibility_m).toLocaleString()} מ׳`]] : []),
        ].map(([icon, label, val]) => (
          <div key={label} className="bg-slate-800 rounded-lg p-2 text-center">
            <div className="text-base">{icon}</div>
            <div className="text-slate-500 font-mono text-[10px] mt-0.5">{label}</div>
            <div className="text-white font-bold text-[11px] mt-0.5">{val}</div>
          </div>
        ))}
      </div>

      {/* Risk factors */}
      {risks.length > 0 && (
        <div className="space-y-1">
          <div className="text-slate-500 font-mono text-xs uppercase tracking-wider">⚠️ גורמי סיכון</div>
          <div className="flex flex-wrap gap-1">
            {risks.map((r, i) => (
              <span key={i} className="text-xs bg-orange-950 text-orange-300 border border-orange-800 px-2 py-0.5 rounded-full">{r}</span>
            ))}
          </div>
        </div>
      )}

      {/* Nearby POIs */}
      {pois.length > 0 && (
        <div className="space-y-1">
          <div className="text-slate-500 font-mono text-xs uppercase tracking-wider">🏢 מקומות בסביבה</div>
          <div className="space-y-1 max-h-28 overflow-y-auto">
            {pois.slice(0, 6).map((p, i) => (
              <div key={i} className="flex items-center justify-between text-xs bg-slate-800 rounded-lg px-2 py-1">
                <span className="text-slate-300">{p.name || p.type}</span>
                <span className="text-slate-500 font-mono">{p.distance_m} מ׳</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Geometry cross-section ────────────────────────────────────────────────────
function GeometrySection({ d }) {
  const L = d.defect_length_cm || 0;
  const W = d.defect_width_cm || 0;
  const D = d.defect_depth_cm || 0;
  const mid = 100;
  const halfW = Math.min(60, W * 0.5);
  const depth = Math.min(35, D * 1.5);

  return (
    <div className="bg-slate-900 border border-slate-600 rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2 text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest">
        <span>📐</span><span>גיאומטריה</span>
        <span className="ml-auto text-slate-500 font-normal normal-case text-xs">הערכת חיישן</span>
      </div>
      <table className="w-full text-sm font-mono">
        <tbody>
          {[
            ['אורך',          fmt(L, 1), 'ס"מ'],
            ['רוחב',          fmt(W, 1), 'ס"מ'],
            ['עומק',          fmt(D, 1), 'ס"מ'],
            ['שטח פנים',      fmt(d.surface_area_m2, 4), 'מ"ר'],
            ['נפח',           fmt(d.defect_volume_m3, 6), 'מ"ק'],
            ['חומר תיקון',    fmt(d.repair_material_m3, 6), 'מ"ק'],
          ].map(([label, val, unit]) => (
            <tr key={label} className="border-b border-slate-800">
              <td className="py-1.5 text-slate-400 pr-4">{label}</td>
              <td className="py-1.5 text-white text-right font-bold tabular-nums">{val}</td>
              <td className="py-1.5 text-slate-500 pl-2">{unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <svg viewBox="0 0 200 70" className="w-full h-16 rounded bg-slate-950">
        <rect x="0" y="15" width="200" height="8" fill="#555" rx="1"/>
        <text x="5" y="11" fill="#888" fontSize="7" fontFamily="monospace">ROAD SURFACE</text>
        <path
          d={`M ${mid - halfW},23 Q ${mid - halfW * 0.3},${23 + depth} ${mid},${23 + depth} Q ${mid + halfW * 0.3},${23 + depth} ${mid + halfW},23`}
          stroke="#ef4444" strokeWidth="1.5" fill="#1e1e1e"
        />
        <line x1={mid} y1="24" x2={mid} y2={22 + depth} stroke="#ef4444" strokeWidth="0.8" strokeDasharray="2,2"/>
        <text x={mid + 3} y={24 + depth * 0.5} fill="#ef4444" fontSize="6" fontFamily="monospace">~{fmt(D, 0)}ס"מ</text>
        <line x1={mid - halfW} y1="60" x2={mid + halfW} y2="60" stroke="#3b82f6" strokeWidth="0.8"/>
        <text x={mid - 12} y="68" fill="#3b82f6" fontSize="6" fontFamily="monospace">{fmt(W, 0)}ס"מ</text>
      </svg>
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'info',     label: '📋 מידע' },
  { id: 'workflow', label: '🔄 תהליך' },
  { id: 'ai',       label: '🤖 AI' },
];

// ── Main Drawer ───────────────────────────────────────────────────────────────
export default function DefectDrawer({ ticket, onClose, onStatusChange }) {
  const [fullTicket, setFullTicket] = useState(ticket);
  const [loading, setLoading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('info');

  const loadTicket = () => {
    setLoading(true);
    getTicket(ticket.id)
      .then(setFullTicket)
      .catch(() => setFullTicket(ticket))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!ticket) return;
    loadTicket();
  }, [ticket?.id]);

  if (!ticket) return null;

  const t = fullTicket;
  const d = t.detections?.[0] || {};
  const sev = SEV_COLORS[t.severity] || SEV_COLORS.low;
  const nextStatus = STATUS_FLOW[STATUS_FLOW.indexOf(t.status) + 1];
  const currentIdx = STATUS_FLOW.indexOf(t.status);

  const handleStatus = async (newStatus) => {
    setStatusLoading(true);
    try {
      const updated = await updateTicket(t.id, newStatus);
      setFullTicket(prev => ({ ...prev, status: newStatus }));
      onStatusChange?.(updated);
    } finally {
      setStatusLoading(false);
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('he-IL', {
      weekday: 'long', day: '2-digit', month: 'short',
      year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-[9998] backdrop-blur-sm" onClick={onClose} />

      <div
        className="fixed top-0 right-0 h-full w-full max-w-[500px] bg-slate-950 border-l border-slate-700 z-[9999] flex flex-col shadow-2xl overflow-hidden"
        style={{ animation: 'slideIn 0.25s ease-out' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 bg-slate-900 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-2xl shrink-0">{DEFECT_LABELS[t.defect_type]?.split(' ')[0]}</span>
            <div className="min-w-0">
              <div className="text-white font-bold text-sm flex items-center gap-2">
                טיקט #{t.id}
                {t.sla_breached && (
                  <span className="text-xs bg-red-900 text-red-300 px-1.5 py-0.5 rounded-full border border-red-700 animate-pulse">
                    SLA הופר
                  </span>
                )}
              </div>
              <div className="text-slate-400 text-xs font-mono truncate">{t.address}</div>
            </div>
          </div>
          <button onClick={onClose}
            className="text-slate-400 hover:text-white w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-700 text-xl transition-colors shrink-0">
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-800 bg-slate-900 shrink-0">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'text-white border-b-2 border-blue-500 bg-slate-950'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">

          {/* ── INFO TAB ── */}
          {activeTab === 'info' && (
            <div className="px-5 py-4 space-y-4">
              {loading && (
                <div className="flex items-center justify-center h-24 text-slate-400">
                  <div className="animate-spin text-2xl">⚙️</div>
                </div>
              )}

              {d.image_url && (
                <div className="rounded-xl overflow-hidden border border-slate-700">
                  <img src={d.image_url} alt={d.image_caption || 'תמונת תקלה'}
                    className="w-full h-48 object-cover"
                    onError={e => { e.target.style.display = 'none'; }}
                  />
                  {d.image_caption && (
                    <div className="px-3 py-1.5 bg-slate-900 text-slate-400 text-xs italic">{d.image_caption}</div>
                  )}
                </div>
              )}

              {/* Badges */}
              <div className="flex gap-2 flex-wrap">
                <span className={`${sev.bg} text-white text-xs font-bold px-3 py-1 rounded-full`}>{sev.label}</span>
                <span className="bg-slate-700 text-white text-xs font-bold px-3 py-1 rounded-full">
                  {DEFECT_LABELS[t.defect_type] || t.defect_type}
                </span>
                <span className="bg-slate-800 text-slate-300 text-xs px-3 py-1 rounded-full border border-slate-600">
                  {STATUS_LABELS[t.status] || t.status}
                </span>
                {t.score > 0 && (
                  <span className={`text-xs px-3 py-1 rounded-full border font-mono font-bold ${
                    t.score >= 80 ? 'bg-red-950 text-red-300 border-red-700' :
                    t.score >= 60 ? 'bg-orange-950 text-orange-300 border-orange-700' :
                    'bg-slate-800 text-slate-300 border-slate-600'
                  }`}>
                    ⚡ {t.score}/100
                  </span>
                )}
                {t.detection_count > 1 && (
                  <span className="bg-purple-900 text-purple-300 text-xs px-3 py-1 rounded-full border border-purple-700">
                    📡 {t.detection_count} דיווחים
                  </span>
                )}
              </div>

              {/* Location */}
              <div className="bg-slate-900 border border-slate-700 rounded-xl p-4 space-y-2">
                <div className="text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest mb-2">📍 מיקום ושעה</div>
                <div className="text-sm space-y-1.5">
                  <div className="flex items-start gap-2">
                    <span className="text-slate-500 w-16 shrink-0">תאריך</span>
                    <span className="text-white">{formatDate(d.detected_at || t.created_at)}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-slate-500 w-16 shrink-0">כתובת</span>
                    <span className="text-white">{t.address}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-slate-500 w-16 shrink-0">GPS</span>
                    <span className="text-slate-300 font-mono text-xs">{fmt(t.lat, 6)}, {fmt(t.lng, 6)}</span>
                    <button onClick={() => navigator.clipboard.writeText(`${t.lat},${t.lng}`)}
                      className="text-xs text-blue-400 hover:text-blue-300 ml-auto">📋</button>
                  </div>
                </div>
              </div>

              {/* Vehicle */}
              <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
                <div className="text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest mb-3">🚗 רכב ומערכת</div>
                <div className="grid grid-cols-2 gap-y-2 text-sm">
                  {[
                    ['מזהה רכב',    d.vehicle_id || '—'],
                    ['דגם',         d.vehicle_model || '—'],
                    ['מהירות',      `${fmt(d.vehicle_speed_kmh, 1)} קמ"ש`],
                    ['כיוון',       `${fmt(d.vehicle_heading_deg, 0)}° (${COMPASS(d.vehicle_heading_deg || 0)})`],
                    ['חיישן',       d.vehicle_sensor_version || '—'],
                    ['מדווח ע"י',   d.reported_by || 'simulator'],
                  ].map(([label, val]) => (
                    <div key={label} className="flex flex-col">
                      <span className="text-slate-500 text-xs font-mono">{label}</span>
                      <span className="text-white font-medium text-xs">{val}</span>
                    </div>
                  ))}
                </div>
              </div>

              <GeometrySection d={d} />

              <EnvironmentSection d={d} />

              {/* Status progress */}
              <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
                <div className="text-cyan-400 font-mono text-sm font-bold uppercase tracking-widest mb-3">📊 התקדמות</div>
                <div className="flex items-center gap-1">
                  {STATUS_FLOW.map((s, i) => (
                    <div key={s} className="flex items-center gap-1 flex-1">
                      <div className={`h-2 rounded-full flex-1 transition-colors ${i <= currentIdx ? 'bg-blue-500' : 'bg-slate-700'}`} />
                      {i === currentIdx && <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />}
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
          )}

          {/* ── WORKFLOW TAB ── */}
          {activeTab === 'workflow' && (
            <div className="px-5 py-4">
              <WorkflowTimeline
                ticket={t}
                onWorkflowStarted={() => loadTicket()}
              />
            </div>
          )}

          {/* ── AI TAB ── */}
          {activeTab === 'ai' && (
            <div className="px-5 py-4 space-y-3">
              <div className="text-cyan-400 font-mono text-xs font-bold uppercase tracking-widest">🤖 תוצאות Pipeline AI</div>
              {d.notes ? (
                <AIPipelineSection notes={d.notes} />
              ) : (
                <div className="text-slate-500 text-sm text-center py-8">
                  אין תוצאות AI לטיקט זה עדיין
                </div>
              )}
            </div>
          )}
        </div>

        {/* Action bar */}
        <div className="border-t border-slate-800 px-5 py-4 bg-slate-900 shrink-0">
          {nextStatus ? (
            <button
              onClick={() => handleStatus(nextStatus)}
              disabled={statusLoading}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold py-3 rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              {statusLoading ? '⏳ מעדכן...' : `→ העבר ל: ${STATUS_LABELS[nextStatus]}`}
            </button>
          ) : (
            <div className="text-center text-green-400 font-mono text-sm py-2">✔️ טיקט טופל</div>
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
