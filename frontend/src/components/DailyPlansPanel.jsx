import { useEffect, useState } from 'react';
import { getDailyPlanWorkers, generateDailyPlan, getDailyPlans } from '../api/client';

const ROLE_LABELS = {
  work_manager: '👷 מנהל עבודה',
  contractor: '🔨 קבלן',
  field_worker: '⛏️ פועל שטח',
  inspector: '🔍 מפקח',
};

const VEHICLE_ICONS = { truck: '🚛', car: '🚗', bike: '🏍️', none: '🚶' };

function WorkerCard({ worker, onGenerate, generating }) {
  return (
    <div className="border border-slate-700 rounded-xl p-4 bg-slate-900/60">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-white font-semibold text-sm">{worker.name}</div>
          <div className="text-slate-400 text-xs font-mono mt-0.5">
            {ROLE_LABELS[worker.role] || worker.role}
          </div>
          <div className="flex flex-wrap gap-1 mt-2">
            {worker.skills.map(s => (
              <span key={s} className="text-xs bg-cyan-900/50 text-cyan-300 px-2 py-0.5 rounded-full">{s}</span>
            ))}
          </div>
        </div>
        <div className="text-right shrink-0">
          <span className="text-lg">{VEHICLE_ICONS[worker.vehicle_type] || '🚗'}</span>
          <div className="text-xs text-slate-500 mt-1">{worker.current_workload} משימות</div>
        </div>
      </div>
      <button
        onClick={() => onGenerate(worker.id)}
        disabled={generating}
        className="mt-3 w-full text-xs font-bold px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white transition-colors"
      >
        {generating ? '⏳ מייצר תוכנית...' : '🤖 צור תוכנית עבודה'}
      </button>
    </div>
  );
}

