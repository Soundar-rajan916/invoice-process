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

  // Fetch recent invoices with automatic polling if anything is PROCESSING
  const { data: queueData, isFetching, refetch } = useQuery({
    queryKey: ["recent-invoices"],
    queryFn: () => apiRequest("/api/v1/invoices?sort=newest&page=1&page_size=15"),
    refetchInterval: (query) => {
      const items = query.state.data?.items || [];
      const hasProcessing = items.some(
        (inv: any) => inv.status === "PROCESSING" || inv.status === "RECEIVED"
      );
      return hasProcessing ? 3000 : 15000;
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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Document Inbox</h1>
        <p className="text-sm text-slate-600 mt-1">
          Upload PDF or image invoices (JPEG, PNG, WebP, HEIC). System will extract, validate, and deduplicate automatically.
        </p>
      </div>

      {/* Drag & Drop Upload Zone */}
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-10 flex flex-col items-center justify-center cursor-pointer transition-all ${
          dragActive
            ? "border-indigo-600 bg-indigo-50/50 scale-[1.01]"
            : "border-slate-300 bg-white hover:border-slate-400 hover:bg-slate-50/50"
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
        <div className="h-16 w-16 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 mb-4 shadow-sm">
          <UploadCloud className="h-8 w-8" />
        </div>
        <p className="text-base font-semibold text-slate-800">
          {uploading
            ? "Uploading and queueing invoices..."
            : "Drop invoice files here, or click to browse"}
        </p>
        <p className="text-xs text-slate-500 mt-1">
          Supports multi-file uploads: PDF, JPEG, PNG, WebP, HEIC (Max 20MB per file)
        </p>
      </div>

      {/* Upload Results Table */}
      {uploadResults.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
            <h3 className="font-semibold text-slate-800 text-sm">Upload Batch Results</h3>
            <button
              onClick={() => setUploadResults([])}
              className="text-xs font-medium text-slate-500 hover:text-slate-800"
            >
              Clear
            </button>
          </div>
          <div className="divide-y divide-slate-100">
            {uploadResults.map((res, idx) => (
              <div key={idx} className="px-6 py-3.5 flex items-center justify-between text-sm">
                <div className="flex items-center space-x-3">
                  {res.status === "created" && (
                    <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                  )}
                  {res.status === "duplicate_skipped" && (
                    <Clock className="h-5 w-5 text-amber-500" />
                  )}
                  {res.status === "failed" && (
                    <AlertTriangle className="h-5 w-5 text-red-500" />
                  )}
                  <span className="font-medium text-slate-700">{res.file_name}</span>
                </div>
                <div className="flex items-center space-x-4">
                  <span
                    className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                      res.status === "created"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : res.status === "duplicate_skipped"
                        ? "bg-amber-50 text-amber-700 border border-amber-200"
                        : "bg-red-50 text-red-700 border border-red-200"
                    }`}
                  >
                    {res.status === "created"
                      ? "Queued for Processing"
                      : res.status === "duplicate_skipped"
                      ? "Duplicate File Skipped"
                      : "Upload Failed"}
                  </span>
                  {res.invoice_id && (
                    <Link
                      to={`/invoices/${res.invoice_id}`}
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 flex items-center space-x-1"
                    >
                      <span>View</span>
                      <ArrowRight className="h-3 w-3" />
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Live Processing & Recent Invoices */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
          <div className="flex items-center space-x-2">
            <FileCheck className="h-5 w-5 text-indigo-600" />
            <h3 className="font-semibold text-slate-800 text-sm">Recent Ingested Invoices</h3>
          </div>
          <button
            onClick={() => refetch()}
            className="inline-flex items-center space-x-1.5 text-xs font-medium text-slate-600 hover:text-slate-900"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>

        {recentItems.length === 0 ? (
          <div className="px-6 py-12 text-center text-slate-500 text-sm">
            No invoices uploaded yet. Drop files above to start processing.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3">Invoice / GSTIN</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Received</th>
                  <th className="px-6 py-3">Issues</th>
                  <th className="px-6 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {recentItems.map((inv: any) => (
                  <tr key={inv.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="px-6 py-3.5">
                      <div className="font-semibold text-slate-900">
                        {inv.normalized_invoice_number || "Extracting..."}
                      </div>
                      <div className="text-xs text-slate-400 font-mono">
                        {inv.supplier_gstin || "Awaiting pipeline"}
                      </div>
                    </td>
                    <td className="px-6 py-3.5">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                          inv.status === "NEEDS_REVIEW"
                            ? "bg-amber-100 text-amber-800"
                            : inv.status === "APPROVED"
                            ? "bg-blue-100 text-blue-800"
                            : inv.status === "PUSHED"
                            ? "bg-emerald-100 text-emerald-800"
                            : inv.status === "PROCESSING"
                            ? "bg-purple-100 text-purple-800 animate-pulse"
                            : "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {inv.status}
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-xs text-slate-500">
                      {new Date(inv.received_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="px-6 py-3.5">
                      {inv.error_count > 0 ? (
                        <span className="text-xs font-semibold text-red-600 bg-red-50 px-2 py-0.5 rounded border border-red-200">
                          {inv.error_count} error{inv.error_count > 1 ? "s" : ""}
                        </span>
                      ) : inv.warning_count > 0 ? (
                        <span className="text-xs font-semibold text-amber-600 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                          {inv.warning_count} warning{inv.warning_count > 1 ? "s" : ""}
                        </span>
                      ) : (
                        <span className="text-xs text-emerald-600 font-medium">Clean</span>
                      )}
                    </td>
                    <td className="px-6 py-3.5 text-right">
                      <Link
                        to={`/invoices/${inv.id}`}
                        className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 inline-flex items-center space-x-1"
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
