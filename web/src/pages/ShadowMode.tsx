import React, { useState, useEffect } from "react";
import { Upload, CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";

interface ShadowReport {
  total_shadow_records: number;
  total_matched: number;
  perfect_matches: number;
  overall_agreement_pct: number;
  amount_matches: number;
  date_matches: number;
  missing_in_invoiceflow: Array<{
    invoice_number: string;
    supplier_gstin: string;
    total: number;
  }>;
  mismatches_by_supplier: Array<{
    supplier_gstin: string;
    mismatches: number;
  }>;
}

export const ShadowMode: React.FC = () => {
  const [report, setReport] = useState<ShadowReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/admin/shadow/report");
      if (!res.ok) throw new Error("Failed to load shadow mode report");
      const data = await res.json();
      setReport(data);
    } catch (err: any) {
      setError(err.message || "Failed to fetch shadow mode report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadMessage(null);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/v1/admin/shadow/import", {
        method: "POST",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
        body: formData,
      });

      if (!res.ok) throw new Error("Failed to import CSV ground truth");
      const data = await res.json();
      setUploadMessage(`Successfully imported ${data.total_imported} records from ${file.name}`);
      fetchReport();
    } catch (err: any) {
      setError(err.message || "Failed to upload ground truth CSV");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
              Shadow Mode Evaluation
            </h1>
            <span
              className="px-2.5 py-0.5 text-xs font-semibold rounded-full uppercase tracking-wider"
              style={{
                backgroundColor: "var(--accent-soft)",
                color: "var(--ink)",
              }}
            >
              Dual-Run Verification
            </span>
          </div>
          <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
            Compare AI extraction and validation outputs against historical human accounting decisions before going live.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchReport}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-[10px] text-xs font-semibold transition-all border shadow-xs"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
              color: "var(--text)",
            }}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh Data
          </button>
        </div>
      </div>

      {/* Upload Box */}
      <div
        className="p-6 rounded-[14px] border shadow-xs"
        style={{
          backgroundColor: "var(--bg-card)",
          borderColor: "var(--border)",
        }}
      >
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="space-y-1">
            <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Import Accounts Team Ledger (CSV)
            </h3>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Required CSV headers: <code className="font-mono">invoice_number</code>, <code className="font-mono">supplier_gstin</code>, <code className="font-mono">invoice_date</code>, <code className="font-mono">total</code>.
            </p>
          </div>

          <div className="flex items-center gap-4">
            <label className="cursor-pointer">
              <input
                type="file"
                accept=".csv"
                onChange={handleFileUpload}
                disabled={uploading}
                className="hidden"
              />
              <span
                className="inline-flex items-center gap-2 px-4 py-2 rounded-[10px] text-sm font-medium transition-all shadow-xs"
                style={{
                  backgroundColor: "var(--ink)",
                  color: "#FFFFFF",
                }}
              >
                <Upload className="w-4 h-4" />
                {uploading ? "Importing Ledger..." : "Upload Ledger CSV"}
              </span>
            </label>
          </div>
        </div>

        {uploadMessage && (
          <div
            className="mt-4 p-3 rounded-[10px] text-xs font-medium flex items-center gap-2"
            style={{
              backgroundColor: "var(--accent-soft)",
              color: "var(--ink)",
            }}
          >
            <CheckCircle2 className="w-4 h-4" />
            {uploadMessage}
          </div>
        )}

        {error && (
          <div
            className="mt-4 p-3 rounded-[10px] text-xs font-medium flex items-center gap-2"
            style={{
              backgroundColor: "var(--danger-soft)",
              color: "var(--danger)",
            }}
          >
            <AlertCircle className="w-4 h-4" />
            {error}
          </div>
        )}
      </div>

      {/* Summary KPI Cards */}
      {report && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div
            className="p-5 rounded-[14px] border shadow-xs"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Overall Agreement Rate
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold" style={{ color: "var(--text)" }}>
                {report.overall_agreement_pct}%
              </span>
              <span
                className="text-xs px-2 py-0.5 rounded-full font-semibold"
                style={{
                  backgroundColor: report.overall_agreement_pct >= 95 ? "var(--accent-soft)" : "var(--warning-soft)",
                  color: "var(--ink)",
                }}
              >
                {report.overall_agreement_pct >= 95 ? "Target Met" : "Calibrating"}
              </span>
            </div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              {report.perfect_matches} of {report.total_matched} verified
            </p>
          </div>

          <div
            className="p-5 rounded-[14px] border shadow-xs"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Amount Matches
            </div>
            <div className="mt-2 text-3xl font-extrabold" style={{ color: "var(--text)" }}>
              {report.amount_matches}
            </div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Total math within ₹1.00 tolerance
            </p>
          </div>

          <div
            className="p-5 rounded-[14px] border shadow-xs"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Date Matches
            </div>
            <div className="mt-2 text-3xl font-extrabold" style={{ color: "var(--text)" }}>
              {report.date_matches}
            </div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Exact calendar date parity
            </p>
          </div>

          <div
            className="p-5 rounded-[14px] border shadow-xs"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
              Missing in InvoiceFlow
            </div>
            <div className="mt-2 text-3xl font-extrabold" style={{ color: "var(--text)" }}>
              {report.missing_in_invoiceflow.length}
            </div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Ledger entries without intake record
            </p>
          </div>
        </div>
      )}

      {/* Discrepancies by Supplier */}
      {report && report.mismatches_by_supplier.length > 0 && (
        <div
          className="p-6 rounded-[14px] border shadow-xs space-y-4"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div>
            <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              Mismatches Grouped by Supplier
            </h3>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              Identifies suppliers whose invoice formats trigger human discrepancies or math differences.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b" style={{ borderColor: "var(--border)" }}>
                  <th className="py-2.5 px-3 font-semibold" style={{ color: "var(--text-muted)" }}>
                    Supplier GSTIN
                  </th>
                  <th className="py-2.5 px-3 font-semibold text-right" style={{ color: "var(--text-muted)" }}>
                    Discrepancy Count
                  </th>
                  <th className="py-2.5 px-3 font-semibold text-right" style={{ color: "var(--text-muted)" }}>
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: "var(--border)" }}>
                {report.mismatches_by_supplier.map((s, idx) => (
                  <tr key={idx} className="hover:bg-white/40">
                    <td className="py-2.5 px-3 font-mono font-medium" style={{ color: "var(--text)" }}>
                      {s.supplier_gstin}
                    </td>
                    <td className="py-2.5 px-3 text-right font-bold" style={{ color: "var(--danger)" }}>
                      {s.mismatches}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span
                        className="px-2 py-0.5 rounded-full text-[11px] font-semibold"
                        style={{
                          backgroundColor: "var(--danger-soft)",
                          color: "var(--danger)",
                        }}
                      >
                        Needs Review
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Missing Invoices Table */}
      {report && report.missing_in_invoiceflow.length > 0 && (
        <div
          className="p-6 rounded-[14px] border shadow-xs space-y-4"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
            Invoices Missing in InvoiceFlow
          </h3>
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            Invoices recorded in the manual accounts ledger that were not ingested via Email, WhatsApp, or Upload.
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b" style={{ borderColor: "var(--border)" }}>
                  <th className="py-2.5 px-3 font-semibold" style={{ color: "var(--text-muted)" }}>
                    Invoice Number
                  </th>
                  <th className="py-2.5 px-3 font-semibold" style={{ color: "var(--text-muted)" }}>
                    Supplier GSTIN
                  </th>
                  <th className="py-2.5 px-3 font-semibold text-right" style={{ color: "var(--text-muted)" }}>
                    Total Amount
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: "var(--border)" }}>
                {report.missing_in_invoiceflow.map((m, idx) => (
                  <tr key={idx} className="hover:bg-white/40">
                    <td className="py-2.5 px-3 font-mono font-medium" style={{ color: "var(--text)" }}>
                      {m.invoice_number}
                    </td>
                    <td className="py-2.5 px-3 font-mono" style={{ color: "var(--text-secondary)" }}>
                      {m.supplier_gstin}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-semibold" style={{ color: "var(--text)" }}>
                      ₹{m.total.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
