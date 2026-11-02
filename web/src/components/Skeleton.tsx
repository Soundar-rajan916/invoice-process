import React from "react";

// ==========================================
// 1. Core Atomic Skeleton Primitives
// ==========================================

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
  rounded?: "sm" | "md" | "lg" | "full" | "card" | "btn";
}

export function Skeleton({
  className = "",
  rounded = "md",
  style,
  ...props
}: SkeletonProps) {
  const roundedClass =
    rounded === "full"
      ? "rounded-full"
      : rounded === "card"
      ? "rounded-card"
      : rounded === "btn"
      ? "rounded-btn"
      : rounded === "sm"
      ? "rounded-[4px]"
      : rounded === "lg"
      ? "rounded-[16px]"
      : "rounded-[8px]";

  return (
    <div
      className={`animate-pulse ${roundedClass} ${className}`}
      style={{
        backgroundColor: "var(--border)",
        opacity: 0.75,
        ...style,
      }}
      aria-hidden="true"
      {...props}
    />
  );
}

export function SkeletonText({
  lines = 2,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  const widths = ["w-full", "w-11/12", "w-4/5", "w-3/4", "w-1/2"];
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={`h-3.5 ${widths[i % widths.length]}`}
          rounded="sm"
        />
      ))}
    </div>
  );
}

export function SkeletonPill({
  className = "w-20 h-5",
}: {
  className?: string;
}) {
  return <Skeleton rounded="full" className={className} />;
}

// ==========================================
// 2. Review Queue Table Skeleton
// ==========================================

