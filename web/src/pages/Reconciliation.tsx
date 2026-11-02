import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiRequest } from "@/lib/api";
import {
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  ShieldCheck,
  Scale,
  ExternalLink,
  Copy,
  Check,
  Server,
  Layers,
  AlertTriangle,
} from "lucide-react";
import {
  ReconciliationRunsSkeleton,
  ReconciliationFindingsSkeleton,
} from "@/components/Skeleton";

export function Reconciliation() {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("ALL");

  // 1. Fetch Audit Runs
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

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(id);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const findings = runDetail?.findings || [];
  const filteredFindings = findings.filter((f: any) => {
    const type = f.finding_type || f.discrepancy_type || "";
    if (filterType === "ALL") return true;
    if (filterType === "MISSING_ACC") return type === "missing_in_accounting";
    if (filterType === "MISMATCH") return type === "amount_mismatch";
    if (filterType === "MISSING_IF") return type === "missing_in_invoiceflow";
    return true;
  });

  const totalChecked = runDetail?.total_checked ?? 0;
  const totalMatched = runDetail?.total_matched ?? 0;
  const totalDiscrepancies = runDetail?.total_discrepancies ?? 0;
  const matchRate = totalChecked > 0 ? Math.round((totalMatched / totalChecked) * 100) : 100;

  return (
    <div className="w-full space-y-6 pb-12">
      {/* Hero Header */}
      <div
        className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 p-6 sm:p-8 rounded-card border shadow-xs"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        <div className="space-y-2 max-w-2xl">
          <div className="flex items-center space-x-2.5">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 shadow-2xs"
              style={{
                backgroundColor: "var(--accent-soft)",
                color: "var(--accent-strong)",
              }}
            >
              <Scale className="h-4 w-4 stroke-[2.5]" />
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
              Accounting Reconciliation
            </h1>
          </div>
          <p className="text-xs sm:text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            Independent ledger auditing comparing InvoiceFlow's approved invoice records with your external ERP / accounting books to guarantee balance integrity.
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <div
              className="inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-medium border"
              style={{
                backgroundColor: "var(--bg-inset)",
                borderColor: "var(--border)",
                color: "var(--text-secondary)",
              }}
            >
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <Server className="h-3.5 w-3.5" style={{ color: "var(--text-muted)" }} />
              <span>Accounting Bridge: Active</span>
            </div>

            <div
              className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-medium border"
              style={{
                backgroundColor: "var(--bg-inset)",
                borderColor: "var(--border)",
                color: "var(--text-muted)",
              }}
            >
              <Layers className="h-3.5 w-3.5" />
              <span>Daily Automated Sweep</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 shrink-0">
          <button
            onClick={() => triggerMutation.mutate()}
            disabled={triggerMutation.isPending}
            className="inline-flex items-center justify-center space-x-2 px-5 py-3 rounded-btn text-xs font-semibold shadow-xs cursor-pointer select-none transition-all active:scale-[0.98]"
            style={{
              backgroundColor: "var(--ink)",
              color: "#FFFFFF",
            }}
          >
            <RefreshCw
              className={`h-4 w-4 ${triggerMutation.isPending ? "animate-spin" : ""}`}
            />
            <span>{triggerMutation.isPending ? "Auditing Books..." : "Trigger Reconciliation"}</span>
          </button>
        </div>
      </div>

      {actionError && (
        <div
          className="p-4 rounded-xl border flex items-center space-x-2.5 text-xs shadow-xs"
          style={{
            backgroundColor: "var(--danger-soft)",
            borderColor: "rgba(254, 130, 135, 0.4)",
            color: "var(--danger-strong)",
          }}
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Main KPI Strip for Active Run */}
      {runDetail && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Consistency Rate */}
          <div
            className="p-5 rounded-card border shadow-xs flex flex-col justify-between"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                Consistency Rate
              </span>
              <ShieldCheck
                className="h-4 w-4"
                style={{
                  color: matchRate === 100 ? "var(--success-strong)" : "var(--warning-strong)",
                }}
              />
            </div>
            <div className="mt-3">
              <div className="text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums" style={{ color: "var(--text)" }}>
                {matchRate}%
              </div>
              <div className="text-[11px] mt-1 font-medium" style={{ color: "var(--text-muted)" }}>
                {matchRate === 100 ? "Full Ledger Parity" : "Discrepancies Detected"}
              </div>
            </div>
          </div>

          {/* Total Audited */}
          <div
            className="p-5 rounded-card border shadow-xs flex flex-col justify-between"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                Invoices Audited
              </span>
              <Layers className="h-4 w-4" style={{ color: "var(--text-muted)" }} />
            </div>
            <div className="mt-3">
              <div className="text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums" style={{ color: "var(--text)" }}>
                {totalChecked}
              </div>
              <div className="text-[11px] mt-1 font-medium" style={{ color: "var(--text-muted)" }}>
                Target batch scope
              </div>
            </div>
          </div>

          {/* Matched Cleanly */}
          <div
            className="p-5 rounded-card border shadow-xs flex flex-col justify-between"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                Clean Matches
              </span>
              <CheckCircle2 className="h-4 w-4" style={{ color: "var(--success-strong)" }} />
            </div>
            <div className="mt-3">
              <div className="text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums text-emerald-600">
                {totalMatched}
              </div>
              <div className="text-[11px] mt-1 font-medium" style={{ color: "var(--text-muted)" }}>
                Exact balance agreement
              </div>
            </div>
          </div>

          {/* Discrepancies */}
          <div
            className="p-5 rounded-card border shadow-xs flex flex-col justify-between"
            style={{
              backgroundColor: totalDiscrepancies > 0 ? "var(--warning-soft)" : "var(--bg-card)",
              borderColor: totalDiscrepancies > 0 ? "rgba(255, 172, 111, 0.4)" : "var(--border)",
            }}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium" style={{ color: totalDiscrepancies > 0 ? "var(--warning-strong)" : "var(--text-muted)" }}>
                Discrepancies
              </span>
              <AlertTriangle className="h-4 w-4" style={{ color: totalDiscrepancies > 0 ? "var(--warning-strong)" : "var(--text-muted)" }} />
            </div>
            <div className="mt-3">
              <div
                className="text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums"
                style={{
                  color: totalDiscrepancies > 0 ? "var(--warning-strong)" : "var(--text)",
                }}
              >
                {totalDiscrepancies}
              </div>
              <div className="text-[11px] mt-1 font-medium" style={{ color: totalDiscrepancies > 0 ? "var(--warning-strong)" : "var(--text-muted)" }}>
                {totalDiscrepancies > 0 ? "Requires ledger review" : "Zero variances"}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left: Audit Runs History (4 cols) */}
        <div
          className="lg:col-span-4 rounded-card border shadow-xs overflow-hidden"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div
            className="px-5 py-4 border-b flex items-center justify-between"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
            }}
          >
            <div>
              <h2 className="text-sm font-bold tracking-tight" style={{ color: "var(--text)" }}>
                Audit Run History
              </h2>
              <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                Recent ledger validation sweeps
              </p>
            </div>
            <span
              className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-medium border"
              style={{
                backgroundColor: "var(--bg-card)",
                borderColor: "var(--border)",
                color: "var(--text-secondary)",
              }}
            >
              {runs.length} runs
            </span>
          </div>

          <div className="p-3 space-y-2 max-h-[560px] overflow-y-auto">
            {loadingRuns ? (
              <ReconciliationRunsSkeleton count={4} />
            ) : runs.length === 0 ? (
              <div className="py-12 text-center text-xs space-y-2" style={{ color: "var(--text-muted)" }}>
                <p>No reconciliation runs found.</p>
                <button
                  onClick={() => triggerMutation.mutate()}
                  className="text-xs font-semibold underline cursor-pointer"
                  style={{ color: "var(--ink)" }}
                >
                  Run first audit now
                </button>
              </div>
            ) : (
              runs.map((r: any) => {
                const isSelected = r.id === activeRunId;
                const hasIssues = (r.total_discrepancies || 0) > 0;
                const runDate = new Date(r.started_at);

                return (
                  <button
                    key={r.id}
                    onClick={() => setSelectedRunId(r.id)}
                    className="w-full text-left p-3.5 rounded-card border transition-all cursor-pointer relative"
                    style={{
                      backgroundColor: isSelected ? "var(--bg-inset)" : "rgba(255, 255, 255, 0.45)",
                      borderColor: isSelected ? "var(--ink)" : "var(--border)",
                      boxShadow: isSelected
                        ? "0 4px 14px -2px rgba(0, 0, 0, 0.08), 0 0 0 1px var(--ink)"
                        : "none",
                    }}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center space-x-2">
                        {isSelected && (
                          <span
                            className="w-2 h-2 rounded-full shrink-0"
                            style={{ backgroundColor: "var(--accent-strong)" }}
                          />
                        )}
                        <span
                          className={`text-xs ${isSelected ? "font-bold" : "font-semibold"}`}
                          style={{ color: "var(--text)" }}
                        >
                          {runDate.toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                          })}{" "}
                          at{" "}
                          {runDate.toLocaleTimeString(undefined, {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                      </div>
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

                    <div
                      className="flex items-center justify-between text-[11px] font-mono"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <span>Checked: {r.total_checked}</span>
                      <span
                        className="font-bold px-2 py-0.5 rounded-full text-[10px]"
                        style={{
                          backgroundColor: hasIssues ? "var(--warning-soft)" : "var(--success-soft)",
                          color: hasIssues ? "var(--warning-strong)" : "var(--success-strong)",
                        }}
                      >
                        {hasIssues ? `${r.total_discrepancies} Issue${r.total_discrepancies === 1 ? "" : "s"}` : "Clean"}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right: Selected Run Findings & Details (8 cols) */}
        <div
          className="lg:col-span-8 rounded-card border shadow-xs overflow-hidden"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          {loadingDetail ? (
            <div className="p-6">
              <ReconciliationFindingsSkeleton count={3} />
            </div>
          ) : !runDetail ? (
            <div className="py-20 text-center space-y-2" style={{ color: "var(--text-muted)" }}>
              <Scale className="h-8 w-8 mx-auto stroke-1" />
              <p className="text-sm font-medium">Select a reconciliation run from the left</p>
              <p className="text-xs">Inspect individual discrepancy items and balance records.</p>
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: "var(--border)" }}>
              {/* Detail Header & Scope Bar */}
              <div
                className="p-5 sm:p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                style={{ backgroundColor: "var(--bg-inset)" }}
              >
                <div>
                  <div className="flex items-center space-x-2">
                    <h2 className="text-base font-bold" style={{ color: "var(--text)" }}>
                      Audit Findings & Variances
                    </h2>
                    <span
                      className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase"
                      style={{
                        backgroundColor: totalDiscrepancies > 0 ? "var(--warning-soft)" : "var(--success-soft)",
                        color: totalDiscrepancies > 0 ? "var(--warning-strong)" : "var(--success-strong)",
                      }}
                    >
                      {totalDiscrepancies > 0 ? `${totalDiscrepancies} Variance${totalDiscrepancies === 1 ? "" : "s"}` : "Zero Variances"}
                    </span>
                  </div>
                  <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                    Run ID: <span className="font-mono">{runDetail.id.slice(0, 8)}...</span> · Completed{" "}
                    {runDetail.completed_at ? new Date(runDetail.completed_at).toLocaleTimeString() : "Just now"}
                  </p>
                </div>

                {/* Filter Tabs */}
                {findings.length > 0 && (
                  <div
                    className="inline-flex items-center p-1 rounded-lg border text-xs"
                    style={{
                      backgroundColor: "var(--bg-card)",
                      borderColor: "var(--border)",
                    }}
                  >
                    <button
                      onClick={() => setFilterType("ALL")}
                      className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer ${
                        filterType === "ALL" ? "shadow-2xs" : ""
                      }`}
                      style={{
                        backgroundColor: filterType === "ALL" ? "var(--bg-inset)" : "transparent",
                        color: filterType === "ALL" ? "var(--text)" : "var(--text-muted)",
                      }}
                    >
                      All ({findings.length})
                    </button>
                    <button
                      onClick={() => setFilterType("MISSING_ACC")}
                      className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer ${
                        filterType === "MISSING_ACC" ? "shadow-2xs" : ""
                      }`}
                      style={{
                        backgroundColor: filterType === "MISSING_ACC" ? "var(--bg-inset)" : "transparent",
                        color: filterType === "MISSING_ACC" ? "var(--danger-strong)" : "var(--text-muted)",
                      }}
                    >
                      Missing
                    </button>
                    <button
                      onClick={() => setFilterType("MISMATCH")}
                      className={`px-2.5 py-1 rounded-md font-semibold transition-all cursor-pointer ${
                        filterType === "MISMATCH" ? "shadow-2xs" : ""
                      }`}
                      style={{
                        backgroundColor: filterType === "MISMATCH" ? "var(--bg-inset)" : "transparent",
                        color: filterType === "MISMATCH" ? "var(--warning-strong)" : "var(--text-muted)",
                      }}
                    >
                      Mismatches
                    </button>
                  </div>
                )}
              </div>

              {/* Findings Content */}
              <div className="p-6 max-h-[580px] overflow-y-auto">
                {findings.length === 0 ? (
                  /* 100% Consistent State */
                  <div
                    className="p-8 sm:p-10 rounded-2xl border text-center space-y-3"
                    style={{
                      backgroundColor: "var(--success-soft)",
                      borderColor: "rgba(160, 232, 158, 0.5)",
                    }}
                  >
                    <div
                      className="w-12 h-12 rounded-full mx-auto flex items-center justify-center shadow-xs"
                      style={{
                        backgroundColor: "var(--success)",
                        color: "var(--ink)",
                      }}
                    >
                      <CheckCircle2 className="h-6 w-6 stroke-[2.5]" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-emerald-950">
                        100% Ledger Balance Verified
                      </h3>
                      <p className="text-xs text-emerald-800 max-w-md mx-auto mt-1 leading-relaxed">
                        Every invoice pushed from InvoiceFlow matches the downstream accounting ledger perfectly. No missing invoices, unrecorded balances, or amount discrepancies were found.
                      </p>
                    </div>

                    <div
                      className="inline-flex items-center space-x-2 px-3 py-1.5 rounded-full text-[11px] font-mono font-medium border mt-2"
                      style={{
                        backgroundColor: "var(--bg-inset)",
                        borderColor: "rgba(160, 232, 158, 0.6)",
                        color: "var(--success-strong)",
                      }}
                    >
                      <span>Audited Records: {totalChecked}</span>
                      <span>·</span>
                      <span>Clean Matches: {totalMatched}</span>
                    </div>
                  </div>
                ) : filteredFindings.length === 0 ? (
                  <div className="py-12 text-center text-xs" style={{ color: "var(--text-muted)" }}>
                    No findings match the selected filter.
                  </div>
                ) : (
                  /* Discrepancy Cards */
                  <div className="space-y-4">
                    {filteredFindings.map((f: any, idx: number) => {
                      const type = f.finding_type || f.discrepancy_type || "discrepancy";
                      const isMissing = type === "missing_in_accounting";
                      const isMismatch = type === "amount_mismatch";
                      const details = f.details || {};
                      const invoiceNum = details.normalized_invoice_number || details.invoice_number || "Invoice";
                      const accountingId = details.accounting_id || f.accounting_id || "Unassigned";

                      return (
                        <div
                          key={f.id || idx}
                          className="rounded-2xl border overflow-hidden shadow-2xs transition-all hover:shadow-xs"
                          style={{
                            backgroundColor: "var(--bg-inset)",
                            borderColor: isMissing
                              ? "rgba(254, 130, 135, 0.4)"
                              : isMismatch
                              ? "rgba(255, 172, 111, 0.4)"
                              : "var(--border)",
                          }}
                        >
                          {/* Card Header Strip */}
                          <div
                            className="px-5 py-3.5 border-b flex flex-wrap items-center justify-between gap-2.5"
                            style={{
                              backgroundColor: isMissing
                                ? "var(--danger-soft)"
                                : isMismatch
                                ? "var(--warning-soft)"
                                : "var(--bg-card)",
                              borderColor: "var(--border)",
                            }}
                          >
                            <div className="flex items-center space-x-2">
                              <span
                                className="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider"
                                style={{
                                  backgroundColor: isMissing
                                    ? "var(--danger)"
                                    : isMismatch
                                    ? "var(--warning)"
                                    : "var(--accent)",
                                  color: "var(--ink)",
                                }}
                              >
                                {isMissing
                                  ? "Missing in Accounting"
                                  : isMismatch
                                  ? "Amount Mismatch"
                                  : type.replace(/_/g, " ")}
                              </span>
                              <span className="text-xs font-bold font-mono" style={{ color: "var(--text)" }}>
                                {invoiceNum}
                              </span>
                            </div>

                            {f.invoice_id && (
                              <Link
                                to={`/invoices/${f.invoice_id}`}
                                className="inline-flex items-center space-x-1 text-xs font-semibold transition-colors hover:underline"
                                style={{ color: "var(--accent-strong)" }}
                              >
                                <span>Inspect Invoice</span>
                                <ExternalLink className="h-3.5 w-3.5" />
                              </Link>
                            )}
                          </div>

                          {/* Card Body */}
                          <div className="p-5 space-y-4">
                            {/* Explanatory Message */}
                            <div
                              className="p-3.5 rounded-xl border text-xs leading-relaxed flex items-start space-x-2.5"
                              style={{
                                backgroundColor: "var(--bg-card)",
                                borderColor: "var(--border)",
                                color: "var(--text)",
                              }}
                            >
                              <AlertCircle
                                className="h-4 w-4 shrink-0 mt-0.5"
                                style={{
                                  color: isMissing ? "var(--danger-strong)" : "var(--warning-strong)",
                                }}
                              />
                              <div>
                                {isMissing && (
                                  <>
                                    <strong>Record missing from accounting ledger.</strong> InvoiceFlow marked this invoice as <code className="font-mono text-[11px] font-semibold px-1 py-0.5 bg-white rounded border">PUSHED</code>, but the downstream accounting software has no confirmation record. This occurs if the accounting server restarted, crashed, or was restored from a prior snapshot.
                                  </>
                                )}
                                {isMismatch && (
                                  <>
                                    <strong>Amount difference detected.</strong> InvoiceFlow recorded a total of{" "}
                                    <span className="font-mono font-bold">₹{details.invoiceflow_total}</span>, but the accounting software reflects{" "}
                                    <span className="font-mono font-bold">₹{details.accounting_total}</span> (Variance: ₹{details.diff}).
                                  </>
                                )}
                                {!isMissing && !isMismatch && (
                                  <>{details.reason || "Discrepancy detected between ledger records."}</>
                                )}
                              </div>
                            </div>

                            {/* Key-Value Details Grid */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                              <div
                                className="p-3 rounded-xl border flex flex-col justify-between"
                                style={{
                                  backgroundColor: "var(--bg-card)",
                                  borderColor: "var(--border)",
                                }}
                              >
                                <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                                  Accounting Confirmation ID
                                </span>
                                <div className="flex items-center justify-between mt-1">
                                  <span className="font-mono font-semibold" style={{ color: "var(--text)" }}>
                                    {accountingId}
                                  </span>
                                  {accountingId !== "None" && accountingId !== "Unassigned" && (
                                    <button
                                      onClick={() => copyToClipboard(accountingId, `acc-${f.id}`)}
                                      className="p-1 rounded hover:bg-white text-stone-500 cursor-pointer transition"
                                      title="Copy ID"
                                    >
                                      {copiedKey === `acc-${f.id}` ? (
                                        <Check className="h-3.5 w-3.5 text-emerald-600" />
                                      ) : (
                                        <Copy className="h-3.5 w-3.5" />
                                      )}
                                    </button>
                                  )}
                                </div>
                              </div>

                              <div
                                className="p-3 rounded-xl border flex flex-col justify-between"
                                style={{
                                  backgroundColor: "var(--bg-card)",
                                  borderColor: "var(--border)",
                                }}
                              >
                                <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                                  Idempotency Key
                                </span>
                                <div className="flex items-center justify-between mt-1">
                                  <span className="font-mono text-[11px] truncate max-w-[200px]" style={{ color: "var(--text)" }}>
                                    {details.idempotency_key || "None"}
                                  </span>
                                  {details.idempotency_key && (
                                    <button
                                      onClick={() => copyToClipboard(details.idempotency_key, `key-${f.id}`)}
                                      className="p-1 rounded hover:bg-white text-stone-500 cursor-pointer transition shrink-0 ml-2"
                                      title="Copy Key"
                                    >
                                      {copiedKey === `key-${f.id}` ? (
                                        <Check className="h-3.5 w-3.5 text-emerald-600" />
                                      ) : (
                                        <Copy className="h-3.5 w-3.5" />
                                      )}
                                    </button>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
