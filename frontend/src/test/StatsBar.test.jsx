import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import StatsBar from '../components/StatsBar';
import * as client from '../api/client';

const mockStats = {
  total_open: 12,
  critical_count: 3,
  in_progress: 5,
  resolved_today: 2,
  detections_last_hour: 7,
  detections_per_hour: [{ hour: '10:00', count: 3 }, { hour: '11:00', count: 4 }],
};

describe('StatsBar', () => {
  beforeEach(() => {
    vi.spyOn(client, 'getStats').mockResolvedValue(mockStats);
  });

  it('shows loading state initially', () => {
    render(<StatsBar />);
    expect(screen.getByText(/loading stats/i)).toBeInTheDocument();
  });

  it('renders stat cards after load', async () => {
    render(<StatsBar />);
    await waitFor(() => {
      expect(screen.getByText('Open Tickets')).toBeInTheDocument();
      expect(screen.getByText('12')).toBeInTheDocument();
    });
  });

  it('displays critical count', async () => {
    render(<StatsBar />);
    await waitFor(() => {
      expect(screen.getByText('Critical')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
    });
  });

  it('reloads on wsEvent change', async () => {
    const { rerender } = render(<StatsBar wsEvent={null} />);
    await waitFor(() => screen.getByText('Open Tickets'));

    rerender(<StatsBar wsEvent={{ type: 'new_detection' }} />);
    await waitFor(() => {
      expect(client.getStats).toHaveBeenCalledTimes(2);
    });
  });

  it('handles API error gracefully', async () => {
    vi.spyOn(client, 'getStats').mockRejectedValue(new Error('Network error'));
    render(<StatsBar />);
    // Should show loading and not crash
    expect(screen.getByText(/loading stats/i)).toBeInTheDocument();
  });
});
