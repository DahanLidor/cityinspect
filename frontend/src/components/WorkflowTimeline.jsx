import { useEffect, useState } from 'react';
import { getTicketSteps, getTicketAudit, openTicketWorkflow, performWorkflowAction } from '../api/client';

const STEP_STATUS_CONFIG = {
  open:    { color: 'border-blue-500 bg-blue-950',    dot: 'bg-blue-400 animate-pulse', label: 'פעיל' },
  done:    { color: 'border-green-600 bg-green-950',  dot: 'bg-green-400',              label: 'הושלם' },
  skipped: { color: 'border-slate-600 bg-slate-900',  dot: 'bg-slate-500',              label: 'דולג' },
  timeout: { color: 'border-red-700 bg-red-950',      dot: 'bg-red-400',                label: 'פגי תוקף' },
};

const ROLE_LABELS = {
  work_manager:          '👷 מנהל עבודה',
  infrastructure_manager:'🏗️ מנהל תשתיות',
  city_manager:          '🏙️ מנהל עיר',
  contractor:            '🔨 קבלן',
  field_worker:          '⛏️ פועל שטח',
  inspector:             '🔍 מפקח',
};

const ACTION_CONFIG = {
  approve:           { label: 'אשר',           color: 'bg-green-600 hover:bg-green-500 text-white' },
  reject:            { label: 'דחה',           color: 'bg-red-600 hover:bg-red-500 text-white' },
  assign_contractor: { label: 'הקצה קבלן',    color: 'bg-blue-600 hover:bg-blue-500 text-white' },
  assign_team:       { label: 'הקצה צוות',    color: 'bg-blue-600 hover:bg-blue-500 text-white' },
  confirm:           { label: 'אשר הגעה',      color: 'bg-green-600 hover:bg-green-500 text-white' },
  complete:          { label: 'סיים תיקון',    color: 'bg-green-600 hover:bg-green-500 text-white' },
  inspect_pass:      { label: 'עבר בדיקה ✓',  color: 'bg-green-600 hover:bg-green-500 text-white' },
  inspect_fail:      { label: 'נכשל בדיקה',   color: 'bg-red-600 hover:bg-red-500 text-white' },
  reject_redo:       { label: 'החזר לתיקון',  color: 'bg-orange-600 hover:bg-orange-500 text-white' },
  close:             { label: 'סגור טיקט',    color: 'bg-slate-600 hover:bg-slate-500 text-white' },
};

