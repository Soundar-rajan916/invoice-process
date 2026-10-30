import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import {
  RefreshCw,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";

export function Reconciliation() {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // 1. Fetch Runs
  const { data: runs = [], isLoading: loadingRuns } = useQuery({
    queryKey: ["admin-reconciliation-runs"],
    queryFn: () => apiRequest("/api/v1/admin/reconciliation/runs?limit=20"),
    refetchInterval: 15000,
  });

  // 2. Fetch Selected Run Detail & Findings
  const activeRunId = selectedRunId || (runs.length > 0 ? runs[0].id : null);

  const { data: runDetail, isLoading: loadingDetail } = useQuery({
    queryKey: ["admin-reconciliation-detail", activeRunId],
    queryFn: () => apiRequest(`/api/v1/admin/reconciliation/runs/${activeRunId}`),
    enabled: !!activeRunId,
  });

  // 3. Trigger Run Mutation
  const triggerMutation = useMutation({
    mutationFn: () =>
      apiRequest("/api/v1/admin/reconciliation/trigger", {
        method: "POST",
      }),
    onSuccess: (data: any) => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-reconciliation-runs"] });
      if (data?.run_id) {
        setSelectedRunId(data.run_id);
      }
    },
    onError: (err: any) => {
      setActionError(err.message || "Failed to trigger reconciliation run");
    },
  });

  return (
    <div className="w-full space-y-6">
      {/* Header */}
      <div
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-card border shadow-xs"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
            Accounting Reconciliation
          </h1>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Nightly discrepancy detection between InvoiceFlow ledger and external ERP/accounting books.
          </p>
        </div>

        <button
          onClick={() => triggerMutation.mutate()}
          disabled={triggerMutation.isPending}
          className="inline-flex items-center space-x-2 px-4 py-2.5 rounded-btn text-xs font-semibold shadow-xs cursor-pointer select-none transition-colors"
          style={{
            backgroundColor: "var(--ink)",
            color: "#FFFFFF",
          }}
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${triggerMutation.isPending ? "animate-spin" : ""}`}
          />
          <span>{triggerMutation.isPending ? "Starting Run..." : "Trigger Reconciliation"}</span>
        </button>
      </div>

      {actionError && (
        <div
          className="p-4 rounded-xl border flex items-center space-x-2 text-xs"
          style={{
            backgroundColor: "var(--danger-soft)",
            borderColor: "rgba(254, 130, 135, 0.3)",
            color: "var(--danger-strong)",
          }}
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Grid: Runs list on left, Findings on right */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Runs List */}
        <div
          className="rounded-[20px] border shadow-xs p-5 space-y-4"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-sm" style={{ color: "var(--text)" }}>
              Audit Runs
            </h3>
            <span className="text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
              {runs.length} runs
            </span>
          </div>

          {loadingRuns ? (
            <div className="py-8 text-center text-xs" style={{ color: "var(--text-muted)" }}>
              Loading runs...
            </div>
          ) : runs.length === 0 ? (
            <div className="py-8 text-center text-xs" style={{ color: "var(--text-muted)" }}>
              No reconciliation runs recorded yet.
            </div>
          ) : (
            <div className="space-y-2">
              {runs.map((r: any) => {
                const isSelected = r.id === activeRunId;
                const hasDiscrepancies = (r.total_discrepancies || 0) > 0;
                return (
                  <button
                    key={r.id}
                    onClick={() => setSelectedRunId(r.id)}
                    className="w-full text-left p-3.5 rounded-xl border transition-all cursor-pointer"
                    style={{
                      backgroundColor: isSelected ? "var(--bg-inset)" : "transparent",
                      borderColor: isSelected ? "var(--accent)" : "var(--border)",
                    }}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold" style={{ color: "var(--text)" }}>
                        {new Date(r.started_at).toLocaleString()}
                      </span>
                      <span
                        className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                        style={{
                          backgroundColor:
                            r.status === "completed"
                              ? "var(--success)"
                              : r.status === "failed"
                              ? "var(--danger)"
                              : "var(--warning)",
                          color: "var(--ink)",
                        }}
                      >
                        {r.status}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] font-mono mt-2" style={{ color: "var(--text-muted)" }}>
                      <span>Checked: {r.total_checked}</span>
                      <span
                        className="font-bold px-1.5 py-0.5 rounded"
                        style={{
                          backgroundColor: hasDiscrepancies ? "var(--warning-soft)" : "transparent",
                          color: hasDiscrepancies ? "var(--warning-strong)" : "var(--text-muted)",
                        }}
                      >
                        {r.total_discrepancies} Discrepanc{r.total_discrepancies === 1 ? "y" : "ies"}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Selected Run Findings Detail */}
        <div
          className="lg:col-span-2 rounded-[20px] border shadow-xs p-6 space-y-6"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          {loadingDetail ? (
            <div className="py-12 text-center text-xs" style={{ color: "var(--text-muted)" }}>
              Loading run findings...
            </div>
          ) : !runDetail ? (
            <div className="py-12 text-center text-xs" style={{ color: "var(--text-muted)" }}>
              Select a reconciliation run to view findings.
            </div>
          ) : (
            <>
              {/* Summary Stats */}
              <div className="grid grid-cols-3 gap-3">
                <div
                  className="p-4 rounded-xl border text-center"
                  style={{
                    backgroundColor: "var(--bg-inset)",
                    borderColor: "var(--border)",
                  }}
                >
                  <div className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>
                    Total Checked
                  </div>
                  <div className="text-xl font-bold font-mono tabular-nums mt-1" style={{ color: "var(--text)" }}>
                    {runDetail.total_checked}
                  </div>
                </div>

                <div
                  className="p-4 rounded-xl border text-center"
                  style={{
                    backgroundColor: "var(--bg-inset)",
                    borderColor: "var(--border)",
                  }}
                >
                  <div className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>
                    Matched Cleanly
                  </div>
                  <div className="text-xl font-bold font-mono tabular-nums mt-1" style={{ color: "var(--text)" }}>
                    {runDetail.total_matched}
                  </div>
                </div>

                <div
                  className="p-4 rounded-xl border text-center"
                  style={{
                    backgroundColor:
                      (runDetail.total_discrepancies || 0) > 0
                        ? "var(--warning-soft)"
                        : "var(--bg-inset)",
                    borderColor: "var(--border)",
                  }}
                >
                  <div className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>
                    Discrepancies
                  </div>
                  <div
                    className="text-xl font-bold font-mono tabular-nums mt-1"
                    style={{
                      color:
                        (runDetail.total_discrepancies || 0) > 0
                          ? "var(--warning-strong)"
                          : "var(--text)",
                    }}
                  >
                    {runDetail.total_discrepancies}
                  </div>
                </div>
              </div>

              {/* Discrepancy Findings List */}
              <div className="space-y-3">
                <h3 className="font-bold text-sm" style={{ color: "var(--text)" }}>
                  Discrepancy Findings ({runDetail.findings?.length || 0})
                </h3>

                {(!runDetail.findings || runDetail.findings.length === 0) ? (
                  <div
                    className="p-6 rounded-xl border text-center space-y-1"
                    style={{
                      backgroundColor: "var(--success-soft)",
                      borderColor: "rgba(160, 232, 158, 0.4)",
                    }}
                  >
                    <CheckCircle2
                      className="h-6 w-6 mx-auto"
                      style={{ color: "var(--success-strong)" }}
                    />
                    <div className="text-xs font-semibold" style={{ color: "var(--success-strong)" }}>
                      100% Ledger Consistency
                    </div>
                    <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                      All pushed invoices strictly match the accounting system records.
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {runDetail.findings.map((f: any) => {
                      const isError = f.severity === "error";
                      return (
                        <div
                          key={f.id}
                          className="p-4 rounded-xl border space-y-2"
                          style={{
                            backgroundColor: isError ? "var(--danger-soft)" : "var(--warning-soft)",
                            borderColor: isError
                              ? "rgba(254, 130, 135, 0.3)"
                              : "rgba(255, 217, 102, 0.4)",
                          }}
                        >
                          <div className="flex items-center justify-between">
                            <span
                              className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                              style={{
                                backgroundColor: isError ? "var(--danger)" : "var(--warning)",
                                color: "var(--ink)",
                              }}
                            >
                              {f.discrepancy_type.replace(/_/g, " ")}
                            </span>
                            <span className="text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
                              Invoice: {f.invoice_id || "Unlinked"}
                            </span>
                          </div>

                          <div className="text-xs font-medium" style={{ color: "var(--text)" }}>
                            Accounting ID: <span className="font-mono">{f.accounting_id || "None"}</span>
                          </div>

                          {f.details && (
                            <pre
                              className="p-2.5 rounded-lg text-[11px] font-mono overflow-x-auto"
                              style={{
                                backgroundColor: "var(--bg-app)",
                                color: "var(--text)",
                                border: "1px solid var(--border)",
                              }}
                            >
                              {JSON.stringify(f.details, null, 2)}
                            </pre>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
