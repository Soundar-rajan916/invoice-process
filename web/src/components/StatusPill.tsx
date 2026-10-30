import { Check, AlertCircle, Copy, RefreshCw } from "lucide-react";

export type InvoiceStatus =
  | "RECEIVED"
  | "PROCESSING"
  | "WAITING_PROVIDER"
  | "NEEDS_REVIEW"
  | "APPROVED"
  | "PUSHING"
  | "PUSHED"
  | "REJECTED"
  | "FAILED"
  | "PUSH_FAILED"
  | "REJECTED_DUPLICATE"
  | "RESEND_REQUESTED";

interface StatusConfig {
  bgClass: string;
  textClass: string;
  dotColor?: string;
  icon?: "dot" | "check" | "alert" | "copy" | "spinner";
  varName: string;
  textVar: string;
}

const STATUS_CONFIG: Record<InvoiceStatus, StatusConfig> = {
  RECEIVED: {
    bgClass: "bg-accent",
    textClass: "text-ink",
    icon: "dot",
    dotColor: "bg-ink",
    varName: "--accent",
    textVar: "--ink",
  },
  PROCESSING: {
    bgClass: "bg-accent",
    textClass: "text-ink",
    icon: "spinner",
    dotColor: "bg-ink",
    varName: "--accent",
    textVar: "--ink",
  },
  WAITING_PROVIDER: {
    bgClass: "bg-accent-soft",
    textClass: "text-accent-strong",
    icon: "dot",
    dotColor: "bg-accent-strong",
    varName: "--accent-soft",
    textVar: "--accent-strong",
  },
  NEEDS_REVIEW: {
    bgClass: "bg-warning",
    textClass: "text-ink",
    icon: "dot",
    dotColor: "bg-ink",
    varName: "--warning",
    textVar: "--ink",
  },
  APPROVED: {
    bgClass: "bg-success",
    textClass: "text-ink",
    icon: "dot",
    dotColor: "bg-ink",
    varName: "--success",
    textVar: "--ink",
  },
  PUSHING: {
    bgClass: "bg-accent",
    textClass: "text-ink",
    icon: "spinner",
    dotColor: "bg-ink",
    varName: "--accent",
    textVar: "--ink",
  },
  PUSHED: {
    bgClass: "bg-success",
    textClass: "text-ink",
    icon: "check",
    varName: "--success",
    textVar: "--ink",
  },
  REJECTED: {
    bgClass: "bg-danger",
    textClass: "text-ink",
    icon: "alert",
    varName: "--danger",
    textVar: "--ink",
  },
  FAILED: {
    bgClass: "bg-danger",
    textClass: "text-ink",
    icon: "alert",
    varName: "--danger",
    textVar: "--ink",
  },
  PUSH_FAILED: {
    bgClass: "bg-danger",
    textClass: "text-ink",
    icon: "alert",
    varName: "--danger",
    textVar: "--ink",
  },
  REJECTED_DUPLICATE: {
    bgClass: "bg-accent-soft",
    textClass: "text-accent-strong",
    icon: "copy",
    varName: "--accent-soft",
    textVar: "--accent-strong",
  },
  RESEND_REQUESTED: {
    bgClass: "bg-accent",
    textClass: "text-ink",
    icon: "dot",
    dotColor: "bg-ink",
    varName: "--accent",
    textVar: "--ink",
  },
};

export function StatusPill({ status, className = "" }: { status: string; className?: string }) {
  const normStatus = (status || "").toUpperCase() as InvoiceStatus;
  const config = STATUS_CONFIG[normStatus] || {
    bgClass: "bg-accent",
    textClass: "text-ink",
    icon: "dot" as const,
    dotColor: "bg-ink",
    varName: "--accent",
    textVar: "--ink",
  };

  const displayText = status ? status.replace(/_/g, " ") : "UNKNOWN";

  return (
    <span
      className={`inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold select-none shadow-2xs ${config.bgClass} ${config.textClass} ${className}`}
      style={{
        backgroundColor: `var(${config.varName})`,
        color: `var(${config.textVar})`,
      }}
    >
      {config.icon === "check" && <Check className="h-3 w-3 stroke-[2.5]" aria-hidden="true" />}
      {config.icon === "alert" && <AlertCircle className="h-3 w-3 stroke-[2.5]" aria-hidden="true" />}
      {config.icon === "copy" && <Copy className="h-3 w-3 stroke-[2.5]" aria-hidden="true" />}
      {config.icon === "spinner" && <RefreshCw className="h-3 w-3 animate-spin stroke-[2.5]" aria-hidden="true" />}
      {config.icon === "dot" && (
        <span
          className={`h-1.5 w-1.5 rounded-full ${config.dotColor || "bg-ink"}`}
          style={{
            backgroundColor: `var(${config.dotColor === "bg-accent-strong" ? "--accent-strong" : "--ink"})`,
          }}
          aria-hidden="true"
        />
      )}
      <span>{displayText}</span>
    </span>
  );
}

