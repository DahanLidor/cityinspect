import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import WorkflowTimeline from '../components/WorkflowTimeline';

vi.mock('../api/client', () => ({
  getTicketSteps: vi.fn(),
  getTicketAudit: vi.fn(),
  openTicketWorkflow: vi.fn(),
  performWorkflowAction: vi.fn(),
}));

import { getTicketSteps, getTicketAudit, openTicketWorkflow, performWorkflowAction } from '../api/client';

const MOCK_STEPS = [
  {
    id: 1, step_id: 'manager_approval', step_name: 'אישור מנהל',
    status: 'open', owner_role: 'work_manager', owner_person_id: 5,
    opened_at: '2026-04-01T08:00:00Z', deadline_at: '2026-04-01T10:00:00Z',
    completed_at: null, action_taken: null, data: {},
    allowed_actions: ['approve', 'reject'],
  },
];

const MOCK_TICKET = { id: 18, current_step_id: 'manager_approval', sla_deadline: null, sla_breached: false };

describe('WorkflowTimeline', () => {
  beforeEach(() => {
    getTicketSteps.mockResolvedValue(MOCK_STEPS);
    getTicketAudit.mockResolvedValue([]);
    openTicketWorkflow.mockResolvedValue({ step_id: 'manager_approval' });
    performWorkflowAction.mockResolvedValue({ status: 'ok' });
  });

  it('renders step name and role', async () => {
    render(<WorkflowTimeline ticket={MOCK_TICKET} />);
    await waitFor(() => {
      expect(screen.getByText('אישור מנהל')).toBeTruthy();
      expect(screen.getByText(/מנהל עבודה/)).toBeTruthy();
    });
  });

  it('shows action buttons for open steps', async () => {
    render(<WorkflowTimeline ticket={MOCK_TICKET} />);
    await waitFor(() => {
      expect(screen.getByText('אשר')).toBeTruthy();
      expect(screen.getByText('דחה')).toBeTruthy();
    });
  });

  it('shows open workflow button when no steps', async () => {
    getTicketSteps.mockResolvedValue([]);
    const ticket = { id: 99, current_step_id: null };
    render(<WorkflowTimeline ticket={ticket} />);
    await waitFor(() => {
      expect(screen.getByText(/פתח תהליך טיפול/)).toBeTruthy();
    });
  });

  it('calls performWorkflowAction on button click', async () => {
    render(<WorkflowTimeline ticket={MOCK_TICKET} />);
    await waitFor(() => screen.getByText('אשר'));
    fireEvent.click(screen.getByText('אשר'));
    await waitFor(() => {
      expect(performWorkflowAction).toHaveBeenCalledWith(18, { action: 'approve', person_id: 5 });
    });
  });

  it('shows status badge', async () => {
    render(<WorkflowTimeline ticket={MOCK_TICKET} />);
    await waitFor(() => {
      expect(screen.getByText('פעיל')).toBeTruthy();
    });
  });
});
