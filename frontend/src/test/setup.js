import '@testing-library/jest-dom';

// Mock leaflet (no DOM canvas in test env)
vi.mock('leaflet', () => ({
  default: {
    map: vi.fn(() => ({ setView: vi.fn().mockReturnThis(), remove: vi.fn() })),
    tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
    marker: vi.fn(() => ({ addTo: vi.fn(), bindPopup: vi.fn(), on: vi.fn() })),
    icon: vi.fn(),
  },
}));

// Mock react-leaflet
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }) => children,
  TileLayer: () => null,
  Marker: ({ children }) => children,
  Popup: ({ children }) => children,
}));

// Mock WebSocket
class MockWebSocket {
  constructor(url) { this.url = url; this.readyState = 1; }
  send() {}
  close() {}
  addEventListener() {}
  removeEventListener() {}
}
global.WebSocket = MockWebSocket;
