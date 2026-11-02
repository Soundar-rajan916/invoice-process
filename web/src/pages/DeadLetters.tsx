import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiRequest } from "@/lib/api";
import {
  AlertTriangle,
  RotateCcw,
  Trash2,
  CheckCircle2,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Search,
  Zap,
  FileQuestion,
  Server,
  Layers,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  ExternalLink,
  RefreshCw,
} from "lucide-react";
import { DeadLettersSkeleton } from "@/components/Skeleton";

interface DeadLetterItem {
  id: string;
  status: string;
  status_reason: string | null;
  supplier_gstin: string | null;
  normalized_invoice_number: string | null;
  watchdog_requeue_count: number;
  created_at: string;
  updated_at: string;
}

// Parses raw technical python error strings into human-friendly diagnostics
function categorizeError(reason: string | null): {
  category: "RATE_LIMIT" | "DOCUMENT_ERROR" | "CAPACITY" | "STREAM" | "UNKNOWN";
  badgeText: string;
  title: string;
  description: string;
  isRecoverable: boolean;
  colorVar: string;
  badgeBg: string;
  softBg: string;
} {
  if (!reason) {
    return {
      category: "UNKNOWN",
      badgeText: "Unspecified Error",
      title: "Unknown Pipeline Failure",
      description: "No specific error trace was logged during execution.",
      isRecoverable: true,
      colorVar: "var(--warning-strong)",
      badgeBg: "var(--warning)",
      softBg: "var(--warning-soft)",
    };
  }

  const r = reason.toLowerCase();

  if (r.includes("413") || r.includes("rate_limit_exceeded") || r.includes("rate limit") || r.includes("tokens per minute")) {
    return {
      category: "RATE_LIMIT",
      badgeText: "AI Rate Limit",
      title: "Groq Token Rate Limit Exceeded (HTTP 413)",
      description: "The prompt temporarily exceeded the per-minute token quota on the Groq API. Since the time window has passed, this invoice is ready to retry immediately.",
      isRecoverable: true,
      colorVar: "var(--accent-strong)",
      badgeBg: "var(--accent)",
      softBg: "var(--accent-soft)",
    };
  }

  if (r.includes("no renderable pages") || r.includes("corrupt") || r.includes("unsupported")) {
    return {
      category: "DOCUMENT_ERROR",
      badgeText: "Corrupted File",
      title: "No Renderable Pages Found",
      description: "The document contains 0 pages or has corrupt PDF headers that cannot be rendered into images for extraction.",
      isRecoverable: false,
      colorVar: "var(--danger-strong)",
      badgeBg: "var(--danger)",
      softBg: "var(--danger-soft)",
    };
  }

  if (r.includes("400") || r.includes("too many images") || r.includes("capacity")) {
    return {
      category: "CAPACITY",
      badgeText: "Model Limit",
      title: "Exceeded Model Page Limit",
      description: "The vision model supports up to 3 image pages per request. This multi-page document exceeded the batch size.",
      isRecoverable: false,
      colorVar: "var(--warning-strong)",
      badgeBg: "var(--warning)",
      softBg: "var(--warning-soft)",
    };
  }

  if (r.includes("failed to open stream") || r.includes("storage") || r.includes("stream")) {
    return {
      category: "STREAM",
      badgeText: "Storage Stream",
      title: "Storage Stream Read Failure",
      description: "The object storage connection was interrupted while reading the document bytes.",
      isRecoverable: true,
      colorVar: "var(--warning-strong)",
      badgeBg: "var(--warning)",
      softBg: "var(--warning-soft)",
    };
  }

  return {
    category: "UNKNOWN",
    badgeText: "Pipeline Fault",
    title: "General Extraction Failure",
    description: reason.slice(0, 160) + (reason.length > 160 ? "..." : ""),
    isRecoverable: true,
    colorVar: "var(--danger-strong)",
    badgeBg: "var(--danger)",
    softBg: "var(--danger-soft)",
  };
}