export function QueueTableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
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
            <th className="px-6 py-3.5">Invoice #</th>
            <th className="px-6 py-3.5">Supplier GSTIN</th>
            <th className="px-6 py-3.5">Status</th>
            <th className="px-6 py-3.5">Source & Sender</th>
            <th className="px-6 py-3.5">Received / Age</th>
            <th className="px-6 py-3.5">Flags & Issues</th>
            <th className="px-6 py-3.5 text-right">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y" style={{ borderColor: "var(--border)" }}>
          {Array.from({ length: rows }).map((_, i) => (
            <tr
              key={i}
              style={{
                backgroundColor: i % 2 === 0 ? "transparent" : "rgba(255, 255, 255, 0.4)",
              }}
            >
              {/* Invoice # */}
              <td className="px-6 py-4">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-2.5 w-16 mt-1.5 opacity-50" />
              </td>

              {/* Supplier GSTIN */}
              <td className="px-6 py-4">
                <Skeleton className="h-3.5 w-32 font-mono" />
                <Skeleton className="h-2.5 w-20 mt-1.5 opacity-50" />
              </td>

              {/* Status */}
              <td className="px-6 py-4">
                <SkeletonPill className="h-6 w-24" />
              </td>

              {/* Source & Sender */}
              <td className="px-6 py-4">
                <div className="flex items-center space-x-2">
                  <Skeleton rounded="full" className="h-4 w-4 shrink-0" />
                  <Skeleton className="h-3.5 w-20" />
                </div>
                <Skeleton className="h-2.5 w-28 mt-1.5 opacity-50" />
              </td>

              {/* Received / Age */}
              <td className="px-6 py-4">
                <Skeleton className="h-3.5 w-24" />
                <Skeleton className="h-2.5 w-14 mt-1.5 opacity-50" />
              </td>

              {/* Flags & Issues */}
              <td className="px-6 py-4">
                <div className="flex items-center space-x-1.5">
                  <SkeletonPill className="h-5 w-16" />
                  {i % 2 === 0 && <SkeletonPill className="h-5 w-12" />}
                </div>
              </td>

              {/* Action */}
              <td className="px-6 py-4 text-right">
                <div className="inline-block">
                  <Skeleton rounded="btn" className="h-7 w-16" />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ==========================================
// 3. Dashboard Skeleton
// ==========================================

export function DashboardSkeleton() {
  return (
    <div className="w-full space-y-6">
      {/* Page Header */}
      <div className="space-y-2">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-3.5 w-96 opacity-60" />
      </div>

      {/* 4 KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="p-6 rounded-[20px] border shadow-xs flex flex-col justify-between"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
            }}
          >
            <div className="flex items-center space-x-3.5">
              <Skeleton rounded="full" className="h-11 w-11 shrink-0" />
              <div className="space-y-1.5 flex-1">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-2.5 w-16 opacity-50" />
              </div>
            </div>
            <div className="mt-5 space-y-2">
              <Skeleton className="h-8 w-20" />
              <Skeleton className="h-3 w-32 opacity-60" />
            </div>
          </div>
        ))}
      </div>

      {/* 2 Analytics / Chart Panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div
          className="p-6 rounded-card border shadow-xs space-y-4"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex justify-between items-center">
            <div className="space-y-1.5">
              <Skeleton className="h-5 w-44" />
              <Skeleton className="h-3 w-64 opacity-50" />
            </div>
            <Skeleton rounded="full" className="h-6 w-20" />
          </div>
          <div className="h-60 pt-4 flex items-end justify-between gap-3 px-2">
            {[45, 75, 30, 90, 60, 80, 50, 70].map((h, idx) => (
              <div key={idx} className="flex-1 flex flex-col items-center gap-2">
                <Skeleton
                  rounded="sm"
                  className="w-full"
                  style={{ height: `${h}%` }}
                />
                <Skeleton className="h-2.5 w-6 opacity-40" />
              </div>
            ))}
          </div>
        </div>

        <div
          className="p-6 rounded-card border shadow-xs space-y-4"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div className="space-y-1.5">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-3 w-56 opacity-50" />
          </div>
          <div className="space-y-3 pt-3">
            {Array.from({ length: 5 }).map((_, idx) => (
              <div
                key={idx}
                className="p-3.5 rounded-btn border flex items-center justify-between"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                }}
              >
                <div className="space-y-1">
                  <Skeleton className="h-3.5 w-32" />
                  <Skeleton className="h-2.5 w-20 opacity-50" />
                </div>
                <Skeleton className="h-4 w-12" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ==========================================
// 4. Review Detail (Split-Screen) Skeleton
// ==========================================

export function ReviewDetailSkeleton() {
  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-4rem)] max-h-[calc(100vh-4rem)] min-h-0 overflow-hidden font-sans">
      {/* Top Header Bar */}
      <div
        className="px-6 py-3.5 border-b flex items-center justify-between shrink-0"
        style={{
          backgroundColor: "var(--bg-inset)",
          borderColor: "var(--border)",
        }}
      >
        <div className="flex items-center space-x-3">
          <Skeleton rounded="btn" className="h-8 w-20" />
          <div className="h-5 w-px" style={{ backgroundColor: "var(--border)" }} />
          <Skeleton className="h-5 w-36" />
          <SkeletonPill className="h-5 w-24" />
        </div>
        <div className="flex items-center space-x-2">
          <Skeleton rounded="btn" className="h-8 w-24" />
          <Skeleton rounded="btn" className="h-8 w-28" />
        </div>
      </div>

      {/* Two-Column Split Layout */}
      <div className="flex-1 flex flex-col md:flex-row min-h-0 overflow-hidden">
        {/* Left: Document Viewer Skeleton */}
        <div
          className="w-full md:w-1/2 border-r flex flex-col p-4 space-y-3"
          style={{
            backgroundColor: "var(--bg-app)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center justify-between px-2">
            <div className="flex items-center space-x-2">
              <Skeleton rounded="btn" className="h-7 w-7" />
              <Skeleton rounded="btn" className="h-7 w-7" />
              <Skeleton className="h-4 w-16" />
            </div>
            <Skeleton rounded="btn" className="h-7 w-20" />
          </div>
          <div
            className="flex-1 rounded-card border shadow-inner flex flex-col items-center justify-center p-8 space-y-4"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
            }}
          >
            <Skeleton rounded="lg" className="w-4/5 h-4/5 opacity-40" />
          </div>
        </div>

        {/* Right: Extractions Form & Issues Skeleton */}
        <div
          className="w-full md:w-1/2 flex flex-col p-6 space-y-6 overflow-y-auto"
          style={{ backgroundColor: "var(--bg-card)" }}
        >
          {/* Status summary banner */}
          <div
            className="p-4 rounded-card border space-y-2"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
            }}
          >
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-64 opacity-50" />
          </div>

          {/* Form Fields Grid */}
          <div className="grid grid-cols-2 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="space-y-1.5">
                <Skeleton className="h-3 w-24 opacity-60" />
                <Skeleton rounded="btn" className="h-9 w-full" />
              </div>
            ))}
          </div>

          {/* Line items table skeleton */}
          <div
            className="rounded-card border overflow-hidden"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
            }}
          >
            <div
              className="px-4 py-2.5 border-b flex justify-between"
              style={{ borderColor: "var(--border)" }}
            >
              <Skeleton className="h-3.5 w-28" />
              <Skeleton className="h-3.5 w-16" />
            </div>
            <div className="p-4 space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between gap-4">
                  <Skeleton className="h-3.5 w-48" />
                  <Skeleton className="h-3.5 w-16" />
                  <Skeleton className="h-3.5 w-20" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==========================================
// 5. Accounting Reconciliation Skeleton
// ==========================================

