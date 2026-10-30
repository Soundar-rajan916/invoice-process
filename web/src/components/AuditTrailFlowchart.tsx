import { useState } from "react";
import {
  X,
  Bot,
  User,
  ArrowRight,
  ArrowDown,
  Cpu,
  AlertTriangle,
  CheckCircle2,
  Send,
  Building2,
  XCircle,
  Pencil,
  RotateCcw,
  ShieldAlert,
  Copy,
  ChevronDown,
  ChevronUp,
  FileUp,
  Activity,
  Check,
} from "lucide-react";

export interface AuditEvent {
  id: string;
  action: string;
  actor_email: string;
  payload: any;
  created_at: string;
}

interface AuditTrailFlowchartProps {
  events: AuditEvent[];
  onClose: () => void;
  invoiceNumber?: string;
  currentStatus?: string;
}

export function AuditTrailFlowchart({
  events,
  onClose,
  invoiceNumber,
  currentStatus,
}: AuditTrailFlowchartProps) {
  const [expandedJson, setExpandedJson] = useState<Record<string, boolean>>({});
  const [showAllEvents, setShowAllEvents] = useState(false);

  const toggleJson = (id: string) => {
    setExpandedJson((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Deduplicate redundant idempotent replay cycles (e.g. repeated approvals after already reaching terminal status)
  const dedupedEvents = events.filter((ev, idx) => {
    if (idx === 0) return true;
    const prev = events[idx - 1];
    // If consecutive events have the exact same action and status transition
    if (
      ev.action === prev.action &&
      ev.payload?.to_status &&
      ev.payload?.to_status === prev.payload?.to_status
    ) {
      return false;
    }
    // If invoice was already pushed with this accounting_id, suppress repeated push/approval replay cycles
    const hasPriorPushed = events
      .slice(0, idx)
      .some(
        (e) =>
          e.payload?.to_status === "PUSHED" &&
          e.payload?.accounting_id &&
          e.payload?.accounting_id === ev.payload?.accounting_id
      );
    if (hasPriorPushed) {
      return false;
    }
    return true;
  });

  const displayEvents = showAllEvents ? events : dedupedEvents;
  const duplicateCount = events.length - dedupedEvents.length;

  const getStepDetails = (ev: AuditEvent) => {
    const payload = ev.payload || {};
    const action = ev.action;

    if (action === "status_change") {
      const fromSt = payload.from_status;
      const toSt = payload.to_status;

      if (toSt === "PROCESSING") {
        return {
          title: "Processing Started",
          desc: payload.reason || "OCR & document extraction initiated",
          icon: Cpu,
          badgeColor: "bg-accent text-ink",
          cardBorder: "border-accent/30",
          cardBg: "bg-accent-soft",
        };
      }
      if (toSt === "NEEDS_REVIEW") {
        const issues = payload.issues_count || 0;
        return {
          title: "Queued for Review",
          desc: issues > 0 ? `${issues} issue${issues > 1 ? "s" : ""} flagged for human verification` : "Routing to review queue",
          icon: AlertTriangle,
          badgeColor: "bg-warning text-ink",
          cardBorder: "border-warning/30",
          cardBg: "bg-warning-soft",
        };
      }
      if (toSt === "APPROVED") {
        return {
          title: "Invoice Approved",
          desc: payload.reason || "Validated and approved for accounting push",
          icon: CheckCircle2,
          badgeColor: "bg-success text-ink",
          cardBorder: "border-success/30",
          cardBg: "bg-success-soft",
        };
      }
      if (toSt === "PUSHING") {
        return {
          title: "Dispatching to Accounting",
          desc: "Submitting payload to accounting system",
          icon: Send,
          badgeColor: "bg-accent text-ink",
          cardBorder: "border-accent/30",
          cardBg: "bg-accent-soft",
        };
      }
      if (toSt === "PUSHED") {
        return {
          title: "Pushed to Accounting",
          desc: "Successfully posted to accounting ledger",
          icon: Building2,
          badgeColor: "bg-success text-ink",
          cardBorder: "border-success/30",
          cardBg: "bg-success-soft",
        };
      }
      if (toSt === "PUSH_FAILED" || toSt === "FAILED") {
        return {
          title: "Processing / Push Failed",
          desc: payload.error || "An error occurred during state transition",
          icon: XCircle,
          badgeColor: "bg-danger text-ink",
          cardBorder: "border-danger/30",
          cardBg: "bg-danger-soft",
        };
      }
      return {
        title: `Status: ${toSt.replace(/_/g, " ")}`,
        desc: `Transitioned from ${fromSt || "UNKNOWN"}`,
        icon: Activity,
        badgeColor: "bg-slate-600 text-white",
        cardBorder: "border-slate-200",
        cardBg: "bg-white",
      };
    }

    if (action === "auto_approve") {
      return {
        title: "Straight-Through Auto-Approval",
        desc: payload.reason || "Zero errors or warnings detected — auto-approved",
        icon: CheckCircle2,
        badgeColor: "bg-success text-ink",
        cardBorder: "border-success/30",
        cardBg: "bg-success-soft",
      };
    }

    if (action === "approve") {
      return {
        title: "Reviewer Approved",
        desc: payload.override_reason
          ? `Approved with audit override: "${payload.override_reason}"`
          : "Approved by reviewer for accounting dispatch",
        icon: CheckCircle2,
        badgeColor: "bg-success text-ink",
        cardBorder: "border-success/30",
        cardBg: "bg-success-soft",
      };
    }

    if (action === "edit") {
      return {
        title: `Manual Edits (v${payload.version || 2})`,
        desc: "Reviewer adjusted invoice extracted fields",
        icon: Pencil,
        badgeColor: "bg-purple-500 text-white",
        cardBorder: "border-purple-200",
        cardBg: "bg-purple-50/30",
      };
    }

    if (action === "override_issue") {
      return {
        title: "Issues Overridden",
        desc: payload.override_reason ? `Reason: "${payload.override_reason}"` : "Validation issues bypassed",
        icon: ShieldAlert,
        badgeColor: "bg-warning text-ink",
        cardBorder: "border-warning/30",
        cardBg: "bg-warning-soft",
      };
    }

    if (action === "confirm_duplicate") {
      return {
        title: "Duplicate Confirmed",
        desc: `Marked duplicate of invoice ${payload.dup_of_id || ""}`,
        icon: Copy,
        badgeColor: "bg-danger text-ink",
        cardBorder: "border-danger/30",
        cardBg: "bg-danger-soft",
      };
    }

    if (action === "override_duplicate") {
      return {
        title: "Duplicate Overridden",
        desc: payload.reason ? `Reason: "${payload.reason}"` : "Duplicate warning permitted by reviewer",
        icon: CheckCircle2,
        badgeColor: "bg-warning text-ink",
        cardBorder: "border-warning/30",
        cardBg: "bg-warning-soft",
      };
    }

    if (action === "request_resend") {
      return {
        title: "Resend Requested",
        desc: payload.reason ? `Reason: "${payload.reason}"` : "Requested supplier/user to resubmit invoice",
        icon: RotateCcw,
        badgeColor: "bg-purple-500 text-white",
        cardBorder: "border-purple-200",
        cardBg: "bg-purple-50/30",
      };
    }

    if (action === "resend_fulfilled") {
      return {
        title: "Replacement Document Uploaded",
        desc: payload.filename
          ? `Uploaded "${payload.filename}" — document re-queued for processing`
          : "Replacement file uploaded to fulfill resend request",
        icon: FileUp,
        badgeColor: "bg-success text-ink",
        cardBorder: "border-success/30",
        cardBg: "bg-success-soft",
      };
    }

    if (action === "cancel_resend") {
      return {
        title: "Resend Request Cancelled",
        desc: payload.previous_resend_reason
          ? `Cancelled resend request (prior reason: "${payload.previous_resend_reason}") — returned to review queue`
          : "Reviewer cancelled resend request and returned invoice to review queue",
        icon: RotateCcw,
        badgeColor: "bg-slate-600 text-white",
        cardBorder: "border-slate-200",
        cardBg: "bg-slate-50/50",
      };
    }

    if (action === "reject") {
      return {
        title: "Invoice Rejected",
        desc: payload.reason ? `Reason: "${payload.reason}"` : "Rejected by accounts reviewer",
        icon: XCircle,
        badgeColor: "bg-danger text-ink",
        cardBorder: "border-danger/30",
        cardBg: "bg-danger-soft",
      };
    }

    if (action === "ingest" || action === "upload") {
      return {
        title: "Document Uploaded",
        desc: payload.original_filename || "Source file ingested into system",
        icon: FileUp,
        badgeColor: "bg-slate-700 text-white",
        cardBorder: "border-slate-200",
        cardBg: "bg-white",
      };
    }

    return {
      title: action.replace(/_/g, " ").toUpperCase(),
      desc: "Recorded audit event",
      icon: Activity,
      badgeColor: "bg-slate-500 text-white",
      cardBorder: "border-slate-200",
      cardBg: "bg-white",
    };
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex justify-end animate-in fade-in duration-200">
      <div className="bg-slate-50 w-full max-w-lg h-full shadow-2xl border-l border-slate-200 flex flex-col overflow-hidden">
        {/* Drawer Header */}
        <div className="bg-white px-6 py-4 border-b border-slate-200 shadow-xs flex items-center justify-between">
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-bold text-slate-900 text-base">Audit Trail Flowchart</h3>
              {currentStatus && (
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                  {currentStatus.replace(/_/g, " ")}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              {invoiceNumber ? `Invoice: ${invoiceNumber} • ` : ""}
              {displayEvents.length} workflow transition{displayEvents.length !== 1 ? "s" : ""}
              {duplicateCount > 0 && !showAllEvents && (
                <span className="ml-1 text-slate-400">({duplicateCount} duplicate replays collapsed)</span>
              )}
            </p>
            {duplicateCount > 0 && (
              <button
                onClick={() => setShowAllEvents(!showAllEvents)}
                className="text-[10px] text-indigo-600 hover:text-indigo-800 font-semibold underline mt-0.5 cursor-pointer"
              >
                {showAllEvents ? "Hide duplicate replay attempts" : `Show all ${events.length} raw events`}
              </button>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Timeline Flowchart Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-0">
          {displayEvents.length === 0 ? (
            <div className="text-center py-12 text-slate-400 text-xs">
              No audit events recorded for this invoice yet.
            </div>
          ) : (
            displayEvents.map((ev, idx) => {
              const details = getStepDetails(ev);
              const Icon = details.icon;
              const isLast = idx === displayEvents.length - 1;
              const isExpanded = !!expandedJson[ev.id];
              const payload = ev.payload || {};

              return (
                <div key={ev.id} className="relative flex items-start space-x-4">
                  {/* Left Flow Column: Node Icon + Vertical Connecting Track */}
                  <div className="flex flex-col items-center">
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center shadow-sm shrink-0 z-10 transition-transform ${details.badgeColor}`}
                    >
                      <Icon className="h-4 w-4" />
                    </div>

                    {!isLast && (
                      <div className="w-0.5 bg-slate-200 my-1 flex-1 min-h-[50px] relative flex flex-col justify-center items-center">
                        <ArrowDown className="h-3 w-3 text-slate-300 absolute" />
                      </div>
                    )}
                  </div>

                  {/* Right Flow Card */}
                  <div
                    className={`flex-1 mb-6 rounded-xl border p-3.5 shadow-xs transition-all ${details.cardBg} ${details.cardBorder}`}
                  >
                    {/* Top Row: Title, Step # and Time */}
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center space-x-2">
                          <span className="text-xs font-bold text-slate-900">
                            {details.title}
                          </span>
                          <span className="text-[10px] font-mono text-slate-400 font-semibold">
                            #{idx + 1}
                          </span>
                        </div>
                        <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">
                          {details.desc}
                        </p>
                      </div>

                      <span className="text-[11px] font-mono text-slate-400 shrink-0 whitespace-nowrap">
                        {new Date(ev.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </span>
                    </div>

                    {/* Actor & Transition Badges */}
                    <div className="mt-2.5 pt-2 border-t border-slate-200/60 flex flex-wrap items-center gap-2">
                      {/* Actor Badge */}
                      <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-white text-slate-600 border border-slate-200/80 shadow-2xs">
                        {ev.actor_email && ev.actor_email !== "System" ? (
                          <>
                            <User className="h-3 w-3 text-indigo-500" />
                            <span className="max-w-[140px] truncate">{ev.actor_email}</span>
                          </>
                        ) : (
                          <>
                            <Bot className="h-3 w-3 text-slate-400" />
                            <span>System Pipeline</span>
                          </>
                        )}
                      </span>

                      {/* Status Transition Badges */}
                      {payload.from_status && payload.to_status && (
                        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-md text-[10px] font-mono font-semibold bg-white text-slate-600 border border-slate-200/80 shadow-2xs">
                          <span>{payload.from_status}</span>
                          <ArrowRight className="h-2.5 w-2.5 text-slate-400" />
                          <span className="text-indigo-600">{payload.to_status}</span>
                        </span>
                      )}

                      {/* Accounting ID Tag */}
                      {payload.accounting_id && (
                        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-md text-[10px] font-mono font-bold bg-emerald-100 text-emerald-800 border border-success/30">
                          <Check className="h-3 w-3 text-emerald-600" />
                          <span>Ledger: {payload.accounting_id}</span>
                        </span>
                      )}
                    </div>

                    {/* Diff Viewer for Field Edits */}
                    {ev.action === "edit" && payload.diff && Object.keys(payload.diff).length > 0 && (
                      <div className="mt-2.5 p-2 bg-white rounded-lg border border-purple-200/70 text-[11px] space-y-1">
                        <span className="text-[10px] font-bold text-purple-800 uppercase tracking-wide block">
                          Field Changes:
                        </span>
                        {Object.entries(payload.diff).map(([fKey, diffObj]: [string, any]) => (
                          <div key={fKey} className="flex items-center justify-between font-mono">
                            <span className="text-slate-500 font-semibold">{fKey}:</span>
                            <div className="flex items-center space-x-1">
                              <span className="line-through text-rose-500 bg-rose-50 px-1 rounded">
                                {String(diffObj.before ?? "empty")}
                              </span>
                              <ArrowRight className="h-2.5 w-2.5 text-slate-400" />
                              <span className="font-bold text-emerald-600 bg-emerald-50 px-1 rounded">
                                {String(diffObj.after ?? "empty")}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Expandable JSON Payload */}
                    <div className="mt-2">
                      <button
                        onClick={() => toggleJson(ev.id)}
                        className="inline-flex items-center space-x-1 text-[10px] font-semibold text-slate-400 hover:text-slate-700 transition-colors"
                      >
                        {isExpanded ? (
                          <>
                            <ChevronUp className="h-3 w-3" />
                            <span>Hide payload</span>
                          </>
                        ) : (
                          <>
                            <ChevronDown className="h-3 w-3" />
                            <span>View raw details</span>
                          </>
                        )}
                      </button>

                      {isExpanded && (
                        <pre className="mt-1.5 p-2 bg-slate-900 text-slate-200 rounded-lg font-mono text-[10px] leading-tight overflow-x-auto shadow-inner">
                          {JSON.stringify(payload, null, 2)}
                        </pre>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

