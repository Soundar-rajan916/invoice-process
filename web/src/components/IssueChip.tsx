import { AlertCircle, AlertTriangle, Check } from "lucide-react";

export type IssueChipType = "error" | "warning" | "valid";

interface IssueChipProps {
  type: IssueChipType;
  count?: number;
  className?: string;
}

export function IssueChip({ type, count = 1, className = "" }: IssueChipProps) {
  if (type === "error") {
    return (
      <span
        className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-danger text-ink select-none shadow-2xs ${className}`}
        style={{
          backgroundColor: "var(--danger)",
          color: "var(--ink)",
        }}
      >
        <AlertCircle className="h-3 w-3 stroke-[2.5]" aria-hidden="true" />
        <span className="tabular-nums">
          {count} error{count > 1 ? "s" : ""}
        </span>
      </span>
    );
  }

  if (type === "warning") {
    return (
      <span
        className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-warning text-ink select-none shadow-2xs ${className}`}
        style={{
          backgroundColor: "var(--warning)",
          color: "var(--ink)",
        }}
      >
        <AlertTriangle className="h-3 w-3 stroke-[2.5]" aria-hidden="true" />
        <span className="tabular-nums">
          {count} warning{count > 1 ? "s" : ""}
        </span>
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-success text-ink select-none shadow-2xs ${className}`}
      style={{
        backgroundColor: "var(--success)",
        color: "var(--ink)",
      }}
    >
      <Check className="h-3 w-3 stroke-[2.5]" aria-hidden="true" />
      <span>Valid</span>
    </span>
  );
}

