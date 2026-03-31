import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import DailyPlansPanel from '../components/DailyPlansPanel';

// Mock API
vi.mock('../api/client', () => ({
  getDailyPlanWorkers: vi.fn(),
  generateDailyPlan: vi.fn(),
  getDailyPlans: vi.fn(),
}));

import { getDailyPlanWorkers, generateDailyPlan, getDailyPlans } from '../api/client';

const MOCK_WORKERS = [
  {
    id: 1, name: 'אבי כהן', role: 'contractor',
    specialties: ['pothole'], skills: ['asphalt', 'welding'],
    vehicle_type: 'truck', current_workload: 3,
    home_base_lat: 32.05, home_base_lon: 34.76,
  },
  {
    id: 2, name: 'מוקי אברהם', role: 'inspector',
    specialties: ['pothole', 'road_crack'], skills: ['inspection'],
    vehicle_type: 'car', current_workload: 5,
    home_base_lat: 32.06, home_base_lon: 34.76,
  },
];

const MOCK_PLAN = {
  id: 1, person_id: 1, person_name: 'אבי כהן',
  plan_date: '2026-04-01', status: 'draft',
  total_tasks: 3, total_hours: 6.5, total_distance_km: 18.2,
  plan: {
    tasks: [
      { order: 1, ticket_id: 10, address: 'Herzl 45', defect_type: 'pothole',
        severity: 'high', estimated_duration_min: 45, drive_time_min: 12,
        arrive_by: '08:12', equipment: ['asphalt'], notes: 'test' },
      { order: 'break', time: '12:00', duration_min: 30 },
    ],
    equipment_summary: ['asphalt — 2 bags'],
    summary_he: 'תוכנית בדיקה',
  },
  created_at: '2026-04-01T08:00:00Z',
};

describe('DailyPlansPanel', () => {
  beforeEach(() => {
    getDailyPlanWorkers.mockResolvedValue(MOCK_WORKERS);
    getDailyPlans.mockResolvedValue([]);
    generateDailyPlan.mockResolvedValue(MOCK_PLAN);
  });

  it('renders worker list', async () => {
    render(<DailyPlansPanel />);
    await waitFor(() => {
      expect(screen.getByText('אבי כהן')).toBeTruthy();
      expect(screen.getByText('מוקי אברהם')).toBeTruthy();
    });
  });

  it('shows worker skills', async () => {
    render(<DailyPlansPanel />);
    await waitFor(() => {
      expect(screen.getByText('asphalt')).toBeTruthy();
      expect(screen.getByText('welding')).toBeTruthy();
    });
  });

  it('shows worker count in tab', async () => {
    render(<DailyPlansPanel />);
    await waitFor(() => {
      expect(screen.getByText(/עובדים \(2\)/)).toBeTruthy();
    });
  });

  it('shows empty state when no plans', async () => {
    render(<DailyPlansPanel />);
    await waitFor(() => screen.getByText('אבי כהן'));
    // Switch to plans tab
    fireEvent.click(screen.getByText(/תוכניות/));
    expect(screen.getByText('טרם נוצרו תוכניות עבודה')).toBeTruthy();
  });

  it('displays loading state', () => {
    getDailyPlanWorkers.mockReturnValue(new Promise(() => {})); // never resolves
    getDailyPlans.mockReturnValue(new Promise(() => {}));
    render(<DailyPlansPanel />);
    // Should show spinner (⚙️)
    expect(document.querySelector('.animate-spin')).toBeTruthy();
  });
});
