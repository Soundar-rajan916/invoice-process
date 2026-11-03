import React, { useState, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiRequest } from "@/lib/api";
import {
  UploadCloud,
  Clock,
  FileCheck,
  RefreshCw,
  ArrowRight,
  MessageSquare,
  Mail,
  Upload,
} from "lucide-react";
import { StatusPill } from "@/components/StatusPill";
import { IssueChip } from "@/components/IssueChip";
import { Skeleton, SkeletonPill } from "@/components/Skeleton";

interface UploadFileResult {
  file_name: string;
  status: "created" | "duplicate_skipped" | "failed";
  invoice_id?: string;
  sha256?: string;
  message?: string;
}

export function Inbox() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState<UploadFileResult[]>([]);

  // Fetch recent invoices with automatic polling if anything is PROCESSING or in uploadResults
  const { data: queueData, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["recent-invoices"],
    queryFn: () => apiRequest("/api/v1/invoices?sort=newest&page=1&page_size=20"),
    refetchInterval: (query) => {
      const items = query.state.data?.items || [];
      const hasProcessing = items.some(
        (inv: any) => inv.status === "PROCESSING" || inv.status === "RECEIVED"
      );
      const hasRecentPendingUpload = uploadResults.some((res) => {
        if (!res.invoice_id || res.status === "duplicate_skipped") return false;
        const matching = items.find((i: any) => i.id === res.invoice_id);
        return !matching || matching.status === "PROCESSING" || matching.status === "RECEIVED";
      });
      return hasProcessing || hasRecentPendingUpload ? 2000 : 10000;
    },
  });

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setUploading(true);
    const results: UploadFileResult[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append("files", file);

      try {
        const res = await apiRequest<{ results: UploadFileResult[] }>(
          "/api/v1/files",
          {
            method: "POST",
            body: formData,
          }
        );
        if (res.results && res.results.length > 0) {
          results.push(...res.results);
        }
      } catch (err: any) {
        results.push({
          file_name: file.name,
          status: "failed",
          message: err.message || "Upload failed",
        });
      }
    }

    setUploadResults(results);
    setUploading(false);
    queryClient.invalidateQueries({ queryKey: ["recent-invoices"] });
    queryClient.invalidateQueries({ queryKey: ["invoices-queue"] });
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(true);
  };

  const onDragLeave = () => {
    setDragActive(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    handleFiles(e.dataTransfer.files);
  };

  const recentItems = queueData?.items || [];

  return (
    <div className="w-full space-y-6">
      {/* Top Banner on --bg-card */}
      <div
        className="p-6 rounded-card border shadow-xs"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
          Document Inbox
        </h1>
        <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
          Upload PDF or image invoices (JPEG, PNG, WebP, HEIC). System will extract, validate, and deduplicate automatically.
        </p>
      </div>

      {/* Drag & Drop Upload Zone: dashed border in --accent, --accent-soft tint on drag-over */}
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        className="border-2 border-dashed rounded-card p-10 flex flex-col items-center justify-center cursor-pointer transition-all shadow-xs"
        style={{
          borderColor: "var(--accent)",
          backgroundColor: dragActive ? "var(--accent-soft)" : "var(--bg-inset)",
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.jpg,.jpeg,.png,.webp,.heic"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div
          className="h-14 w-14 rounded-2xl flex items-center justify-center mb-3 shadow-2xs"
          style={{
            backgroundColor: "var(--accent-soft)",
            color: "var(--ink)",
          }}
        >
          <UploadCloud className="h-7 w-7 stroke-[2.2]" />
        </div>
        <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          {uploading
            ? "Uploading and queueing invoices..."
            : "Drop invoice files here, or click to browse"}
        </p>
        <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
          Supports multi-file uploads: PDF, JPEG, PNG, WebP, HEIC (Max 20MB per file)
        </p>
      </div>

      {/* Upload Results Table */}
      {uploadResults.length > 0 && (
        <div
          className="rounded-card border shadow-xs overflow-hidden"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div
            className="px-6 py-3.5 border-b flex justify-between items-center"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
            }}
          >
            <h3 className="font-semibold text-sm" style={{ color: "var(--text)" }}>
              Upload Batch Results
            </h3>
            <button
              onClick={() => setUploadResults([])}
              className="text-xs font-medium cursor-pointer"
              style={{ color: "var(--text-muted)" }}
            >
              Clear
            </button>
          </div>
          <div className="divide-y" style={{ borderColor: "var(--border)" }}>
            {uploadResults.map((res: any, idx) => {
              const fileName = res.file_name || res.filename || "Uploaded File";
              const isDuplicate = res.status === "duplicate_skipped" || res.is_duplicate;
              const liveInvoice = recentItems.find((inv: any) => inv.id === res.invoice_id);
              const status = liveInvoice
                ? liveInvoice.status
                : res.status === "created" || res.status === "RECEIVED"
                ? "RECEIVED"
                : res.status;

              return (
                <div
                  key={idx}
                  className="px-6 py-3.5 flex items-center justify-between text-xs"
                  style={{ backgroundColor: "var(--bg-card)" }}
                >
                  <div className="flex items-center space-x-3">
                    <Clock className="h-4 w-4" style={{ color: "var(--text-muted)" }} />
                    <span className="font-medium" style={{ color: "var(--text)" }}>{fileName}</span>
                  </div>
                  <div className="flex items-center space-x-4">
                    {isDuplicate ? (
                      <span
                        className="text-xs px-2.5 py-0.5 rounded-full font-semibold shadow-2xs"
                        style={{ backgroundColor: "var(--accent-soft)", color: "var(--ink)" }}
                      >
                        Duplicate File Skipped
                      </span>
                    ) : (
                      <StatusPill status={status} />
                    )}
                    {res.invoice_id && (
                      <Link
                        to={`/invoices/${res.invoice_id}`}
                        className="text-xs font-semibold flex items-center space-x-1"
                        style={{ color: "var(--accent-strong)" }}
                      >
                        <span>View</span>
                        <ArrowRight className="h-3 w-3" />
                      </Link>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Live Processing & Recent Invoices on --bg-card */}
      <div
        className="rounded-card border shadow-xs overflow-hidden"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        <div
          className="px-6 py-3.5 border-b flex justify-between items-center"
          style={{
            backgroundColor: "var(--bg-inset)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center space-x-2">
            <FileCheck className="h-4 w-4" style={{ color: "var(--ink)" }} />
            <h3 className="font-semibold text-sm" style={{ color: "var(--text)" }}>
              Recent Ingested Invoices
            </h3>
          </div>
          <button
            onClick={() => refetch()}
            className="inline-flex items-center space-x-1.5 text-xs font-medium cursor-pointer"
            style={{ color: "var(--text-muted)" }}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>

        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className="flex items-center justify-between py-2 border-b last:border-b-0"
                style={{ borderColor: "var(--border)" }}
              >
                <div className="space-y-1.5">
                  <Skeleton className="h-3.5 w-36" />
                  <Skeleton className="h-2.5 w-24 opacity-50" />
                </div>
                <SkeletonPill className="h-5 w-20" />
                <Skeleton className="h-3 w-16" />
                <Skeleton rounded="btn" className="h-7 w-16" />
              </div>
            ))}
          </div>
        ) : recentItems.length === 0 ? (
          <div className="px-6 py-12 text-center text-xs" style={{ color: "var(--text-muted)" }}>
            No invoices uploaded yet. Drop files above to start processing.
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
                  <th className="px-6 py-3.5">Invoice / GSTIN</th>
                  <th className="px-6 py-3.5">Channel</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Received</th>
                  <th className="px-6 py-3.5">Issues</th>
                  <th className="px-6 py-3.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {recentItems.map((inv: any) => (
                  <tr
                    key={inv.id}
                    className="transition-colors group cursor-pointer"
                    style={{ borderBottom: "1px solid var(--border)" }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = "var(--accent-soft)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = "transparent";
                    }}
                  >
                    <td className="px-6 py-3.5">
                      <div className="font-semibold" style={{ color: "var(--text)" }}>
                        {inv.normalized_invoice_number || "Extracting..."}
                      </div>
                      <div className="text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
                        {inv.supplier_gstin || "Awaiting pipeline"}
                      </div>
                    </td>
                    <td className="px-6 py-3.5">
                      {inv.channel === "whatsapp" ? (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                          <MessageSquare className="h-3 w-3 mr-0.5" />
                          <span>WhatsApp</span>
                        </span>
                      ) : inv.channel === "email" ? (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-blue-500/10 text-blue-600 border border-blue-500/20">
                          <Mail className="h-3 w-3 mr-0.5" />
                          <span>Email</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-zinc-500/10 text-zinc-600 border border-zinc-500/20">
                          <Upload className="h-3 w-3 mr-0.5" />
                          <span>Upload</span>
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-3.5">
                      <StatusPill status={inv.status} />
                    </td>
                    <td className="px-6 py-3.5 text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>
                      {new Date(inv.received_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="px-6 py-3.5">
                      {inv.error_count > 0 ? (
                        <IssueChip type="error" count={inv.error_count} />
                      ) : inv.warning_count > 0 ? (
                        <IssueChip type="warning" count={inv.warning_count} />
                      ) : (
                        <IssueChip type="valid" />
                      )}
                    </td>
                    <td className="px-6 py-3.5 text-right">
                      <Link
                        to={`/invoices/${inv.id}`}
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
                        <span>Open</span>
                        <ArrowRight className="h-3 w-3" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
