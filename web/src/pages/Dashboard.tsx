import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import {
  Clock,
  CheckCircle2,
  TrendingUp,
  Activity,
} from "lucide-react";

export function Dashboard() {
  const { data: metrics, isLoading } = useQuery({
    queryKey: ["metrics-summary"],
    queryFn: () => apiRequest("/api/v1/metrics/summary"),
    refetchInterval: 15000,
  });

  if (isLoading) {
    return <div className="p-8 text-center text-slate-500">Loading metrics...</div>;
  }

  const counts = metrics?.status_counts || {};
  const editRates = metrics?.field_edit_rates_7d || {};

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">System Performance & Metrics</h1>
        <p className="text-sm text-slate-600 mt-1">
          Real-time throughput, queue latency, and review accuracy telemetry.
        </p>
      </div>

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Pending Review
            </div>
            <div className="text-2xl font-black text-amber-600 mt-1">
              {counts["NEEDS_REVIEW"] || 0}
            </div>
          </div>
          <div className="h-11 w-11 rounded-xl bg-amber-50 flex items-center justify-center text-amber-600">
            <Clock className="h-6 w-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Pushed to Accounting
            </div>
            <div className="text-2xl font-black text-emerald-600 mt-1">
              {counts["PUSHED"] || 0}
            </div>
          </div>
          <div className="h-11 w-11 rounded-xl bg-emerald-50 flex items-center justify-center text-emerald-600">
            <CheckCircle2 className="h-6 w-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Median Time to Approve
            </div>
            <div className="text-2xl font-black text-indigo-600 mt-1">
              {metrics?.median_time_to_approve_minutes || 0} <span className="text-sm font-medium">min</span>
            </div>
          </div>
          <div className="h-11 w-11 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600">
            <Activity className="h-6 w-6" />
          </div>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Oldest Waiting Queue Age
            </div>
            <div className="text-2xl font-black text-slate-900 mt-1">
              {metrics?.oldest_waiting_age_minutes || 0} <span className="text-sm font-medium">min</span>
            </div>
          </div>
          <div className="h-11 w-11 rounded-xl bg-slate-100 flex items-center justify-center text-slate-700">
            <TrendingUp className="h-6 w-6" />
          </div>
        </div>
      </div>

      {/* Reviewer Edit Rates Breakdown (7 Days) */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-slate-900 text-base">Human Field Edit Rate (Past 7 Days)</h3>
            <p className="text-xs text-slate-500">
              Frequency of reviewer modifications per field (indicates model extraction accuracy trends).
            </p>
          </div>
          <div className="text-xs font-medium text-slate-500">
            Total human edits: {metrics?.total_edits_7d || 0}
          </div>
        </div>

        {Object.keys(editRates).length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-400">
            No human edits recorded in the past 7 days.
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 pt-2">
            {Object.entries(editRates).map(([field, rate]: [string, any]) => (
              <div key={field} className="p-3.5 bg-slate-50 rounded-xl border border-slate-100">
                <div className="text-xs font-semibold text-slate-600 capitalize">
                  {field.replace("_", " ")}
                </div>
                <div className="text-lg font-bold text-indigo-700 mt-1">
                  {(rate * 100).toFixed(1)}%
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
