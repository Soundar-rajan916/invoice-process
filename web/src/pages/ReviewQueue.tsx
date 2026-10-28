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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-6">
      {/* Top Banner with Action & R4 Metric */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Review Queue</h1>
          <p className="text-sm text-slate-600 mt-1">
            Accounts team review and approval verification workspace (R2 guarantee).
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={startReviewing}
            disabled={items.length === 0}
            className="inline-flex items-center space-x-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm rounded-xl shadow-md disabled:opacity-50 transition-all cursor-pointer"
          >
            <Play className="h-4 w-4 fill-white" />
            <span>Start Reviewing</span>
          </button>
        </div>
      </div>

      {/* Filter and Status Summary Pills */}
      <div className="flex items-center space-x-2 overflow-x-auto pb-2">
        {["ALL", "NEEDS_REVIEW", "APPROVED", "PUSHED", "REJECTED"].map((st) => (
          <button
            key={st}
            onClick={() => {
              setStatusFilter(st);
              setPage(1);
            }}
            className={`px-3.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all border ${
              statusFilter === st
                ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
            }`}
          >
            <span>{st.replace("_", " ")}</span>
            {counts[st] !== undefined && (
              <span
                className={`ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] ${
                  statusFilter === st ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600"
                }`}
              >
                {counts[st]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Filter Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 items-center justify-between">
        <div className="relative w-full md:w-80">
          <Search className="h-4 w-4 absolute left-3 top-3 text-slate-400" />
          <input
            type="text"
            placeholder="Search invoice number, GSTIN, file..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div className="flex items-center space-x-4 w-full md:w-auto justify-end">
          <label className="flex items-center space-x-2 text-xs font-medium text-slate-700 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={flaggedOnly}
              onChange={(e) => {
                setFlaggedOnly(e.target.checked);
                setPage(1);
              }}
              className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span>Flagged issues only</span>
          </label>

          <button
            onClick={() => setSortOrder(sortOrder === "oldest" ? "newest" : "oldest")}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <ArrowUpDown className="h-3.5 w-3.5" />
            <span>Sort: {sortOrder === "oldest" ? "Oldest First" : "Newest First"}</span>
          </button>
        </div>
      </div>

      {/* Main Queue Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="py-20 text-center text-sm text-slate-500">Loading invoice queue...</div>
        ) : items.length === 0 ? (
          <div className="py-20 text-center">
            <FileText className="h-10 w-10 text-slate-300 mx-auto mb-2" />
            <p className="text-sm font-medium text-slate-600">No invoices match your filter</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3.5">Invoice #</th>
                  <th className="px-6 py-3.5">Supplier GSTIN</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Received / Age</th>
                  <th className="px-6 py-3.5">Flags & Issues</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((inv: any) => (
                  <tr
                    key={inv.id}
                    className="hover:bg-indigo-50/40 transition-colors group cursor-pointer"
                    onClick={() => navigate(`/invoices/${inv.id}`)}
                  >
                    <td className="px-6 py-4">
                      <div className="font-semibold text-slate-900 group-hover:text-indigo-600 transition-colors">
                        {inv.normalized_invoice_number || "Unextracted"}
                      </div>
                      <div className="text-xs text-slate-400">
                        FY: {inv.financial_year || "Pending"}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="font-mono text-xs text-slate-700 font-medium">
                        {inv.supplier_gstin || "—"}
                      </div>
                      <div className="text-xs text-slate-400">
                        {inv.extraction_path ? `${inv.extraction_path} path` : ""}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                          inv.status === "NEEDS_REVIEW"
                            ? "bg-amber-100 text-amber-800"
                            : inv.status === "APPROVED"
                            ? "bg-blue-100 text-blue-800"
                            : inv.status === "PUSHED"
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {inv.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs">
                      <div className="text-slate-800 font-medium">{formatAge(inv.received_at)}</div>
                      <div className="text-slate-400">
                        {new Date(inv.received_at).toLocaleDateString()}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center space-x-2">
                        {inv.error_count > 0 && (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200">
                            <AlertCircle className="h-3 w-3 text-red-500" />
                            <span>{inv.error_count} error{inv.error_count > 1 ? "s" : ""}</span>
                          </span>
                        )}
                        {inv.warning_count > 0 && (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
                            <AlertTriangle className="h-3 w-3 text-amber-500" />
                            <span>{inv.warning_count} warning{inv.warning_count > 1 ? "s" : ""}</span>
                          </span>
                        )}
                        {inv.error_count === 0 && inv.warning_count === 0 && (
                          <span className="text-xs text-emerald-600 font-medium">Valid</span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        to={`/invoices/${inv.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center space-x-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
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
          <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <div>
              Showing page {page} of {totalPages} ({total} total invoices)
            </div>
            <div className="flex items-center space-x-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="p-1 border border-slate-200 rounded hover:bg-slate-50 disabled:opacity-50"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="p-1 border border-slate-200 rounded hover:bg-slate-50 disabled:opacity-50"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
