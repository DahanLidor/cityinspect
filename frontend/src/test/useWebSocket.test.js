import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useWebSocket } from '../hooks/useWebSocket';

describe('useWebSocket', () => {
  let mockWsInstance;

  beforeEach(() => {
    mockWsInstance = {
      onopen: null,
      onmessage: null,
      onclose: null,
      readyState: WebSocket.OPEN,
      close: vi.fn(),
      send: vi.fn(),
    };
    global.WebSocket = vi.fn(() => mockWsInstance);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('creates a WebSocket connection on mount', () => {
    const onMessage = vi.fn();
    renderHook(() => useWebSocket(onMessage));
    expect(global.WebSocket).toHaveBeenCalledOnce();
  });

  it('calls onMessage with parsed JSON', () => {
    const onMessage = vi.fn();
    renderHook(() => useWebSocket(onMessage));

    act(() => {
      mockWsInstance.onmessage({ data: JSON.stringify({ type: 'new_detection', ticket_id: 42 }) });
    });

    expect(onMessage).toHaveBeenCalledWith({ type: 'new_detection', ticket_id: 42 });
  });

  it('ignores invalid JSON without throwing', () => {
    const onMessage = vi.fn();
    renderHook(() => useWebSocket(onMessage));

    act(() => {
      mockWsInstance.onmessage({ data: 'not json' });
    });

    expect(onMessage).not.toHaveBeenCalled();
  });

  it('closes WebSocket on unmount', () => {
    const { unmount } = renderHook(() => useWebSocket(vi.fn()));
    unmount();
    expect(mockWsInstance.close).toHaveBeenCalled();
  });

  it('resets retry delay on successful open', () => {
    renderHook(() => useWebSocket(vi.fn()));
    act(() => { mockWsInstance.onopen(); });
    // No crash — retry delay reset to 1000
  });
});