function formatDt(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('he-IL', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function StepCard({ step, isLast, onAction, acting }) {
  const cfg = STEP_STATUS_CONFIG[step.status] || STEP_STATUS_CONFIG.open;
  const isOverdue = step.status === 'open' && step.deadline_at && new Date(step.deadline_at) < new Date();

  return (
    <div className="flex gap-3">
      {/* Line + dot */}
      <div className="flex flex-col items-center shrink-0">
        <div className={`w-3 h-3 rounded-full mt-1 ${cfg.dot} ${isOverdue ? 'bg-orange-400 animate-bounce' : ''}`} />
        {!isLast && <div className="w-0.5 flex-1 bg-slate-700 mt-1 mb-1" />}
      </div>

      {/* Card */}
      <div className={`flex-1 border rounded-xl p-3 mb-3 ${cfg.color} ${isOverdue ? 'border-orange-500' : ''}`}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-white text-sm font-semibold">{step.step_name}</div>
            <div className="text-slate-400 text-xs font-mono mt-0.5">
              {ROLE_LABELS[step.owner_role] || step.owner_role}
            </div>
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full font-mono shrink-0 ${
            step.status === 'open'    ? 'bg-blue-900 text-blue-300' :
            step.status === 'done'    ? 'bg-green-900 text-green-300' :
            step.status === 'timeout' ? 'bg-red-900 text-red-300' :
            'bg-slate-800 text-slate-400'
          }`}>
            {cfg.label}
          </span>
        </div>

        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-400">
          <div>
            <span className="text-slate-500">נפתח: </span>
            <span>{formatDt(step.opened_at)}</span>
          </div>
          {step.deadline_at && (
            <div className={isOverdue ? 'text-orange-400' : ''}>
              <span className="text-slate-500">דד-ליין: </span>
              <span>{formatDt(step.deadline_at)}</span>
              {isOverdue && ' ⚠️'}
            </div>
          )}
          {step.completed_at && (
            <div>
              <span className="text-slate-500">הושלם: </span>
              <span>{formatDt(step.completed_at)}</span>
            </div>
          )}
          {step.action_taken && (
            <div>
              <span className="text-slate-500">פעולה: </span>
              <span className="text-white font-mono">{step.action_taken}</span>
            </div>
          )}
        </div>

        {/* Gate data */}
        {step.data && Object.keys(step.data).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {Object.entries(step.data).map(([key, val]) => (
              <span key={key} className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded-full font-mono">
                {key === 'note' ? `📝 ${val}` : `📷 ${key}`}
              </span>
            ))}
          </div>
        )}

        {/* Action buttons — only for open steps with allowed_actions */}
        {step.status === 'open' && step.allowed_actions?.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {step.allowed_actions.map(action => {
              const cfg = ACTION_CONFIG[action] || { label: action, color: 'bg-slate-600 hover:bg-slate-500 text-white' };
              return (
                <button
                  key={action}
                  disabled={acting}
                  onClick={() => onAction(step, action)}
                  className={`text-xs font-semibold px-3 py-1.5 rounded-lg disabled:opacity-50 transition-colors ${cfg.color}`}
                >
                  {acting ? '⏳' : cfg.label}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default function WorkflowTimeline({ ticket, onWorkflowStarted }) {
  const [steps, setSteps] = useState([]);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAudit, setShowAudit] = useState(false);
  const [starting, setStarting] = useState(false);
  const [acting, setActing] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([
      getTicketSteps(ticket.id).catch(() => []),
      getTicketAudit(ticket.id).catch(() => []),
    ]).then(([s, a]) => {
      setSteps(s);
      setAudit(a);
    }).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [ticket.id]);

  const handleStart = async () => {
    setStarting(true);
    try {
      await openTicketWorkflow(ticket.id);
      onWorkflowStarted?.();
      load();
    } catch (e) {
      const d = e.response?.data?.detail;
      const msg = typeof d === 'string' ? d : d ? JSON.stringify(d) : (e.message || 'שגיאה בפתיחת תהליך');
      alert(msg);
    } finally {
      setStarting(false);
    }
  };

  const handleAction = async (step, action) => {
    if (!step.owner_person_id) {
      alert('השלב אינו משויך לאיש קשר — לא ניתן לבצע פעולה');
      return;
    }
    setActing(true);
    try {
      await performWorkflowAction(ticket.id, { action, person_id: step.owner_person_id });
      load();
    } catch (e) {
      const d = e.response?.data?.detail;
      const msg = typeof d === 'string' ? d : d ? JSON.stringify(d) : (e.message || 'שגיאה בביצוע פעולה');
      alert(msg);
    } finally {
      setActing(false);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-32 text-slate-400">
      <div className="animate-spin text-2xl">⚙️</div>
    </div>
  );

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="text-cyan-400 font-mono text-xs font-bold uppercase tracking-widest">
          🔄 תהליך טיפול
        </div>
        <div className="flex items-center gap-2">
          {steps.length > 0 && (
            <button
              onClick={() => setShowAudit(p => !p)}
              className="text-xs text-slate-400 hover:text-white bg-slate-800 px-2 py-1 rounded-lg"
            >
              {showAudit ? 'הסתר' : '📜 לוג'}
            </button>
          )}
          <button
            onClick={load}
            className="text-xs text-slate-400 hover:text-white bg-slate-800 px-2 py-1 rounded-lg"
          >
            🔄
          </button>
        </div>
      </div>

      {/* Current step highlight */}
      {ticket.current_step_id && (
        <div className="bg-blue-950 border border-blue-700 rounded-xl p-3 flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse shrink-0" />
          <div>
            <div className="text-blue-300 text-xs font-mono">שלב נוכחי</div>
            <div className="text-white text-sm font-semibold">{ticket.current_step_id}</div>
          </div>
          {ticket.sla_deadline && (
            <div className={`ml-auto text-xs font-mono ${
              ticket.sla_breached ? 'text-red-400' : 'text-slate-400'
            }`}>
              {ticket.sla_breached ? '🚨 SLA הופר' : `⏰ ${formatDt(ticket.sla_deadline)}`}
            </div>
          )}
        </div>
      )}

      {/* No workflow yet */}
      {steps.length === 0 && !ticket.current_step_id && (
        <div className="text-center py-6">
          <div className="text-slate-500 text-sm mb-3">תהליך טיפול טרם נפתח לטיקט זה</div>
          <button
            onClick={handleStart}
            disabled={starting}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-bold px-4 py-2 rounded-xl"
          >
            {starting ? '⏳ מאתחל...' : '🚀 פתח תהליך טיפול'}
          </button>
        </div>
      )}

      {/* Timeline */}
      {!showAudit && steps.length > 0 && (
        <div>
          {steps.map((step, i) => (
            <StepCard
              key={step.id}
              step={step}
              isLast={i === steps.length - 1}
              onAction={handleAction}
              acting={acting}
            />
          ))}
        </div>
      )}

      {/* Audit log */}
      {showAudit && audit.length > 0 && (
        <div className="space-y-1">
          {audit.map(entry => (
            <div key={entry.id} className="flex items-start gap-2 text-xs py-1.5 border-b border-slate-800">
              <span className="text-slate-500 font-mono shrink-0 w-28">{formatDt(entry.timestamp)}</span>
              <span className={`shrink-0 ${entry.actor_type === 'system' ? 'text-slate-500' : 'text-blue-400'}`}>
                {entry.actor_type === 'system' ? '🤖' : '👤'} {entry.actor_name}
              </span>
              <span className="text-white font-mono">{entry.action}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
