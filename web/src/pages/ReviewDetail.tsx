import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import Decimal from "decimal.js";
import { apiRequest, ConflictError } from "@/lib/api";
import { maskSender } from "@/lib/mask";
import { StatusPill } from "@/components/StatusPill";
import { AuditTrailFlowchart } from "@/components/AuditTrailFlowchart";
import { DocumentViewer } from "@/components/DocumentViewer";
import {
  Check,
  X,
  AlertTriangle,
  AlertCircle,
  Copy,
  History,
  ChevronLeft,
  HelpCircle,
  Plus,
  Trash2,
  Save,
  RefreshCw,
  FileUp,
  RotateCcw,
  Split,
  Mail,
  MessageSquare,
  Upload,
  CheckCircle2,
  XCircle,
  Loader2,
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
  const [wideDocumentMode, setWideDocumentMode] = useState(false);
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
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "EXTRACTING" || status === "UPLOADED" || status === "PUSHING"
        ? 2000
        : false;
    },
  });

  // 2. Fetch Review Queue for next/prev navigation
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

  // Setup React Hook Form
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


  // Split Pages Mutation (R1 multi-page grouped documents)
  const splitPagesMutation = useMutation({
    mutationFn: () => {
      return apiRequest(`/api/v1/invoices/${id}/split-pages`, {
        method: "POST",
      });
    },
    onSuccess: (data: any) => {
      alert(data.message || "Invoice split successfully");
      queryClient.invalidateQueries({ queryKey: ["invoice-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["invoices-queue"] });
      navigate("/queue");
    },
    onError: (err: any) => {
      alert(err.message || "Failed to split pages");
    },
  });

  // Claim takeover mutation (R4 review leases)
  const takeoverMutation = useMutation({
    mutationFn: () => {
      return apiRequest(`/api/v1/invoices/${id}/takeover`, {
        method: "POST",
      });
    },
    onSuccess: () => {
      setConflictMessage(null);
      refetch();
    },
    onError: (err: any) => {
      setActionError(err.message || "Failed to take over review lease");
    },
  });

  // Review lease heartbeat & release (R4)
  useEffect(() => {
    if (!id) return;
    const heartbeatInterval = setInterval(async () => {
      if (document.hidden) return;
      try {
        const res = await apiRequest(`/api/v1/invoices/${id}/heartbeat`, { method: "POST" });
        if (res && res.status === "not_claimed_by_user") {
          setConflictMessage("Your review lease was taken over by another reviewer.");
          refetch();
        }
      } catch {
        // Ignored
      }
    }, 45000);

    const handleBeforeUnload = () => {
      navigator.sendBeacon?.(`/api/v1/invoices/${id}/release`);
    };
    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      clearInterval(heartbeatInterval);
      window.removeEventListener("beforeunload", handleBeforeUnload);
      apiRequest(`/api/v1/invoices/${id}/release`, { method: "POST" }).catch(() => {});
    };
  }, [id, refetch]);

  // Populate form with fetched invoice extractions (supporting both current_extraction and direct fields)
  useEffect(() => {
    if (invoice) {
      const ext = invoice.current_extraction || invoice;
      reset({
        invoice_number: ext.invoice_number || ext.normalized_invoice_number || "",
        invoice_date: ext.invoice_date || ext.normalized_invoice_date || "",
        supplier_name: ext.supplier_name || "",
        supplier_gstin: ext.supplier_gstin || "",
        taxable_value: ext.taxable_value != null ? String(ext.taxable_value) : "",
        cgst: ext.cgst != null ? String(ext.cgst) : "",
        sgst: ext.sgst != null ? String(ext.sgst) : "",
        igst: ext.igst != null ? String(ext.igst) : "",
        total: ext.total != null ? String(ext.total) : ext.total_amount != null ? String(ext.total_amount) : "",
        line_items: (ext.line_items || []).map((li: any) => ({
          description: li.description || "",
          quantity: li.quantity != null ? String(li.quantity) : "",
          rate: li.rate != null ? String(li.rate) : "",
          amount: li.amount != null ? String(li.amount) : "",
        })),
      });
      setConflictMessage(null);
    }
  }, [invoice, reset]);

  // Real-time Decimal.js calculations for line totals and tax reconciliation
  const watchedLines = watch("line_items");
  const watchedCgst = watch("cgst");
  const watchedSgst = watch("sgst");
  const watchedIgst = watch("igst");
  const watchedTotal = watch("total");

  const calculatedTotal = useMemo(() => {
    try {
      let linesSum = new Decimal(0);
      for (const item of watchedLines || []) {
        if (item.amount && !isNaN(Number(item.amount))) {
          linesSum = linesSum.plus(new Decimal(item.amount));
        }
      }
      const c = watchedCgst && !isNaN(Number(watchedCgst)) ? new Decimal(watchedCgst) : new Decimal(0);
      const s = watchedSgst && !isNaN(Number(watchedSgst)) ? new Decimal(watchedSgst) : new Decimal(0);
      const i = watchedIgst && !isNaN(Number(watchedIgst)) ? new Decimal(watchedIgst) : new Decimal(0);

      return linesSum.plus(c).plus(s).plus(i).toFixed(2);
    } catch {
      return "0.00";
    }
  }, [watchedLines, watchedCgst, watchedSgst, watchedIgst]);

  const totalStatus = useMemo(() => {
    try {
      if (!watchedTotal) return { status: "missing", text: "Missing", diff: new Decimal(0) };
      const t1 = new Decimal(watchedTotal);
      const t2 = new Decimal(calculatedTotal);
      const diff = t1.minus(t2).abs();
      if (diff.isZero() || diff.lessThanOrEqualTo(1.0)) {
        return { status: "exact", text: "Matches", diff };
      }
      return { status: "mismatch", text: `Mismatch (₹${diff.toFixed(2)})`, diff };
    } catch {
      return { status: "invalid", text: "Invalid", diff: new Decimal(0) };
    }
  }, [watchedTotal, calculatedTotal]);

  const totalMatches = totalStatus.status === "exact";

  // Find next invoice in queue
  const queueItems = queueData?.items || [];
  const currentIndex = queueItems.findIndex((item: any) => item.id === id);
  const nextInvoiceId = currentIndex >= 0 && currentIndex < queueItems.length - 1 ? queueItems[currentIndex + 1].id : null;
  const prevInvoiceId = currentIndex > 0 ? queueItems[currentIndex - 1].id : null;

  const navigateNext = useCallback(() => {
    if (nextInvoiceId) {
      navigate(`/invoices/${nextInvoiceId}`);
    } else {
      navigate("/queue");
    }
  }, [nextInvoiceId, navigate]);

  const navigatePrev = useCallback(() => {
    if (prevInvoiceId) {
      navigate(`/invoices/${prevInvoiceId}`);
    }
  }, [prevInvoiceId, navigate]);

  // Save Edits Mutation
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
    onSuccess: (updated) => {
      queryClient.setQueryData(["invoice-detail", id], updated);
      queryClient.invalidateQueries({ queryKey: ["invoices-queue"] });
      setConflictMessage(null);
    },
    onError: (err: any) => {
      if (err instanceof ConflictError) {
        setConflictMessage(
          "Another reviewer updated this invoice while you were reviewing. Please reload to see their changes."
        );
      } else {
        alert(err.message || "Failed to save edits");
      }
    },
  });

  // Approve & Push Mutation
  const approveMutation = useMutation({
    mutationFn: async (overrideReason?: string) => {
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
      queryClient.invalidateQueries({ queryKey: ["invoice", id] });
      queryClient.invalidateQueries({ queryKey: ["audit-trail", id] });
      navigateNext();
    },
    onError: (err: any) => {
      if (err instanceof ConflictError) {
        setConflictMessage(
          "Another reviewer modified this invoice. Please refresh and review the updated version."
        );
      } else {
        setActionError(err.message || "Approval failed");
      }
    },
  });

  // Upload Replacement Document Mutation
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadReplacementMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiRequest(`/api/v1/invoices/${id}/upload-replacement`, {
        method: "POST",
        body: formData,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoice-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["invoices-queue"] });
      queryClient.invalidateQueries({ queryKey: ["invoices-queue-nav"] });
      queryClient.invalidateQueries({ queryKey: ["invoice-audit", id] });
      setTimeout(() => {
        refetch();
      }, 1000);
    },
    onError: (err: any) => {
      alert(err.message || "Failed to upload replacement document");
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadReplacementMutation.mutate(file);
      e.target.value = "";
    }
  };

  // Cancel Resend Mutation
  const cancelResendMutation = useMutation({
    mutationFn: () => {
      return apiRequest(`/api/v1/invoices/${id}/cancel-resend`, {
        method: "POST",
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoice-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["invoices-queue"] });
      queryClient.invalidateQueries({ queryKey: ["invoice-audit", id] });
    },
    onError: (err: any) => {
      alert(err.message || "Failed to cancel resend request");
    },
  });

  // Validation Issues extraction
  const issues = invoice?.validation_issues || [];
  const errorIssues = issues.filter(
    (i: any) => i.severity?.toUpperCase() === "ERROR"
  );
  const warningIssues = issues.filter(
    (i: any) => i.severity?.toUpperCase() === "WARNING"
  );

  const getIssueForField = (fieldName: string) => {
    return issues.find((i: any) => i.field === fieldName);
  };

  const onApproveClick = () => {
    if (errorIssues.length > 0) {
      setShowOverrideDialog(true);
    } else {
      approveMutation.mutate(undefined);
    }
  };

  // Keyboard shortcut listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      ) {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          if (invoice?.status === "NEEDS_REVIEW") {
            onApproveClick();
          }
        }
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        if (invoice?.status === "NEEDS_REVIEW") {
          e.preventDefault();
          onApproveClick();
        }
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
      <div className="flex-1 flex items-center justify-center p-12 text-findeck-muted">
        <RefreshCw className="h-5 w-5 animate-spin mr-2 text-success-strong" />
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

  const rawPages: any[] = (invoice?.page_image_urls || []).concat(invoice?.pages || []);
  const pageUrls: { page_number: number; url: string }[] = rawPages.map((p: any, idx: number) => {
    if (typeof p === "string") {
      return { page_number: idx + 1, url: p };
    }
    return {
      page_number: p.page_number ?? idx + 1,
      url: p.url || "",
    };
  });

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-4rem)] max-h-[calc(100vh-4rem)] min-h-0 overflow-hidden bg-findeck-app font-sans">
      {/* Conflict Banner (409 Optimistic Locking) */}
      {conflictMessage && (
        <div className="bg-amber-600 text-white px-6 py-2.5 flex items-center justify-between text-sm shadow-xs animate-bounce shrink-0">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-5 w-5" />
            <span className="font-medium">{conflictMessage}</span>
          </div>
          <button
            onClick={() => {
              refetch();
              setConflictMessage(null);
            }}
            className="px-3 py-1 bg-white text-warning-strong rounded-btn font-semibold text-xs hover:bg-amber-50"
          >
            Reload Latest Version
          </button>
        </div>
      )}

      {/* Top Action Bar */}
      <div className="bg-white border-b border-findeck-border px-6 py-3 flex items-center justify-between shadow-xs shrink-0">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate("/queue")}
            className="p-1.5 rounded-btn border border-findeck-border hover:bg-findeck-bg-sidebar text-findeck-text transition-colors"
            title="Back to queue"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="flex items-center space-x-3">
              <h2 className="text-16 font-bold text-findeck-text">
                {invoice?.normalized_invoice_number || invoice?.current_extraction?.invoice_number || "Invoice Review"}
              </h2>
              <StatusPill status={invoice?.status || ""} />
            </div>
            
            <div className="flex items-center space-x-2 mt-1">
              <span className="text-[11px] text-findeck-muted font-mono">
                ID: {id} • Version: {invoice?.row_version}
              </span>
              {invoice?.channel && (
                <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-accent-soft text-accent-strong">
                  {invoice.channel === "email" ? <Mail className="h-3 w-3" /> : invoice.channel === "whatsapp" ? <MessageSquare className="h-3 w-3" /> : <Upload className="h-3 w-3" />}
                  <span className="capitalize">{invoice.channel}</span>
                  {invoice.sender && <span>: {maskSender(invoice.sender, invoice.channel)}</span>}
                </span>
              )}
              {invoice?.original_filename && (
                <span className="text-[11px] text-findeck-muted font-mono truncate max-w-[200px]" title={invoice.original_filename}>
                  • {invoice.original_filename}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-2.5">
          <button
            onClick={() => setShowShortcutsHelp(true)}
            className="p-2 text-findeck-muted hover:text-findeck-text rounded-btn hover:bg-findeck-bg-sidebar transition-colors"
            title="Keyboard shortcuts (?)"
          >
            <HelpCircle className="h-4 w-4" />
          </button>

          <button
            onClick={() => {
              setShowAuditDrawer(true);
              refetchAudit();
            }}
            className="inline-flex items-center space-x-1 px-3 py-1.5 border border-findeck-border bg-white rounded-btn text-xs font-semibold text-findeck-text hover:bg-findeck-app transition-colors cursor-pointer"
          >
            <History className="h-3.5 w-3.5" />
            <span>Audit Trail</span>
          </button>

          {invoice?.page_count > 1 && (
            <button
              onClick={() => splitPagesMutation.mutate()}
              disabled={splitPagesMutation.isPending || invoice?.is_claim_locked}
              className="inline-flex items-center space-x-1 px-3 py-1.5 border border-findeck-border bg-white rounded-btn text-xs font-semibold text-findeck-text hover:bg-findeck-app transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              title="Split multi-page invoice into individual invoices"
            >
              <Split className="h-3.5 w-3.5" />
              <span>Split Pages</span>
            </button>
          )}

          {invoice?.status === "RESEND_REQUESTED" ? (
            <div
              className="flex items-center space-x-2 text-xs font-semibold px-3 py-1.5 rounded-btn border"
              style={{
                backgroundColor: "var(--accent-soft)",
                borderColor: "var(--accent)",
                color: "var(--accent-strong)",
              }}
            >
              <RotateCcw className="h-3.5 w-3.5" style={{ color: "var(--accent-strong)" }} />
              <span>Awaiting Replacement</span>
            </div>
          ) : invoice?.status === "APPROVED" || invoice?.status === "PUSHING" ? (
            <div className="flex items-center space-x-2 text-xs font-semibold text-sky-800 bg-sky-50 px-3 py-1.5 rounded-btn border border-sky-200/60">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-600" />
              <span>Dispatching to accounting ledger...</span>
            </div>
          ) : invoice?.status === "PUSHED" ? (
            <div className="flex items-center space-x-2 text-xs font-semibold text-findeck-pill-up-text bg-findeck-pill-up-bg px-3 py-1.5 rounded-btn border border-emerald-200/60">
              <CheckCircle2 className="h-3.5 w-3.5 text-success-strong" />
              <span>Pushed to Accounting</span>
              {invoice?.accounting_id && (
                <span className="font-mono text-11 font-bold text-emerald-800 bg-emerald-100/70 px-1.5 py-0.5 rounded">
                  {invoice.accounting_id}
                </span>
              )}
            </div>
          ) : invoice?.status === "REJECTED" || invoice?.status === "REJECTED_DUPLICATE" ? (
            <div className="flex items-center space-x-2 text-xs font-semibold text-danger-strong bg-rose-50 px-3 py-1.5 rounded-btn border border-rose-200/60">
              <XCircle className="h-3.5 w-3.5 text-danger-strong" />
              <span>{invoice?.status === "REJECTED_DUPLICATE" ? "Duplicate Rejected" : "Invoice Rejected"}</span>
            </div>
          ) : (
            <>
              {invoice?.status === "NEEDS_REVIEW" && (
                <>
                  <button
                    onClick={() => setShowResendDialog(true)}
                    disabled={invoice?.is_claim_locked}
                    className="px-3 py-1.5 rounded-btn text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed" style={{ backgroundColor: "var(--bg-inset)", border: "1px solid var(--border)", color: "var(--ink)" }}
                  >
                    Request Resend
                  </button>

                  <button
                    onClick={() => setShowRejectDialog(true)}
                    disabled={invoice?.is_claim_locked}
                    className="px-3 py-1.5 border border-danger/30 text-danger-strong bg-danger-soft rounded-btn text-xs font-semibold hover:bg-danger/20 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Reject
                  </button>
                </>
              )}

              {isDirty && invoice?.status === "NEEDS_REVIEW" && (
                <button
                  onClick={handleSubmit((data) => saveMutation.mutate(data))}
                  disabled={saveMutation.isPending || invoice?.is_claim_locked}
                  className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 bg-ink text-white rounded-btn text-xs font-semibold hover:bg-ink-hover transition-colors shadow-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Save className="h-3.5 w-3.5" />
                  <span>Save Edits</span>
                </button>
              )}

              {invoice?.status === "NEEDS_REVIEW" && (
                <button
                  onClick={onApproveClick}
                  disabled={approveMutation.isPending || invoice?.is_claim_locked}
                  className="inline-flex items-center space-x-1.5 px-4 py-1.5 bg-ink hover:bg-ink-hover text-white rounded-btn text-xs font-semibold shadow-xs transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Check className="h-4 w-4" />
                  <span>Approve & Push</span>
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Review Lease Claim Banner (R4) */}
      {invoice?.is_claim_locked && (
        <div
          className="border-b px-6 py-2.5 flex items-center justify-between shadow-2xs shrink-0"
          style={{
            backgroundColor: "var(--accent-soft)",
            borderColor: "rgba(155, 161, 249, 0.4)",
            color: "var(--ink)",
          }}
        >
          <div className="flex items-center space-x-2.5 text-xs font-medium">
            <AlertCircle className="h-4 w-4 shrink-0" style={{ color: "var(--accent-strong)" }} />
            <span>
              Being reviewed by <strong>{invoice.claimed_by_email || "another reviewer"}</strong>. Editing and approval actions are currently locked.
            </span>
          </div>
          <button
            onClick={() => takeoverMutation.mutate()}
            disabled={takeoverMutation.isPending}
            className="px-3 py-1 rounded-btn text-xs font-semibold cursor-pointer border shadow-xs transition-colors"
            style={{
              backgroundColor: "var(--ink)",
              color: "#FFFFFF",
              borderColor: "transparent",
            }}
          >
            {takeoverMutation.isPending ? "Taking over..." : "Take over review"}
          </button>
        </div>
      )}

      {/* Resend Requested Banner */}
      {invoice?.status === "RESEND_REQUESTED" && (
        <div
          className="border-b px-6 py-3 flex items-center justify-between shadow-2xs shrink-0"
          style={{
            backgroundColor: "var(--accent-soft)",
            borderColor: "rgba(155, 161, 249, 0.4)",
          }}
        >
          <div className="flex items-center space-x-3">
            <div
              className="w-8 h-8 rounded-btn flex items-center justify-center shrink-0"
              style={{
                backgroundColor: "var(--accent)",
                color: "var(--ink)",
              }}
            >
              <RotateCcw className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span
                  className="text-xs font-bold uppercase tracking-wide"
                  style={{ color: "var(--accent-strong)" }}
                >
                  Resend Requested
                </span>
                <span className="text-xs" style={{ color: "var(--accent-strong)" }}>
                  — Awaiting replacement document from supplier
                </span>
              </div>
              <p className="text-xs font-medium mt-0.5" style={{ color: "var(--accent-strong)" }}>
                <span className="font-semibold">Reason:</span>{" "}
                {invoice?.status_reason || "Document requires resubmission."}
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadReplacementMutation.isPending}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-ink text-white rounded-btn text-xs font-semibold hover:bg-ink-hover shadow-xs transition-colors cursor-pointer"
            >
              {uploadReplacementMutation.isPending ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  <span>Uploading & Processing...</span>
                </>
              ) : (
                <>
                  <FileUp className="h-3.5 w-3.5" />
                  <span>Upload Replacement File</span>
                </>
              )}
            </button>
            <button
              onClick={() => cancelResendMutation.mutate()}
              disabled={cancelResendMutation.isPending}
              className="px-3 py-1.5 border rounded-btn text-xs font-semibold transition-colors cursor-pointer"
              style={{
                backgroundColor: "var(--bg-inset)",
                borderColor: "var(--border)",
                color: "var(--text)",
              }}
            >
              Cancel Resend
            </button>
          </div>
        </div>
      )}

      {/* Hidden File Input for Replacement Document */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.webp,.heic"
        onChange={handleFileChange}
        className="hidden"
      />

      {/* Main Split Layout: Left Viewer Card | Right Form Card */}
      <div className="flex-1 h-full min-h-0 flex overflow-hidden p-4 gap-4">
        {/* Left Card: Document Viewer */}
        <div
          className={`${
            wideDocumentMode ? "w-[62%]" : "w-1/2"
          } h-full min-h-0 flex flex-col transition-all duration-200 shrink-0 bg-white rounded-card border border-findeck-border shadow-xs overflow-hidden`}
        >
          <DocumentViewer
            pages={pageUrls}
            activePage={activePage}
            onPageChange={setActivePage}
            wideMode={wideDocumentMode}
            onToggleWideMode={() => setWideDocumentMode(!wideDocumentMode)}
            filename={invoice?.original_filename || invoice?.normalized_invoice_number}
          />
        </div>

        {/* Right Card: Editable Form & Issue Validation Panel */}
        <div className="flex-1 h-full min-h-0 bg-white rounded-card border border-findeck-border shadow-xs overflow-y-auto">
          {/* Duplicate Banner (R3) */}
          {invoice?.dup_of_id && (
            <div className="p-4 border-b" style={{ backgroundColor: "var(--warning-soft)", borderColor: "var(--warning)", color: "var(--warning-strong)" }}>
              <div className="flex items-start space-x-3">
                <Copy className="h-5 w-5 text-warning-strong mt-0.5 shrink-0" />
                <div className="flex-1 text-sm text-warning-strong">
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
                        className="px-3 py-1 bg-amber-700 hover:bg-amber-800 text-white rounded-btn text-xs font-semibold cursor-pointer"
                      >
                        Confirm Duplicate (Reject)
                      </button>
                      <button
                        onClick={() => setShowDuplicateOverrideDialog(true)}
                        className="px-3 py-1 bg-white border border-amber-300 text-warning-strong hover:bg-amber-100 rounded-btn text-xs font-semibold cursor-pointer"
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
            <div className="p-4 border-b" style={{ backgroundColor: "var(--danger-soft)", borderColor: "var(--danger)", color: "var(--danger-strong)" }}>
              <div className="flex items-start space-x-3">
                <AlertCircle className="h-5 w-5 text-danger-strong mt-0.5 shrink-0" />
                <div className="flex-1 text-sm text-danger-strong">
                  <div className="font-bold">
                    {errorIssues.length} Blocking Error{errorIssues.length > 1 ? "s" : ""}
                  </div>
                  <ul className="mt-1 list-disc list-inside text-xs space-y-0.5 text-danger-strong">
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
            <div className="p-4 border-b" style={{ backgroundColor: "var(--warning-soft)", borderColor: "var(--warning)", color: "var(--warning-strong)" }}>
              <div className="flex items-start space-x-3">
                <AlertTriangle className="h-5 w-5 text-warning-strong mt-0.5 shrink-0" />
                <div className="flex-1 text-sm text-warning-strong">
                  <div className="font-bold">
                    {warningIssues.length} Warning{warningIssues.length > 1 ? "s" : ""}
                  </div>
                  <ul className="mt-1 list-disc list-inside text-xs space-y-0.5 text-warning-strong">
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
          <form className="p-6 space-y-6">
            {/* Header Fields Section */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-findeck-text uppercase tracking-wider">
                  Invoice Number
                </label>
                <input
                  type="text"
                  {...register("invoice_number")}
                  className={`mt-1 block w-full px-3 py-2 text-sm border rounded-btn outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong font-semibold text-findeck-text ${
                    getIssueForField("invoice_number")
                      ? "border-danger-strong bg-danger-soft/40"
                      : "border-findeck-border"
                  }`}
                />
                {errors.invoice_number && (
                  <p className="text-xs text-danger-strong mt-1">{errors.invoice_number.message}</p>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-findeck-text uppercase tracking-wider">
                  Invoice Date (YYYY-MM-DD)
                </label>
                <input
                  type="text"
                  {...register("invoice_date")}
                  className={`mt-1 block w-full px-3 py-2 text-sm border rounded-btn outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text ${
                    getIssueForField("invoice_date")
                      ? "border-danger-strong bg-danger-soft/40"
                      : "border-findeck-border"
                  }`}
                />
                {errors.invoice_date && (
                  <p className="text-xs text-danger-strong mt-1">{errors.invoice_date.message}</p>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-findeck-text uppercase tracking-wider">
                  Supplier Name
                </label>
                <input
                  type="text"
                  {...register("supplier_name")}
                  className={`mt-1 block w-full px-3 py-2 text-sm border rounded-btn outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text ${
                    getIssueForField("supplier_name")
                      ? "border-warning-strong bg-warning-soft/40"
                      : "border-findeck-border"
                  }`}
                />
                {errors.supplier_name && (
                  <p className="text-xs text-danger-strong mt-1">{errors.supplier_name.message}</p>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-findeck-text uppercase tracking-wider">
                  Supplier GSTIN
                </label>
                <input
                  type="text"
                  {...register("supplier_gstin")}
                  className={`mt-1 block w-full px-3 py-2 text-sm border rounded-btn font-mono font-medium outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text ${
                    getIssueForField("supplier_gstin")
                      ? "border-danger-strong bg-danger-soft/40"
                      : "border-findeck-border"
                  }`}
                />
                {errors.supplier_gstin && (
                  <p className="text-xs text-danger-strong mt-1">{errors.supplier_gstin.message}</p>
                )}
              </div>
            </div>

            {/* Line Items Table */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold text-findeck-text uppercase tracking-wider">
                  Line Items ({fields.length})
                </h3>
                <button
                  type="button"
                  onClick={() => append({ description: "", quantity: "1", rate: "0", amount: "0.00" })}
                  className="inline-flex items-center space-x-1 text-xs font-semibold text-success-strong hover:text-success-strong-hover cursor-pointer"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Add Line</span>
                </button>
              </div>

              <div className="border border-findeck-border rounded-btn overflow-hidden shadow-xs">
                <div className="max-h-[360px] overflow-y-auto">
                  <table className="w-full text-left text-xs text-findeck-text">
                    <thead className="bg-findeck-bg-sidebar/60 font-semibold text-findeck-muted border-b border-findeck-border sticky top-0 z-10 shadow-xs">
                      <tr>
                        <th className="px-3 py-2 bg-findeck-bg-sidebar/80">Description</th>
                        <th className="px-2 py-2 w-20 bg-findeck-bg-sidebar/80">Qty</th>
                        <th className="px-2 py-2 w-24 bg-findeck-bg-sidebar/80">Rate</th>
                        <th className="px-3 py-2 w-28 bg-findeck-bg-sidebar/80">Amount</th>
                        <th className="px-2 py-2 w-10 text-center bg-findeck-bg-sidebar/80"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-findeck-border/60">
                      {fields.map((field, idx) => (
                        <tr key={field.id} className="hover:bg-findeck-bg-sidebar/30 transition-colors">
                          <td className="px-3 py-1.5">
                            <input
                              type="text"
                              {...register(`line_items.${idx}.description`)}
                              className="w-full px-2 py-1 text-xs border border-transparent hover:border-findeck-border focus:border-findeck-accent focus:bg-white rounded-btn outline-none text-findeck-text"
                            />
                          </td>
                          <td className="px-2 py-1.5">
                            <input
                              type="text"
                              {...register(`line_items.${idx}.quantity`)}
                              className="w-full px-2 py-1 text-xs border border-transparent hover:border-findeck-border focus:border-findeck-accent focus:bg-white rounded-btn outline-none text-right font-mono tabular-nums text-findeck-text"
                            />
                          </td>
                          <td className="px-2 py-1.5">
                            <input
                              type="text"
                              {...register(`line_items.${idx}.rate`)}
                              className="w-full px-2 py-1 text-xs border border-transparent hover:border-findeck-border focus:border-findeck-accent focus:bg-white rounded-btn outline-none text-right font-mono tabular-nums text-findeck-text"
                            />
                          </td>
                          <td className="px-3 py-1.5">
                            <input
                              type="text"
                              {...register(`line_items.${idx}.amount`)}
                              className="w-full px-2 py-1 text-xs border border-transparent hover:border-findeck-border focus:border-findeck-accent focus:bg-white rounded-btn outline-none text-right font-mono tabular-nums font-medium text-findeck-text"
                            />
                          </td>
                          <td className="px-2 py-1.5 text-center">
                            <button
                              type="button"
                              onClick={() => remove(idx)}
                              className="p-1 text-findeck-muted hover:text-danger-strong rounded-btn transition-colors cursor-pointer"
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
            </div>

            {/* Tax Breakdown & Live Total Recalculation (decimal.js) */}
            <div className="bg-findeck-app p-4 rounded-card border border-findeck-border space-y-3">
              <div className="grid grid-cols-4 gap-3 text-xs">
                <div>
                  <label className="text-findeck-muted font-medium">Taxable Value</label>
                  <input
                    type="text"
                    {...register("taxable_value")}
                    className="mt-1 w-full px-2.5 py-1.5 border border-findeck-border rounded-btn font-mono tabular-nums text-right text-findeck-text bg-white outline-none focus:border-findeck-accent"
                  />
                </div>
                <div>
                  <label className="text-findeck-muted font-medium">CGST</label>
                  <input
                    type="text"
                    {...register("cgst")}
                    className="mt-1 w-full px-2.5 py-1.5 border border-findeck-border rounded-btn font-mono tabular-nums text-right text-findeck-text bg-white outline-none focus:border-findeck-accent"
                  />
                </div>
                <div>
                  <label className="text-findeck-muted font-medium">SGST</label>
                  <input
                    type="text"
                    {...register("sgst")}
                    className="mt-1 w-full px-2.5 py-1.5 border border-findeck-border rounded-btn font-mono tabular-nums text-right text-findeck-text bg-white outline-none focus:border-findeck-accent"
                  />
                </div>
                <div>
                  <label className="text-findeck-muted font-medium">IGST</label>
                  <input
                    type="text"
                    {...register("igst")}
                    className="mt-1 w-full px-2.5 py-1.5 border border-findeck-border rounded-btn font-mono tabular-nums text-right text-findeck-text bg-white outline-none focus:border-findeck-accent"
                  />
                </div>
              </div>

              {/* Total & Match Indicator */}
              <div className="pt-3 border-t border-findeck-border flex items-center justify-between">
                <div>
                  <div className="text-xs text-findeck-muted font-medium">Calculated Sum (Lines + Tax)</div>
                  <div className="text-base font-bold font-mono tabular-nums text-findeck-text">
                    ₹{calculatedTotal}
                  </div>
                </div>

                <div className="flex items-center space-x-3">
                  <div className="text-right">
                    <label className="text-xs font-semibold text-findeck-text">Invoice Total</label>
                    <input
                      type="text"
                      {...register("total")}
                      className={`mt-0.5 px-3 py-1.5 border rounded-btn font-mono tabular-nums font-bold text-right text-base w-36 outline-none focus:ring-1 ${
                        totalStatus.status === "mismatch"
                          ? "border-rose-300 bg-rose-50/50 text-danger-strong focus:border-rose-400 focus:ring-rose-400"
                          : "border-findeck-border bg-white text-findeck-text focus:border-findeck-accent focus:ring-findeck-accent"
                      }`}
                    />
                  </div>

                  <div className="mt-4">
                    {totalMatches ? (
                      <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-pill text-xs font-semibold bg-success-soft text-success-strong border border-success/30">
                        <Check className="h-3.5 w-3.5" />
                        <span>Matches</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-pill text-xs font-semibold bg-danger text-ink border border-danger/40">
                        <X className="h-3.5 w-3.5" />
                        <span>{totalStatus.text}</span>
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
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-card max-w-md w-full p-6 shadow-xl border border-findeck-border space-y-4">
            <div className="flex items-center space-x-3 text-danger-strong">
              <AlertCircle className="h-6 w-6" />
              <h3 className="text-lg font-bold text-findeck-text">Approve with Remaining Errors</h3>
            </div>
            <p className="text-xs text-findeck-muted">
              This invoice has unresolved validation errors. R2 policy requires an audit override reason (at least 10 characters) to push to accounting.
            </p>
            <textarea
              rows={3}
              placeholder="e.g., Verified difference against revised credit note received via email..."
              value={dialogReason}
              onChange={(e) => setDialogReason(e.target.value)}
              className="w-full p-3 border border-findeck-border rounded-btn text-sm outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-500 text-findeck-text"
            />
            {actionError && <p className="text-xs text-danger-strong">{actionError}</p>}
            <div className="flex justify-end space-x-2.5">
              <button
                onClick={() => {
                  setShowOverrideDialog(false);
                  setDialogReason("");
                }}
                className="px-4 py-2 border border-findeck-border rounded-btn text-xs font-semibold text-findeck-text hover:bg-findeck-bg-sidebar transition-colors cursor-pointer"
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
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-btn text-xs font-bold disabled:opacity-50 transition-colors cursor-pointer"
              >
                Confirm Override & Approve
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Reason Dialog */}
      {showRejectDialog && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-card max-w-md w-full p-6 shadow-xl border border-findeck-border space-y-4">
            <h3 className="text-lg font-bold text-findeck-text">Reject Invoice</h3>
            <p className="text-xs text-findeck-muted">
              Please enter the reason for rejection (mandatory for accounts audit trail).
            </p>
            <textarea
              rows={3}
              placeholder="Reason for rejection..."
              value={dialogReason}
              onChange={(e) => setDialogReason(e.target.value)}
              className="w-full p-3 border border-findeck-border rounded-btn text-sm outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text"
            />
            <div className="flex justify-end space-x-2.5">
              <button
                onClick={() => {
                  setShowRejectDialog(false);
                  setDialogReason("");
                }}
                className="px-4 py-2 border border-findeck-border rounded-btn text-xs font-semibold text-findeck-text hover:bg-findeck-bg-sidebar transition-colors cursor-pointer"
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
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-btn text-xs font-bold disabled:opacity-50 transition-colors cursor-pointer"
              >
                Reject Invoice
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Request Resend Dialog */}
      {showResendDialog && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-card max-w-md w-full p-6 shadow-xl border border-findeck-border space-y-4">
            <h3 className="text-lg font-bold text-findeck-text">Request Resend</h3>
            <p className="text-xs text-findeck-muted">
              Request the supplier to re-send this invoice (e.g., blurry image, missing pages, or unreadable fields).
            </p>
            <textarea
              rows={3}
              placeholder="Reason for requesting resend..."
              value={dialogReason}
              onChange={(e) => setDialogReason(e.target.value)}
              className="w-full p-3 border border-findeck-border rounded-btn text-sm outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text"
            />
            <div className="flex justify-end space-x-2.5">
              <button
                onClick={() => {
                  setShowResendDialog(false);
                  setDialogReason("");
                }}
                className="px-4 py-2 border border-findeck-border rounded-btn text-xs font-semibold text-findeck-text hover:bg-findeck-bg-sidebar transition-colors cursor-pointer"
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
                className="px-4 py-2 bg-ink text-white rounded-btn text-xs font-bold disabled:opacity-50 transition-colors cursor-pointer hover:bg-ink-hover"
              >
                Request Resend
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Duplicate Override Dialog */}
      {showDuplicateOverrideDialog && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-card max-w-md w-full p-6 shadow-xl border border-findeck-border space-y-4">
            <h3 className="text-lg font-bold text-findeck-text">Override Duplicate Flag</h3>
            <p className="text-xs text-findeck-muted">
              Explain why this invoice is legitimate despite matching an existing business key (e.g., replacement invoice or supplementary billing).
            </p>
            <textarea
              rows={3}
              placeholder="Mandatory reason for override..."
              value={dialogReason}
              onChange={(e) => setDialogReason(e.target.value)}
              className="w-full p-3 border border-findeck-border rounded-btn text-sm outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text"
            />
            <div className="flex justify-end space-x-2.5">
              <button
                onClick={() => {
                  setShowDuplicateOverrideDialog(false);
                  setDialogReason("");
                }}
                className="px-4 py-2 border border-findeck-border rounded-btn text-xs font-semibold text-findeck-text hover:bg-findeck-bg-sidebar transition-colors cursor-pointer"
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
                className="px-4 py-2 bg-findeck-accent hover:bg-findeck-accent-hover text-white rounded-btn text-xs font-bold disabled:opacity-50 transition-colors cursor-pointer"
              >
                Save Override
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Keyboard Shortcuts Dialog */}
      {showShortcutsHelp && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-card max-w-sm w-full p-6 shadow-xl border border-findeck-border space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-findeck-text text-15">Keyboard Shortcuts</h3>
              <button
                onClick={() => setShowShortcutsHelp(false)}
                className="p-1 hover:bg-findeck-bg-sidebar rounded text-findeck-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="divide-y divide-findeck-border/60 text-xs">
              <div className="py-2 flex justify-between">
                <span className="text-findeck-muted">Approve & Push</span>
                <kbd className="px-2 py-0.5 rounded font-mono font-bold text-xs" style={{ backgroundColor: "var(--bg-app)", color: "var(--text-secondary)" }}>Ctrl + Enter</kbd>
              </div>
              <div className="py-2 flex justify-between">
                <span className="text-findeck-muted">Next Invoice</span>
                <kbd className="px-2 py-0.5 rounded font-mono font-bold text-xs" style={{ backgroundColor: "var(--bg-app)", color: "var(--text-secondary)" }}>Alt + →</kbd>
              </div>
              <div className="py-2 flex justify-between">
                <span className="text-findeck-muted">Previous Invoice</span>
                <kbd className="px-2 py-0.5 rounded font-mono font-bold text-xs" style={{ backgroundColor: "var(--bg-app)", color: "var(--text-secondary)" }}>Alt + ←</kbd>
              </div>
              <div className="py-2 flex justify-between">
                <span className="text-findeck-muted">Reject Invoice</span>
                <kbd className="px-2 py-0.5 rounded font-mono font-bold text-xs" style={{ backgroundColor: "var(--bg-app)", color: "var(--text-secondary)" }}>Alt + R</kbd>
              </div>
              <div className="py-2 flex justify-between">
                <span className="text-findeck-muted">Help / Shortcuts</span>
                <kbd className="px-2 py-0.5 rounded font-mono font-bold text-xs" style={{ backgroundColor: "var(--bg-app)", color: "var(--text-secondary)" }}>?</kbd>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Audit Trail Flowchart Drawer */}
      {showAuditDrawer && (
        <AuditTrailFlowchart
          events={auditTrail || []}
          onClose={() => setShowAuditDrawer(false)}
          invoiceNumber={invoice?.normalized_invoice_number}
          currentStatus={invoice?.status}
        />
      )}
    </div>
  );
}
