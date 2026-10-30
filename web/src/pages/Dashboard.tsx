import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import {
  Clock,
  CheckCircle2,
  TrendingUp,
  Activity,
  Info,
  Building2,
  Cpu,
} from "lucide-react";

export function Dashboard() {
  const { data: metrics, isLoading } = useQuery({
    queryKey: ["metrics-summary"],
    queryFn: () => apiRequest("/api/v1/metrics/summary"),
    refetchInterval: 15000,
  });

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-12 text-xs" style={{ color: "var(--text-muted)" }}>
        Loading metrics...
      </div>
    );
  }

  const counts = metrics?.status_counts || {};
  const editRates = metrics?.field_edit_rates_7d || {};

  return (
    <div className="w-full space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
            System Performance & Metrics
          </h1>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Real-time throughput, queue latency, and review accuracy telemetry.
          </p>
        </div>
      </div>

      {/* KPI Cards Grid (4 equal-width cards rotating through Reference B pastel badges) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Pending Review (Periwinkle pastel badge - #9BA1F9) */}
        <div
          className="p-6 rounded-[20px] border shadow-xs hover:shadow-sm transition-all flex flex-col justify-between"
          style={{
            backgroundColor: "var(--bg-inset)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center space-x-3.5">
            <div
              className="h-11 w-11 rounded-full flex items-center justify-center shrink-0 shadow-[0_4px_12px_rgba(155,161,249,0.35)]"
              style={{
                backgroundColor: "var(--accent)",
                color: "var(--ink)",
              }}
            >
              <Clock className="h-5 w-5 stroke-[2.2]" aria-hidden="true" />
            </div>
            <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Pending Review
            </span>
          </div>

          <div className="mt-5">
            <div className="flex items-center gap-2.5">
              <span className="text-[32px] font-bold tracking-tight font-mono tabular-nums leading-none" style={{ color: "var(--text)" }}>
                {counts["NEEDS_REVIEW"] || 0}
              </span>
              <span
                className="inline-flex items-center text-[11px] font-bold px-2 py-0.5 rounded-full"
                style={{
                  backgroundColor: "var(--accent)",
                  color: "var(--ink)",
                }}
              >
                Active
              </span>
            </div>
            <p className="text-xs font-medium mt-1.5" style={{ color: "var(--text-muted)" }}>
              requires review
            </p>
          </div>
        </div>

        {/* 2. Pushed to Accounting (Mint pastel badge - #A0E89E) */}
        <div
          className="p-6 rounded-[20px] border shadow-xs hover:shadow-sm transition-all flex flex-col justify-between"
          style={{
            backgroundColor: "var(--bg-inset)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center space-x-3.5">
            <div
              className="h-11 w-11 rounded-full flex items-center justify-center shrink-0 shadow-[0_4px_12px_rgba(160,232,158,0.4)]"
              style={{
                backgroundColor: "var(--success)",
                color: "var(--ink)",
              }}
            >
              <CheckCircle2 className="h-5 w-5 stroke-[2.2]" aria-hidden="true" />
            </div>
            <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Pushed to Accounting
            </span>
          </div>

          <div className="mt-5">
            <div className="flex items-center gap-2.5">
              <span className="text-[32px] font-bold tracking-tight font-mono tabular-nums leading-none" style={{ color: "var(--text)" }}>
                {counts["PUSHED"] || 0}
              </span>
              <span
                className="inline-flex items-center text-[11px] font-bold px-2 py-0.5 rounded-full"
                style={{
                  backgroundColor: "var(--success)",
                  color: "var(--ink)",
                }}
              >
                Pushed
              </span>
            </div>
            <p className="text-xs font-medium mt-1.5" style={{ color: "var(--text-muted)" }}>
              ledger synced
            </p>
          </div>
        </div>

        {/* 3. Median Time to Approve (Coral pastel badge - #FE8287) */}
        <div
          className="p-6 rounded-[20px] border shadow-xs hover:shadow-sm transition-all flex flex-col justify-between"
          style={{
            backgroundColor: "var(--bg-inset)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center space-x-3.5">
            <div
              className="h-11 w-11 rounded-full flex items-center justify-center shrink-0 shadow-[0_4px_12px_rgba(254,130,135,0.35)]"
              style={{
                backgroundColor: "var(--danger)",
                color: "var(--ink)",
              }}
            >
              <Activity className="h-5 w-5 stroke-[2.2]" aria-hidden="true" />
            </div>
            <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Median Time to Approve
            </span>
          </div>

          <div className="mt-5">
            <div className="flex items-center gap-2.5">
              <span className="text-[32px] font-bold tracking-tight font-mono tabular-nums leading-none flex items-baseline gap-1" style={{ color: "var(--text)" }}>
                <span>{metrics?.median_time_to_approve_minutes || 0}</span>
                <span className="text-sm font-normal" style={{ color: "var(--text-muted)" }}>min</span>
              </span>
              <span
                className="inline-flex items-center text-[11px] font-bold px-2 py-0.5 rounded-full"
                style={{
                  backgroundColor: "var(--danger)",
                  color: "var(--ink)",
                }}
              >
                Throughput
              </span>
            </div>
            <p className="text-xs font-medium mt-1.5" style={{ color: "var(--text-muted)" }}>
              review speed
            </p>
          </div>
        </div>

        {/* 4. Oldest Waiting Queue Age (Orange pastel badge - #FFAC6F) */}
        <div
          className="p-6 rounded-[20px] border shadow-xs hover:shadow-sm transition-all flex flex-col justify-between"
          style={{
            backgroundColor: "var(--bg-inset)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center space-x-3.5">
            <div
              className="h-11 w-11 rounded-full flex items-center justify-center shrink-0 shadow-[0_4px_12px_rgba(255,172,111,0.4)]"
              style={{
                backgroundColor: "var(--warning)",
                color: "var(--ink)",
              }}
            >
              <TrendingUp className="h-5 w-5 stroke-[2.2]" aria-hidden="true" />
            </div>
            <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Oldest Waiting Queue Age
            </span>
          </div>

          <div className="mt-5">
            <div className="flex items-center gap-2.5">
              <span className="text-[32px] font-bold tracking-tight font-mono tabular-nums leading-none flex items-baseline gap-1" style={{ color: "var(--text)" }}>
                <span>{metrics?.oldest_waiting_age_minutes || 0}</span>
                <span className="text-sm font-normal" style={{ color: "var(--text-muted)" }}>min</span>
              </span>
              <span
                className="inline-flex items-center text-[11px] font-bold px-2 py-0.5 rounded-full"
                style={{
                  backgroundColor: "var(--warning)",
                  color: "var(--ink)",
                }}
              >
                Queue
              </span>
            </div>
            <p className="text-xs font-medium mt-1.5" style={{ color: "var(--text-muted)" }}>
              wait latency
            </p>
          </div>
        </div>
      </div>

      {/* Reviewer Edit Rates Breakdown on --bg-card */}
      <div
        className="rounded-[20px] border shadow-xs p-6 space-y-6"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-base" style={{ color: "var(--text)" }}>
                Human Field Edit Rate (Past 7 Days)
              </h3>
              <Info className="h-3.5 w-3.5 opacity-60" style={{ color: "var(--text-muted)" }} aria-hidden="true" />
            </div>
            <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
              Frequency of reviewer modifications per field (indicates model extraction accuracy trends).
            </p>
          </div>
          <div
            className="text-xs font-semibold px-3.5 py-1.5 rounded-full border font-mono tabular-nums shadow-2xs self-start sm:self-auto"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
              color: "var(--text)",
            }}
          >
            Total human edits: {metrics?.total_edits_7d || 0}
          </div>
        </div>

        {Object.keys(editRates).length === 0 ? (
          <div className="py-10 text-center text-xs" style={{ color: "var(--text-muted)" }}>
            No human edits recorded in the past 7 days.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {Object.entries(editRates).map(([field, rate]: [string, any]) => {
              const pct = (rate * 100);
              const isHigh = pct > 20;
              return (
                <div
                  key={field}
                  className="p-5 rounded-2xl border shadow-2xs hover:shadow-xs transition-shadow flex flex-col justify-between"
                  style={{
                    backgroundColor: "var(--bg-inset)",
                    borderColor: "var(--border)",
                  }}
                >
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="font-semibold text-sm capitalize" style={{ color: "var(--text)" }}>
                      {field.replace(/_/g, " ")}
                    </span>
                    <span
                      className="font-mono tabular-nums font-bold text-xs px-2.5 py-0.5 rounded-full"
                      style={{
                        backgroundColor: isHigh ? "var(--warning)" : "var(--accent)",
                        color: "var(--ink)",
                      }}
                    >
                      {pct.toFixed(1)}%
                    </span>
                  </div>
                  {/* Modern rounded progress bar */}
                  <div
                    className="mt-4 h-2.5 w-full rounded-full overflow-hidden border"
                    style={{
                      backgroundColor: "var(--bg-app)",
                      borderColor: "var(--border)",
                    }}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${Math.min(pct, 100)}%`,
                        backgroundColor: isHigh ? "var(--warning)" : "var(--accent)",
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Grid: Worst 5 Suppliers and LLM Cost & Usage */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Worst 5 Suppliers by Human Edit Rate */}
        <div
          className="rounded-[20px] border shadow-xs p-6 flex flex-col justify-between"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div>
            <div className="flex items-center justify-between gap-3 mb-4">
              <div className="flex items-center space-x-2.5">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
                  style={{
                    backgroundColor: "var(--warning-soft)",
                    color: "var(--warning-strong)",
                  }}
                >
                  <Building2 className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="font-bold text-sm" style={{ color: "var(--text)" }}>
                    Worst Suppliers by Human Edit Rate
                  </h3>
                  <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                    Suppliers with highest frequency of manual reviewer corrections.
                  </p>
                </div>
              </div>
            </div>

            {(!metrics?.worst_suppliers || metrics.worst_suppliers.length === 0) ? (
              <div className="py-8 text-center text-xs" style={{ color: "var(--text-muted)" }}>
                No supplier corrections recorded.
              </div>
            ) : (
              <div className="space-y-3">
                {metrics.worst_suppliers.map((s: any) => {
                  const ratePct = (s.edit_rate * 100).toFixed(1);
                  return (
                    <div
                      key={s.gstin}
                      className="p-3 rounded-xl border flex items-center justify-between transition-all"
                      style={{
                        backgroundColor: "var(--bg-inset)",
                        borderColor: "var(--border)",
                      }}
                    >
                      <div className="min-w-0 pr-3">
                        <div className="text-xs font-semibold truncate" style={{ color: "var(--text)" }}>
                          {s.name}
                        </div>
                        <div className="text-[11px] font-mono mt-0.5" style={{ color: "var(--text-muted)" }}>
                          {s.gstin} • {s.total_invoices} invoices ({s.edit_count} edits)
                        </div>
                      </div>
                      <span
                        className="px-2.5 py-1 rounded-full text-xs font-bold font-mono tabular-nums shrink-0"
                        style={{
                          backgroundColor: "var(--warning)",
                          color: "var(--ink)",
                        }}
                      >
                        {ratePct}%
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* LLM Cost & Token Usage */}
        <div
          className="rounded-[20px] border shadow-xs p-6 flex flex-col justify-between"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div>
            <div className="flex items-center space-x-2.5 mb-4">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
                style={{
                  backgroundColor: "var(--accent-soft)",
                  color: "var(--accent-strong)",
                }}
              >
                <Cpu className="h-4 w-4" />
              </div>
              <div>
                <h3 className="font-bold text-sm" style={{ color: "var(--text)" }}>
                  LLM Extraction Cost & Quality
                </h3>
                <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                  Token consumption, model efficiency, and estimated extraction spend.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <div
                className="p-3.5 rounded-xl border"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                }}
              >
                <div className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>
                  Estimated Total Cost
                </div>
                <div className="text-xl font-bold font-mono tabular-nums mt-1" style={{ color: "var(--text)" }}>
                  ${(metrics?.cost_and_usage?.estimated_total_cost_usd ?? 0).toFixed(4)}
                </div>
                <div className="text-[10px] mt-1" style={{ color: "var(--text-muted)" }}>
                  avg ${(metrics?.cost_and_usage?.estimated_cost_per_invoice_usd ?? 0).toFixed(4)} / invoice
                </div>
              </div>

              <div
                className="p-3.5 rounded-xl border"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                }}
              >
                <div className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>
                  Total Tokens Processed
                </div>
                <div className="text-xl font-bold font-mono tabular-nums mt-1" style={{ color: "var(--text)" }}>
                  {(metrics?.cost_and_usage?.total_tokens ?? 0).toLocaleString()}
                </div>
                <div className="text-[10px] mt-1" style={{ color: "var(--text-muted)" }}>
                  avg {(metrics?.cost_and_usage?.avg_tokens_per_invoice ?? 0).toLocaleString()} / invoice
                </div>
              </div>
            </div>

            <div
              className="p-3.5 rounded-xl border text-xs space-y-2"
              style={{
                backgroundColor: "var(--bg-inset)",
                borderColor: "var(--border)",
              }}
            >
              <div className="flex items-center justify-between text-[11px]">
                <span style={{ color: "var(--text-muted)" }}>Prompt Tokens</span>
                <span className="font-mono font-semibold" style={{ color: "var(--text)" }}>
                  {(metrics?.cost_and_usage?.prompt_tokens ?? 0).toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span style={{ color: "var(--text-muted)" }}>Completion Tokens</span>
                <span className="font-mono font-semibold" style={{ color: "var(--text)" }}>
                  {(metrics?.cost_and_usage?.completion_tokens ?? 0).toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
