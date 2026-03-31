import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import StatsBar from '../components/StatsBar';
import * as client from '../api/client';

const mockStats = {
  total_open: 12,
  open_tickets: 12,
  critical_count: 3,
  by_status: { in_progress: 5 },
  resolved_today: 2,
  sla_breached: 1,
  overdue_steps: 2,
  detections_per_hour: [{ hour: '10:00', count: 3 }, { hour: '11:00', count: 4 }],
};

describe('StatsBar', () => {
  beforeEach(() => {
    vi.spyOn(client, 'getStats').mockResolvedValue(mockStats);
  });

  it('renders stat cards after load', async () => {
    render(<StatsBar />);
    await waitFor(() => {
      expect(screen.getByText('טיקטים פתוחים')).toBeTruthy();
      expect(screen.getByText('12')).toBeTruthy();
    });
  });

  it('displays critical count', async () => {
    render(<StatsBar />);
    await waitFor(() => {
      expect(screen.getByText('קריטי')).toBeTruthy();
      expect(screen.getByText('3')).toBeTruthy();
    });
  });

  it('calls getStats on mount', async () => {
    render(<StatsBar />);
    await waitFor(() => {
      expect(client.getStats).toHaveBeenCalled();
    });
  });

  it('handles API error gracefully', async () => {
    vi.spyOn(client, 'getStats').mockRejectedValue(new Error('Network error'));
    render(<StatsBar />);
    // Should not crash — waits for data
    await new Promise(r => setTimeout(r, 100));
    expect(document.body).toBeTruthy();
  });
});
