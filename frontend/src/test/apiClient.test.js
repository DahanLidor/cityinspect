import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';

vi.mock('axios', () => {
  const mockAxios = {
    defaults: { headers: { common: {} } },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    create: vi.fn(),
  };
  mockAxios.create = vi.fn(() => mockAxios);
  return { default: mockAxios };
});

describe('API client', () => {
  it('module loads without error', async () => {
    const mod = await import('../api/client');
    expect(mod).toBeDefined();
  });
});
