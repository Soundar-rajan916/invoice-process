import { useState, useEffect, useMemo, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import Decimal from "decimal.js";
import {
  TransformWrapper,
  TransformComponent,
} from "react-zoom-pan-pinch";
import { apiRequest, ConflictError } from "@/lib/api";
import {
  ZoomIn,
  ZoomOut,
  RotateCw,
  Maximize2,
  Check,
  X,
  AlertTriangle,
  AlertCircle,
  HelpCircle,
  History,
  Copy,
  ChevronLeft,
  Plus,
  Trash2,
  Save,
  RefreshCw,
} from "lucide-react";

// Form Schema with validation matching Phase 3 rules
const invoiceFormSchema = z.object({
  invoice_number: z.string().min(1, "Invoice number is required"),
  invoice_date: z.string().min(1, "Invoice date is required"),
  supplier_name: z.string().min(1, "Supplier name is required"),
  supplier_gstin: z
    .string()
    .length(15, "GSTIN must be 15 characters")
    .regex(/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$/, "Invalid GSTIN format"),
  taxable_value: z.string().optional(),
  cgst: z.string().optional(),
  sgst: z.string().optional(),
  igst: z.string().optional(),
  total: z.string().min(1, "Total amount is required"),
  line_items: z.array(
    z.object({
      description: z.string().min(1, "Description required"),
      quantity: z.string().optional(),
      rate: z.string().optional(),
      amount: z.string().min(1, "Amount required"),
    })
  ),
});

type InvoiceFormValues = z.infer<typeof invoiceFormSchema>;

export function ReviewDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [activePage, setActivePage] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);
  const [showAuditDrawer, setShowAuditDrawer] = useState(false);
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);
  const [showOverrideDialog, setShowOverrideDialog] = useState(false);
  const [showRejectDialog, setShowRejectDialog] = useState(false);
  const [showResendDialog, setShowResendDialog] = useState(false);
  const [showDuplicateOverrideDialog, setShowDuplicateOverrideDialog] = useState(false);
  const [dialogReason, setDialogReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  // 1. Fetch Invoice Detail
  const { data: invoice, isLoading, refetch } = useQuery({
    queryKey: ["invoice-detail", id],
    queryFn: () => apiRequest(`/api/v1/invoices/${id}`),
    enabled: !!id,
  });

  // 2. Fetch Review Queue for Next/Previous Navigation
  const { data: queueData } = useQuery({
    queryKey: ["invoices-queue-nav"],
    queryFn: () => apiRequest("/api/v1/invoices?status=NEEDS_REVIEW&page_size=100"),
  });

  // 3. Fetch Audit Trail
  const { data: auditTrail, refetch: refetchAudit } = useQuery({
    queryKey: ["invoice-audit", id],
    queryFn: () => apiRequest(`/api/v1/invoices/${id}/audit`),
    enabled: showAuditDrawer && !!id,
  });

  const {
    register,
    control,
    handleSubmit,
    reset,
    watch,
    formState: { isDirty, errors },
  } = useForm<InvoiceFormValues>({
    resolver: zodResolver(invoiceFormSchema),
    defaultValues: {
      invoice_number: "",
      invoice_date: "",
      supplier_name: "",
      supplier_gstin: "",
      taxable_value: "",
      cgst: "",
      sgst: "",
      igst: "",
      total: "",
      line_items: [],
    },
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: "line_items",
  });

  // Sync loaded extraction data to form
  useEffect(() => {
    if (invoice?.current_extraction) {
      const ext = invoice.current_extraction;
      reset({
        invoice_number: ext.invoice_number || "",
        invoice_date: ext.invoice_date || "",
        supplier_name: ext.supplier_name || "",
        supplier_gstin: ext.supplier_gstin || "",
        taxable_value: ext.taxable_value || "",
        cgst: ext.cgst || "",
        sgst: ext.sgst || "",
        igst: ext.igst || "",
        total: ext.total || "",
        line_items: (ext.line_items || []).map((li: any) => ({
          description: li.description || "",
          quantity: li.quantity ? String(li.quantity) : "",
          rate: li.rate ? String(li.rate) : "",
          amount: li.amount ? String(li.amount) : "",
        })),
      });
      setConflictMessage(null);
    }
  }, [invoice, reset]);

  // Real-time calculated total using decimal.js
  const watchedLines = watch("line_items");
  const watchedCgst = watch("cgst");
  const watchedSgst = watch("sgst");
  const watchedIgst = watch("igst");
  const watchedTotal = watch("total");

  const calculatedTotal = useMemo(() => {
    try {
      let sum = new Decimal(0);
      for (const li of watchedLines || []) {
        if (li.amount) {
          sum = sum.plus(new Decimal(li.amount));
        }
      }
      if (watchedCgst) sum = sum.plus(new Decimal(watchedCgst));
      if (watchedSgst) sum = sum.plus(new Decimal(watchedSgst));
      if (watchedIgst) sum = sum.plus(new Decimal(watchedIgst));
      return sum.toFixed(2);
    } catch {
      return "0.00";
    }
  }, [watchedLines, watchedCgst, watchedSgst, watchedIgst]);

  const totalMatches = useMemo(() => {
    try {
      if (!watchedTotal) return false;
      const t1 = new Decimal(watchedTotal);
      const t2 = new Decimal(calculatedTotal);
      return t1.minus(t2).abs().lessThanOrEqualTo(1.0); // Within total rounding tolerance
    } catch {
      return false;
    }
  }, [watchedTotal, calculatedTotal]);

  // Next / Previous navigation in queue
  const queueItems = queueData?.items || [];
  const currentIndex = queueItems.findIndex((it: any) => it.id === id);
  const nextInvoiceId = currentIndex >= 0 && currentIndex < queueItems.length - 1 ? queueItems[currentIndex + 1].id : null;
  const prevInvoiceId = currentIndex > 0 ? queueItems[currentIndex - 1].id : null;

  const navigateNext = useCallback(() => {
    if (nextInvoiceId) navigate(`/invoices/${nextInvoiceId}`);
    else navigate("/queue");
  }, [nextInvoiceId, navigate]);

  const navigatePrev = useCallback(() => {
    if (prevInvoiceId) navigate(`/invoices/${prevInvoiceId}`);
  }, [prevInvoiceId, navigate]);

  // Save Edits Mutation (PATCH /api/v1/invoices/{id}/fields)
  const saveMutation = useMutation({
    mutationFn: (values: InvoiceFormValues) => {
      const payload = {
        extraction: {
          invoice_number: values.invoice_number,
          invoice_date: values.invoice_date,
          supplier_name: values.supplier_name,
          supplier_gstin: values.supplier_gstin,
          taxable_value: values.taxable_value || null,
          cgst: values.cgst || null,
          sgst: values.sgst || null,
          igst: values.igst || null,
          total: values.total,
          line_items: values.line_items.map((li) => ({
            description: li.description,
            quantity: li.quantity ? li.quantity : null,
            rate: li.rate ? li.rate : null,
            amount: li.amount,
          })),
          field_confidence: invoice?.current_extraction?.field_confidence || {},
          unreadable_fields: [],
        },
        row_version: invoice?.row_version ?? 1,
      };
      return apiRequest(`/api/v1/invoices/${id}/fields`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoice-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["invoices-queue"] });
    },
    onError: (err: any) => {
      if (err instanceof ConflictError) {
        setConflictMessage(err.message);
      } else {
        alert(err.message || "Failed to save invoice edits");
      }
    },
  });

  // Approve Mutation (POST /api/v1/invoices/{id}/approve)
  const approveMutation = useMutation({
    mutationFn: (overrideReason?: string) => {
      return apiRequest(`/api/v1/invoices/${id}/approve`, {
        method: "POST",
        body: JSON.stringify({
          row_version: invoice?.row_version ?? 1,
          override_reason: overrideReason || null,
        }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoices-queue"] });
      navigateNext();
    },
    onError: (err: any) => {
      if (err.status === 422) {
        setShowOverrideDialog(true);
      } else if (err instanceof ConflictError) {
        setConflictMessage(err.message);
      } else {
        setActionError(err.message || "Failed to approve invoice");
      }
    },
  });

  // Validation issues lookup
  const issues = invoice?.validation_issues || [];
  const errorIssues = issues.filter((i: any) => i.severity === "error" && !i.resolved_by_override);
  const warningIssues = issues.filter((i: any) => i.severity === "warning");

  const getIssueForField = (field: string) => {
    return issues.find((i: any) => i.field === field);
  };

  const onApproveClick = () => {
    setActionError(null);
    if (errorIssues.length > 0) {
      setShowOverrideDialog(true);
    } else {
      approveMutation.mutate(undefined);
    }
  };

  // Keyboard Shortcuts Hook
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        // Only trigger Ctrl+Enter inside inputs
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          onApproveClick();
        }
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        onApproveClick();
      } else if (e.altKey && e.key === "ArrowRight") {
        e.preventDefault();
        navigateNext();
      } else if (e.altKey && e.key === "ArrowLeft") {
        e.preventDefault();
        navigatePrev();
      } else if (e.altKey && e.key === "r") {
        e.preventDefault();
        setShowRejectDialog(true);
      } else if (e.key === "?") {
        e.preventDefault();
        setShowShortcutsHelp(true);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center p-12 text-slate-500">
        <RefreshCw className="h-6 w-6 animate-spin mr-2" />
        <span>Loading invoice document and extractions...</span>
      </div>
    );
  }

  if (!isLoading && !invoice) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-500">
        <AlertCircle className="h-8 w-8 text-red-500 mb-2" />
        <p className="text-sm font-semibold">Invoice not found or could not be loaded.</p>
        <button
          onClick={() => navigate("/queue")}
          className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold"
        >
          Back to Queue
        </button>
      </div>
    );
  }

  const rawPages = invoice?.pages || [];
  const pageUrls = rawPages.map((p: any, idx: number) =>
    typeof p === "string" ? { page_number: idx + 1, url: p } : p
  );
  const currentPageImage =
    pageUrls.find((p: any) => p.page_number === activePage)?.url ||
    pageUrls[0]?.url ||
    "";

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-4rem)] overflow-hidden bg-slate-100">
      {/* Conflict Banner (409 Optimistic Locking) */}
      {conflictMessage && (
        <div className="bg-amber-600 text-white px-6 py-2.5 flex items-center justify-between text-sm shadow-md animate-bounce">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-5 w-5" />
            <span className="font-medium">{conflictMessage}</span>
          </div>
          <button
            onClick={() => {
              refetch();
              setConflictMessage(null);
            }}
            className="px-3 py-1 bg-white text-amber-800 rounded font-semibold text-xs hover:bg-amber-50"
          >
            Reload Latest Version
          </button>
        </div>
      )}

      {/* Top Action Bar */}
      <div className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate("/queue")}
            className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600"
            title="Back to queue"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="flex items-center space-x-3">
              <h2 className="text-base font-bold text-slate-900">
                {invoice?.normalized_invoice_number || "Invoice Review"}
              </h2>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${
                  invoice?.status === "APPROVED"
                    ? "bg-blue-100 text-blue-800"
                    : invoice?.status === "PUSHED"
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-amber-100 text-amber-800"
                }`}
              >
                {invoice?.status}
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono">
              ID: {id} • Version: {invoice?.row_version}
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setShowShortcutsHelp(true)}
            className="p-2 text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-100"
            title="Keyboard shortcuts (?)"
          >
            <HelpCircle className="h-4 w-4" />
          </button>

          <button
            onClick={() => {
              setShowAuditDrawer(true);
              refetchAudit();
            }}
            className="inline-flex items-center space-x-1 px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            <History className="h-3.5 w-3.5" />
            <span>Audit Trail</span>
          </button>

          <button
            onClick={() => setShowResendDialog(true)}
            className="px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            Request Resend
          </button>

          <button
            onClick={() => setShowRejectDialog(true)}
            className="px-3 py-1.5 border border-red-200 text-red-600 rounded-lg text-xs font-semibold hover:bg-red-50"
          >
            Reject
          </button>

          {isDirty && (
            <button
              onClick={handleSubmit((data) => saveMutation.mutate(data))}
              disabled={saveMutation.isPending}
              className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 bg-slate-900 text-white rounded-lg text-xs font-semibold hover:bg-slate-800 shadow-sm"
            >
              <Save className="h-3.5 w-3.5" />
              <span>Save Edits</span>
            </button>
          )}

          <button
            onClick={onApproveClick}
            disabled={approveMutation.isPending}
            className="inline-flex items-center space-x-1.5 px-4 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-bold hover:bg-emerald-700 shadow-md cursor-pointer"
          >
            <Check className="h-4 w-4" />
            <span>Approve & Push</span>
          </button>
        </div>
      </div>

      {/* Main Split Layout: Left Viewer | Right Form */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Pane: Document Viewer with Zoom/Pan/Rotate */}
        <div className="w-1/2 flex flex-col bg-slate-900 border-r border-slate-800 relative">
          <TransformWrapper
            initialScale={1}
            minScale={0.5}
            maxScale={4}
            centerOnInit
          >
            {({ zoomIn, zoomOut, resetTransform }) => (
              <>
                {/* Viewer Controls Floating Toolbar */}
                <div className="absolute top-4 left-4 z-20 flex items-center space-x-1.5 bg-slate-800/90 backdrop-blur-md px-3 py-1.5 rounded-xl border border-slate-700 text-white shadow-lg">
                  <div className="flex items-center space-x-2 text-xs">
                    <button
                      type="button"
                      onClick={() => zoomIn()}
                      className="p-1 hover:bg-slate-700 rounded text-slate-200 hover:text-white"
                      title="Zoom in"
                    >
                      <ZoomIn className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => zoomOut()}
                      className="p-1 hover:bg-slate-700 rounded text-slate-200 hover:text-white"
                      title="Zoom out"
                    >
                      <ZoomOut className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => resetTransform()}
                      className="p-1 hover:bg-slate-700 rounded text-slate-200 hover:text-white"
                      title="Reset view"
                    >
                      <Maximize2 className="h-4 w-4" />
                    </button>
                    <div className="h-4 w-px bg-slate-600 mx-1" />
                    <button
                      type="button"
                      onClick={() => setRotation((r) => (r + 90) % 360)}
                      className="p-1 hover:bg-slate-700 rounded text-slate-200 hover:text-white"
                      title="Rotate 90°"
                    >
                      <RotateCw className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Interactive Document Pan/Zoom Component */}
                <div className="flex-1 flex items-center justify-center overflow-hidden">
                  <TransformComponent
                    wrapperClass="!w-full !h-full"
                    contentClass="!w-full !h-full flex items-center justify-center"
                  >
                    {currentPageImage ? (
                      <img
                        src={currentPageImage}
                        alt={`Invoice page ${activePage}`}
                        style={{ transform: `rotate(${rotation}deg)` }}
                        className="max-h-full max-w-full object-contain shadow-2xl transition-transform duration-200 select-none"
                      />
                    ) : (
                      <div className="text-slate-500 text-sm">No page image available</div>
                    )}
                  </TransformComponent>
                </div>
              </>
            )}
          </TransformWrapper>

          {/* Bottom Page Thumbnail Switcher (R1 multi-page support) */}
          {pageUrls.length > 1 && (
            <div className="h-20 bg-slate-800/80 border-t border-slate-700 flex items-center px-4 space-x-3 overflow-x-auto">
              {pageUrls.map((p: any) => (
                <button
                  key={p.page_number}
                  onClick={() => setActivePage(p.page_number)}
                  className={`h-14 w-11 rounded border overflow-hidden shrink-0 transition-all ${
                    activePage === p.page_number
                      ? "border-indigo-500 ring-2 ring-indigo-400"
                      : "border-slate-600 opacity-60 hover:opacity-100"
                  }`}
                >
                  <img
                    src={p.url}
                    alt={`Thumbnail page ${p.page_number}`}
                    className="h-full w-full object-cover"
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right Pane: Editable Form & Issue Validation Panel */}
        <div className="w-1/2 flex flex-col bg-white overflow-y-auto">
          {/* Duplicate Banner (R3) */}
          {invoice?.dup_of_id && (
            <div className="bg-amber-50 border-b border-amber-200 p-4">
              <div className="flex items-start space-x-3">
                <Copy className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
                <div className="flex-1 text-sm text-amber-900">
                  <div className="font-bold">Duplicate Detected (R3 Layer 2)</div>
                  <p className="text-xs mt-0.5">
                    Matches invoice <strong>{invoice.duplicate_info?.invoice_number}</strong> from GSTIN{" "}
                    <strong>{invoice.duplicate_info?.supplier_gstin}</strong>.
                    {invoice.dup_overridden && (
                      <span className="block mt-1 font-semibold text-emerald-700">
                        ✓ Duplicate check overridden: {invoice.dup_override_reason}
                      </span>
                    )}
                  </p>
                  {!invoice.dup_overridden && (
                    <div className="mt-3 flex items-center space-x-2">
                      <button
                        onClick={async () => {
                          await apiRequest(`/api/v1/invoices/${id}/confirm-duplicate`, { method: "POST" });
                          queryClient.invalidateQueries({ queryKey: ["invoice-detail", id] });
                          navigateNext();
                        }}
                        className="px-3 py-1 bg-amber-700 hover:bg-amber-800 text-white rounded text-xs font-semibold"
                      >
                        Confirm Duplicate (Reject)
                      </button>
                      <button
                        onClick={() => setShowDuplicateOverrideDialog(true)}
                        className="px-3 py-1 bg-white border border-amber-300 text-amber-900 hover:bg-amber-100 rounded text-xs font-semibold"
                      >
                        Not a Duplicate (Override)
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Validation Issues Alert Banner */}
          {errorIssues.length > 0 && (
            <div className="bg-red-50 border-b border-red-200 p-4">
              <div className="flex items-start space-x-3">
                <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 shrink-0" />
                <div className="flex-1 text-sm text-red-900">
                  <div className="font-bold">
                    {errorIssues.length} Blocking Error{errorIssues.length > 1 ? "s" : ""}
                  </div>
                  <ul className="mt-1 list-disc list-inside text-xs space-y-0.5 text-red-800">
                    {errorIssues.map((iss: any) => (
                      <li key={iss.id}>
                        <strong>{iss.field || iss.code}:</strong> {iss.message}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Validation Warnings Alert Banner */}
          {warningIssues.length > 0 && (
            <div className="bg-amber-50 border-b border-amber-200 p-4">
              <div className="flex items-start space-x-3">
                <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
                <div className="flex-1 text-sm text-amber-900">
                  <div className="font-bold">
                    {warningIssues.length} Warning{warningIssues.length > 1 ? "s" : ""}
                  </div>
                  <ul className="mt-1 list-disc list-inside text-xs space-y-0.5 text-amber-800">
                    {warningIssues.map((iss: any) => (
                      <li key={iss.id}>
                        <strong>{iss.field || iss.code}:</strong> {iss.message}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Form */}
          <form className="p-6 space-y-6 flex-1">
            {/* Header Fields Section */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Invoice Number
                </label>
                <input
                  type="text"
                  {...register("invoice_number")}
                  className={`mt-1 block w-full px-3 py-2 text-sm border rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 font-semibold ${
                    getIssueForField("invoice_number")
                      ? "border-red-400 bg-red-50/50"
                      : "border-slate-200"
                  }`}
                />
                {errors.invoice_number && (
                  <p className="text-xs text-red-600 mt-1">{errors.invoice_number.message}</p>
                )}
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Invoice Date (YYYY-MM-DD)
                </label>
                <input
                  type="text"
                  {...register("invoice_date")}
                  className={`mt-1 block w-full px-3 py-2 text-sm border rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 ${
                    getIssueForField("invoice_date")
                      ? "border-red-400 bg-red-50/50"
                      : "border-slate-200"
                  }`}
                />
                {errors.invoice_date && (
                  <p className="text-xs text-red-600 mt-1">{errors.invoice_date.message}</p>
                )}
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Supplier Name
                </label>
                <input
                  type="text"
                  {...register("supplier_name")}
                  className={`mt-1 block w-full px-3 py-2 text-sm border rounded-lg outline-none focus:ring-2 focus:ring-indigo-500 ${
                    getIssueForField("supplier_name")
                      ? "border-amber-400 bg-amber-50/50"
                      : "border-slate-200"
                  }`}
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Supplier GSTIN
                </label>
                <input
                  type="text"
                  {...register("supplier_gstin")}
                  className={`mt-1 block w-full px-3 py-2 text-sm border rounded-lg font-mono font-medium outline-none focus:ring-2 focus:ring-indigo-500 ${
                    getIssueForField("supplier_gstin")
                      ? "border-red-400 bg-red-50/50"
                      : "border-slate-200"
                  }`}
                />
                {errors.supplier_gstin && (
                  <p className="text-xs text-red-600 mt-1">{errors.supplier_gstin.message}</p>
                )}
              </div>
            </div>

            {/* Line Items Table */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Line Items ({fields.length})
                </h3>
                <button
                  type="button"
                  onClick={() => append({ description: "", quantity: "1", rate: "0", amount: "0.00" })}
                  className="inline-flex items-center space-x-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Add Line</span>
                </button>
              </div>

              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs text-slate-600">
                  <thead className="bg-slate-50 font-semibold text-slate-500 border-b border-slate-200">
                    <tr>
                      <th className="px-3 py-2">Description</th>
                      <th className="px-2 py-2 w-20">Qty</th>
                      <th className="px-2 py-2 w-24">Rate</th>
                      <th className="px-3 py-2 w-28">Amount</th>
                      <th className="px-2 py-2 w-10 text-center"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {fields.map((field, idx) => (
                      <tr key={field.id} className="hover:bg-slate-50/50">
                        <td className="px-3 py-1.5">
                          <input
                            type="text"
                            {...register(`line_items.${idx}.description`)}
                            className="w-full px-2 py-1 text-xs border border-transparent hover:border-slate-200 focus:border-indigo-500 rounded outline-none"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <input
                            type="text"
                            {...register(`line_items.${idx}.quantity`)}
                            className="w-full px-2 py-1 text-xs border border-transparent hover:border-slate-200 focus:border-indigo-500 rounded outline-none text-right"
                          />
                        </td>
                        <td className="px-2 py-1.5">
                          <input
                            type="text"
                            {...register(`line_items.${idx}.rate`)}
                            className="w-full px-2 py-1 text-xs border border-transparent hover:border-slate-200 focus:border-indigo-500 rounded outline-none text-right font-mono"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <input
                            type="text"
                            {...register(`line_items.${idx}.amount`)}
                            className="w-full px-2 py-1 text-xs border border-transparent hover:border-slate-200 focus:border-indigo-500 rounded outline-none text-right font-mono font-medium"
                          />
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          <button
                            type="button"
                            onClick={() => remove(idx)}
                            className="p-1 text-slate-400 hover:text-red-600 rounded"
                            title="Remove row"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Tax Breakdown & Live Total Recalculation (decimal.js) */}
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-3">
              <div className="grid grid-cols-4 gap-3 text-xs">
                <div>
                  <label className="text-slate-500 font-medium">Taxable Value</label>
                  <input
                    type="text"
                    {...register("taxable_value")}
                    className="mt-1 w-full px-2.5 py-1.5 border border-slate-200 rounded font-mono text-right"
                  />
                </div>
                <div>
                  <label className="text-slate-500 font-medium">CGST</label>
                  <input
                    type="text"
                    {...register("cgst")}
                    className="mt-1 w-full px-2.5 py-1.5 border border-slate-200 rounded font-mono text-right"
                  />
                </div>
                <div>
                  <label className="text-slate-500 font-medium">SGST</label>
                  <input
                    type="text"
                    {...register("sgst")}
                    className="mt-1 w-full px-2.5 py-1.5 border border-slate-200 rounded font-mono text-right"
                  />
                </div>
                <div>
                  <label className="text-slate-500 font-medium">IGST</label>
                  <input
                    type="text"
                    {...register("igst")}
                    className="mt-1 w-full px-2.5 py-1.5 border border-slate-200 rounded font-mono text-right"
                  />
                </div>
              </div>

              {/* Total & Match Indicator */}
              <div className="pt-3 border-t border-slate-200 flex items-center justify-between">
                <div>
                  <div className="text-xs text-slate-500 font-medium">Calculated Sum (Lines + Tax)</div>
                  <div className="text-base font-bold font-mono text-slate-800">
                    ₹{calculatedTotal}
                  </div>
                </div>

                <div className="flex items-center space-x-3">
                  <div className="text-right">
                    <label className="text-xs font-bold text-slate-700">Invoice Total</label>
                    <input
                      type="text"
                      {...register("total")}
                      className="mt-0.5 px-3 py-1.5 border border-slate-300 rounded font-mono font-bold text-right text-base w-36 outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>

                  <div className="mt-4">
                    {totalMatches ? (
                      <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300">
                        <Check className="h-3.5 w-3.5" />
                        <span>Matches</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800 border border-red-300">
                        <X className="h-3.5 w-3.5" />
                        <span>Mismatch</span>
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Override Reason Dialog for Blocking Errors (R2 guarantee) */}
      {showOverrideDialog && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center space-x-3 text-red-600">
              <AlertCircle className="h-6 w-6" />
              <h3 className="text-lg font-bold text-slate-900">Approve with Remaining Errors</h3>
            </div>
            <p className="text-xs text-slate-600">
              This invoice has unresolved validation errors. R2 policy requires an audit override reason (at least 10 characters) to push to accounting.
            </p>
            <textarea
              rows={3}
              placeholder="e.g., Verified difference against revised credit note received via email..."
              value={dialogReason}
              onChange={(e) => setDialogReason(e.target.value)}
              className="w-full p-3 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-red-500"
            />
            {actionError && <p className="text-xs text-red-600">{actionError}</p>}
            <div className="flex justify-end space-x-3">
              <button
                onClick={() => {
                  setShowOverrideDialog(false);
                  setDialogReason("");
                }}
                className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                disabled={dialogReason.trim().length < 10}
                onClick={() => {
                  approveMutation.mutate(dialogReason.trim());
                  setShowOverrideDialog(false);
                  setDialogReason("");
                }}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold disabled:opacity-50"
              >
                Confirm Override & Approve
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Reason Dialog */}
      {showRejectDialog && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <h3 className="text-lg font-bold text-slate-900">Reject Invoice</h3>
            <p className="text-xs text-slate-600">
              Please enter the reason for rejection (mandatory for accounts audit trail).
            </p>
            <textarea
              rows={3}
              placeholder="Reason for rejection..."
              value={dialogReason}
              onChange={(e) => setDialogReason(e.target.value)}
              className="w-full p-3 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <div className="flex justify-end space-x-3">
              <button
                onClick={() => {
                  setShowRejectDialog(false);
                  setDialogReason("");
                }}
                className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                disabled={dialogReason.trim().length < 3}
                onClick={async () => {
                  await apiRequest(`/api/v1/invoices/${id}/reject`, {
                    method: "POST",
                    body: JSON.stringify({ reason: dialogReason.trim() }),
                  });
                  queryClient.invalidateQueries({ queryKey: ["invoices-queue"] });
                  setShowRejectDialog(false);
                  navigateNext();
                }}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold disabled:opacity-50"
              >
                Reject Invoice
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Request Resend Dialog */}
      {showResendDialog && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <h3 className="text-lg font-bold text-slate-900">Request Resend</h3>
            <p className="text-xs text-slate-600">
              Request the supplier to re-send this invoice (e.g., blurry image, missing pages, or unreadable fields).
            </p>
            <textarea
              rows={3}
              placeholder="Reason for requesting resend..."
              value={dialogReason}
              onChange={(e) => setDialogReason(e.target.value)}
              className="w-full p-3 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <div className="flex justify-end space-x-3">
              <button
                onClick={() => {
                  setShowResendDialog(false);
                  setDialogReason("");
                }}
                className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                disabled={dialogReason.trim().length < 3}
                onClick={async () => {
                  await apiRequest(`/api/v1/invoices/${id}/request-resend`, {
                    method: "POST",
                    body: JSON.stringify({ reason: dialogReason.trim() }),
                  });
                  queryClient.invalidateQueries({ queryKey: ["invoices-queue"] });
                  setShowResendDialog(false);
                  navigateNext();
                }}
                className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold disabled:opacity-50"
              >
                Request Resend
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Duplicate Override Dialog */}
      {showDuplicateOverrideDialog && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <h3 className="text-lg font-bold text-slate-900">Override Duplicate Flag</h3>
            <p className="text-xs text-slate-600">
              Explain why this invoice is legitimate despite matching an existing business key (e.g., replacement invoice or supplementary billing).
            </p>
            <textarea
              rows={3}
              placeholder="Mandatory reason for override..."
              value={dialogReason}
              onChange={(e) => setDialogReason(e.target.value)}
              className="w-full p-3 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <div className="flex justify-end space-x-3">
              <button
                onClick={() => {
                  setShowDuplicateOverrideDialog(false);
                  setDialogReason("");
                }}
                className="px-4 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                disabled={dialogReason.trim().length < 3}
                onClick={async () => {
                  await apiRequest(`/api/v1/invoices/${id}/override-duplicate`, {
                    method: "POST",
                    body: JSON.stringify({ reason: dialogReason.trim() }),
                  });
                  queryClient.invalidateQueries({ queryKey: ["invoice-detail", id] });
                  setShowDuplicateOverrideDialog(false);
                  setDialogReason("");
                }}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold disabled:opacity-50"
              >
                Save Override
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Keyboard Shortcuts Dialog */}
      {showShortcutsHelp && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-sm w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-base">Keyboard Shortcuts</h3>
              <button
                onClick={() => setShowShortcutsHelp(false)}
                className="p-1 hover:bg-slate-100 rounded text-slate-500"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="divide-y divide-slate-100 text-xs">
              <div className="py-2 flex justify-between">
                <span className="text-slate-600">Approve & Push</span>
                <kbd className="px-2 py-0.5 bg-slate-100 rounded font-mono font-bold">Ctrl + Enter</kbd>
              </div>
              <div className="py-2 flex justify-between">
                <span className="text-slate-600">Next Invoice</span>
                <kbd className="px-2 py-0.5 bg-slate-100 rounded font-mono font-bold">Alt + →</kbd>
              </div>
              <div className="py-2 flex justify-between">
                <span className="text-slate-600">Previous Invoice</span>
                <kbd className="px-2 py-0.5 bg-slate-100 rounded font-mono font-bold">Alt + ←</kbd>
              </div>
              <div className="py-2 flex justify-between">
                <span className="text-slate-600">Reject Invoice</span>
                <kbd className="px-2 py-0.5 bg-slate-100 rounded font-mono font-bold">Alt + R</kbd>
              </div>
              <div className="py-2 flex justify-between">
                <span className="text-slate-600">Help / Shortcuts</span>
                <kbd className="px-2 py-0.5 bg-slate-100 rounded font-mono font-bold">?</kbd>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Audit Trail Drawer (Right Slide-over) */}
      {showAuditDrawer && (
        <div className="fixed inset-0 z-50 bg-slate-900/30 backdrop-blur-xs flex justify-end">
          <div className="bg-white w-96 h-full shadow-2xl border-l border-slate-200 p-6 flex flex-col">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-900 text-base">Audit Trail</h3>
              <button
                onClick={() => setShowAuditDrawer(false)}
                className="p-1 hover:bg-slate-100 rounded text-slate-500"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto py-4 space-y-4">
              {(auditTrail || []).map((ev: any) => (
                <div key={ev.id} className="text-xs border-l-2 border-indigo-500 pl-3 py-1 space-y-1">
                  <div className="flex justify-between items-center text-slate-400">
                    <span className="font-bold text-slate-700 uppercase tracking-wider">{ev.action}</span>
                    <span>{new Date(ev.created_at).toLocaleTimeString()}</span>
                  </div>
                  <div className="text-slate-600 font-mono text-[11px] bg-slate-50 p-2 rounded">
                    {JSON.stringify(ev.payload, null, 2)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
