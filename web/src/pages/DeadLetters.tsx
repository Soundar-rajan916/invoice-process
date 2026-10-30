import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import {
  AlertTriangle,
  RotateCcw,
  Trash2,
  CheckCircle2,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { StatusPill } from "@/components/StatusPill";

export function DeadLetters() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const [discardInvoiceId, setDiscardInvoiceId] = useState<string | null>(null);
  const [discardReason, setDiscardReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-dead-letters", page],
    queryFn: () =>
      apiRequest(`/api/v1/admin/dead-letters?page=${page}&page_size=${pageSize}`),
    refetchInterval: 10000,
  });

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

  const items = data?.items || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / pageSize) || 1;

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
            Dead-Letter Invoices
          </h1>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Invoices stuck in unrecoverable failure states or exceeding watchdog requeue limits.
          </p>
        </div>
        <div
          className="text-xs font-semibold px-3 py-1.5 rounded-full border self-start sm:self-auto font-mono tabular-nums"
          style={{
            backgroundColor: "var(--danger-soft)",
            borderColor: "rgba(254, 130, 135, 0.3)",
            color: "var(--danger-strong)",
          }}
        >
          {total} Dead Letter{total === 1 ? "" : "s"}
        </div>
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

      {/* Main Table / List */}
      <div
        className="rounded-[20px] border shadow-xs overflow-hidden"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        {isLoading ? (
          <div className="py-12 text-center text-xs" style={{ color: "var(--text-muted)" }}>
            Loading dead-letter items...
          </div>
        ) : items.length === 0 ? (
          <div className="py-16 text-center space-y-2">
            <CheckCircle2
              className="h-10 w-10 mx-auto stroke-[1.8]"
              style={{ color: "var(--success-strong)" }}
            />
            <h3 className="font-semibold text-sm" style={{ color: "var(--text)" }}>
              No Dead-Letter Invoices
            </h3>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              All invoices are healthy or progressing through normal processing queues.
            </p>
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: "var(--border)" }}>
            {items.map((inv: any) => (
              <div
                key={inv.id}
                className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-colors"
                style={{
                  backgroundColor: "var(--danger-soft)",
                }}
              >
                <div className="space-y-1.5 min-w-0">
                  <div className="flex items-center space-x-3">
                    <StatusPill status={inv.status} />
                    <span className="text-xs font-mono font-semibold" style={{ color: "var(--text)" }}>
                      {inv.normalized_invoice_number || "Unparsed Invoice"}
                    </span>
                    <span className="text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
                      ID: {inv.id}
                    </span>
                  </div>

                  <div className="text-xs font-medium" style={{ color: "var(--danger-strong)" }}>
                    Reason: {inv.status_reason || "Unknown failure reason"}
                  </div>

                  <div className="flex items-center space-x-4 text-[11px]" style={{ color: "var(--text-muted)" }}>
                    {inv.supplier_gstin && <span>GSTIN: {inv.supplier_gstin}</span>}
                    <span>Watchdog retries: {inv.watchdog_requeue_count}</span>
                    <span>Last updated: {new Date(inv.updated_at).toLocaleString()}</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center space-x-2 shrink-0">
                  <button
                    onClick={() => retryMutation.mutate(inv.id)}
                    disabled={retryMutation.isPending}
                    className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-btn text-xs font-semibold border shadow-2xs transition-all cursor-pointer"
                    style={{
                      backgroundColor: "var(--bg-inset)",
                      borderColor: "var(--border)",
                      color: "var(--text)",
                    }}
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    <span>Retry Pipeline</span>
                  </button>

                  <button
                    onClick={() => {
                      setDiscardInvoiceId(inv.id);
                      setDiscardReason("");
                    }}
                    className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-btn text-xs font-semibold border transition-all cursor-pointer"
                    style={{
                      backgroundColor: "var(--danger-soft)",
                      borderColor: "rgba(254, 130, 135, 0.3)",
                      color: "var(--danger-strong)",
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    <span>Discard</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div
            className="p-4 border-t flex items-center justify-between text-xs"
            style={{ borderColor: "var(--border)" }}
          >
            <span style={{ color: "var(--text-muted)" }}>
              Page {page} of {totalPages}
            </span>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg border disabled:opacity-40 cursor-pointer"
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
                className="p-1.5 rounded-lg border disabled:opacity-40 cursor-pointer"
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
                className="px-4 py-2 rounded-btn text-xs font-semibold cursor-pointer border"
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