function TaskTimeline({ plan }) {
  const tasks = plan?.tasks || [];
  if (!tasks.length) return <div className="text-slate-500 text-sm text-center py-4">אין משימות</div>;

  return (
    <div className="space-y-2">
      {tasks.map((task, i) => {
        if (task.order === 'break') {
          return (
            <div key={`break-${i}`} className="flex items-center gap-3 py-2">
              <div className="w-8 h-8 rounded-full bg-orange-900/50 flex items-center justify-center text-sm">☕</div>
              <div className="text-orange-300 text-xs font-mono">
                {task.time} — הפסקה ({task.duration_min} דק׳)
              </div>
            </div>
          );
        }

        const slaUrgent = task.sla_remaining_hours != null && task.sla_remaining_hours < 6;

        return (
          <div key={task.order} className={`border rounded-xl p-3 ${slaUrgent ? 'border-red-600 bg-red-950/30' : 'border-slate-700 bg-slate-800/50'}`}>
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold bg-blue-900 text-blue-300 w-6 h-6 rounded-full flex items-center justify-center">
                  {task.order}
                </span>
                <div>
                  <div className="text-white text-sm font-semibold">#{task.ticket_id} — {task.defect_type}</div>
                  <div className="text-slate-400 text-xs">{task.address}</div>
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-xs text-slate-400 font-mono">{task.arrive_by}</div>
                <div className="text-xs text-slate-500">{task.estimated_duration_min} דק׳</div>
              </div>
            </div>

            {task.notes && (
              <div className="mt-2 text-xs text-slate-400 bg-slate-900/50 rounded-lg p-2">
                {task.notes}
              </div>
            )}

            {task.equipment?.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {task.equipment.map((eq, j) => (
                  <span key={j} className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">🔧 {eq}</span>
                ))}
              </div>
            )}

            {slaUrgent && (
              <div className="mt-1 text-xs text-red-400 font-mono">
                ⚠️ SLA: {task.sla_remaining_hours?.toFixed(1)} שעות נותרו
              </div>
            )}

            {task.drive_time_min > 0 && (
              <div className="mt-1 text-xs text-slate-500">🚗 {task.drive_time_min} דק׳ נסיעה</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PlanDetail({ plan, onBack }) {
  const data = plan.plan;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="text-xs text-slate-400 hover:text-white bg-slate-800 px-3 py-1 rounded-lg">
          → חזור
        </button>
        <span className={`text-xs px-2 py-0.5 rounded-full font-mono ${
          plan.status === 'draft' ? 'bg-yellow-900 text-yellow-300' :
          plan.status === 'sent' ? 'bg-blue-900 text-blue-300' :
          plan.status === 'active' ? 'bg-green-900 text-green-300' :
          'bg-slate-800 text-slate-400'
        }`}>
          {plan.status}
        </span>
      </div>

      {/* Summary header */}
      <div className="bg-slate-800/80 border border-slate-700 rounded-xl p-4">
        <div className="text-white font-semibold">{plan.person_name}</div>
        <div className="text-slate-400 text-xs mt-1">{plan.plan_date}</div>
        <div className="grid grid-cols-3 gap-3 mt-3">
          <div className="text-center">
            <div className="text-cyan-400 font-bold text-lg">{plan.total_tasks}</div>
            <div className="text-slate-500 text-xs">משימות</div>
          </div>
          <div className="text-center">
            <div className="text-cyan-400 font-bold text-lg">{plan.total_hours.toFixed(1)}</div>
            <div className="text-slate-500 text-xs">שעות</div>
          </div>
          <div className="text-center">
            <div className="text-cyan-400 font-bold text-lg">{plan.total_distance_km.toFixed(1)}</div>
            <div className="text-slate-500 text-xs">ק"מ</div>
          </div>
        </div>
      </div>

      {/* Weather warning */}
      {data.weather_warning && (
        <div className="bg-orange-950/50 border border-orange-700 rounded-xl p-3 text-xs text-orange-300">
          🌦️ {data.weather_warning}
        </div>
      )}

      {/* Equipment summary */}
      {data.equipment_summary?.length > 0 && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-3">
          <div className="text-slate-400 text-xs font-bold mb-2">🧰 ציוד נדרש</div>
          <div className="flex flex-wrap gap-1">
            {data.equipment_summary.map((eq, i) => (
              <span key={i} className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded-full">{eq}</span>
            ))}
          </div>
        </div>
      )}

      {/* Hebrew summary */}
      {data.summary_he && (
        <div className="text-sm text-slate-300 bg-slate-800/30 rounded-xl p-3">
          {data.summary_he}
        </div>
      )}

      {/* Timeline */}
      <TaskTimeline plan={data} />
    </div>
  );
}

export default function DailyPlansPanel() {
  const [workers, setWorkers] = useState([]);
  const [plans, setPlans] = useState([]);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [generating, setGenerating] = useState(null); // person_id being generated
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('workers'); // workers | plans

  useEffect(() => {
    Promise.all([
      getDailyPlanWorkers().catch(() => []),
      getDailyPlans().catch(() => []),
    ]).then(([w, p]) => {
      setWorkers(w);
      setPlans(p);
    }).finally(() => setLoading(false));
  }, []);

  const handleGenerate = async (personId) => {
    setGenerating(personId);
    try {
      const plan = await generateDailyPlan({ person_id: personId });
      setPlans(prev => [plan, ...prev]);
      setSelectedPlan(plan);
      setTab('plans');
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'שגיאה ביצירת תוכנית';
      alert(msg);
    } finally {
      setGenerating(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        <div className="animate-spin text-2xl">⚙️</div>
      </div>
    );
  }

  if (selectedPlan) {
    return <PlanDetail plan={selectedPlan} onBack={() => setSelectedPlan(null)} />;
  }

  return (
    <div className="space-y-4">
      {/* Tab switcher */}
      <div className="flex gap-2">
        <button
          onClick={() => setTab('workers')}
          className={`text-xs font-bold px-3 py-1.5 rounded-lg transition-colors ${
            tab === 'workers' ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'
          }`}
        >
          👥 עובדים ({workers.length})
        </button>
        <button
          onClick={() => setTab('plans')}
          className={`text-xs font-bold px-3 py-1.5 rounded-lg transition-colors ${
            tab === 'plans' ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'
          }`}
        >
          📋 תוכניות ({plans.length})
        </button>
      </div>

      {tab === 'workers' && (
        <div className="grid gap-3">
          {workers.map(w => (
            <WorkerCard
              key={w.id}
              worker={w}
              onGenerate={handleGenerate}
              generating={generating === w.id}
            />
          ))}
          {workers.length === 0 && (
            <div className="text-slate-500 text-sm text-center py-8">אין עובדים פעילים</div>
          )}
        </div>
      )}

      {tab === 'plans' && (
        <div className="space-y-2">
          {plans.map(p => (
            <button
              key={p.id}
              onClick={() => setSelectedPlan(p)}
              className="w-full text-right border border-slate-700 rounded-xl p-3 bg-slate-800/50 hover:bg-slate-800 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-white text-sm font-semibold">{p.person_name}</div>
                  <div className="text-slate-400 text-xs font-mono">{p.plan_date}</div>
                </div>
                <div className="text-right">
                  <div className="text-cyan-400 text-sm font-bold">{p.total_tasks} משימות</div>
                  <div className="text-slate-500 text-xs">{p.total_hours.toFixed(1)}h / {p.total_distance_km.toFixed(1)}km</div>
                </div>
              </div>
            </button>
          ))}
          {plans.length === 0 && (
            <div className="text-slate-500 text-sm text-center py-8">טרם נוצרו תוכניות עבודה</div>
          )}
        </div>
      )}
    </div>
  );
}
