import { useEffect, useRef, useCallback } from 'react';

const BASE_WS = process.env.REACT_APP_WS_URL ||
  (window.location.protocol === 'https:' ? 'wss' : 'ws') +
  '://' + (process.env.REACT_APP_API_HOST || 'localhost:8000') + '/ws';

export function useWebSocket(onMessage) {
  const ws = useRef(null);
  const retryDelay = useRef(1000);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    try {
      ws.current = new WebSocket(BASE_WS);
      ws.current.onopen = () => { retryDelay.current = 1000; };
      ws.current.onmessage = (e) => {
        try { onMessageRef.current(JSON.parse(e.data)); } catch {}
      };
      ws.current.onclose = () => {
        setTimeout(() => {
          retryDelay.current = Math.min(retryDelay.current * 2, 30000);
          connect();
        }, retryDelay.current);
      };
    } catch {}
  }, []);

  useEffect(() => {
    connect();
    return () => ws.current?.close();
  }, [connect]);
}
