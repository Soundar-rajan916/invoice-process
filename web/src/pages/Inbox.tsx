import React, { useState, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiRequest } from "@/lib/api";
import {
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  Clock,
  FileCheck,
  RefreshCw,
  ArrowRight,
  Check,
  AlertCircle,
} from "lucide-react";

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
  const { data: queueData, isFetching, refetch } = useQuery({
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
      {/* Top Banner with Title */}
      <div className="bg-findeck-card p-6 rounded-card border border-findeck-border shadow-xs">
        <h1 className="text-2xl font-bold text-findeck-text tracking-tight">Document Inbox</h1>
        <p className="text-xs text-findeck-muted mt-1">
          Upload PDF or image invoices (JPEG, PNG, WebP, HEIC). System will extract, validate, and deduplicate automatically.
        </p>
      </div>

      {/* Drag & Drop Upload Zone: dashed border in --accent, --accent-soft tint on drag-over */}
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-card p-10 flex flex-col items-center justify-center cursor-pointer transition-all ${
          dragActive
            ? "border-accent bg-accent-soft scale-[1.01]"
            : "border-findeck-border bg-white hover:border-accent-strong hover:bg-accent-soft/30"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.jpg,.jpeg,.png,.webp,.heic"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div className="h-14 w-14 rounded-2xl bg-accent-soft flex items-center justify-center text-ink mb-3 shadow-2xs">
          <UploadCloud className="h-7 w-7 text-ink" />
        </div>
        <p className="text-sm font-semibold text-findeck-text">
          {uploading
            ? "Uploading and queueing invoices..."
            : "Drop invoice files here, or click to browse"}
        </p>
        <p className="text-xs text-findeck-muted mt-1">
          Supports multi-file uploads: PDF, JPEG, PNG, WebP, HEIC (Max 20MB per file)
        </p>
      </div>

      {/* Upload Results Table */}
      {uploadResults.length > 0 && (
        <div className="bg-findeck-card rounded-card border border-findeck-border shadow-xs overflow-hidden">
          <div className="px-6 py-3.5 border-b border-findeck-border flex justify-between items-center bg-white">
            <h3 className="font-semibold text-findeck-text text-sm">Upload Batch Results</h3>
            <button
              onClick={() => setUploadResults([])}
              className="text-xs font-medium text-findeck-muted hover:text-findeck-text cursor-pointer"
            >
              Clear
            </button>
          </div>
          <div className="divide-y divide-findeck-border">
            {uploadResults.map((res: any, idx) => {
              const fileName = res.file_name || res.filename || "Uploaded File";
              const isDuplicate = res.status === "duplicate_skipped" || res.is_duplicate;
              const liveInvoice = recentItems.find((inv: any) => inv.id === res.invoice_id);
              const status = liveInvoice
                ? liveInvoice.status
                : res.status === "created" || res.status === "RECEIVED"
                ? "RECEIVED"
                : res.status;

              let badgeColor = "bg-accent-soft text-accent-strong border-accent/30";
              let badgeText = "Queued for Processing";
              let StatusIcon = Clock;

              if (isDuplicate) {
                badgeColor = "bg-accent-soft text-ink border-accent/30";
                badgeText = "Duplicate File Skipped";
                StatusIcon = Clock;
              } else if (status === "PROCESSING") {
                badgeColor = "bg-accent-soft text-accent-strong border-accent/30";
                badgeText = "Extracting & Validating...";
                StatusIcon = RefreshCw;
              } else if (status === "NEEDS_REVIEW") {
                badgeColor = "bg-warning-soft text-warning-strong border-warning/30";
                badgeText =
                  liveInvoice?.error_count > 0
                    ? `Ready for Review (${liveInvoice.error_count} error${
                        liveInvoice.error_count > 1 ? "s" : ""
                      })`
                    : "Ready for Review";
                StatusIcon = CheckCircle2;
              } else if (status === "APPROVED" || status === "PUSHED") {
                badgeColor = "bg-success-soft text-success-strong border-success/30";
                badgeText = status === "PUSHED" ? "Pushed to Accounting" : "Approved";
                StatusIcon = CheckCircle2;
              } else if (status === "RESEND_REQUESTED") {
                badgeColor = "bg-warning-soft text-warning-strong border-warning/30";
                badgeText = "Resend Requested";
                StatusIcon = AlertTriangle;
              } else if (status === "REJECTED") {
                badgeColor = "bg-danger-soft text-danger-strong border-danger/30";
                badgeText = "Rejected";
                StatusIcon = AlertTriangle;
              } else if (status === "FAILED" || res.status === "failed") {
                badgeColor = "bg-danger-soft text-danger-strong border-danger/30";
                badgeText = "Processing Failed";
                StatusIcon = AlertTriangle;
              }

              return (
                <div key={idx} className="px-6 py-3.5 flex items-center justify-between text-xs bg-findeck-card">
                  <div className="flex items-center space-x-3">
                    <StatusIcon
                      className={`h-4 w-4 ${
                        status === "PROCESSING"
                          ? "animate-spin text-accent-strong"
                          : isDuplicate
                          ? "text-ink"
                          : status === "NEEDS_REVIEW"
                          ? "text-warning-strong"
                          : status === "APPROVED" || status === "PUSHED"
                          ? "text-success-strong"
                          : status === "FAILED" || res.status === "failed"
                          ? "text-danger-strong"
                          : "text-accent-strong"
                      }`}
                    />
                    <span className="font-medium text-findeck-text">{fileName}</span>
                  </div>
                  <div className="flex items-center space-x-4">
                    <span
                      className={`text-xs px-2.5 py-0.5 rounded-pill font-medium border ${badgeColor}`}
                    >
                      {badgeText}
                    </span>
                    {res.invoice_id && (
                      <Link
                        to={`/invoices/${res.invoice_id}`}
                        className="text-xs font-semibold text-accent-strong hover:underline flex items-center space-x-1"
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

      {/* Live Processing & Recent Invoices */}
      <div className="bg-findeck-card rounded-card border border-findeck-border shadow-xs overflow-hidden">
        <div className="px-6 py-3.5 border-b border-findeck-border flex justify-between items-center bg-white">
          <div className="flex items-center space-x-2">
            <FileCheck className="h-4 w-4 text-ink" />
            <h3 className="font-semibold text-findeck-text text-sm">Recent Ingested Invoices</h3>
          </div>
          <button
            onClick={() => refetch()}
            className="inline-flex items-center space-x-1.5 text-xs font-medium text-findeck-muted hover:text-findeck-text cursor-pointer"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>

        {recentItems.length === 0 ? (
          <div className="px-6 py-12 text-center text-findeck-muted text-xs">
            No invoices uploaded yet. Drop files above to start processing.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-findeck-text">
              <thead className="bg-white text-[11px] font-semibold text-text-secondary uppercase tracking-wider border-b border-findeck-border">
                <tr>
                  <th className="px-6 py-3.5">Invoice / GSTIN</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5">Received</th>
                  <th className="px-6 py-3.5">Issues</th>
                  <th className="px-6 py-3.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-findeck-border">
                {recentItems.map((inv: any) => (
                  <tr key={inv.id} className="hover:bg-white transition-colors">
                    <td className="px-6 py-3.5">
                      <div className="font-semibold text-findeck-text">
                        {inv.normalized_invoice_number || "Extracting..."}
                      </div>
                      <div className="text-[11px] text-findeck-muted font-mono">
                        {inv.supplier_gstin || "Awaiting pipeline"}
                      </div>
                    </td>
                    <td className="px-6 py-3.5">
                      <span
                        className={`inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-pill text-xs font-medium border ${
                          inv.status === "NEEDS_REVIEW"
                            ? "bg-warning-soft text-warning-strong border-warning/30"
                            : inv.status === "APPROVED" || inv.status === "PUSHED"
                            ? "bg-success-soft text-success-strong border-success/30"
                            : inv.status === "PROCESSING"
                            ? "bg-accent-soft text-accent-strong border-accent/30 animate-pulse"
                            : inv.status === "RESEND_REQUESTED"
                            ? "bg-warning-soft text-warning-strong border-warning/30"
                            : inv.status === "REJECTED" || inv.status === "FAILED"
                            ? "bg-danger-soft text-danger-strong border-danger/30"
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
                                : inv.status === "PROCESSING"
                                ? "bg-accent"
                                : "bg-danger"
                            }`}
                          />
                        )}
                        <span>{inv.status}</span>
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-xs text-findeck-muted tabular-nums">
                      {new Date(inv.received_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="px-6 py-3.5">
                      {inv.error_count > 0 ? (
                        <span className="inline-flex items-center space-x-1 text-xs font-semibold text-danger-strong bg-danger-soft px-2 py-0.5 rounded-pill border border-danger/30">
                          <AlertCircle className="h-3 w-3" />
                          <span className="tabular-nums">{inv.error_count} error{inv.error_count > 1 ? "s" : ""}</span>
                        </span>
                      ) : inv.warning_count > 0 ? (
                        <span className="inline-flex items-center space-x-1 text-xs font-semibold text-warning-strong bg-warning-soft px-2 py-0.5 rounded-pill border border-warning/30">
                          <AlertTriangle className="h-3 w-3" />
                          <span className="tabular-nums">{inv.warning_count} warning{inv.warning_count > 1 ? "s" : ""}</span>
                        </span>
                      ) : (
                        <span className="text-xs text-success-strong font-medium">Clean</span>
                      )}
                    </td>
                    <td className="px-6 py-3.5 text-right">
                      <Link
                        to={`/invoices/${inv.id}`}
                        className="text-xs font-semibold text-accent-strong hover:underline inline-flex items-center space-x-1"
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
