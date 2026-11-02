import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { apiRequest } from "@/lib/api";
import {
  Search,
  Play,
  ArrowUpDown,
  FileText,
  ChevronLeft,
  ChevronRight,
  Mail,
  MessageSquare,
  Upload,
} from "lucide-react";
import { maskSender } from "@/lib/mask";
import { StatusPill } from "@/components/StatusPill";
import { IssueChip } from "@/components/IssueChip";
import { QueueTableSkeleton } from "@/components/Skeleton";

export function ReviewQueue() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState("NEEDS_REVIEW");
  const [channelFilter, setChannelFilter] = useState("ALL");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOrder, setSortOrder] = useState<"oldest" | "newest">("oldest");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: [
      "invoices-queue",
      statusFilter,
      channelFilter,
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
      if (channelFilter && channelFilter !== "ALL") {
        params.set("channel", channelFilter.toLowerCase());
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
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Reset page if totalPages shrinks below current page
  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [totalPages, page]);

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
  };

  const getPageItems = (current: number, maxPages: number): (number | "...")[] => {
    if (maxPages <= 7) {
      return Array.from({ length: maxPages }, (_, i) => i + 1);
    }
    if (current <= 4) {
      return [1, 2, 3, 4, 5, "...", maxPages];
    }
    if (current >= maxPages - 3) {
      return [1, "...", maxPages - 4, maxPages - 3, maxPages - 2, maxPages - 1, maxPages];
    }
    return [1, "...", current - 1, current, current + 1, "...", maxPages];
  };

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

  const getTabCountStyle = (st: string) => {
    if (st === "RESEND_REQUESTED" || st === "WAITING_PROVIDER") {
      return { bg: "var(--accent)", text: "var(--ink)" };
    }
    if (st === "NEEDS_REVIEW") {
      return { bg: "var(--warning)", text: "var(--ink)" };
    }
    if (st === "PUSHED" || st === "APPROVED") {
      return { bg: "var(--success)", text: "var(--ink)" };
    }
    if (st === "REJECTED") {
      return { bg: "var(--danger)", text: "var(--ink)" };
    }
    return { bg: "var(--bg-app)", text: "var(--ink)" };
  };

  return (
    <div className="w-full space-y-6">
      {/* Top Banner with Action & Title on --bg-card */}
      <div
        className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-card border shadow-xs"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
            Review Queue
          </h1>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Accounts team review and approval verification workspace.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={startReviewing}
            disabled={items.length === 0}
            className="inline-flex items-center space-x-2 px-4 py-2.5 font-semibold text-xs rounded-btn shadow-xs transition-colors cursor-pointer select-none"
            style={{
              backgroundColor: items.length === 0 ? "var(--bg-disabled)" : "var(--ink)",
              color: items.length === 0 ? "var(--text-muted)" : "#FFFFFF",
              border: items.length === 0 ? "1px solid var(--border)" : "none",
            }}
          >
            <Play className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
            <span>Start Reviewing</span>
          </button>
        </div>
      </div>

      {/* Tabs (ALL, NEEDS REVIEW, WAITING PROVIDER, PUSHED, REJECTED, RESEND REQUESTED) */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-1">
        {["ALL", "NEEDS_REVIEW", "WAITING_PROVIDER", "PUSHED", "REJECTED", "RESEND_REQUESTED"].map((st) => {
          const isSelected = statusFilter === st;
          const countStyle = getTabCountStyle(st);
          return (
            <button
              key={st}
              onClick={() => {
                setStatusFilter(st);
                setPage(1);
              }}
              className="px-3.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all border cursor-pointer flex items-center"
              style={{
                backgroundColor: isSelected ? "var(--ink)" : "transparent",
                color: isSelected ? "#FFFFFF" : "var(--text-secondary)",
                borderColor: isSelected ? "var(--ink)" : "transparent",
              }}
            >
              <span>{st.replace(/_/g, " ")}</span>
              {counts[st] !== undefined && (
                <span
                  className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold tabular-nums"
                  style={{
                    backgroundColor: countStyle.bg,
                    color: countStyle.text,
                  }}
                >
                  {counts[st]}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {/* Channel Filters */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-1 text-xs">
        <span className="text-[11px] font-semibold uppercase tracking-wider mr-1" style={{ color: "var(--text-muted)" }}>Channel:</span>
        {["ALL", "UPLOAD", "EMAIL", "WHATSAPP"].map((ch) => {
          const isSelected = channelFilter === ch;
          return (
            <button
              key={ch}
              onClick={() => {
                setChannelFilter(ch);
                setPage(1);
              }}
              className="px-3 py-1 rounded-full text-xs font-semibold whitespace-nowrap transition-all border cursor-pointer flex items-center space-x-1"
              style={{
                backgroundColor: isSelected ? "var(--ink)" : "var(--bg-inset)",
                color: isSelected ? "#FFFFFF" : "var(--text-secondary)",
                borderColor: isSelected ? "var(--ink)" : "var(--border)",
              }}
            >
              {ch === "EMAIL" && <Mail className="h-3 w-3 mr-1" aria-hidden="true" />}
              {ch === "WHATSAPP" && <MessageSquare className="h-3 w-3 mr-1" aria-hidden="true" />}
              {ch === "UPLOAD" && <Upload className="h-3 w-3 mr-1" aria-hidden="true" />}
              <span>{ch}</span>
            </button>
          );
        })}
      </div>

      {/* Filter Bar Card (Search, Flagged toggle, Sort) on --bg-card */}
      <div
        className="p-4 rounded-card border shadow-xs flex flex-col md:flex-row gap-4 items-center justify-between"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        <div className="relative w-full md:w-80">
          <Search className="h-4 w-4 absolute left-3 top-2.5 text-muted pointer-events-none" aria-hidden="true" />
          <input
            type="text"
            placeholder="Search invoice number, GSTIN, file..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full pl-9 pr-8 py-2 text-xs rounded-btn outline-none transition-all placeholder:text-muted"
            style={{
              backgroundColor: "var(--bg-inset)",
              border: "1px solid var(--border)",
              color: "var(--text)",
            }}
          />
          <span className="absolute right-2.5 top-2.5 text-[10px] text-muted font-mono">/</span>
        </div>

        <div className="flex items-center space-x-4 w-full md:w-auto justify-end">
          <label className="flex items-center space-x-2 text-xs font-medium cursor-pointer select-none" style={{ color: "var(--text)" }}>
            <input
              type="checkbox"
              checked={flaggedOnly}
              onChange={(e) => {
                setFlaggedOnly(e.target.checked);
                setPage(1);
              }}
              className="h-4 w-4 rounded-[4px] cursor-pointer"
              style={{
                accentColor: "var(--accent)",
              }}
            />
            <span>Flagged issues only</span>
          </label>

          <button
            onClick={() => setSortOrder(sortOrder === "oldest" ? "newest" : "oldest")}
            className="inline-flex items-center space-x-1.5 px-3 py-2 rounded-btn text-xs font-medium transition-colors cursor-pointer"
            style={{
              backgroundColor: "var(--bg-inset)",
              border: "1px solid var(--border)",
              color: "var(--text)",
            }}
          >
            <ArrowUpDown className="h-3.5 w-3.5" style={{ color: "var(--text-muted)" }} aria-hidden="true" />
            <span>Sort: {sortOrder === "oldest" ? "Oldest First" : "Newest First"}</span>
          </button>
        </div>
      </div>

      {/* Main Queue Table Card on --bg-card */}
      <div
        className="rounded-card border shadow-xs overflow-hidden"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        {isLoading ? (
          <QueueTableSkeleton rows={8} />
        ) : items.length === 0 ? (
          <div className="py-20 text-center">
            <FileText className="h-10 w-10 mx-auto mb-2 opacity-40" style={{ color: "var(--text-muted)" }} aria-hidden="true" />
            <p className="text-xs font-medium" style={{ color: "var(--text)" }}>
              No invoices match your filter
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs" style={{ color: "var(--text)" }}>
              <thead
                className="text-[11px] font-semibold uppercase tracking-wider border-b"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  color: "var(--text-secondary)",
                  borderColor: "var(--border)",
                }}
              >
                <tr>
                  <th className="px-6 py-3.5">Invoice #</th>
                  <th className="px-6 py-3.5">Supplier GSTIN</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Source & Sender</th>
                  <th className="px-6 py-3.5">Received / Age</th>
                  <th className="px-6 py-3.5">Flags & Issues</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((inv: any) => (
                  <tr
                    key={inv.id}
                    className="transition-colors group cursor-pointer"
                    style={{
                      borderBottom: "1px solid var(--border)",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = "var(--accent-soft)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = "transparent";
                    }}
                    onClick={() => navigate(`/invoices/${inv.id}`)}
                  >
                    <td className="px-6 py-4">
                      <div className="font-semibold" style={{ color: "var(--text)" }}>
                        {inv.normalized_invoice_number || "Unextracted"}
                      </div>
                      <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                        FY: {inv.financial_year || "Pending"}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="font-mono text-xs font-medium" style={{ color: "var(--text)" }}>
                        {inv.supplier_gstin || "—"}
                      </div>
                      <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                        {inv.extraction_path ? `${inv.extraction_path} path` : ""}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <StatusPill status={inv.status} />
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center space-x-1.5">
                        {inv.channel === "email" ? (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-accent-soft text-accent-strong">
                            <Mail className="h-3 w-3" aria-hidden="true" />
                            <span>Email</span>
                          </span>
                        ) : inv.channel === "whatsapp" ? (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-success-soft text-success-strong">
                            <MessageSquare className="h-3 w-3" aria-hidden="true" />
                            <span>WhatsApp</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-bg-inset text-text-muted border border-border">
                            <Upload className="h-3 w-3" aria-hidden="true" />
                            <span>Upload</span>
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] truncate max-w-[160px] mt-1" style={{ color: "var(--text-muted)" }} title={inv.sender || inv.original_filename || ""}>
                        {inv.sender ? maskSender(inv.sender, inv.channel) : inv.original_filename || "—"}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-xs">
                      <div className="font-medium tabular-nums" style={{ color: "var(--text)" }}>
                        {formatAge(inv.received_at)}
                      </div>
                      <div className="tabular-nums text-[11px]" style={{ color: "var(--text-muted)" }}>
                        {new Date(inv.received_at).toLocaleDateString()}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center space-x-2">
                        {inv.status === "RESEND_REQUESTED" ? (
                          <span
                            className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-btn text-xs font-medium"
                            style={{
                              backgroundColor: "var(--accent-soft)",
                              color: "var(--accent-strong)",
                              border: "1px solid var(--accent)",
                            }}
                          >
                            <span className="font-semibold">Reason:</span>
                            <span className="truncate max-w-[240px]" title={inv.status_reason || "Pending vendor resubmission"}>
                              {inv.status_reason || "Pending vendor resubmission"}
                            </span>
                          </span>
                        ) : (
                          <>
                            {inv.error_count > 0 && <IssueChip type="error" count={inv.error_count} />}
                            {inv.warning_count > 0 && <IssueChip type="warning" count={inv.warning_count} />}
                            {inv.error_count === 0 && inv.warning_count === 0 && <IssueChip type="valid" />}
                          </>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        to={`/invoices/${inv.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center space-x-1 px-3 py-1.5 rounded-btn text-xs font-semibold transition-all shadow-2xs"
                        style={{
                          backgroundColor: "var(--bg-inset)",
                          border: "1px solid var(--border)",
                          color: "var(--ink)",
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = "var(--accent-soft)";
                          e.currentTarget.style.color = "var(--accent-strong)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = "var(--bg-inset)";
                          e.currentTarget.style.color = "var(--ink)";
                        }}
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
        {total > 0 && (
          <div
            className="px-6 py-3.5 border-t flex flex-col sm:flex-row items-center justify-between gap-3 text-xs"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
              color: "var(--text-muted)",
            }}
          >
            <div className="tabular-nums">
              Showing{" "}
              <strong className="font-semibold" style={{ color: "var(--text)" }}>
                {(page - 1) * pageSize + 1}
              </strong>
              {" "}–{" "}
              <strong className="font-semibold" style={{ color: "var(--text)" }}>
                {Math.min(page * pageSize, total)}
              </strong>
              {" "}of{" "}
              <strong className="font-semibold" style={{ color: "var(--text)" }}>
                {total}
              </strong>{" "}
              invoices
            </div>

            {totalPages > 1 && (
              <div className="flex items-center space-x-1.5">
                <button
                  type="button"
                  onClick={() => handlePageChange(Math.max(1, page - 1))}
                  disabled={page <= 1}
                  className="px-2.5 h-8 flex items-center justify-center space-x-1 border rounded-btn disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer select-none"
                  style={{
                    backgroundColor: "var(--bg-card)",
                    borderColor: "var(--border)",
                    color: "var(--text)",
                  }}
                  title="Previous page"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline text-xs font-medium">Prev</span>
                </button>

                <div className="flex items-center space-x-1">
                  {getPageItems(page, totalPages).map((item, idx) => {
                    if (item === "...") {
                      return (
                        <span
                          key={`dots-${idx}`}
                          className="w-8 h-8 flex items-center justify-center text-xs font-semibold select-none"
                          style={{ color: "var(--text-muted)" }}
                        >
                          …
                        </span>
                      );
                    }

                    const pageNum = Number(item);
                    const isActive = pageNum === page;

                    return (
                      <button
                        key={pageNum}
                        type="button"
                        onClick={() => handlePageChange(pageNum)}
                        className="w-8 h-8 flex items-center justify-center text-xs font-semibold rounded-btn border transition-colors cursor-pointer"
                        style={{
                          backgroundColor: isActive ? "var(--ink)" : "var(--bg-card)",
                          color: isActive ? "#FFFFFF" : "var(--text)",
                          borderColor: isActive ? "var(--ink)" : "var(--border)",
                        }}
                      >
                        {pageNum}
                      </button>
                    );
                  })}
                </div>

                <button
                  type="button"
                  onClick={() => handlePageChange(Math.min(totalPages, page + 1))}
                  disabled={page >= totalPages}
                  className="px-2.5 h-8 flex items-center justify-center space-x-1 border rounded-btn disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer select-none"
                  style={{
                    backgroundColor: "var(--bg-card)",
                    borderColor: "var(--border)",
                    color: "var(--text)",
                  }}
                  title="Next page"
                >
                  <span className="hidden sm:inline text-xs font-medium">Next</span>
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
