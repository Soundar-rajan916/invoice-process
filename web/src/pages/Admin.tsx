import { Pagination, PaginationItemType } from '@heroui/react';
import { useState, useRef, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import {
  Users,
  Building2,
  Plus,
  FileSpreadsheet,
  Check,
  Search,
  ChevronLeft,
  ChevronRight,
  MessageSquare,
  ExternalLink,
  RefreshCw,
  Clock,
  Send,
  FileText,
  ArrowRight,
  ImageIcon,
} from "lucide-react";
import { SuppliersTableSkeleton } from "@/components/Skeleton";

export const GST_STATE_MAP: Record<string, string> = {
  "01": "Jammu & Kashmir",
  "02": "Himachal Pradesh",
  "03": "Punjab",
  "04": "Chandigarh",
  "05": "Uttarakhand",
  "06": "Haryana",
  "07": "Delhi",
  "08": "Rajasthan",
  "09": "Uttar Pradesh",
  "10": "Bihar",
  "11": "Sikkim",
  "12": "Arunachal Pradesh",
  "13": "Nagaland",
  "14": "Manipur",
  "15": "Mizoram",
  "16": "Tripura",
  "17": "Meghalaya",
  "18": "Assam",
  "19": "West Bengal",
  "20": "Jharkhand",
  "21": "Odisha",
  "22": "Chhattisgarh",
  "23": "Madhya Pradesh",
  "24": "Gujarat",
  "25": "Daman & Diu",
  "26": "Dadra & Nagar Haveli",
  "27": "Maharashtra",
  "28": "Andhra Pradesh (Old)",
  "29": "Karnataka",
  "30": "Goa",
  "31": "Lakshadweep",
  "32": "Kerala",
  "33": "Tamil Nadu",
  "34": "Puducherry",
  "35": "Andaman & Nicobar",
  "36": "Telangana",
  "37": "Andhra Pradesh",
  "38": "Ladakh",
  "97": "Other Territory",
};

export function formatStateDisplay(code?: string): string {
  if (!code) return "—";
  const name = GST_STATE_MAP[code];
  return name ? `(${name}) ${code}` : code;
}

export function Admin() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"suppliers" | "users" | "whatsapp">("suppliers");

  const { data: whatsappStatus, isLoading: loadingWhatsApp, refetch: refetchWhatsApp } = useQuery({
    queryKey: ["admin-whatsapp-status"],
    queryFn: () => apiRequest("/api/v1/admin/whatsapp/status"),
    enabled: activeTab === "whatsapp",
    refetchInterval: activeTab === "whatsapp" ? 10000 : false,
  });

  // Supplier state
  const [newGstin, setNewGstin] = useState("");
  const [newName, setNewName] = useState("");
  const [supplierSearch, setSupplierSearch] = useState("");
  const [supplierError, setSupplierError] = useState<string | null>(null);
  const [csvResult, setCsvResult] = useState<any | null>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);
  const [supplierPage, setSupplierPage] = useState(1);
  const [supplierPageSize, setSupplierPageSize] = useState(10);

  // User state
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState<"reviewer" | "admin">("reviewer");
  const [userError, setUserError] = useState<string | null>(null);
  const [userSuccess, setUserSuccess] = useState<string | null>(null);

  // 1. Fetch Suppliers
  const { data: suppliers = [], isLoading: loadingSuppliers } = useQuery({
    queryKey: ["admin-suppliers"],
    queryFn: () => apiRequest("/api/v1/admin/suppliers"),
  });

  const filteredSuppliers = useMemo(() => {
    return (suppliers || []).filter(
      (s: any) =>
        !supplierSearch ||
        s.name?.toLowerCase().includes(supplierSearch.toLowerCase()) ||
        s.gstin?.toLowerCase().includes(supplierSearch.toLowerCase()) ||
        formatStateDisplay(s.state_code).toLowerCase().includes(supplierSearch.toLowerCase())
    );
  }, [suppliers, supplierSearch]);

  const totalSupplierPages = Math.ceil(filteredSuppliers.length / supplierPageSize) || 1;
  const currentSupplierPage = Math.min(supplierPage, totalSupplierPages);

  const paginatedSuppliers = useMemo(() => {
    const start = (currentSupplierPage - 1) * supplierPageSize;
    return filteredSuppliers.slice(start, start + supplierPageSize);
  }, [filteredSuppliers, currentSupplierPage, supplierPageSize]);

  // 2. Fetch Users
  const { data: users = [] } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiRequest("/api/v1/admin/users"),
  });

  // Create Supplier
  const createSupplierMutation = useMutation({
    mutationFn: () =>
      apiRequest("/api/v1/admin/suppliers", {
        method: "POST",
        body: JSON.stringify({
          gstin: newGstin.toUpperCase().trim(),
          name: newName.trim(),
        }),
      }),
    onSuccess: () => {
      setNewGstin("");
      setNewName("");
      setSupplierError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-suppliers"] });
    },
    onError: (err: any) => {
      setSupplierError(err.message || "Failed to create supplier");
    },
  });

  // Toggle Supplier Status
  const toggleSupplierActiveMutation = useMutation({
    mutationFn: ({ supplierId, isActive }: { supplierId: string; isActive: boolean }) => {
      return apiRequest(`/api/v1/admin/suppliers/${supplierId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: isActive }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-suppliers"] });
    },
    onError: (err: any) => {
      alert(err.message || "Failed to update supplier status");
    },
  });

  // CSV Import
  const handleCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await apiRequest("/api/v1/admin/suppliers/import-csv", {
        method: "POST",
        body: formData,
      });
      setCsvResult(res);
      queryClient.invalidateQueries({ queryKey: ["admin-suppliers"] });
    } catch (err: any) {
      setSupplierError(err.message || "CSV import failed");
    }
  };

  // Create User
  const createUserMutation = useMutation({
    mutationFn: () => {
      const email = newUserEmail.trim();
      if (!email.includes("@")) {
        throw new Error("Please enter a valid email address (e.g. user@company.com)");
      }
      if (newUserPassword.length < 6) {
        throw new Error("Password must be at least 6 characters long");
      }
      return apiRequest("/api/v1/admin/users", {
        method: "POST",
        body: JSON.stringify({
          email: email,
          password: newUserPassword,
          role: newUserRole,
        }),
      });
    },
    onSuccess: () => {
      const email = newUserEmail.trim();
      setNewUserEmail("");
      setNewUserPassword("");
      setUserError(null);
      setUserSuccess(`Team member ${email || "user"} created successfully!`);
      setTimeout(() => setUserSuccess(null), 5000);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err: any) => {
      setUserSuccess(null);
      setUserError(err.message || "Failed to create user");
    },
  });

  // Update User Status
  const toggleUserActiveMutation = useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) => {
      return apiRequest(`/api/v1/admin/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: isActive }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
  });

  return (
    <div className="w-full space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
            System Administration
          </h1>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Manage authorized suppliers master directory and reviewer team accounts.
          </p>
        </div>

        {/* Tab Switcher - Segmented control */}
        <div
          className="flex p-1 rounded-full border self-start sm:self-auto shadow-2xs"
          style={{
            backgroundColor: "var(--bg-card)",
            borderColor: "var(--border)",
          }}
        >
          <button
            onClick={() => setActiveTab("suppliers")}
            className="flex items-center space-x-2 px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer"
            style={{
              backgroundColor: activeTab === "suppliers" ? "var(--ink)" : "transparent",
              color: activeTab === "suppliers" ? "#FFFFFF" : "var(--text-muted)",
            }}
          >
            <Building2 className="h-3.5 w-3.5" />
            <span>Suppliers Master</span>
          </button>
          <button
            onClick={() => setActiveTab("users")}
            className="flex items-center space-x-2 px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer"
            style={{
              backgroundColor: activeTab === "users" ? "var(--ink)" : "transparent",
              color: activeTab === "users" ? "#FFFFFF" : "var(--text-muted)",
            }}
          >
            <Users className="h-3.5 w-3.5" />
            <span>User Accounts</span>
          </button>
          <button
            onClick={() => setActiveTab("whatsapp")}
            className="flex items-center space-x-2 px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer"
            style={{
              backgroundColor: activeTab === "whatsapp" ? "var(--ink)" : "transparent",
              color: activeTab === "whatsapp" ? "#FFFFFF" : "var(--text-muted)",
            }}
          >
            <MessageSquare className="h-3.5 w-3.5" />
            <span>WhatsApp Gateway</span>
          </button>
        </div>
      </div>

      {activeTab === "suppliers" && (
        <div className="space-y-6">
          {/* Add Supplier & CSV Import Form on --bg-card */}
          <div
            className="p-6 rounded-card border shadow-xs space-y-4"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <h3 className="font-semibold text-sm" style={{ color: "var(--text)" }}>
              Add New Verified Supplier
            </h3>
            {supplierError && (
              <div
                className="p-3 text-xs rounded-btn border"
                style={{
                  backgroundColor: "var(--danger-soft)",
                  borderColor: "var(--danger)",
                  color: "var(--danger-strong)",
                }}
              >
                {supplierError}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <input
                type="text"
                placeholder="GSTIN (15 characters, e.g., 27AAPFU0939F1ZV)"
                value={newGstin}
                onChange={(e) => setNewGstin(e.target.value)}
                className="px-3.5 py-2 border rounded-btn text-xs font-mono outline-none"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                  color: "var(--text)",
                }}
              />
              <input
                type="text"
                placeholder="Supplier Business Name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="px-3.5 py-2 border rounded-btn text-xs outline-none"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                  color: "var(--text)",
                }}
              />
              <div className="flex space-x-2">
                <button
                  onClick={() => createSupplierMutation.mutate()}
                  disabled={!newGstin || !newName || createSupplierMutation.isPending}
                  className="flex-1 inline-flex items-center justify-center space-x-1.5 px-4 py-2 rounded-btn text-xs font-semibold disabled:opacity-50 transition-colors cursor-pointer shadow-xs"
                  style={{
                    backgroundColor: "var(--ink)",
                    color: "#FFFFFF",
                  }}
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Add Supplier</span>
                </button>
                <button
                  onClick={() => csvInputRef.current?.click()}
                  className="inline-flex items-center space-x-1.5 px-3 py-2 border rounded-btn text-xs font-semibold transition-colors cursor-pointer"
                  style={{
                    backgroundColor: "var(--bg-inset)",
                    borderColor: "var(--border)",
                    color: "var(--ink)",
                  }}
                  title="Import CSV"
                >
                  <FileSpreadsheet className="h-4 w-4" style={{ color: "var(--ink)" }} />
                  <span>CSV</span>
                </button>
                <input
                  ref={csvInputRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={handleCsvUpload}
                />
              </div>
            </div>

            {/* CSV Import Report */}
            {csvResult && (
              <div
                className="mt-3 p-4 border rounded-card text-xs space-y-2"
                style={{
                  backgroundColor: "var(--bg-app)",
                  borderColor: "var(--border)",
                }}
              >
                <div className="font-semibold" style={{ color: "var(--text)" }}>
                  Imported {csvResult.imported} supplier(s) successfully.
                </div>
                {csvResult.errors?.length > 0 && (
                  <div className="space-y-1" style={{ color: "var(--danger-strong)" }}>
                    <span className="font-bold">Errors encountered:</span>
                    {csvResult.errors.map((err: any, i: number) => (
                      <div key={i}>
                        Row {err.row}: {err.error} {err.gstin && `(${err.gstin})`}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Suppliers List Table on --bg-card */}
          <div
            className="rounded-card border shadow-xs overflow-hidden"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div
              className="px-6 py-3.5 border-b flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-semibold"
              style={{
                backgroundColor: "var(--bg-card)",
                borderColor: "var(--border)",
                color: "var(--text-muted)",
              }}
            >
              <span className="uppercase tracking-wider">Registered Master Suppliers ({suppliers.length})</span>
              <div className="relative w-full sm:w-64">
                <Search className="h-3.5 w-3.5 absolute left-3 top-2.5 opacity-60" />
                <input
                  type="text"
                  placeholder="Filter suppliers by name or GSTIN..."
                  value={supplierSearch}
                  onChange={(e) => {
                    setSupplierSearch(e.target.value);
                    setSupplierPage(1);
                  }}
                  className="w-full pl-8 pr-3 py-1.5 text-xs font-normal border rounded-btn outline-none"
                  style={{
                    backgroundColor: "var(--bg-inset)",
                    borderColor: "var(--border)",
                    color: "var(--text)",
                  }}
                />
              </div>
            </div>
            {loadingSuppliers ? (
              <SuppliersTableSkeleton rows={5} />
            ) : suppliers.length === 0 ? (
              <div className="p-8 text-center text-xs" style={{ color: "var(--text-muted)" }}>
                No suppliers registered.
              </div>
            ) : filteredSuppliers.length === 0 ? (
              <div className="p-8 text-center text-xs" style={{ color: "var(--text-muted)" }}>
                No suppliers match your search.
              </div>
            ) : (
              <>
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
                    <tbody>
                      {paginatedSuppliers.map((s: any) => (
                        <tr
                          key={s.id}
                          className="transition-colors text-xs"
                          style={{ borderBottom: "1px solid var(--border)" }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.backgroundColor = "var(--accent-soft)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.backgroundColor = "transparent";
                          }}
                        >
                          <td className="px-6 py-3.5 font-mono font-medium">{s.gstin}</td>
                          <td className="px-6 py-3.5 font-medium">{s.name}</td>
                          <td className="px-6 py-3.5" style={{ color: "var(--text-muted)" }}>
                            {formatStateDisplay(s.state_code)}
                          </td>
                          <td className="px-6 py-3.5">
                            <span
                              className="px-2.5 py-0.5 rounded-full text-xs font-semibold shadow-2xs"
                              style={{
                                backgroundColor: s.is_active ? "var(--success)" : "var(--danger)",
                                color: "var(--ink)",
                              }}
                            >
                              {s.is_active ? "Active" : "Deactivated"}
                            </span>
                          </td>
                          <td className="px-6 py-3.5 text-right">
                            <button
                              onClick={() =>
                                toggleSupplierActiveMutation.mutate({
                                  supplierId: s.id,
                                  isActive: !s.is_active,
                                })
                              }
                              disabled={toggleSupplierActiveMutation.isPending}
                              className="text-xs font-semibold px-2.5 py-1 rounded-btn transition-colors cursor-pointer shadow-2xs"
                              style={{
                                backgroundColor: s.is_active ? "var(--danger)" : "var(--success)",
                                color: "var(--ink)",
                              }}
                            >
                              {s.is_active ? "Deactivate" : "Activate"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination Controls */}
                <div
                  className="px-6 py-3.5 border-t flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
                  style={{
                    backgroundColor: "var(--bg-inset)",
                    borderColor: "var(--border)",
                    color: "var(--text-muted)",
                  }}
                >
                  <div className="flex items-center space-x-3">
                    <span className="tabular-nums">
                      Showing{" "}
                      <strong className="font-semibold" style={{ color: "var(--text)" }}>
                        {(currentSupplierPage - 1) * supplierPageSize + 1}
                      </strong>
                      –
                      <strong className="font-semibold" style={{ color: "var(--text)" }}>
                        {Math.min(currentSupplierPage * supplierPageSize, filteredSuppliers.length)}
                      </strong>{" "}
                      of{" "}
                      <strong className="font-semibold" style={{ color: "var(--text)" }}>
                        {filteredSuppliers.length}
                      </strong>{" "}
                      suppliers
                    </span>
                    <span style={{ color: "var(--border)" }}>|</span>
                    <div className="flex items-center space-x-1.5">
                      <span>Per page:</span>
                      <select
                        value={supplierPageSize}
                        onChange={(e) => {
                          setSupplierPageSize(Number(e.target.value));
                          setSupplierPage(1);
                        }}
                        className="px-2 py-0.5 border rounded-btn text-xs outline-none cursor-pointer"
                        style={{
                          backgroundColor: "var(--bg-inset)",
                          borderColor: "var(--border)",
                          color: "var(--text)",
                        }}
                      >
                        <option value={10}>10</option>
                        <option value={20}>20</option>
                        <option value={50}>50</option>
                        <option value={100}>100</option>
                      </select>
                    </div>
                  </div>

                  {totalSupplierPages > 1 && (
                    <Pagination
                      total={totalSupplierPages}
                      page={currentSupplierPage}
                      onChange={(newPage) => setSupplierPage(newPage)}
                      showControls
                      disableCursorAnimation
                      classNames={{
                        base: "overflow-visible",
                        wrapper: "gap-1.5",
                      }}
                      renderItem={({
                        ref,
                        key,
                        value,
                        isActive,
                        onNext,
                        onPrevious,
                        setPage,
                      }) => {
                        if (value === PaginationItemType.NEXT) {
                          return (
                            <button
                              key={key}
                              type="button"
                              onClick={onNext}
                              disabled={currentSupplierPage >= totalSupplierPages}
                              className="w-8 h-8 flex items-center justify-center border rounded-btn disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                              style={{
                                backgroundColor: "var(--bg-inset)",
                                borderColor: "var(--border)",
                                color: "var(--text)",
                              }}
                              title="Next page"
                            >
                              <ChevronRight className="h-4 w-4" />
                            </button>
                          );
                        }

                        if (value === PaginationItemType.PREV) {
                          return (
                            <button
                              key={key}
                              type="button"
                              onClick={onPrevious}
                              disabled={currentSupplierPage <= 1}
                              className="w-8 h-8 flex items-center justify-center border rounded-btn disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                              style={{
                                backgroundColor: "var(--bg-inset)",
                                borderColor: "var(--border)",
                                color: "var(--text)",
                              }}
                              title="Previous page"
                            >
                              <ChevronLeft className="h-4 w-4" />
                            </button>
                          );
                        }

                        if (value === PaginationItemType.DOTS) {
                          return (
                            <span
                              key={key}
                              className="w-8 h-8 flex items-center justify-center text-xs font-semibold"
                              style={{ color: "var(--text-muted)" }}
                            >
                              ...
                            </span>
                          );
                        }

                        return (
                          <button
                            ref={ref}
                            key={key}
                            type="button"
                            onClick={() => setPage(value)}
                            className="w-8 h-8 flex items-center justify-center text-xs font-semibold rounded-btn border transition-colors cursor-pointer"
                            style={{
                              backgroundColor: isActive ? "var(--ink)" : "var(--bg-inset)",
                              color: isActive ? "#FFFFFF" : "var(--text)",
                              borderColor: isActive ? "var(--ink)" : "var(--border)",
                            }}
                          >
                            {value}
                          </button>
                        );
                      }}
                    />
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {activeTab === "users" && (
        <div className="space-y-6">
          {/* Create User Form on --bg-card */}
          <div
            className="p-6 rounded-card border shadow-xs space-y-4"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <h3 className="font-semibold text-sm" style={{ color: "var(--text)" }}>
              Create New Team Member
            </h3>
            {userError && (
              <div
                className="p-3 text-xs rounded-btn border"
                style={{
                  backgroundColor: "var(--danger-soft)",
                  borderColor: "var(--danger)",
                  color: "var(--danger-strong)",
                }}
              >
                {userError}
              </div>
            )}
            {userSuccess && (
              <div
                className="p-3 text-xs rounded-btn border flex items-center space-x-2"
                style={{
                  backgroundColor: "var(--success-soft)",
                  borderColor: "var(--success)",
                  color: "var(--success-strong)",
                }}
              >
                <Check className="h-4 w-4 shrink-0" />
                <span>{userSuccess}</span>
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <input
                type="email"
                placeholder="user@invoiceflow.internal"
                value={newUserEmail}
                onChange={(e) => {
                  setNewUserEmail(e.target.value);
                  setUserError(null);
                }}
                className="px-3.5 py-2 border rounded-btn text-xs outline-none"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                  color: "var(--text)",
                }}
              />
              <input
                type="password"
                placeholder="Password (min 6 characters)"
                value={newUserPassword}
                onChange={(e) => {
                  setNewUserPassword(e.target.value);
                  setUserError(null);
                }}
                className="px-3.5 py-2 border rounded-btn text-xs outline-none"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                  color: "var(--text)",
                }}
              />
              <select
                value={newUserRole}
                onChange={(e) => setNewUserRole(e.target.value as any)}
                className="px-3.5 py-2 border rounded-btn text-xs outline-none cursor-pointer"
                style={{
                  backgroundColor: "var(--bg-inset)",
                  borderColor: "var(--border)",
                  color: "var(--text)",
                }}
              >
                <option value="reviewer">Reviewer</option>
                <option value="admin">Administrator</option>
              </select>
              <button
                onClick={() => createUserMutation.mutate()}
                disabled={!newUserEmail || !newUserPassword || createUserMutation.isPending}
                className="inline-flex items-center justify-center space-x-1.5 px-4 py-2 rounded-btn text-xs font-semibold disabled:opacity-50 transition-colors cursor-pointer shadow-xs"
                style={{
                  backgroundColor: "var(--ink)",
                  color: "#FFFFFF",
                }}
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Create User</span>
              </button>
            </div>
          </div>

          {/* Users List Table on --bg-card */}
          <div
            className="rounded-card border shadow-xs overflow-hidden"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div
              className="px-6 py-3.5 border-b text-xs font-semibold uppercase tracking-wider"
              style={{
                backgroundColor: "var(--bg-card)",
                borderColor: "var(--border)",
                color: "var(--text-muted)",
              }}
            >
              Accounts Team Users ({users.length})
            </div>
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
                    <th className="px-6 py-3.5">User Email</th>
                    <th className="px-6 py-3.5">Role</th>
                    <th className="px-6 py-3.5">Status</th>
                    <th className="px-6 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u: any) => (
                    <tr
                      key={u.id}
                      className="transition-colors text-xs"
                      style={{ borderBottom: "1px solid var(--border)" }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = "var(--accent-soft)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = "transparent";
                      }}
                    >
                      <td className="px-6 py-3.5 font-medium">{u.email}</td>
                      <td className="px-6 py-3.5">
                        <span
                          className="capitalize font-semibold px-2 py-0.5 rounded-full text-[11px] shadow-2xs"
                          style={{
                            backgroundColor: u.role === "admin" ? "var(--accent)" : "var(--success)",
                            color: "var(--ink)",
                          }}
                        >
                          {u.role}
                        </span>
                      </td>
                      <td className="px-6 py-3.5">
                        <span
                          className="px-2.5 py-0.5 rounded-full text-xs font-semibold shadow-2xs"
                          style={{
                            backgroundColor: u.is_active ? "var(--success)" : "var(--danger)",
                            color: "var(--ink)",
                          }}
                        >
                          {u.is_active ? "Active" : "Deactivated"}
                        </span>
                      </td>
                      <td className="px-6 py-3.5 text-right">
                        {u.email === "admin@invoiceflow.local" || u.email === "admin@invoiceflow.io" ? (
                          <span className="text-xs italic" style={{ color: "var(--text-muted)" }}>Primary Admin</span>
                        ) : (
                          <button
                            onClick={() =>
                              toggleUserActiveMutation.mutate({
                                userId: u.id,
                                isActive: !u.is_active,
                              })
                            }
                            className="text-xs font-semibold px-2.5 py-1 rounded-btn transition-colors cursor-pointer shadow-2xs"
                            style={{
                              backgroundColor: u.is_active ? "var(--danger)" : "var(--success)",
                              color: "var(--ink)",
                            }}
                          >
                            {u.is_active ? "Deactivate" : "Activate"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
      {activeTab === "whatsapp" && (
        <div className="space-y-6">
          <div
            className="p-6 rounded-card border shadow-xs space-y-6"
            style={{
              backgroundColor: "var(--bg-card)",
              borderColor: "var(--border)",
            }}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4" style={{ borderColor: "var(--border)" }}>
              <div>
                <h3 className="font-semibold text-base flex items-center space-x-2" style={{ color: "var(--text)" }}>
                  <MessageSquare className="h-5 w-5 text-accent" />
                  <span>WhatsApp Ingestion Gateway</span>
                </h3>
                <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                  Monitor WhatsApp session connectivity, inbound message receipt, and safe outbound pacing.
                </p>
              </div>
              <div className="flex items-center space-x-3">
                <button
                  onClick={() => refetchWhatsApp()}
                  className="flex items-center space-x-1.5 px-3 py-1.5 rounded-btn text-xs font-medium border transition-colors cursor-pointer"
                  style={{
                    backgroundColor: "var(--bg-inset)",
                    borderColor: "var(--border)",
                    color: "var(--text)",
                  }}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  <span>Refresh</span>
                </button>
                {whatsappStatus?.dashboard_url && (
                  <a
                    href={(() => {
                      try {
                        const u = new URL(whatsappStatus.dashboard_url);
                        if (u.hostname === "localhost" || u.hostname === "127.0.0.1") {
                          u.hostname = window.location.hostname;
                        }
                        return u.toString();
                      } catch {
                        return `http://${window.location.hostname}:2785`;
                      }
                    })()}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center space-x-1.5 px-3 py-1.5 rounded-btn text-xs font-semibold transition-colors shadow-2xs"
                    style={{
                      backgroundColor: "var(--ink)",
                      color: "#FFFFFF",
                    }}
                  >
                    <span>OpenWA Dashboard</span>
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            </div>

            {loadingWhatsApp ? (
              <div className="py-8 text-center text-xs" style={{ color: "var(--text-muted)" }}>
                Loading gateway status...
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Active Provider */}
                <div
                  className="p-4 rounded-card border space-y-1"
                  style={{ backgroundColor: "var(--bg-inset)", borderColor: "var(--border)" }}
                >
                  <span className="text-[11px] font-medium uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    Active Provider
                  </span>
                  <div className="text-lg font-bold capitalize" style={{ color: "var(--text)" }}>
                    {whatsappStatus?.provider || "openwa"}
                  </div>
                  <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                    {whatsappStatus?.provider === "openwa" ? "OpenWA Gateway (Self-hosted)" : "Meta Cloud API"}
                  </div>
                </div>

                {/* Session Connectivity */}
                <div
                  className="p-4 rounded-card border space-y-1"
                  style={{ backgroundColor: "var(--bg-inset)", borderColor: "var(--border)" }}
                >
                  <span className="text-[11px] font-medium uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    Session State
                  </span>
                  <div className="pt-1">
                    {(() => {
                      const state = (whatsappStatus?.state || "unknown").toLowerCase();
                      let bg = "var(--danger)";
                      let text = "var(--ink)";
                      let label = state;
                      if (state === "connected") {
                        bg = "var(--success)";
                        label = "Connected";
                      } else if (state === "needs_qr") {
                        bg = "var(--warning)";
                        label = "Needs QR Scan";
                      } else if (state === "disconnected") {
                        bg = "var(--danger)";
                        label = "Disconnected";
                      } else {
                        bg = "var(--danger)";
                        label = "Unknown";
                      }
                      return (
                        <span
                          className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold shadow-2xs"
                          style={{ backgroundColor: bg, color: text }}
                        >
                          <span className="w-1.5 h-1.5 rounded-full mr-1.5 bg-black/40" />
                          {label}
                        </span>
                      );
                    })()}
                  </div>
                  <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                    {whatsappStatus?.last_changed_at
                      ? `Updated ${new Date(whatsappStatus.last_changed_at).toLocaleTimeString()}`
                      : "No state change recorded"}
                  </div>
                </div>

                {/* Last Message Received */}
                <div
                  className="p-4 rounded-card border space-y-1"
                  style={{ backgroundColor: "var(--bg-inset)", borderColor: "var(--border)" }}
                >
                  <span className="text-[11px] font-medium uppercase tracking-wider flex items-center space-x-1" style={{ color: "var(--text-muted)" }}>
                    <Clock className="h-3 w-3" />
                    <span>Last Received</span>
                  </span>
                  <div className="text-base font-semibold" style={{ color: "var(--text)" }}>
                    {whatsappStatus?.last_received_at
                      ? new Date(whatsappStatus.last_received_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                      : "None yet"}
                  </div>
                  <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                    {whatsappStatus?.last_received_at
                      ? new Date(whatsappStatus.last_received_at).toLocaleDateString()
                      : "Awaiting first inbound invoice"}
                  </div>
                </div>

                {/* Hourly Outbound vs Cap */}
                <div
                  className="p-4 rounded-card border space-y-1"
                  style={{ backgroundColor: "var(--bg-inset)", borderColor: "var(--border)" }}
                >
                  <span className="text-[11px] font-medium uppercase tracking-wider flex items-center space-x-1" style={{ color: "var(--text-muted)" }}>
                    <Send className="h-3 w-3" />
                    <span>Hourly Outbound</span>
                  </span>
                  <div className="text-lg font-bold" style={{ color: "var(--text)" }}>
                    {whatsappStatus?.outbound_last_hour ?? 0}
                    <span className="text-xs font-normal text-muted ml-1" style={{ color: "var(--text-muted)" }}>
                      / {whatsappStatus?.outbound_cap_per_hour ?? 20} max
                    </span>
                  </div>
                  <div className="w-full bg-border rounded-full h-1.5 mt-2 overflow-hidden" style={{ backgroundColor: "var(--border)" }}>
                    <div
                      className="h-1.5 rounded-full transition-all"
                      style={{
                        width: `${Math.min(100, Math.round(((whatsappStatus?.outbound_last_hour ?? 0) / (whatsappStatus?.outbound_cap_per_hour || 20)) * 100))}%`,
                        backgroundColor: (whatsappStatus?.outbound_last_hour ?? 0) >= (whatsappStatus?.outbound_cap_per_hour || 20)
                          ? "var(--danger)"
                          : "var(--accent)",
                      }}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Recent Inbound WhatsApp Messages Table */}
            <div
              className="p-6 rounded-card border shadow-xs space-y-4"
              style={{
                backgroundColor: "var(--bg-inset)",
                borderColor: "var(--border)",
              }}
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-3" style={{ borderColor: "var(--border)" }}>
                <div>
                  <h4 className="font-semibold text-sm flex items-center space-x-2" style={{ color: "var(--text)" }}>
                    <MessageSquare className="h-4 w-4 text-accent" />
                    <span>Recent Inbound WhatsApp Messages</span>
                  </h4>
                  <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                    Live activity stream of inbound invoices and messages received by the gateway.
                  </p>
                </div>
                <span
                  className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold"
                  style={{
                    backgroundColor: "var(--bg-card)",
                    color: "var(--text-secondary)",
                    border: "1px solid var(--border)",
                  }}
                >
                  {whatsappStatus?.recent_messages?.length ?? 0} messages
                </span>
              </div>

              {(!whatsappStatus?.recent_messages || whatsappStatus.recent_messages.length === 0) ? (
                <div className="py-10 text-center space-y-2">
                  <MessageSquare className="h-8 w-8 mx-auto opacity-30" style={{ color: "var(--text-muted)" }} />
                  <p className="text-xs font-medium" style={{ color: "var(--text)" }}>
                    No WhatsApp messages received yet
                  </p>
                  <p className="text-xs max-w-md mx-auto" style={{ color: "var(--text-muted)" }}>
                    Send an invoice PDF or photo to the connected WhatsApp number (+91 90809 65547) to trigger automated intake.
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs" style={{ color: "var(--text)" }}>
                    <thead
                      className="text-[11px] font-semibold uppercase tracking-wider border-b"
                      style={{
                        backgroundColor: "var(--bg-card)",
                        color: "var(--text-secondary)",
                        borderColor: "var(--border)",
                      }}
                    >
                      <tr>
                        <th className="px-4 py-3">Received</th>
                        <th className="px-4 py-3">Sender</th>
                        <th className="px-4 py-3">Type & Content</th>
                        <th className="px-4 py-3">Gateway Status</th>
                        <th className="px-4 py-3 text-right">Pipeline / Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {whatsappStatus.recent_messages.map((msg: any) => {
                        const isDoc = msg.message_type === "document" || (msg.subject && msg.subject.toLowerCase().endsWith(".pdf"));
                        const isImg = msg.message_type === "image";
                        return (
                          <tr
                            key={msg.id}
                            className="transition-colors border-b last:border-b-0 hover:bg-black/5 dark:hover:bg-white/5"
                            style={{ borderColor: "var(--border)" }}
                          >
                            <td className="px-4 py-3 whitespace-nowrap">
                              <div className="font-semibold tabular-nums" style={{ color: "var(--text)" }}>
                                {msg.received_at ? new Date(msg.received_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : "—"}
                              </div>
                              <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                                {msg.received_at ? new Date(msg.received_at).toLocaleDateString() : ""}
                              </div>
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <div className="flex items-center space-x-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                <span className="font-mono font-medium" style={{ color: "var(--text)" }}>
                                  {msg.sender}
                                </span>
                              </div>
                              <div className="text-[10px] truncate max-w-[140px]" style={{ color: "var(--text-muted)" }} title={msg.raw_sender}>
                                {msg.raw_sender}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center space-x-2">
                                {isDoc ? (
                                  <FileText className="h-4 w-4 text-accent shrink-0" />
                                ) : isImg ? (
                                  <ImageIcon className="h-4 w-4 text-emerald-500 shrink-0" />
                                ) : (
                                  <MessageSquare className="h-4 w-4 text-muted shrink-0" />
                                )}
                                <span className="font-medium truncate max-w-[260px]" style={{ color: "var(--text)" }} title={msg.subject || ""}>
                                  {msg.subject || (isDoc ? "PDF Invoice" : isImg ? "Invoice Image" : "Text message")}
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              {msg.status === "ingested" ? (
                                <span
                                  className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold"
                                  style={{ backgroundColor: "var(--success)", color: "var(--ink)" }}
                                >
                                  Ingested
                                </span>
                              ) : msg.status === "ignored" ? (
                                <span
                                  className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold cursor-help"
                                  style={{ backgroundColor: "var(--bg-card)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
                                  title={msg.status_reason || "Skipped (no invoice attachment)"}
                                >
                                  Skipped
                                </span>
                              ) : (
                                <span
                                  className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold"
                                  style={{ backgroundColor: "var(--danger)", color: "var(--ink)" }}
                                >
                                  {msg.status}
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-right whitespace-nowrap">
                              {msg.invoice_id ? (
                                <Link
                                  to={`/invoices/${msg.invoice_id}`}
                                  className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-btn text-xs font-semibold transition-all shadow-2xs hover:opacity-90"
                                  style={{
                                    backgroundColor: "var(--ink)",
                                    color: "#FFFFFF",
                                  }}
                                >
                                  <span>Review Invoice</span>
                                  <ArrowRight className="h-3 w-3" />
                                </Link>
                              ) : (
                                <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                                  {msg.status === "ignored" ? "No invoice created" : "Processing..."}
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}