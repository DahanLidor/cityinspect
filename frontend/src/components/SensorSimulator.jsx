import { useState, useEffect, useRef } from 'react';
import { postDetection } from '../api/client';

const TEL_AVIV = { latMin: 32.05, latMax: 32.11, lngMin: 34.76, lngMax: 34.82 };
const DEFECT_TYPES = ['pothole','road_crack','broken_light','drainage_blocked','sidewalk'];
const SEVERITIES = ['low','medium','high','critical'];
const VEHICLES = ['V001','V002','V003','V004','V005'];
const WEATHERS = ['Clear','Cloudy','Rain','Fog','Partly Cloudy'];

function rand(min, max) { return Math.random() * (max - min) + min; }
function randItem(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

function buildRandomDetection() {
  const lat = parseFloat(rand(TEL_AVIV.latMin, TEL_AVIV.latMax).toFixed(6));
  const lng = parseFloat(rand(TEL_AVIV.lngMin, TEL_AVIV.lngMax).toFixed(6));
  const type = randItem(DEFECT_TYPES);
  const L = parseFloat(rand(20, 100).toFixed(1));
  const W = parseFloat(rand(15, 80).toFixed(1));
  const D = parseFloat(rand(3, 15).toFixed(1));
  const ambient = parseFloat(rand(14, 28).toFixed(1));
  return {
    vehicle_id: randItem(VEHICLES),
    vehicle_model: `Ford Transit ${randItem(VEHICLES)}`,
    vehicle_sensor_version: 'SensorArray-v2.3',
    vehicle_speed_kmh: parseFloat(rand(5, 60).toFixed(1)),
    vehicle_heading_deg: parseFloat(rand(0, 360).toFixed(1)),
    reported_by: 'simulator',
    defect_type: type,
    severity: randItem(SEVERITIES),
    lat, lng,
    defect_length_cm: L,
    defect_width_cm: W,
    defect_depth_cm: D,
    ambient_temp_c: ambient,
    asphalt_temp_c: parseFloat((ambient + rand(8, 22)).toFixed(1)),
    weather_condition: randItem(WEATHERS),
    wind_speed_kmh: parseFloat(rand(0, 40).toFixed(1)),
    humidity_pct: parseFloat(rand(30, 90).toFixed(1)),
    visibility_m: randItem([2000, 5000, 8000, 10000]),
    image_url: type === 'pothole'
      ? 'https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Pothole_on_D2128_%28Poland%29.jpg/640px-Pothole_on_D2128_%28Poland%29.jpg'
      : '',
    image_caption: 'Simulated detection',
    notes: '',
  };
}

export default function SensorSimulator({ onDetection }) {
  const [log, setLog] = useState([]);
  const [autoMode, setAutoMode] = useState(false);
  const [countdown, setCountdown] = useState(3);
  const [sending, setSending] = useState(false);
  const autoRef = useRef(null);
  const countRef = useRef(null);

  const send = async (data) => {
    setSending(true);
    try {
      const res = await postDetection(data);
      const entry = {
        id: Date.now(),
        vehicle: data.vehicle_id,
        type: data.defect_type,
        severity: data.severity,
        isNew: res.is_new_ticket,
        address: res.address,
        time: new Date().toLocaleTimeString('en-GB'),
      };
      setLog(prev => [entry, ...prev].slice(0, 8));
      onDetection?.(res);
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    if (!autoMode) {
      clearInterval(autoRef.current);
      clearInterval(countRef.current);
      setCountdown(3);
      return;
    }
    send(buildRandomDetection());
    setCountdown(3);
    autoRef.current = setInterval(() => { send(buildRandomDetection()); setCountdown(3); }, 3000);
    countRef.current = setInterval(() => setCountdown(c => c > 0 ? c - 1 : 3), 1000);
    return () => { clearInterval(autoRef.current); clearInterval(countRef.current); };
  }, [autoMode]);

  const SEV_COLOR = { critical: 'text-red-400', high: 'text-orange-400', medium: 'text-yellow-400', low: 'text-green-400' };

  return (
    <div className="flex flex-col h-full bg-slate-950 border-r border-slate-800">
      <div className="px-4 py-3 border-b border-slate-800">
        <div className="text-xs font-mono font-bold text-cyan-400 uppercase tracking-widest">
          📡 Sensor Simulator
        </div>
      </div>

      <div className="p-4 space-y-3">
        {/* Random send */}
        <button
          onClick={() => send(buildRandomDetection())}
          disabled={sending}
          className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold py-2.5 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
        >
          {sending ? '⏳ Sending...' : '🎲 Random Detect'}
        </button>

        {/* Auto mode */}
        <button
          onClick={() => setAutoMode(p => !p)}
          className={`w-full font-bold py-2.5 rounded-xl text-sm transition-colors flex items-center justify-center gap-2 border ${
            autoMode
              ? 'bg-red-950 border-red-700 text-red-400 hover:bg-red-900'
              : 'bg-slate-800 border-slate-600 text-slate-300 hover:bg-slate-700'
          }`}
        >
          {autoMode ? `⏹ Stop Auto (${countdown}s)` : '▶ Auto Mode (3s)'}
          {autoMode && <div className="w-2 h-2 rounded-full bg-red-400 animate-pulse" />}
        </button>
      </div>

      {/* Log */}
      <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
        <div className="text-xs font-mono text-slate-500 uppercase tracking-widest mb-2">
          Recent Detections
        </div>
        {log.length === 0 && (
          <div className="text-slate-600 text-xs text-center py-4">
            Hit "Random Detect" to simulate a sensor report
          </div>
        )}
        {log.map(entry => (
          <div key={entry.id}
            className="bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-xs space-y-0.5 animate-fadeIn">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 font-mono">{entry.vehicle}</span>
              <span className={`font-bold uppercase ${SEV_COLOR[entry.severity]}`}>{entry.severity}</span>
            </div>
            <div className="text-white font-medium capitalize">{entry.type.replace('_', ' ')}</div>
            <div className="text-slate-500 truncate">{entry.address}</div>
            <div className="flex items-center justify-between pt-0.5">
              <span className="text-slate-600">{entry.time}</span>
              <span className={`text-xs font-mono ${entry.isNew ? 'text-green-400' : 'text-yellow-400'}`}>
                {entry.isNew ? '🆕 New ticket' : '🔄 Merged'}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
