import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import {
  Clock,
  CheckCircle2,
  TrendingUp,
  Activity,
  Info,
  MoreHorizontal,
} from "lucide-react";

export function Dashboard() {
  const { data: metrics, isLoading } = useQuery({
    queryKey: ["metrics-summary"],
    queryFn: () => apiRequest("/api/v1/metrics/summary"),
    refetchInterval: 15000,
  });

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-12 text-findeck-muted">
        Loading metrics...
      </div>
    );
  }

  const counts = metrics?.status_counts || {};
  const editRates = metrics?.field_edit_rates_7d || {};

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-22 font-semibold text-findeck-text tracking-tight">
            System Performance & Metrics
          </h1>
          <p className="text-sm text-findeck-muted mt-1">
            Real-time throughput, queue latency, and review accuracy telemetry.
          </p>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Pending Review */}
        <div className="bg-white p-5 rounded-card border border-findeck-border shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-findeck-muted flex items-center gap-1.5">
              <span>Pending Review</span>
              <Info className="h-3.5 w-3.5 text-findeck-muted/70" />
            </span>
            <MoreHorizontal className="h-4 w-4 text-findeck-muted/50" />
          </div>
          <div className="mt-3">
            <div className="text-28 font-semibold text-findeck-text tracking-tight font-mono tabular-nums">
              {counts["NEEDS_REVIEW"] || 0}
            </div>
            <div className="mt-2.5 flex items-center gap-2">
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-pill bg-amber-50 text-amber-800 border border-amber-200/60">
                <Clock className="h-3 w-3 mr-1" />
                Active
              </span>
              <span className="text-xs text-findeck-muted">requires review</span>
            </div>
          </div>
        </div>

        {/* Pushed to Accounting */}
        <div className="bg-white p-5 rounded-card border border-findeck-border shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-findeck-muted flex items-center gap-1.5">
              <span>Pushed to Accounting</span>
              <Info className="h-3.5 w-3.5 text-findeck-muted/70" />
            </span>
            <MoreHorizontal className="h-4 w-4 text-findeck-muted/50" />
          </div>
          <div className="mt-3">
            <div className="text-28 font-semibold text-findeck-text tracking-tight font-mono tabular-nums">
              {counts["PUSHED"] || 0}
            </div>
            <div className="mt-2.5 flex items-center gap-2">
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-pill bg-findeck-pill-up-bg text-findeck-pill-up-text border border-emerald-200/50">
                <CheckCircle2 className="h-3 w-3 mr-1" />
                Pushed
              </span>
              <span className="text-xs text-findeck-muted">ledger synced</span>
            </div>
          </div>
        </div>

        {/* Median Time to Approve */}
        <div className="bg-white p-5 rounded-card border border-findeck-border shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-findeck-muted flex items-center gap-1.5">
              <span>Median Time to Approve</span>
              <Info className="h-3.5 w-3.5 text-findeck-muted/70" />
            </span>
            <MoreHorizontal className="h-4 w-4 text-findeck-muted/50" />
          </div>
          <div className="mt-3">
            <div className="text-28 font-semibold text-findeck-text tracking-tight font-mono tabular-nums">
              {metrics?.median_time_to_approve_minutes || 0}{" "}
              <span className="text-sm font-normal text-findeck-muted">min</span>
            </div>
            <div className="mt-2.5 flex items-center gap-2">
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-pill bg-findeck-bg-sidebar text-findeck-text border border-findeck-border">
                <Activity className="h-3 w-3 mr-1 text-findeck-muted" />
                Throughput
              </span>
              <span className="text-xs text-findeck-muted">review speed</span>
            </div>
          </div>
        </div>

        {/* Oldest Waiting Queue Age */}
        <div className="bg-white p-5 rounded-card border border-findeck-border shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-findeck-muted flex items-center gap-1.5">
              <span>Oldest Waiting Queue Age</span>
              <Info className="h-3.5 w-3.5 text-findeck-muted/70" />
            </span>
            <MoreHorizontal className="h-4 w-4 text-findeck-muted/50" />
          </div>
          <div className="mt-3">
            <div className="text-28 font-semibold text-findeck-text tracking-tight font-mono tabular-nums">
              {metrics?.oldest_waiting_age_minutes || 0}{" "}
              <span className="text-sm font-normal text-findeck-muted">min</span>
            </div>
            <div className="mt-2.5 flex items-center gap-2">
              <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-pill bg-findeck-bg-sidebar text-findeck-text border border-findeck-border">
                <TrendingUp className="h-3 w-3 mr-1 text-findeck-muted" />
                Queue
              </span>
              <span className="text-xs text-findeck-muted">wait latency</span>
            </div>
          </div>
        </div>
      </div>

      {/* Reviewer Edit Rates Breakdown (7 Days) */}
      <div className="bg-white rounded-card border border-findeck-border shadow-xs p-6 space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-findeck-text text-15">
                Human Field Edit Rate (Past 7 Days)
              </h3>
              <Info className="h-3.5 w-3.5 text-findeck-muted/70" />
            </div>
            <p className="text-xs text-findeck-muted mt-0.5">
              Frequency of reviewer modifications per field (indicates model extraction accuracy trends).
            </p>
          </div>
          <div className="text-xs font-medium text-findeck-muted bg-findeck-bg-sidebar px-3 py-1.5 rounded-pill border border-findeck-border font-mono tabular-nums">
            Total human edits: {metrics?.total_edits_7d || 0}
          </div>
        </div>

        {Object.keys(editRates).length === 0 ? (
          <div className="py-8 text-center text-xs text-findeck-muted">
            No human edits recorded in the past 7 days.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-1">
            {Object.entries(editRates).map(([field, rate]: [string, any]) => {
              const pct = (rate * 100);
              const isHigh = pct > 20;
              return (
                <div
                  key={field}
                  className="p-4 bg-findeck-app rounded-card border border-findeck-border/80 flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-findeck-text capitalize">
                      {field.replace(/_/g, " ")}
                    </span>
                    <span
                      className={`font-mono tabular-nums font-semibold ${
                        isHigh ? "text-amber-700" : "text-findeck-accent"
                      }`}
                    >
                      {pct.toFixed(1)}%
                    </span>
                  </div>
                  {/* Findeck-style progress bar */}
                  <div className="mt-3 h-2 w-full bg-findeck-border/60 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-300 ${
                        isHigh ? "bg-amber-500" : "bg-findeck-accent"
                      }`}
                      style={{ width: `${Math.min(pct, 100)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