export function ReconciliationRunsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="p-3.5 rounded-card border space-y-2.5"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center justify-between">
            <Skeleton className="h-3.5 w-32" />
            <SkeletonPill className="h-5 w-20" />
          </div>
          <div className="flex items-center justify-between opacity-60">
            <Skeleton className="h-2.5 w-20" />
            <Skeleton className="h-2.5 w-24" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ReconciliationFindingsSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="p-5 rounded-card border space-y-4"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <SkeletonPill className="h-5 w-36" />
              <Skeleton className="h-4 w-28" />
            </div>
            <Skeleton className="h-3.5 w-24" />
          </div>
          <div
            className="p-3.5 rounded-btn border space-y-2"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
            }}
          >
            <Skeleton className="h-3.5 w-3/4" />
            <Skeleton className="h-3 w-1/2 opacity-50" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Skeleton rounded="btn" className="h-12 w-full" />
            <Skeleton rounded="btn" className="h-12 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ==========================================
// 6. Dead-Letters Skeleton
// ==========================================

export function DeadLettersSkeleton() {
  return (
    <div className="p-4 space-y-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="p-5 rounded-card border space-y-4"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Skeleton rounded="full" className="h-8 w-8 shrink-0" />
              <div className="space-y-1.5">
                <div className="flex items-center space-x-2">
                  <Skeleton className="h-4 w-24" />
                  <SkeletonPill className="h-5 w-28" />
                </div>
                <Skeleton className="h-3 w-40 opacity-50" />
              </div>
            </div>
            <Skeleton rounded="btn" className="h-8 w-24" />
          </div>
          <div
            className="p-3.5 rounded-btn border space-y-2"
            style={{
              backgroundColor: "var(--bg-inset)",
              borderColor: "var(--border)",
            }}
          >
            <Skeleton className="h-3.5 w-4/5" />
            <Skeleton className="h-2.5 w-2/3 opacity-50" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ==========================================
// 7. Master Data Suppliers Table Skeleton
// ==========================================

export function SuppliersTableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
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
            <th className="px-6 py-3.5">GSTIN</th>
            <th className="px-6 py-3.5">Supplier Name</th>
            <th className="px-6 py-3.5">State</th>
            <th className="px-6 py-3.5">Status</th>
            <th className="px-6 py-3.5 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y" style={{ borderColor: "var(--border)" }}>
          {Array.from({ length: rows }).map((_, i) => (
            <tr key={i}>
              <td className="px-6 py-4">
                <Skeleton className="h-3.5 w-32 font-mono" />
              </td>
              <td className="px-6 py-4">
                <Skeleton className="h-4 w-44" />
              </td>
              <td className="px-6 py-4">
                <Skeleton className="h-3.5 w-24" />
              </td>
              <td className="px-6 py-4">
                <SkeletonPill className="h-5 w-16" />
              </td>
              <td className="px-6 py-4 text-right">
                <div className="inline-flex space-x-2">
                  <Skeleton rounded="btn" className="h-7 w-12" />
                  <Skeleton rounded="btn" className="h-7 w-12" />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ==========================================
// 8. Full App Loading Skeleton (Auth / Session)
// ==========================================

export function AppLoadingSkeleton() {
  return (
    <div
      className="min-h-screen flex font-sans"
      style={{ backgroundColor: "var(--bg-app)" }}
    >
      {/* Sidebar Mock */}
      <div
        className="hidden md:flex w-64 border-r flex-col p-6 space-y-6"
        style={{
          backgroundColor: "var(--bg-inset)",
          borderColor: "var(--border)",
        }}
      >
        <div className="flex items-center space-x-3">
          <Skeleton rounded="lg" className="h-9 w-9 shrink-0" />
          <Skeleton className="h-5 w-28" />
        </div>
        <div className="space-y-3 pt-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex items-center space-x-3 p-2">
              <Skeleton rounded="md" className="h-5 w-5 shrink-0" />
              <Skeleton className="h-4 w-32" />
            </div>
          ))}
        </div>
      </div>

      {/* Main View Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header Mock */}
        <div
          className="h-16 border-b px-8 flex items-center justify-between shrink-0"
          style={{
            backgroundColor: "var(--bg-inset)",
            borderColor: "var(--border)",
          }}
        >
          <Skeleton className="h-4 w-36" />
          <div className="flex items-center space-x-3">
            <Skeleton rounded="full" className="h-8 w-8" />
            <Skeleton className="h-3.5 w-20" />
          </div>
        </div>

        {/* Content Body Mock */}
        <div className="p-8 space-y-6 flex-1 overflow-y-auto">
          <div className="space-y-2">
            <Skeleton className="h-7 w-56" />
            <Skeleton className="h-3.5 w-80 opacity-50" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 pt-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} rounded="card" className="h-28 w-full" />
            ))}
          </div>
          <Skeleton rounded="card" className="h-96 w-full" />
        </div>
      </div>
    </div>
  );
}

