import { Pagination, PaginationItemType } from '@heroui/react';
import { useState, useRef, useMemo } from "react";
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
} from "lucide-react";

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
  const [activeTab, setActiveTab] = useState<"suppliers" | "users">("suppliers");

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
          <h1 className="text-2xl font-bold text-findeck-text tracking-tight">
            System Administration
          </h1>
          <p className="text-xs text-findeck-muted mt-1">
            Manage authorized suppliers master directory and reviewer team accounts.
          </p>
        </div>

        {/* Tab Switcher - Segmented control */}
        <div className="flex bg-findeck-card p-1 rounded-pill border border-findeck-border self-start sm:self-auto shadow-2xs">
          <button
            onClick={() => setActiveTab("suppliers")}
            className={`flex items-center space-x-2 px-4 py-1.5 rounded-pill text-xs font-medium transition-all cursor-pointer ${
              activeTab === "suppliers"
                ? "bg-white text-findeck-text shadow-xs font-semibold"
                : "text-findeck-muted hover:text-findeck-text"
            }`}
          >
            <Building2 className="h-3.5 w-3.5" />
            <span>Suppliers Master</span>
          </button>
          <button
            onClick={() => setActiveTab("users")}
            className={`flex items-center space-x-2 px-4 py-1.5 rounded-pill text-xs font-medium transition-all cursor-pointer ${
              activeTab === "users"
                ? "bg-white text-findeck-text shadow-xs font-semibold"
                : "text-findeck-muted hover:text-findeck-text"
            }`}
          >
            <Users className="h-3.5 w-3.5" />
            <span>User Accounts</span>
          </button>
        </div>
      </div>

      {activeTab === "suppliers" && (
        <div className="space-y-6">
          {/* Add Supplier & CSV Import Form */}
          <div className="bg-white p-6 rounded-card border border-findeck-border shadow-xs space-y-4">
            <h3 className="font-semibold text-findeck-text text-sm">
              Add New Verified Supplier
            </h3>
            {supplierError && (
              <div className="p-3 bg-danger-soft text-danger-strong text-xs rounded-btn border border-danger/30">
                {supplierError}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <input
                type="text"
                placeholder="GSTIN (15 characters, e.g., 27AAPFU0939F1ZV)"
                value={newGstin}
                onChange={(e) => setNewGstin(e.target.value)}
                className="px-3.5 py-2 border border-findeck-border rounded-btn text-xs font-mono outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text bg-white"
              />
              <input
                type="text"
                placeholder="Supplier Business Name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="px-3.5 py-2 border border-findeck-border rounded-btn text-xs outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text bg-white"
              />
              <div className="flex space-x-2">
                <button
                  onClick={() => createSupplierMutation.mutate()}
                  disabled={!newGstin || !newName || createSupplierMutation.isPending}
                  className="flex-1 inline-flex items-center justify-center space-x-1.5 px-4 py-2 bg-ink hover:bg-ink-hover text-white rounded-btn text-xs font-semibold disabled:opacity-50 transition-colors cursor-pointer shadow-xs"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Add Supplier</span>
                </button>
                <button
                  onClick={() => csvInputRef.current?.click()}
                  className="inline-flex items-center space-x-1.5 px-3 py-2 border border-findeck-border rounded-btn text-xs font-semibold text-findeck-text hover:bg-findeck-app transition-colors cursor-pointer bg-white"
                  title="Import CSV"
                >
                  <FileSpreadsheet className="h-4 w-4 text-ink" />
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
              <div className="mt-3 p-4 bg-findeck-app border border-findeck-border rounded-card text-xs space-y-2">
                <div className="font-semibold text-findeck-text">
                  Imported {csvResult.imported} supplier(s) successfully.
                </div>
                {csvResult.errors?.length > 0 && (
                  <div className="text-danger-strong space-y-1">
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

          {/* Suppliers List Table */}
          <div className="bg-white rounded-card border border-findeck-border shadow-xs overflow-hidden">
            <div className="px-6 py-3.5 border-b border-findeck-border bg-findeck-card flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-semibold text-findeck-muted">
              <span className="uppercase tracking-wider">Registered Master Suppliers ({suppliers.length})</span>
              <div className="relative w-full sm:w-64">
                <Search className="h-3.5 w-3.5 absolute left-3 top-2.5 text-findeck-muted" />
                <input
                  type="text"
                  placeholder="Filter suppliers by name or GSTIN..."
                  value={supplierSearch}
                  onChange={(e) => {
                    setSupplierSearch(e.target.value);
                    setSupplierPage(1);
                  }}
                  className="w-full pl-8 pr-3 py-1.5 text-xs font-normal border border-findeck-border rounded-btn outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong bg-white text-findeck-text"
                />
              </div>
            </div>
            {loadingSuppliers ? (
              <div className="p-8 text-center text-xs text-findeck-muted">Loading suppliers...</div>
            ) : suppliers.length === 0 ? (
              <div className="p-8 text-center text-xs text-findeck-muted">No suppliers registered.</div>
            ) : filteredSuppliers.length === 0 ? (
              <div className="p-8 text-center text-xs text-findeck-muted">No suppliers match your search.</div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs text-findeck-text">
                    <thead className="bg-white text-[11px] font-semibold text-text-secondary uppercase tracking-wider border-b border-findeck-border">
                      <tr>
                        <th className="px-6 py-3.5">GSTIN</th>
                        <th className="px-6 py-3.5">Supplier Name</th>
                        <th className="px-6 py-3.5">State</th>
                        <th className="px-6 py-3.5">Status</th>
                        <th className="px-6 py-3.5 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-findeck-border">
                      {paginatedSuppliers.map((s: any) => (
                        <tr key={s.id} className="hover:bg-findeck-app/50 transition-colors">
                          <td className="px-6 py-3.5 font-mono font-medium text-findeck-text">{s.gstin}</td>
                          <td className="px-6 py-3.5 font-medium text-findeck-text">{s.name}</td>
                          <td className="px-6 py-3.5 text-findeck-muted font-medium">{formatStateDisplay(s.state_code)}</td>
                          <td className="px-6 py-3.5">
                            <span
                              className={`px-2.5 py-0.5 rounded-pill text-xs font-medium border ${
                                s.is_active
                                  ? "bg-success-soft text-success-strong border-success/30"
                                  : "bg-danger-soft text-danger-strong border-danger/30"
                              }`}
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
                              className={`text-xs font-semibold px-2.5 py-1 rounded-btn transition-colors cursor-pointer border ${
                                s.is_active
                                  ? "text-danger-strong bg-danger-soft hover:bg-danger/20 border-danger/30"
                                  : "text-success-strong bg-success-soft hover:bg-success/20 border-success/30"
                              }`}
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
                <div className="px-6 py-3.5 border-t border-findeck-border bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-findeck-muted">
                  <div className="flex items-center space-x-3">
                    <span className="tabular-nums">
                      Showing{" "}
                      <strong className="text-findeck-text font-semibold">
                        {(currentSupplierPage - 1) * supplierPageSize + 1}
                      </strong>
                      –
                      <strong className="text-findeck-text font-semibold">
                        {Math.min(currentSupplierPage * supplierPageSize, filteredSuppliers.length)}
                      </strong>{" "}
                      of{" "}
                      <strong className="text-findeck-text font-semibold">
                        {filteredSuppliers.length}
                      </strong>{" "}
                      suppliers
                    </span>
                    <span className="text-findeck-border">|</span>
                    <div className="flex items-center space-x-1.5">
                      <span>Per page:</span>
                      <select
                        value={supplierPageSize}
                        onChange={(e) => {
                          setSupplierPageSize(Number(e.target.value));
                          setSupplierPage(1);
                        }}
                        className="px-2 py-0.5 border border-findeck-border rounded-btn text-xs bg-white text-findeck-text outline-none focus:border-accent-strong cursor-pointer"
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
                              className="w-8 h-8 flex items-center justify-center border border-findeck-border rounded-btn bg-white hover:bg-findeck-app text-findeck-text disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
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
                              className="w-8 h-8 flex items-center justify-center border border-findeck-border rounded-btn bg-white hover:bg-findeck-app text-findeck-text disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
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
                              className="w-8 h-8 flex items-center justify-center text-findeck-muted text-xs font-semibold"
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
                            className={`w-8 h-8 flex items-center justify-center text-xs font-semibold rounded-btn border transition-colors cursor-pointer ${
                              isActive
                                ? "bg-ink text-white border-ink shadow-xs"
                                : "border-findeck-border bg-white text-findeck-text hover:bg-findeck-app"
                            }`}
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
          {/* Create User Form */}
          <div className="bg-white p-6 rounded-card border border-findeck-border shadow-xs space-y-4">
            <h3 className="font-semibold text-findeck-text text-sm">
              Create New Team Member
            </h3>
            {userError && (
              <div className="p-3 bg-danger-soft text-danger-strong text-xs rounded-btn border border-danger/30">
                {userError}
              </div>
            )}
            {userSuccess && (
              <div className="p-3 bg-success-soft text-success-strong text-xs rounded-btn border border-success/30 flex items-center space-x-2">
                <Check className="h-4 w-4 text-success-strong shrink-0" />
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
                className="px-3.5 py-2 border border-findeck-border rounded-btn text-xs outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text bg-white"
              />
              <input
                type="password"
                placeholder="Password (min 6 characters)"
                value={newUserPassword}
                onChange={(e) => {
                  setNewUserPassword(e.target.value);
                  setUserError(null);
                }}
                className="px-3.5 py-2 border border-findeck-border rounded-btn text-xs outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text bg-white"
              />
              <select
                value={newUserRole}
                onChange={(e) => setNewUserRole(e.target.value as any)}
                className="px-3.5 py-2 border border-findeck-border rounded-btn text-xs outline-none focus:border-accent-strong focus:ring-1 focus:ring-accent-strong text-findeck-text bg-white cursor-pointer"
              >
                <option value="reviewer">Reviewer</option>
                <option value="admin">Administrator</option>
              </select>
              <button
                onClick={() => createUserMutation.mutate()}
                disabled={!newUserEmail || !newUserPassword || createUserMutation.isPending}
                className="inline-flex items-center justify-center space-x-1.5 px-4 py-2 bg-ink hover:bg-ink-hover text-white rounded-btn text-xs font-semibold disabled:opacity-50 transition-colors cursor-pointer shadow-xs"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Create User</span>
              </button>
            </div>
          </div>

          {/* Users List Table */}
          <div className="bg-white rounded-card border border-findeck-border shadow-xs overflow-hidden">
            <div className="px-6 py-3.5 border-b border-findeck-border bg-findeck-card text-xs font-semibold text-findeck-muted uppercase tracking-wider">
              Accounts Team Users ({users.length})
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-findeck-text">
                <thead className="bg-white text-[11px] font-semibold text-text-secondary uppercase tracking-wider border-b border-findeck-border">
                  <tr>
                    <th className="px-6 py-3.5">User Email</th>
                    <th className="px-6 py-3.5">Role</th>
                    <th className="px-6 py-3.5">Status</th>
                    <th className="px-6 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-findeck-border">
                  {users.map((u: any) => (
                    <tr key={u.id} className="hover:bg-findeck-app/50 transition-colors">
                      <td className="px-6 py-3.5 font-medium text-findeck-text">{u.email}</td>
                      <td className="px-6 py-3.5">
                        <span className="capitalize font-medium text-findeck-text">{u.role}</span>
                      </td>
                      <td className="px-6 py-3.5">
                        <span
                          className={`px-2.5 py-0.5 rounded-pill text-xs font-medium border ${
                            u.is_active
                              ? "bg-success-soft text-success-strong border-success/30"
                              : "bg-danger-soft text-danger-strong border-danger/30"
                          }`}
                        >
                          {u.is_active ? "Active" : "Deactivated"}
                        </span>
                      </td>
                      <td className="px-6 py-3.5 text-right">
                        {u.email === "admin@invoiceflow.io" ? (
                          <span className="text-findeck-muted text-xs italic">Primary Admin</span>
                        ) : (
                          <button
                            onClick={() =>
                              toggleUserActiveMutation.mutate({
                                userId: u.id,
                                isActive: !u.is_active,
                              })
                            }
                            className={`text-xs font-semibold px-2.5 py-1 rounded-btn transition-colors cursor-pointer border ${
                              u.is_active
                                ? "text-danger-strong bg-danger-soft hover:bg-danger/20 border-danger/30"
                                : "text-success-strong bg-success-soft hover:bg-success/20 border-success/30"
                            }`}
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
    </div>
  );
}
