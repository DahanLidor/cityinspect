import { useEffect, useRef, useState, useCallback } from 'react';
import { getTickets } from '../api/client';

const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const TEL_AVIV = [32.0853, 34.7818];

const DEFECT_CONFIG = {
  pothole:           { emoji: '🕳️', color: '#ef4444', border: '#dc2626' },
  road_crack:        { emoji: '⚠️', color: '#f97316', border: '#ea580c' },
  broken_light:      { emoji: '💡', color: '#eab308', border: '#ca8a04' },
  drainage_blocked:  { emoji: '🌊', color: '#3b82f6', border: '#2563eb' },
  sidewalk:          { emoji: '🧱', color: '#a855f7', border: '#9333ea' },
};

const SEV_SIZE = { critical: 48, high: 40, medium: 34, low: 28 };

export default function MapView({ onSelectTicket, wsEvent }) {
  const mapRef = useRef(null);
  const leafletMap = useRef(null);
  const markersRef = useRef({});
  const [tickets, setTickets] = useState([]);

  const createIcon = useCallback((ticket) => {
    const L = window.L;
    if (!L) return null;
    const cfg = DEFECT_CONFIG[ticket.defect_type] || { emoji: '📍', color: '#64748b', border: '#475569' };
    const size = SEV_SIZE[ticket.severity] || 34;
    const pulse = ticket.severity === 'critical'
      ? `box-shadow:0 0 0 4px ${cfg.color}44,0 0 16px ${cfg.color}88;animation:pulse 1.5s infinite;`
      : '';

    return L.divIcon({
      className: '',
      html: `<div style="
        width:${size}px;height:${size}px;border-radius:50%;
        background:${cfg.color};border:2px solid ${cfg.border};
        display:flex;align-items:center;justify-content:center;
        font-size:${size * 0.45}px;cursor:pointer;
        transition:transform 0.15s;${pulse}
      " title="${ticket.defect_type}">${cfg.emoji}</div>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
  }, []);

  // Init map
  useEffect(() => {
    if (!mapRef.current || leafletMap.current) return;
    const L = window.L;
    if (!L) return;

    const map = L.map(mapRef.current, { zoomControl: false, scrollWheelZoom: false }).setView(TEL_AVIV, 14);
    L.tileLayer(TILE_URL, {
      attribution: '© <a href="https://www.openstreetmap.org">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    leafletMap.current = map;

    // Load tickets
    getTickets({ limit: 200 }).then(data => {
      setTickets(Array.isArray(data) ? data : (data.items || []));
    });

    // CSS for pulse
    const style = document.createElement('style');
    style.textContent = `@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.4)}50%{box-shadow:0 0 0 8px rgba(239,68,68,0)}}`;
    document.head.appendChild(style);

    return () => { map.remove(); leafletMap.current = null; };
  }, []);

  // Add/update markers when tickets change
  useEffect(() => {
    const map = leafletMap.current;
    const L = window.L;
    if (!map || !L) return;

    tickets.forEach(ticket => {
      if (markersRef.current[ticket.id]) {
        markersRef.current[ticket.id].setIcon(createIcon(ticket));
        return;
      }
      const icon = createIcon(ticket);
      if (!icon) return;

      const marker = L.marker([ticket.lat, ticket.lng], { icon })
        .addTo(map)
        .on('click', () => onSelectTicket(ticket));

      markersRef.current[ticket.id] = marker;
    });
  }, [tickets, createIcon, onSelectTicket]);

  // Handle WebSocket events
  useEffect(() => {
    if (!wsEvent) return;
    if (wsEvent.type === 'new_detection' || wsEvent.type === 'ticket_created') {
      getTickets({ limit: 200 }).then(data => setTickets(Array.isArray(data) ? data : (data.items || [])));
    }
    if (wsEvent.type === 'ticket_updated') {
      setTickets(prev => prev.map(t =>
        t.id === wsEvent.ticket_id ? { ...t, status: wsEvent.status } : t
      ));
    }
  }, [wsEvent]);

  return (
    <div className="relative w-full h-full">
      <div ref={mapRef} className="w-full h-full" />
      {/* Live badge */}
      <div className="absolute top-3 left-3 z-[1000] flex items-center gap-2 bg-slate-900/90 backdrop-blur border border-slate-700 rounded-full px-3 py-1.5 text-xs">
        <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
        <span className="text-slate-300">Live — {tickets.filter(t => t.status !== 'resolved').length} open</span>
      </div>

      {/* Legend */}
      <div className="absolute bottom-12 left-3 z-[1000] bg-slate-900/90 backdrop-blur border border-slate-700 rounded-xl px-3 py-2 text-xs space-y-1">
        {Object.entries(DEFECT_CONFIG).map(([key, cfg]) => (
          <div key={key} className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full" style={{ background: cfg.color }} />
            <span className="text-slate-300 capitalize">{key.replace('_', ' ')}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