export function DeadLetters() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");
  const [expandedTraceId, setExpandedTraceId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [discardInvoiceId, setDiscardInvoiceId] = useState<string | null>(null);
  const [discardReason, setDiscardReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [batchRetrying, setBatchRetrying] = useState(false);

  // 1. Fetch Dead Letters
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["admin-dead-letters", page],
    queryFn: () =>
      apiRequest(`/api/v1/admin/dead-letters?page=${page}&page_size=${pageSize}`),
    refetchInterval: 12000,
  });

  // 2. Retry Single Invoice
  const retryMutation = useMutation({
    mutationFn: (invoiceId: string) =>
      apiRequest(`/api/v1/admin/dead-letters/${invoiceId}/retry`, {
        method: "POST",
      }),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-dead-letters"] });
    },
    onError: (err: any) => {
      setActionError(err.message || "Failed to retry invoice");
    },
  });

  // 3. Discard Invoice
  const discardMutation = useMutation({
    mutationFn: ({ invoiceId, reason }: { invoiceId: string; reason: string }) =>
      apiRequest(`/api/v1/admin/dead-letters/${invoiceId}/discard`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      }),
    onSuccess: () => {
      setDiscardInvoiceId(null);
      setDiscardReason("");
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-dead-letters"] });
    },
    onError: (err: any) => {
      setActionError(err.message || "Failed to discard invoice");
    },
  });

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const allItems: DeadLetterItem[] = data?.items || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / pageSize) || 1;

  // Breakdown counts for KPI strip
  const stats = useMemo(() => {
    let rateLimits = 0;
    let documentErrors = 0;
    let streamErrors = 0;
    let recoverable = 0;

    for (const item of allItems) {
      const diag = categorizeError(item.status_reason);
      if (diag.category === "RATE_LIMIT") rateLimits++;
      if (diag.category === "DOCUMENT_ERROR") documentErrors++;
      if (diag.category === "STREAM" || diag.category === "CAPACITY") streamErrors++;
      if (diag.isRecoverable) recoverable++;
    }

    return { rateLimits, documentErrors, streamErrors, recoverable };
  }, [allItems]);

  // Filtered Items
  const filteredItems = useMemo(() => {
    return allItems.filter((item) => {
      const diag = categorizeError(item.status_reason);

      // Category tab
      if (categoryFilter === "RECOVERABLE" && !diag.isRecoverable) return false;
      if (categoryFilter === "RATE_LIMIT" && diag.category !== "RATE_LIMIT") return false;
      if (categoryFilter === "DOCUMENT_ERROR" && diag.category !== "DOCUMENT_ERROR") return false;
      if (categoryFilter === "STREAM" && diag.category !== "STREAM" && diag.category !== "CAPACITY") return false;

      // Text search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesId = item.id.toLowerCase().includes(q);
        const matchesNum = (item.normalized_invoice_number || "").toLowerCase().includes(q);
        const matchesGstin = (item.supplier_gstin || "").toLowerCase().includes(q);
        const matchesReason = (item.status_reason || "").toLowerCase().includes(q);
        return matchesId || matchesNum || matchesGstin || matchesReason;
      }

      return true;
    });
  }, [allItems, categoryFilter, searchQuery]);

  // Batch Retry Recoverable
  const handleBatchRetryRecoverable = async () => {
    const recoverableItems = allItems.filter((item) => categorizeError(item.status_reason).isRecoverable);
    if (recoverableItems.length === 0) return;

    setBatchRetrying(true);
    setActionError(null);
    try {
      for (const item of recoverableItems) {
        await apiRequest(`/api/v1/admin/dead-letters/${item.id}/retry`, { method: "POST" });
      }
      queryClient.invalidateQueries({ queryKey: ["admin-dead-letters"] });
    } catch (err: any) {
      setActionError(err.message || "Failed to complete batch retry");
    } finally {
      setBatchRetrying(false);
    }
  };

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
                backgroundColor: total > 0 ? "var(--danger-soft)" : "var(--success-soft)",
                color: total > 0 ? "var(--danger-strong)" : "var(--success-strong)",
              }}
            >
              <AlertTriangle className="h-4 w-4 stroke-[2.5]" />
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
              Dead-Letter Queue (DLQ)
            </h1>
          </div>
          <p className="text-xs sm:text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            Incident triage workspace for invoices that failed automated extraction or exceeded retry limits. Recover transient errors or safely discard bad inputs with an audit trail.
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
              <span className={`w-2 h-2 rounded-full ${total > 0 ? "bg-amber-500 animate-pulse" : "bg-emerald-500"}`} />
              <span>{total > 0 ? `${total} Invoices Awaiting Triage` : "Queue Healthy · Zero Failures"}</span>
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
              <span>Watchdog Auto-Requeue Limit: 3 Attempts</span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 shrink-0">
          {stats.recoverable > 0 && (
            <button
              onClick={handleBatchRetryRecoverable}
              disabled={batchRetrying}
              className="inline-flex items-center justify-center space-x-2 px-4 py-2.5 rounded-btn text-xs font-semibold shadow-xs cursor-pointer select-none transition-all active:scale-[0.98]"
              style={{
                backgroundColor: "var(--ink)",
                color: "#FFFFFF",
              }}
            >
              <Zap className={`h-3.5 w-3.5 ${batchRetrying ? "animate-spin" : ""}`} />
              <span>{batchRetrying ? "Retrying..." : `Retry ${stats.recoverable} Recoverable`}</span>
            </button>
          )}

          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ["admin-dead-letters"] })}
            className="p-2.5 rounded-btn border text-xs font-medium transition cursor-pointer hover:bg-white"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
              color: "var(--text)",
            }}
            title="Refresh queue"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
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

      {/* KPI Triage Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total in DLQ */}
        <div
          className="p-5 rounded-card border shadow-xs flex flex-col justify-between"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
              Total Dead Letters
            </span>
            <AlertTriangle className="h-4 w-4" style={{ color: total > 0 ? "var(--danger-strong)" : "var(--success-strong)" }} />
          </div>
          <div className="mt-3">
            <div className="text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums" style={{ color: "var(--text)" }}>
              {total}
            </div>
            <div className="text-[11px] mt-1 font-medium" style={{ color: "var(--text-muted)" }}>
              Current queue backlog
            </div>
          </div>
        </div>

        {/* Rate Limits */}
        <div
          className="p-5 rounded-card border shadow-xs flex flex-col justify-between"
          style={{
            backgroundColor: stats.rateLimits > 0 ? "var(--accent-soft)" : "var(--bg-card)",
            borderColor: stats.rateLimits > 0 ? "rgba(155, 161, 249, 0.4)" : "var(--border)",
          }}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium" style={{ color: stats.rateLimits > 0 ? "var(--accent-strong)" : "var(--text-muted)" }}>
              AI Rate Limits
            </span>
            <Zap className="h-4 w-4" style={{ color: stats.rateLimits > 0 ? "var(--accent-strong)" : "var(--text-muted)" }} />
          </div>
          <div className="mt-3">
            <div className="text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums" style={{ color: stats.rateLimits > 0 ? "var(--accent-strong)" : "var(--text)" }}>
              {stats.rateLimits}
            </div>
            <div className="text-[11px] mt-1 font-medium" style={{ color: stats.rateLimits > 0 ? "var(--accent-strong)" : "var(--text-muted)" }}>
              100% transient & retryable
            </div>
          </div>
        </div>

        {/* Document Errors */}
        <div
          className="p-5 rounded-card border shadow-xs flex flex-col justify-between"
          style={{
            backgroundColor: stats.documentErrors > 0 ? "var(--danger-soft)" : "var(--bg-card)",
            borderColor: stats.documentErrors > 0 ? "rgba(254, 130, 135, 0.4)" : "var(--border)",
          }}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium" style={{ color: stats.documentErrors > 0 ? "var(--danger-strong)" : "var(--text-muted)" }}>
              Document Errors
            </span>
            <FileQuestion className="h-4 w-4" style={{ color: stats.documentErrors > 0 ? "var(--danger-strong)" : "var(--text-muted)" }} />
          </div>
          <div className="mt-3">
            <div className="text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums" style={{ color: stats.documentErrors > 0 ? "var(--danger-strong)" : "var(--text)" }}>
              {stats.documentErrors}
            </div>
            <div className="text-[11px] mt-1 font-medium" style={{ color: stats.documentErrors > 0 ? "var(--danger-strong)" : "var(--text-muted)" }}>
              Corrupt or unreadable files
            </div>
          </div>
        </div>

        {/* Stream / Infrastructure */}
        <div
          className="p-5 rounded-card border shadow-xs flex flex-col justify-between"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
              Storage / System
            </span>
            <Server className="h-4 w-4" style={{ color: "var(--text-muted)" }} />
          </div>
          <div className="mt-3">
            <div className="text-2xl sm:text-3xl font-extrabold tracking-tight tabular-nums" style={{ color: "var(--text)" }}>
              {stats.streamErrors}
            </div>
            <div className="text-[11px] mt-1 font-medium" style={{ color: "var(--text-muted)" }}>
              Stream or size constraints
            </div>
          </div>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div
        className="p-4 rounded-card border shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        {/* Category Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setCategoryFilter("ALL")}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer border ${
              categoryFilter === "ALL" ? "shadow-2xs" : ""
            }`}
            style={{
              backgroundColor: categoryFilter === "ALL" ? "var(--ink)" : "var(--bg-inset)",
              borderColor: categoryFilter === "ALL" ? "transparent" : "var(--border)",
              color: categoryFilter === "ALL" ? "#FFFFFF" : "var(--text)",
            }}
          >
            All Items ({allItems.length})
          </button>

          <button
            onClick={() => setCategoryFilter("RECOVERABLE")}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer border ${
              categoryFilter === "RECOVERABLE" ? "shadow-2xs" : ""
            }`}
            style={{
              backgroundColor: categoryFilter === "RECOVERABLE" ? "var(--accent)" : "var(--bg-inset)",
              borderColor: categoryFilter === "RECOVERABLE" ? "transparent" : "var(--border)",
              color: categoryFilter === "RECOVERABLE" ? "var(--ink)" : "var(--text)",
            }}
          >
            ⚡ Recoverable ({stats.recoverable})
          </button>

          <button
            onClick={() => setCategoryFilter("RATE_LIMIT")}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer border ${
              categoryFilter === "RATE_LIMIT" ? "shadow-2xs" : ""
            }`}
            style={{
              backgroundColor: categoryFilter === "RATE_LIMIT" ? "var(--accent-soft)" : "var(--bg-inset)",
              borderColor: categoryFilter === "RATE_LIMIT" ? "var(--accent-strong)" : "var(--border)",
              color: categoryFilter === "RATE_LIMIT" ? "var(--accent-strong)" : "var(--text)",
            }}
          >
            Rate Limits ({stats.rateLimits})
          </button>

          <button
            onClick={() => setCategoryFilter("DOCUMENT_ERROR")}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer border ${
              categoryFilter === "DOCUMENT_ERROR" ? "shadow-2xs" : ""
            }`}
            style={{
              backgroundColor: categoryFilter === "DOCUMENT_ERROR" ? "var(--danger-soft)" : "var(--bg-inset)",
              borderColor: categoryFilter === "DOCUMENT_ERROR" ? "var(--danger-strong)" : "var(--border)",
              color: categoryFilter === "DOCUMENT_ERROR" ? "var(--danger-strong)" : "var(--text)",
            }}
          >
            Corrupted Files ({stats.documentErrors})
          </button>
        </div>

        {/* Search Input */}
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-stone-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by ID, invoice #, GSTIN..."
            className="w-full pl-9 pr-3 py-2 rounded-xl border text-xs focus:outline-none"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
              color: "var(--text)",
            }}
          />
        </div>
      </div>

      {/* Main List */}
      <div
        className="rounded-card border shadow-xs overflow-hidden"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        {isLoading ? (
          <DeadLettersSkeleton />
        ) : allItems.length === 0 ? (
          /* Zero Failure State */
          <div
            className="p-12 sm:p-16 text-center space-y-3"
            style={{ backgroundColor: "var(--bg-inset)" }}
          >
            <div
              className="w-14 h-14 rounded-full mx-auto flex items-center justify-center shadow-xs"
              style={{
                backgroundColor: "var(--success-soft)",
                color: "var(--success-strong)",
              }}
            >
              <CheckCircle2 className="h-8 w-8 stroke-[2.2]" />
            </div>
            <h3 className="text-base font-bold" style={{ color: "var(--text)" }}>
              No Dead-Letter Invoices
            </h3>
            <p className="text-xs max-w-md mx-auto leading-relaxed" style={{ color: "var(--text-muted)" }}>
              All documents are flowing smoothly through intake, AI extraction, and accounting push queues without fatal exceptions.
            </p>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="py-16 text-center text-xs space-y-2" style={{ color: "var(--text-muted)" }}>
            <p>No dead-letter items match the active search or filter.</p>
            <button
              onClick={() => {
                setSearchQuery("");
                setCategoryFilter("ALL");
              }}
              className="font-semibold underline cursor-pointer"
              style={{ color: "var(--ink)" }}
            >
              Clear filters
            </button>
          </div>
        ) : (
          /* Cards Container (Scrollable) */
          <div className="p-4 sm:p-6 max-h-[620px] overflow-y-auto space-y-4">
            {filteredItems.map((inv) => {
              const diag = categorizeError(inv.status_reason);
              const isExpanded = expandedTraceId === inv.id;
              const formattedDate = new Date(inv.updated_at).toLocaleString(undefined, {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              });

              return (
                <div
                  key={inv.id}
                  className="rounded-2xl border overflow-hidden shadow-2xs transition-all hover:shadow-xs"
                  style={{
                    backgroundColor: "var(--bg-inset)",
                    borderColor: diag.category === "RATE_LIMIT"
                      ? "rgba(155, 161, 249, 0.4)"
                      : "rgba(254, 130, 135, 0.4)",
                  }}
                >
                  {/* Card Header Strip */}
                  <div
                    className="px-5 py-3.5 border-b flex flex-wrap items-center justify-between gap-3"
                    style={{
                      backgroundColor: diag.softBg,
                      borderColor: "var(--border)",
                    }}
                  >
                    <div className="flex items-center space-x-2.5">
                      <span
                        className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider"
                        style={{
                          backgroundColor: diag.badgeBg,
                          color: "var(--ink)",
                        }}
                      >
                        {diag.badgeText}
                      </span>

                      <span className="text-xs font-bold font-mono" style={{ color: "var(--text)" }}>
                        {inv.normalized_invoice_number || "Unparsed Document"}
                      </span>

                      {diag.isRecoverable && (
                        <span
                          className="px-2 py-0.5 rounded-md text-[10px] font-bold font-mono uppercase border"
                          style={{
                            backgroundColor: "var(--bg-inset)",
                            borderColor: "rgba(155, 161, 249, 0.5)",
                            color: "var(--accent-strong)",
                          }}
                        >
                          ⚡ Ready to Retry
                        </span>
                      )}
                    </div>

                    <div className="flex items-center space-x-3 text-xs">
                      <span className="text-[11px] font-medium" style={{ color: "var(--text-muted)" }}>
                        Failed {formattedDate}
                      </span>
                      <Link
                        to={`/invoices/${inv.id}`}
                        className="inline-flex items-center space-x-1 font-semibold text-xs hover:underline"
                        style={{ color: "var(--ink)" }}
                      >
                        <span>View</span>
                        <ExternalLink className="h-3 w-3" />
                      </Link>
                    </div>
                  </div>

                  {/* Card Body */}
                  <div className="p-5 space-y-4">
                    {/* Diagnostic Summary */}
                    <div
                      className="p-3.5 rounded-xl border text-xs leading-relaxed flex items-start space-x-3"
                      style={{
                        backgroundColor: "var(--bg-card)",
                        borderColor: "var(--border)",
                      }}
                    >
                      <AlertCircle
                        className="h-4 w-4 shrink-0 mt-0.5"
                        style={{ color: diag.colorVar }}
                      />
                      <div className="space-y-1 w-full">
                        <div className="font-bold" style={{ color: "var(--text)" }}>
                          {diag.title}
                        </div>
                        <p style={{ color: "var(--text-secondary)" }}>
                          {diag.description}
                        </p>
                      </div>
                    </div>

                    {/* Metadata & Identifier Row */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                      {/* Unique Invoice ID */}
                      <div
                        className="p-3 rounded-xl border flex flex-col justify-between"
                        style={{
                          backgroundColor: "var(--bg-card)",
                          borderColor: "var(--border)",
                        }}
                      >
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                          Internal Invoice ID
                        </span>
                        <div className="flex items-center justify-between mt-1">
                          <span className="font-mono text-[11px] truncate max-w-[140px]" style={{ color: "var(--text)" }}>
                            {inv.id}
                          </span>
                          <button
                            onClick={() => copyToClipboard(inv.id, `id-${inv.id}`)}
                            className="p-1 rounded hover:bg-white text-stone-500 cursor-pointer transition shrink-0"
                            title="Copy ID"
                          >
                            {copiedId === `id-${inv.id}` ? (
                              <Check className="h-3.5 w-3.5 text-emerald-600" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </div>
                      </div>

                      {/* Supplier GSTIN */}
                      <div
                        className="p-3 rounded-xl border flex flex-col justify-between"
                        style={{
                          backgroundColor: "var(--bg-card)",
                          borderColor: "var(--border)",
                        }}
                      >
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                          Supplier GSTIN
                        </span>
                        <div className="mt-1 font-mono font-semibold" style={{ color: "var(--text)" }}>
                          {inv.supplier_gstin || "Not detected"}
                        </div>
                      </div>

                      {/* Watchdog Requeue Count */}
                      <div
                        className="p-3 rounded-xl border flex flex-col justify-between"
                        style={{
                          backgroundColor: "var(--bg-card)",
                          borderColor: "var(--border)",
                        }}
                      >
                        <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                          Watchdog Requeue Retries
                        </span>
                        <div className="mt-1 font-mono font-semibold" style={{ color: "var(--text)" }}>
                          {inv.watchdog_requeue_count} / 3 attempts
                        </div>
                      </div>
                    </div>

                    {/* Collapsible Raw Technical Trace */}
                    {inv.status_reason && (
                      <div>
                        <button
                          onClick={() => setExpandedTraceId(isExpanded ? null : inv.id)}
                          className="inline-flex items-center space-x-1.5 text-[11px] font-semibold text-stone-500 hover:text-stone-800 transition cursor-pointer"
                        >
                          {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                          <span>{isExpanded ? "Hide Raw Diagnostic Trace" : "View Raw Diagnostic Trace"}</span>
                        </button>

                        {isExpanded && (
                          <pre
                            className="mt-2 p-3 rounded-xl text-[11px] font-mono overflow-x-auto border leading-relaxed"
                            style={{
                              backgroundColor: "var(--bg-app)",
                              borderColor: "var(--border)",
                              color: "var(--text)",
                            }}
                          >
                            {inv.status_reason}
                          </pre>
                        )}
                      </div>
                    )}

                    {/* Action Bar */}
                    <div
                      className="pt-3 border-t flex flex-wrap items-center justify-between gap-3"
                      style={{ borderColor: "var(--border)" }}
                    >
                      <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                        Status: <strong className="font-mono text-rose-600">{inv.status}</strong>
                      </span>

                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() =>
                            discardMutation.mutate({
                              invoiceId: inv.id,
                              reason: "Discarded by reviewer from dead-letter queue",
                            })
                          }
                          disabled={discardMutation.isPending}
                          className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-btn text-xs font-semibold border transition-all cursor-pointer hover:bg-rose-50"
                          style={{
                            backgroundColor: "var(--bg-inset)",
                            borderColor: "rgba(254, 130, 135, 0.4)",
                            color: "var(--danger-strong)",
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          <span>Discard</span>
                        </button>

                        <button
                          onClick={() => retryMutation.mutate(inv.id)}
                          disabled={retryMutation.isPending}
                          className="inline-flex items-center space-x-1.5 px-4 py-1.5 rounded-btn text-xs font-semibold border shadow-2xs transition-all cursor-pointer active:scale-95"
                          style={{
                            backgroundColor: "var(--ink)",
                            borderColor: "transparent",
                            color: "#FFFFFF",
                          }}
                        >
                          <RotateCcw className={`h-3.5 w-3.5 ${retryMutation.isPending ? "animate-spin" : ""}`} />
                          <span>Retry Pipeline</span>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div
            className="p-4 border-t flex items-center justify-between text-xs"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
            }}
          >
            <span style={{ color: "var(--text-muted)" }}>
              Page {page} of {totalPages} ({total} total)
            </span>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg border disabled:opacity-40 cursor-pointer hover:bg-white"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                  color: "var(--text)",
                }}
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-lg border disabled:opacity-40 cursor-pointer hover:bg-white"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                  color: "var(--text)",
                }}
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Discard Confirmation Dialog */}
      {discardInvoiceId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
          <div
            className="w-full max-w-md p-6 rounded-[20px] border shadow-xl space-y-4"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div className="flex items-center space-x-2.5">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
                style={{
                  backgroundColor: "var(--danger-soft)",
                  color: "var(--danger-strong)",
                }}
              >
                <AlertTriangle className="h-4 w-4" />
              </div>
              <h3 className="font-bold text-base" style={{ color: "var(--text)" }}>
                Discard Dead-Letter Invoice
              </h3>
            </div>

            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Permanently mark this invoice as rejected. Provide an audit justification for compliance.
            </p>

            <textarea
              value={discardReason}
              onChange={(e) => setDiscardReason(e.target.value)}
              placeholder="Reason for discarding (e.g. invalid document, corrupted unrecoverable file)..."
              rows={3}
              className="w-full p-3 rounded-xl border text-xs resize-none focus:outline-none"
              style={{
                backgroundColor: "var(--bg-inset)",
                borderColor: "var(--border)",
                color: "var(--text)",
              }}
            />

            <div className="flex items-center justify-end space-x-2 pt-2">
              <button
                onClick={() => setDiscardInvoiceId(null)}
                className="px-4 py-2 rounded-btn text-xs font-semibold cursor-pointer border hover:bg-white"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                  color: "var(--text)",
                }}
              >
                Cancel
              </button>

              <button
                onClick={() =>
                  discardMutation.mutate({
                    invoiceId: discardInvoiceId,
                    reason: discardReason.trim() || "Manual discard by administrator",
                  })
                }
                disabled={discardMutation.isPending}
                className="px-4 py-2 rounded-btn text-xs font-semibold cursor-pointer border"
                style={{
                  backgroundColor: "var(--danger-strong)",
                  borderColor: "transparent",
                  color: "#FFFFFF",
                }}
              >
                {discardMutation.isPending ? "Discarding..." : "Confirm Discard"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
