import { Pagination, PaginationItemType } from '@heroui/react';
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { apiRequest } from "@/lib/api";
import {
  Search,
  Play,
  AlertCircle,
  AlertTriangle,
  ArrowUpDown,
  FileText,
  ChevronLeft,
  ChevronRight,
  Check,
} from "lucide-react";

export function ReviewQueue() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState("NEEDS_REVIEW");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOrder, setSortOrder] = useState<"oldest" | "newest">("oldest");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: [
      "invoices-queue",
      statusFilter,
      flaggedOnly,
      searchQuery,
      sortOrder,
      page,
    ],
    queryFn: () => {
      const params = new URLSearchParams();
      if (statusFilter && statusFilter !== "ALL") {
        params.set("status", statusFilter);
      }
      if (flaggedOnly) {
        params.set("flagged", "true");
      }
      if (searchQuery.trim()) {
        params.set("q", searchQuery.trim());
      }
      params.set("sort", sortOrder);
      params.set("page", page.toString());
      params.set("page_size", pageSize.toString());

      return apiRequest(`/api/v1/invoices?${params.toString()}`);
    },
    refetchInterval: 10000,
  });

  const items = data?.items || [];
  const counts = data?.counts || {};
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / pageSize) || 1;

  // Find oldest unreviewed invoice for "Start reviewing" button
  const startReviewing = () => {
    if (items.length > 0) {
      navigate(`/invoices/${items[0].id}`);
    }
  };

  const formatAge = (isoString: string) => {
    const ms = Date.now() - new Date(isoString).getTime();
    const minutes = Math.floor(ms / (1000 * 60));
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ${minutes % 60}m ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  return (
    <div className="w-full space-y-6">
      {/* Top Banner with Action & Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-findeck-card p-6 rounded-card border border-findeck-border shadow-xs">
        <div>
          <h1 className="text-2xl font-bold text-findeck-text tracking-tight">Review Queue</h1>
          <p className="text-xs text-findeck-muted mt-1">
            Accounts team review and approval verification workspace (R2 guarantee).
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={startReviewing}
            disabled={items.length === 0}
            className="inline-flex items-center space-x-2 px-4 py-2.5 bg-ink hover:bg-ink-hover text-white font-medium text-xs rounded-btn shadow-xs disabled:opacity-50 transition-colors cursor-pointer"
          >
            <Play className="h-3.5 w-3.5 fill-white" />
            <span>Start Reviewing</span>
          </button>
        </div>
      </div>

      {/* Filter and Status Summary Pills */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-1">
        {["ALL", "NEEDS_REVIEW", "PUSHED", "REJECTED", "RESEND_REQUESTED"].map((st) => (
          <button
            key={st}
            onClick={() => {
              setStatusFilter(st);
              setPage(1);
            }}
            className={`px-3 py-1.5 rounded-pill text-xs font-semibold whitespace-nowrap transition-all border ${
              statusFilter === st
                ? "bg-white text-findeck-text border-findeck-border shadow-2xs"
                : "bg-transparent text-findeck-muted border-transparent hover:bg-white/60 hover:text-findeck-text"
            }`}
          >
            <span>{st.replace(/_/g, " ")}</span>
            {counts[st] !== undefined && (
              <span
                className={`ml-1.5 px-1.5 py-0.2 rounded-pill text-[10px] tabular-nums ${
                  statusFilter === st ? "bg-accent-soft text-ink font-bold" : "bg-slate-200/60 text-findeck-muted"
                }`}
              >
                {counts[st]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Filter Bar (Search, Flagged toggle, Sort) */}
      <div className="bg-findeck-card p-4 rounded-card border border-findeck-border shadow-xs flex flex-col md:flex-row gap-4 items-center justify-between">
        <div className="relative w-full md:w-80">
          <Search className="h-4 w-4 absolute left-3 top-3 text-findeck-muted" />
          <input
            type="text"
            placeholder="Search invoice number, GSTIN, file..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full pl-9 pr-8 py-2 text-xs bg-white border border-findeck-border rounded-btn focus:outline-none focus:ring-1 focus:ring-accent-strong focus:border-accent-strong transition-all text-findeck-text placeholder:text-findeck-muted"
          />
          <span className="absolute right-2.5 top-2.5 text-[10px] text-findeck-muted font-mono">/</span>
        </div>

        <div className="flex items-center space-x-4 w-full md:w-auto justify-end">
          <label className="flex items-center space-x-2 text-xs font-medium text-findeck-text cursor-pointer select-none">
            <input
              type="checkbox"
              checked={flaggedOnly}
              onChange={(e) => {
                setFlaggedOnly(e.target.checked);
                setPage(1);
              }}
              className="h-4 w-4 rounded-[4px] border-findeck-border text-ink focus:ring-accent-strong"
            />
            <span>Flagged issues only</span>
          </label>

          <button
            onClick={() => setSortOrder(sortOrder === "oldest" ? "newest" : "oldest")}
            className="inline-flex items-center space-x-1.5 px-3 py-2 border border-findeck-border rounded-btn text-xs font-medium text-findeck-text hover:bg-white transition-colors cursor-pointer bg-white"
          >
            <ArrowUpDown className="h-3.5 w-3.5 text-findeck-muted" />
            <span>Sort: {sortOrder === "oldest" ? "Oldest First" : "Newest First"}</span>
          </button>
        </div>
      </div>

      {/* Main Queue Table Card */}
      <div className="bg-findeck-card rounded-card border border-findeck-border shadow-xs overflow-hidden">
        {isLoading ? (
          <div className="py-20 text-center text-xs text-findeck-muted">Loading invoice queue...</div>
        ) : items.length === 0 ? (
          <div className="py-20 text-center">
            <FileText className="h-10 w-10 text-findeck-muted/40 mx-auto mb-2" />
            <p className="text-xs font-medium text-findeck-text">No invoices match your filter</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-findeck-text">
              <thead className="bg-white text-[11px] font-semibold text-text-secondary uppercase tracking-wider border-b border-findeck-border">
                <tr>
                  <th className="px-6 py-3.5">Invoice #</th>
                  <th className="px-6 py-3.5">Supplier GSTIN</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Received / Age</th>
                  <th className="px-6 py-3.5">Flags & Issues</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-findeck-border">
                {items.map((inv: any) => (
                  <tr
                    key={inv.id}
                    className="hover:bg-white transition-colors group cursor-pointer"
                    onClick={() => navigate(`/invoices/${inv.id}`)}
                  >
                    <td className="px-6 py-4">
                      <div className="font-semibold text-findeck-text group-hover:text-accent-strong transition-colors">
                        {inv.normalized_invoice_number || "Unextracted"}
                      </div>
                      <div className="text-[11px] text-findeck-muted">
                        FY: {inv.financial_year || "Pending"}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="font-mono text-xs text-findeck-text font-medium">
                        {inv.supplier_gstin || "—"}
                      </div>
                      <div className="text-[11px] text-findeck-muted">
                        {inv.extraction_path ? `${inv.extraction_path} path` : ""}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-pill text-xs font-medium border ${
                          inv.status === "NEEDS_REVIEW"
                            ? "bg-warning-soft text-warning-strong border-warning/30"
                            : inv.status === "APPROVED"
                            ? "bg-success-soft text-success-strong border-success/30"
                            : inv.status === "PUSHED"
                            ? "bg-success-soft text-success-strong border-success/30"
                            : inv.status === "RESEND_REQUESTED"
                            ? "bg-warning-soft text-warning-strong border-warning/30"
                            : inv.status === "REJECTED" || inv.status === "FAILED" || inv.status === "PUSH_FAILED"
                            ? "bg-danger-soft text-danger-strong border-danger/30"
                            : inv.status.includes("DUPLICATE")
                            ? "bg-accent-soft text-ink border-accent/30"
                            : "bg-findeck-app text-findeck-text border-findeck-border"
                        }`}
                      >
                        {inv.status === "PUSHED" ? (
                          <Check className="h-3 w-3 text-success-strong" />
                        ) : (
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              inv.status === "NEEDS_REVIEW"
                                ? "bg-warning"
                                : inv.status === "APPROVED" || inv.status === "PUSHED"
                                ? "bg-success"
                                : inv.status === "RESEND_REQUESTED"
                                ? "bg-warning"
                                : "bg-danger"
                            }`}
                          />
                        )}
                        <span>{inv.status.replace(/_/g, " ")}</span>
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs">
                      <div className="text-findeck-text font-medium tabular-nums">{formatAge(inv.received_at)}</div>
                      <div className="text-findeck-muted tabular-nums">
                        {new Date(inv.received_at).toLocaleDateString()}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center space-x-2">
                        {inv.status === "RESEND_REQUESTED" ? (
                          <span className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-btn text-xs font-medium bg-warning-soft text-warning-strong border border-warning/30">
                            <span className="font-semibold">Reason:</span>
                            <span className="truncate max-w-[240px]" title={inv.status_reason || "Pending vendor resubmission"}>
                              {inv.status_reason || "Pending vendor resubmission"}
                            </span>
                          </span>
                        ) : (
                          <>
                            {inv.error_count > 0 && (
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-pill text-xs font-semibold bg-danger-soft text-danger-strong border border-danger/30">
                                <AlertCircle className="h-3 w-3" />
                                <span className="tabular-nums">{inv.error_count} error{inv.error_count > 1 ? "s" : ""}</span>
                              </span>
                            )}
                            {inv.warning_count > 0 && (
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-pill text-xs font-semibold bg-warning-soft text-warning-strong border border-warning/30">
                                <AlertTriangle className="h-3 w-3" />
                                <span className="tabular-nums">{inv.warning_count} warning{inv.warning_count > 1 ? "s" : ""}</span>
                              </span>
                            )}
                            {inv.error_count === 0 && inv.warning_count === 0 && (
                              <span className="text-xs text-success-strong font-medium">Valid</span>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        to={`/invoices/${inv.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center space-x-1 text-xs font-semibold text-accent-strong hover:underline"
                      >
                        <span>Review</span>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Bar */}
        {totalPages > 1 && (
          <div className="px-6 py-3 border-t border-findeck-border flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-findeck-muted bg-white">
            <div className="tabular-nums">
              Showing page <strong className="text-findeck-text font-semibold">{page}</strong> of{" "}
              <strong className="text-findeck-text font-semibold">{totalPages}</strong> ({total} total invoices)
            </div>
            <Pagination
              total={totalPages}
              page={page}
              onChange={(newPage) => setPage(newPage)}
              showControls
              disableCursorAnimation
              classNames={{
                base: "overflow-visible",
                wrapper: "gap-1.5",
              }}
              renderItem={({
                ref,
                key,
                value,
                isActive,
                onNext,
                onPrevious,
                setPage,
              }) => {
                if (value === PaginationItemType.NEXT) {
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={onNext}
                      disabled={page >= totalPages}
                      className="w-8 h-8 flex items-center justify-center border border-findeck-border rounded-btn bg-white hover:bg-findeck-app text-findeck-text disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                      title="Next page"
                    >
                      <ChevronRight className="h-4 w-4" />
                    </button>
                  );
                }

                if (value === PaginationItemType.PREV) {
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={onPrevious}
                      disabled={page <= 1}
                      className="w-8 h-8 flex items-center justify-center border border-findeck-border rounded-btn bg-white hover:bg-findeck-app text-findeck-text disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                      title="Previous page"
                    >
                      <ChevronLeft className="h-4 w-4" />
                    </button>
                  );
                }

                if (value === PaginationItemType.DOTS) {
                  return (
                    <span
                      key={key}
                      className="w-8 h-8 flex items-center justify-center text-findeck-muted text-xs font-semibold"
                    >
                      ...
                    </span>
                  );
                }

                return (
                  <button
                    ref={ref}
                    key={key}
                    type="button"
                    onClick={() => setPage(value)}
                    className={`w-8 h-8 flex items-center justify-center text-xs font-semibold rounded-btn border transition-colors cursor-pointer ${
                      isActive
                        ? "bg-ink text-white border-ink shadow-xs"
                        : "border-findeck-border bg-white text-findeck-text hover:bg-findeck-app"
                    }`}
                  >
                    {value}
                  </button>
                );
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
