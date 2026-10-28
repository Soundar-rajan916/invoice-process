import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import {
  Users,
  Building2,
  Plus,
  FileSpreadsheet,
} from "lucide-react";

export function Admin() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"suppliers" | "users">("suppliers");

  // Supplier state
  const [newGstin, setNewGstin] = useState("");
  const [newName, setNewName] = useState("");
  const [supplierError, setSupplierError] = useState<string | null>(null);
  const [csvResult, setCsvResult] = useState<any | null>(null);
  const csvInputRef = useRef<HTMLInputElement>(null);

  // User state
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState<"reviewer" | "admin">("reviewer");
  const [userError, setUserError] = useState<string | null>(null);

  // 1. Fetch Suppliers
  const { data: suppliers = [], isLoading: loadingSuppliers } = useQuery({
    queryKey: ["admin-suppliers"],
    queryFn: () => apiRequest("/api/v1/admin/suppliers"),
  });

  // 2. Fetch Users
  const { data: users = [] } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiRequest("/api/v1/admin/users"),
  });

  // Create Supplier
  const createSupplierMutation = useMutation({
    mutationFn: () => {
      return apiRequest("/api/v1/admin/suppliers", {
        method: "POST",
        body: JSON.stringify({ gstin: newGstin.trim(), name: newName.trim() }),
      });
    },
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
      return apiRequest("/api/v1/admin/users", {
        method: "POST",
        body: JSON.stringify({
          email: newUserEmail.trim(),
          password: newUserPassword,
          role: newUserRole,
        }),
      });
    },
    onSuccess: () => {
      setNewUserEmail("");
      setNewUserPassword("");
      setUserError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err: any) => {
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
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">System Administration</h1>
          <p className="text-sm text-slate-600 mt-1">
            Manage authorized suppliers master directory and reviewer team accounts.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex bg-slate-200/80 p-1 rounded-xl">
          <button
            onClick={() => setActiveTab("suppliers")}
            className={`flex items-center space-x-2 px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === "suppliers"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Building2 className="h-4 w-4" />
            <span>Suppliers Master</span>
          </button>
          <button
            onClick={() => setActiveTab("users")}
            className={`flex items-center space-x-2 px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === "users"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Users className="h-4 w-4" />
            <span>User Accounts</span>
          </button>
        </div>
      </div>

      {activeTab === "suppliers" && (
        <div className="space-y-6">
          {/* Add Supplier & CSV Import Form */}
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
            <h3 className="font-bold text-slate-900 text-sm">Add New Verified Supplier</h3>
            {supplierError && (
              <div className="p-3 bg-red-50 text-red-700 text-xs rounded-lg border border-red-200">
                {supplierError}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <input
                type="text"
                placeholder="GSTIN (15 characters, e.g., 27AAPFU0939F1ZV)"
                value={newGstin}
                onChange={(e) => setNewGstin(e.target.value)}
                className="px-3.5 py-2 border border-slate-300 rounded-lg text-xs font-mono outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <input
                type="text"
                placeholder="Supplier Business Name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="px-3.5 py-2 border border-slate-300 rounded-lg text-xs outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <div className="flex space-x-2">
                <button
                  onClick={() => createSupplierMutation.mutate()}
                  disabled={!newGstin || !newName || createSupplierMutation.isPending}
                  className="flex-1 inline-flex items-center justify-center space-x-1.5 px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Add Supplier</span>
                </button>
                <button
                  onClick={() => csvInputRef.current?.click()}
                  className="inline-flex items-center space-x-1 px-3 py-2 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  title="Import CSV"
                >
                  <FileSpreadsheet className="h-4 w-4 text-emerald-600" />
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
              <div className="mt-3 p-4 bg-slate-50 border border-slate-200 rounded-xl text-xs space-y-2">
                <div className="font-semibold text-slate-800">
                  Imported {csvResult.imported} supplier(s) successfully.
                </div>
                {csvResult.errors?.length > 0 && (
                  <div className="text-red-600 space-y-1">
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
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-3.5 border-b border-slate-100 bg-slate-50/50 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Registered Master Suppliers ({suppliers.length})
            </div>
            {loadingSuppliers ? (
              <div className="p-8 text-center text-xs text-slate-500">Loading suppliers...</div>
            ) : suppliers.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">No suppliers registered.</div>
            ) : (
              <table className="w-full text-left text-sm text-slate-600">
                <thead className="bg-slate-50 text-xs text-slate-500 border-b border-slate-100">
                  <tr>
                    <th className="px-6 py-3 font-semibold">GSTIN</th>
                    <th className="px-6 py-3 font-semibold">Supplier Name</th>
                    <th className="px-6 py-3 font-semibold">State</th>
                    <th className="px-6 py-3 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {suppliers.map((s: any) => (
                    <tr key={s.id} className="hover:bg-slate-50/50 text-xs">
                      <td className="px-6 py-3 font-mono font-medium text-slate-900">{s.gstin}</td>
                      <td className="px-6 py-3 font-medium text-slate-800">{s.name}</td>
                      <td className="px-6 py-3 text-slate-500">{s.state_code}</td>
                      <td className="px-6 py-3">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800">
                          Active
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {activeTab === "users" && (
        <div className="space-y-6">
          {/* Create User Form */}
          <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
            <h3 className="font-bold text-slate-900 text-sm">Create New Team Member</h3>
            {userError && (
              <div className="p-3 bg-red-50 text-red-700 text-xs rounded-lg border border-red-200">
                {userError}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <input
                type="email"
                placeholder="user@invoiceflow.internal"
                value={newUserEmail}
                onChange={(e) => setNewUserEmail(e.target.value)}
                className="px-3.5 py-2 border border-slate-300 rounded-lg text-xs outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <input
                type="password"
                placeholder="Secure Password"
                value={newUserPassword}
                onChange={(e) => setNewUserPassword(e.target.value)}
                className="px-3.5 py-2 border border-slate-300 rounded-lg text-xs outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <select
                value={newUserRole}
                onChange={(e) => setNewUserRole(e.target.value as any)}
                className="px-3.5 py-2 border border-slate-300 rounded-lg text-xs outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="reviewer">Reviewer</option>
                <option value="admin">Administrator</option>
              </select>
              <button
                onClick={() => createUserMutation.mutate()}
                disabled={!newUserEmail || !newUserPassword || createUserMutation.isPending}
                className="inline-flex items-center justify-center space-x-1.5 px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Create User</span>
              </button>
            </div>
          </div>

          {/* Users List Table */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-6 py-3.5 border-b border-slate-100 bg-slate-50/50 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Accounts Team Users ({users.length})
            </div>
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs text-slate-500 border-b border-slate-100">
                <tr>
                  <th className="px-6 py-3 font-semibold">User Email</th>
                  <th className="px-6 py-3 font-semibold">Role</th>
                  <th className="px-6 py-3 font-semibold">Status</th>
                  <th className="px-6 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.map((u: any) => (
                  <tr key={u.id} className="hover:bg-slate-50/50 text-xs">
                    <td className="px-6 py-3 font-medium text-slate-900">{u.email}</td>
                    <td className="px-6 py-3">
                      <span className="capitalize font-medium text-slate-700">{u.role}</span>
                    </td>
                    <td className="px-6 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          u.is_active
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-red-100 text-red-800"
                        }`}
                      >
                        {u.is_active ? "Active" : "Deactivated"}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-right">
                      <button
                        onClick={() =>
                          toggleUserActiveMutation.mutate({
                            userId: u.id,
                            isActive: !u.is_active,
                          })
                        }
                        className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
                      >
                        {u.is_active ? "Deactivate" : "Activate"}
                      </button>
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
}
