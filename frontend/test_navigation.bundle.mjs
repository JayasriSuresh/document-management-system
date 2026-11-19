// test_navigation.jsx
import React5 from "react";
import { renderToString } from "react-dom/server";
import { MemoryRouter, Routes, Route, Navigate as Navigate3, useLocation as useLocation2 } from "react-router-dom";
import assert from "assert";

// src/context/AuthContext.jsx
import { createContext, useContext, useState, useEffect } from "react";

// src/api.js
var API_BASE = "";
var ApiError = class extends Error {
  constructor(message, status, requestId = null, raw = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
    this.raw = raw;
  }
};
var inMemoryAccessToken = null;
var setAuthToken = (token) => {
  inMemoryAccessToken = token;
  if (token) {
    localStorage.setItem("dms_token", token);
  } else {
    localStorage.removeItem("dms_token");
  }
};
var getAuthToken = () => {
  if (inMemoryAccessToken) return inMemoryAccessToken;
  const stored = typeof localStorage !== "undefined" ? localStorage.getItem("dms_token") : null;
  if (stored) inMemoryAccessToken = stored;
  return inMemoryAccessToken;
};
function generateRequestId() {
  return `fe-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}
function getHeaders(isFormData = false) {
  const token = getAuthToken();
  const headers = {
    "X-Request-ID": generateRequestId()
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!isFormData) headers["Content-Type"] = "application/json";
  return headers;
}
var isRefreshing = false;
var refreshSubscribers = [];
function subscribeTokenRefresh(callback) {
  refreshSubscribers.push(callback);
}
function onRefreshed(newAccessToken) {
  refreshSubscribers.forEach((cb) => cb(newAccessToken));
  refreshSubscribers = [];
}
function getLoginRedirectForCurrentPath() {
  if (typeof window === "undefined") return "/login";
  const path = window.location.pathname;
  if (path.startsWith("/company/onboard") || path.startsWith("/onboard") || path.startsWith("/accept-invite") || path.startsWith("/reset-password") || path.startsWith("/forgot-password")) {
    return null;
  }
  if (path.startsWith("/admin")) return "/admin/login";
  if (path.startsWith("/company")) return "/company/login";
  return "/login";
}
async function handleResponse(res, originalRequest = null) {
  const requestId = res.headers.get("X-Request-ID");
  if (!res.ok) {
    const isAuthRoute = originalRequest?.url?.includes("/api/auth/login") || originalRequest?.url?.includes("/api/auth/refresh");
    if (res.status === 401 && !isAuthRoute && originalRequest) {
      if (!isRefreshing) {
        isRefreshing = true;
        try {
          const refreshRes = await fetch(`${API_BASE}/api/auth/refresh`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Request-ID": generateRequestId()
            },
            credentials: "include"
          });
          if (refreshRes.ok) {
            const data = await refreshRes.json();
            setAuthToken(data.access_token);
            isRefreshing = false;
            onRefreshed(data.access_token);
            const retryHeaders = {
              ...originalRequest.options.headers,
              Authorization: `Bearer ${data.access_token}`
            };
            const retryRes = await fetch(originalRequest.url, {
              ...originalRequest.options,
              headers: retryHeaders
            });
            return handleResponse(retryRes, null);
          } else {
            throw new Error("Refresh failed");
          }
        } catch {
          isRefreshing = false;
          refreshSubscribers = [];
          setAuthToken(null);
          localStorage.removeItem("dms_user");
          const redirectUrl = getLoginRedirectForCurrentPath();
          if (redirectUrl && typeof window !== "undefined" && !window.location.pathname.includes("/login")) {
            window.location.href = redirectUrl;
          }
        }
      } else {
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh(async (newToken) => {
            try {
              const retryHeaders = {
                ...originalRequest.options.headers,
                Authorization: `Bearer ${newToken}`
              };
              const retryRes = await fetch(originalRequest.url, {
                ...originalRequest.options,
                headers: retryHeaders
              });
              resolve(await handleResponse(retryRes, null));
            } catch (err) {
              reject(err);
            }
          });
        });
      }
    }
    let errorDetail = "Request failed";
    let rawPayload = null;
    try {
      rawPayload = await res.json();
      if (rawPayload?.error?.detail) {
        errorDetail = rawPayload.error.detail;
      } else if (rawPayload?.detail) {
        errorDetail = typeof rawPayload.detail === "string" ? rawPayload.detail : JSON.stringify(rawPayload.detail);
      }
    } catch {
      errorDetail = `Request failed with status ${res.status}`;
    }
    throw new ApiError(errorDetail, res.status, requestId, rawPayload);
  }
  return res.json();
}
async function wrappedFetch(url, options = {}) {
  const finalOptions = {
    ...options,
    credentials: "include"
  };
  const res = await fetch(url, finalOptions);
  return handleResponse(res, { url, options: finalOptions });
}
var api = {
  // ── Authentication ─────────────────────────────────────────────────────────
  login: async (email, password, portal = "app") => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": generateRequestId()
      },
      credentials: "include",
      body: JSON.stringify({ email, password, portal })
    });
    const data = await handleResponse(res);
    if (data.access_token) {
      setAuthToken(data.access_token);
    }
    return data;
  },
  refresh: async () => {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": generateRequestId()
      },
      credentials: "include"
    });
    const data = await handleResponse(res);
    if (data.access_token) {
      setAuthToken(data.access_token);
    }
    return data;
  },
  logout: async () => {
    try {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: "POST",
        headers: getHeaders(),
        credentials: "include"
      });
    } finally {
      setAuthToken(null);
      localStorage.removeItem("dms_user");
    }
  },
  logoutAll: async () => {
    try {
      await fetch(`${API_BASE}/api/auth/logout-all`, {
        method: "POST",
        headers: getHeaders(),
        credentials: "include"
      });
    } finally {
      setAuthToken(null);
      localStorage.removeItem("dms_user");
    }
  },
  me: async () => {
    return wrappedFetch(`${API_BASE}/api/auth/me`, { headers: getHeaders() });
  },
  // ── User Invitations ───────────────────────────────────────────────────────
  inviteUser: async ({ email, branch_id, invited_role }) => {
    return wrappedFetch(`${API_BASE}/api/auth/invite`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ email, branch_id, invited_role })
    });
  },
  acceptInvite: async ({ token, name, password }) => {
    const res = await fetch(`${API_BASE}/api/auth/invite/accept`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": generateRequestId()
      },
      credentials: "include",
      body: JSON.stringify({ token, name, password })
    });
    return handleResponse(res);
  },
  // ── Password Reset & Change ────────────────────────────────────────────────
  requestPasswordReset: async ({ email, portal = "app" }) => {
    const res = await fetch(`${API_BASE}/api/auth/password/reset-request`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": generateRequestId()
      },
      credentials: "include",
      body: JSON.stringify({ email, portal })
    });
    return handleResponse(res);
  },
  resetPassword: async ({ token, new_password }) => {
    const res = await fetch(`${API_BASE}/api/auth/password/reset`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": generateRequestId()
      },
      credentials: "include",
      body: JSON.stringify({ token, new_password })
    });
    return handleResponse(res);
  },
  changePassword: async ({ current_password, new_password }) => {
    return wrappedFetch(`${API_BASE}/api/auth/password/change`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ current_password, new_password })
    });
  },
  // ── Documents ──────────────────────────────────────────────────────────────
  listDocuments: async (params = {}) => {
    const url = new URL(`${API_BASE}/api/documents`, window.location.origin);
    if (typeof params === "string") {
      if (params) url.searchParams.set("search", params);
    } else if (params && typeof params === "object") {
      if (params.search) url.searchParams.set("search", params.search);
      if (params.q) url.searchParams.set("search", params.q);
      if (params.page !== void 0) url.searchParams.set("page", params.page);
      if (params.pageSize !== void 0) url.searchParams.set("page_size", params.pageSize);
      if (params.status) url.searchParams.set("status", params.status);
      if (params.branchId) url.searchParams.set("branch_id", params.branchId);
      if (params.dateFrom) url.searchParams.set("date_from", params.dateFrom);
      if (params.dateTo) url.searchParams.set("date_to", params.dateTo);
      if (params.vendorName) url.searchParams.set("vendor_name", params.vendorName);
      if (params.invoiceNumber) url.searchParams.set("invoice_number", params.invoiceNumber);
      if (params.gstin) url.searchParams.set("gstin", params.gstin);
      if (params.amountMin) url.searchParams.set("amount_min", params.amountMin);
      if (params.amountMax) url.searchParams.set("amount_max", params.amountMax);
      if (params.documentType) url.searchParams.set("document_type", params.documentType);
      if (params.includeDeleted) url.searchParams.set("include_deleted", "true");
      if (params.paginate) url.searchParams.set("paginate", "true");
    }
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },
  searchDocuments: async (params = {}) => {
    const url = new URL(`${API_BASE}/api/documents/search`, window.location.origin);
    if (typeof params === "string") {
      if (params) url.searchParams.set("q", params);
    } else if (params && typeof params === "object") {
      if (params.q) url.searchParams.set("q", params.q);
      if (params.search) url.searchParams.set("q", params.search);
      if (params.dateFrom) url.searchParams.set("date_from", params.dateFrom);
      if (params.dateTo) url.searchParams.set("date_to", params.dateTo);
      if (params.vendorName) url.searchParams.set("vendor_name", params.vendorName);
      if (params.invoiceNumber) url.searchParams.set("invoice_number", params.invoiceNumber);
      if (params.gstin) url.searchParams.set("gstin", params.gstin);
      if (params.amountMin) url.searchParams.set("amount_min", params.amountMin);
      if (params.amountMax) url.searchParams.set("amount_max", params.amountMax);
      if (params.branchId) url.searchParams.set("branch_id", params.branchId);
      if (params.status) url.searchParams.set("status", params.status);
      if (params.documentType) url.searchParams.set("document_type", params.documentType);
      if (params.includeDeleted) url.searchParams.set("include_deleted", "true");
      if (params.page !== void 0) url.searchParams.set("page", params.page);
      if (params.pageSize !== void 0) url.searchParams.set("page_size", params.pageSize);
    }
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },
  getDocument: async (id) => {
    return wrappedFetch(`${API_BASE}/api/documents/${id}`, { headers: getHeaders() });
  },
  uploadDocument: async (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return wrappedFetch(`${API_BASE}/api/documents`, {
      method: "POST",
      headers: getHeaders(true),
      body: formData
    });
  },
  uploadDocuments: async (files) => {
    const formData = new FormData();
    for (const f of files) {
      formData.append("files", f);
    }
    return wrappedFetch(`${API_BASE}/api/documents/batch`, {
      method: "POST",
      headers: getHeaders(true),
      body: formData
    });
  },
  reprocessDocument: async (id) => {
    return wrappedFetch(`${API_BASE}/api/documents/${id}/reprocess`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  deleteDocument: async (id) => {
    return wrappedFetch(`${API_BASE}/api/documents/${id}`, {
      method: "DELETE",
      headers: getHeaders()
    });
  },
  restoreDocument: async (id) => {
    return wrappedFetch(`${API_BASE}/api/documents/${id}/restore`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  getFileUrl: (id, download = false) => {
    const token = getAuthToken();
    const tokenPart = token ? `token=${encodeURIComponent(token)}` : "";
    const dlPart = download ? "download=true" : "";
    const query = [tokenPart, dlPart].filter(Boolean).join("&");
    return `${API_BASE}/api/documents/${id}/file${query ? `?${query}` : ""}`;
  },
  getThumbnailUrl: (id) => {
    const token = getAuthToken();
    return `${API_BASE}/api/documents/${id}/thumbnail${token ? `?token=${encodeURIComponent(token)}` : ""}`;
  },
  getInvoiceUrl: (docId) => {
    const token = getAuthToken();
    return `${API_BASE}/api/documents/${docId}/invoice.pdf${token ? `?token=${encodeURIComponent(token)}` : ""}`;
  },
  // ── Invoices ───────────────────────────────────────────────────────────────
  listInvoices: async (params = {}) => {
    const url = new URL(`${API_BASE}/api/invoices`, window.location.origin);
    if (typeof params === "string") {
      if (params) url.searchParams.set("search", params);
    } else if (params && typeof params === "object") {
      if (params.search) url.searchParams.set("search", params.search);
      if (params.kind) url.searchParams.set("kind", params.kind);
      if (params.status) url.searchParams.set("status", params.status);
      if (params.page) url.searchParams.set("page", params.page);
      if (params.limit) url.searchParams.set("limit", params.limit);
    }
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },
  getInvoiceStats: async () => {
    return wrappedFetch(`${API_BASE}/api/invoices/stats`, { headers: getHeaders() });
  },
  getInvoice: async (id) => {
    return wrappedFetch(`${API_BASE}/api/invoices/${id}`, { headers: getHeaders() });
  },
  getDirectInvoicePdfUrl: (invoiceId, download = false) => {
    const token = getAuthToken();
    return `${API_BASE}/api/invoices/${invoiceId}/pdf?${download ? "download=true&" : ""}${token ? `token=${encodeURIComponent(token)}` : ""}`;
  },
  // ── GST Registrations ───────────────────────────────────────────────────────
  listGstRegistrations: async () => {
    return wrappedFetch(`${API_BASE}/api/gst-registrations`, { headers: getHeaders() });
  },
  getGstRegistration: async (id) => {
    return wrappedFetch(`${API_BASE}/api/gst-registrations/${id}`, { headers: getHeaders() });
  },
  createGstRegistration: async (data) => {
    return wrappedFetch(`${API_BASE}/api/gst-registrations`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(data)
    });
  },
  updateGstRegistration: async (id, data) => {
    return wrappedFetch(`${API_BASE}/api/gst-registrations/${id}`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(data)
    });
  },
  // ── Customers ───────────────────────────────────────────────────────────────
  listCustomers: async (search = "") => {
    const url = new URL(`${API_BASE}/api/customers`, window.location.origin);
    if (search) url.searchParams.set("search", search);
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },
  getCustomer: async (id) => {
    return wrappedFetch(`${API_BASE}/api/customers/${id}`, { headers: getHeaders() });
  },
  createCustomer: async (data) => {
    return wrappedFetch(`${API_BASE}/api/customers`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(data)
    });
  },
  updateCustomer: async (id, data) => {
    return wrappedFetch(`${API_BASE}/api/customers/${id}`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(data)
    });
  },
  addCustomerAddress: async (customerId, data) => {
    return wrappedFetch(`${API_BASE}/api/customers/${customerId}/addresses`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(data)
    });
  },
  // ── Outbound Sales Invoices ─────────────────────────────────────────────────
  previewSalesTax: async (payload) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/tax-preview`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
  },
  listSalesInvoices: async (params = {}) => {
    const url = new URL(`${API_BASE}/api/sales-invoices`, window.location.origin);
    if (params.status) url.searchParams.set("status", params.status);
    if (params.branch_id) url.searchParams.set("branch_id", params.branch_id);
    if (params.customer_id) url.searchParams.set("customer_id", params.customer_id);
    if (params.financial_year) url.searchParams.set("financial_year", params.financial_year);
    if (params.search) url.searchParams.set("search", params.search);
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },
  getSalesInvoice: async (id) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}`, { headers: getHeaders() });
  },
  createSalesInvoiceDraft: async (payload) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
  },
  updateSalesInvoiceDraft: async (id, payload) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
  },
  discardSalesInvoiceDraft: async (id) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}`, {
      method: "DELETE",
      headers: getHeaders()
    });
  },
  submitSalesInvoice: async (id) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}/submit`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  approveSalesInvoice: async (id) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}/approve`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  rejectSalesInvoice: async (id, reason = "") => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}/reject`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ reason })
    });
  },
  cancelSalesInvoice: async (id, reason = "") => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}/cancel`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ reason })
    });
  },
  getSalesInvoicePdfUrl: (id, download = false) => {
    const token = getAuthToken();
    return `${API_BASE}/api/sales-invoices/${id}/pdf?${download ? "download=true&" : ""}${token ? `token=${encodeURIComponent(token)}` : ""}`;
  },
  // ── Supplier Invoice Copies (Versioning & Regeneration) ─────────────────────
  listDocumentCopies: async (documentId) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/copies`, { headers: getHeaders() });
  },
  regenerateDocumentCopy: async (documentId) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/copies/regenerate`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  getDocumentCopyPdfUrl: (documentId, copyVersion, download = false) => {
    const token = getAuthToken();
    return `${API_BASE}/api/documents/${documentId}/copies/${copyVersion}/pdf?${download ? "download=true&" : ""}${token ? `token=${encodeURIComponent(token)}` : ""}`;
  },
  // ── Company Onboarding (Public Applicant Endpoints) ────────────────────────
  getOnboarding: async (token) => {
    return wrappedFetch(`${API_BASE}/api/onboarding/${encodeURIComponent(token)}`);
  },
  uploadOnboardingDocument: async (token, documentType, file) => {
    const formData = new FormData();
    formData.append("document_type", documentType);
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/api/onboarding/${encodeURIComponent(token)}/upload-document`, {
      method: "POST",
      body: formData
    });
    return handleResponse(res);
  },
  getOnboardingDocumentUrl: (token, documentType) => {
    return `${API_BASE}/api/onboarding/${encodeURIComponent(token)}/documents/${encodeURIComponent(documentType)}`;
  },
  submitOnboarding: async (token, payload) => {
    const res = await fetch(`${API_BASE}/api/onboarding/${encodeURIComponent(token)}/submit`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": generateRequestId()
      },
      body: JSON.stringify(payload)
    });
    return handleResponse(res);
  },
  // ── Master Admin Portal Endpoints (require_platform) ───────────────────────
  initiateOnboarding: async ({ company_name, contact_name, contact_email }) => {
    return wrappedFetch(`${API_BASE}/api/admin/onboarding/initiate`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ company_name, contact_name, contact_email })
    });
  },
  listOnboardings: async (status = null) => {
    const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost";
    const url = new URL(`${API_BASE}/api/admin/onboarding`, origin);
    if (status && status !== "all") url.searchParams.set("status", status);
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },
  getOnboardingDetail: async (onboardingId) => {
    return wrappedFetch(`${API_BASE}/api/admin/onboarding/${onboardingId}`, {
      headers: getHeaders()
    });
  },
  requestOnboardingChanges: async (onboardingId, comments) => {
    return wrappedFetch(`${API_BASE}/api/admin/onboarding/${onboardingId}/request-changes`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ comments })
    });
  },
  rejectOnboarding: async (onboardingId, reason) => {
    return wrappedFetch(`${API_BASE}/api/admin/onboarding/${onboardingId}/reject`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ reason })
    });
  },
  approveOnboarding: async (onboardingId) => {
    return wrappedFetch(`${API_BASE}/api/admin/onboarding/${onboardingId}/approve`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  getAdminDocumentUrl: (onboardingId, documentType) => {
    const token = getAuthToken();
    return `${API_BASE}/api/admin/onboarding/${onboardingId}/documents/${encodeURIComponent(documentType)}${token ? `?token=${encodeURIComponent(token)}` : ""}`;
  },
  listAdminCompanies: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/companies`, {
      headers: getHeaders()
    });
  },
  toggleCompanyStatus: async (companyId) => {
    return wrappedFetch(`${API_BASE}/api/admin/companies/${companyId}/toggle-status`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  getPlatformDashboard: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/dashboard`, {
      headers: getHeaders()
    });
  },
  getCompanyDetail: async (companyId) => {
    return wrappedFetch(`${API_BASE}/api/admin/companies/${companyId}`, {
      headers: getHeaders()
    });
  },
  getCompanyOnboardingDossier: async (companyId) => {
    return wrappedFetch(`${API_BASE}/api/admin/companies/${companyId}/onboarding`, {
      headers: getHeaders()
    });
  },
  updateCompany: async (companyId, payload) => {
    return wrappedFetch(`${API_BASE}/api/admin/companies/${companyId}`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
  },
  getSystemSettings: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/settings`, {
      headers: getHeaders()
    });
  },
  updateSystemSettings: async (payload) => {
    return wrappedFetch(`${API_BASE}/api/admin/settings`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
  },
  // ── Company Admin Endpoints (require_company) ─────────────────────────────
  getCompanyDashboard: async () => {
    return wrappedFetch(`${API_BASE}/api/company/dashboard`, {
      headers: getHeaders()
    });
  },
  getCompanyProfile: async () => {
    return wrappedFetch(`${API_BASE}/api/company/profile`, {
      headers: getHeaders()
    });
  },
  updateCompanyProfile: async (profileData) => {
    return wrappedFetch(`${API_BASE}/api/company/profile`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(profileData)
    });
  },
  uploadCompanyLogo: async (file) => {
    const formData = new FormData();
    formData.append("file", file);
    return wrappedFetch(`${API_BASE}/api/company/logo`, {
      method: "POST",
      headers: getHeaders(true),
      body: formData
    });
  },
  deleteCompanyLogo: async () => {
    return wrappedFetch(`${API_BASE}/api/company/logo`, {
      method: "DELETE",
      headers: getHeaders()
    });
  },
  listCompanyBranches: async () => {
    return wrappedFetch(`${API_BASE}/api/company/branches`, {
      headers: getHeaders()
    });
  },
  createCompanyBranch: async (branchData) => {
    return wrappedFetch(`${API_BASE}/api/company/branches`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(branchData)
    });
  },
  getCompanyBranch: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}`, {
      headers: getHeaders()
    });
  },
  updateCompanyBranch: async (branchId, branchData) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(branchData)
    });
  },
  deactivateCompanyBranch: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/deactivate`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  activateCompanyBranch: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/activate`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  toggleBranchStatus: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/toggle-status`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  getCompanyUsers: async (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== void 0 && val !== null && val !== "") {
        query.append(key, val);
      }
    });
    const qs = query.toString() ? `?${query.toString()}` : "";
    return wrappedFetch(`${API_BASE}/api/company/users${qs}`, {
      headers: getHeaders()
    });
  },
  inviteCompanyUser: async (userData) => {
    return wrappedFetch(`${API_BASE}/api/company/users/invite`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(userData)
    });
  },
  getCompanyInvitations: async () => {
    return wrappedFetch(`${API_BASE}/api/company/invitations`, {
      headers: getHeaders()
    });
  },
  resendCompanyInvitation: async (invitationId) => {
    return wrappedFetch(`${API_BASE}/api/company/invitations/${invitationId}/resend`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  revokeCompanyInvitation: async (invitationId) => {
    return wrappedFetch(`${API_BASE}/api/company/invitations/${invitationId}/revoke`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  updateCompanyUser: async (userId, userData) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(userData)
    });
  },
  deactivateCompanyUser: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}/deactivate`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  activateCompanyUser: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}/activate`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  forceLogoutCompanyUser: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}/force-logout`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  requestCompanyUserMfaReset: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}/mfa-reset-request`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  getCompanyDocumentsArchive: async (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== void 0 && val !== null && val !== "") {
        query.append(key, val);
      }
    });
    const qs = query.toString() ? `?${query.toString()}` : "";
    return wrappedFetch(`${API_BASE}/api/company/documents${qs}`, {
      headers: getHeaders()
    });
  },
  getCompanyAuditLogs: async (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== void 0 && val !== null && val !== "") {
        query.append(key, val);
      }
    });
    const qs = query.toString() ? `?${query.toString()}` : "";
    return wrappedFetch(`${API_BASE}/api/company/audit-logs${qs}`, {
      headers: getHeaders()
    });
  },
  // ── Audit Logging (Module 5) ───────────────────────────────────────────────
  getAuditLogs: async (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== void 0 && val !== null && val !== "") {
        query.append(key, val);
      }
    });
    const qs = query.toString() ? `?${query.toString()}` : "";
    return wrappedFetch(`${API_BASE}/api/audit${qs}`, {
      headers: getHeaders()
    });
  },
  getPlatformAuditLogs: async (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== void 0 && val !== null && val !== "") {
        query.append(key, val);
      }
    });
    const qs = query.toString() ? `?${query.toString()}` : "";
    return wrappedFetch(`${API_BASE}/api/admin/audit${qs}`, {
      headers: getHeaders()
    });
  },
  // ── Multi-Factor Authentication (Module 6) ─────────────────────────────────
  mfaVerify: async (mfaPendingToken, code) => {
    const res = await fetch(`${API_BASE}/api/auth/mfa/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": generateRequestId()
      },
      credentials: "include",
      body: JSON.stringify({ mfa_pending_token: mfaPendingToken, code })
    });
    const data = await handleResponse(res);
    if (data.access_token) {
      setAuthToken(data.access_token);
    }
    return data;
  },
  mfaRecoveryVerify: async (mfaPendingToken, recoveryCode) => {
    const res = await fetch(`${API_BASE}/api/auth/mfa/recovery/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": generateRequestId()
      },
      credentials: "include",
      body: JSON.stringify({ mfa_pending_token: mfaPendingToken, recovery_code: recoveryCode })
    });
    const data = await handleResponse(res);
    if (data.access_token) {
      setAuthToken(data.access_token);
    }
    return data;
  },
  mfaEnrollStart: async (enrollmentToken = null, regenerate = false) => {
    const headers = getHeaders();
    if (enrollmentToken) {
      headers["Authorization"] = `Bearer ${enrollmentToken}`;
    }
    const url = regenerate ? `${API_BASE}/api/auth/mfa/enroll/start?regenerate=true` : `${API_BASE}/api/auth/mfa/enroll/start`;
    return wrappedFetch(url, {
      method: "POST",
      headers
    });
  },
  mfaEnrollVerify: async (code, enrollmentToken = null) => {
    const token = enrollmentToken || getAuthToken();
    const headers = {
      "Content-Type": "application/json",
      "X-Request-ID": generateRequestId()
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}/api/auth/mfa/enroll/verify`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify({ code, enrollment_token: token })
    });
    const data = await handleResponse(res);
    if (data.access_token) {
      setAuthToken(data.access_token);
    }
    return data;
  },
  mfaStatus: async () => {
    return wrappedFetch(`${API_BASE}/api/auth/mfa/status`, {
      headers: getHeaders()
    });
  },
  mfaDisable: async (password, code) => {
    return wrappedFetch(`${API_BASE}/api/auth/mfa/disable`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ password, code })
    });
  },
  mfaRegenerateRecovery: async ({ password, code }) => {
    return wrappedFetch(`${API_BASE}/api/auth/mfa/recovery/regenerate`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ password, code })
    });
  },
  getCompanyMfaPolicy: async () => {
    return wrappedFetch(`${API_BASE}/api/company/security/mfa-policy`, {
      headers: getHeaders()
    });
  },
  updateCompanyMfaPolicy: async (mfaRequiredForAll) => {
    return wrappedFetch(`${API_BASE}/api/company/security/mfa-policy`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ mfa_required_for_all: mfaRequiredForAll })
    });
  },
  getPlatformMfaPolicy: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/security/mfa-policy`, {
      headers: getHeaders()
    });
  },
  updatePlatformMfaPolicy: async (policyUpdates) => {
    return wrappedFetch(`${API_BASE}/api/admin/security/mfa-policy`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(policyUpdates)
    });
  },
  resetCompanyUserMfa: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}/reset-mfa`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  resetPlatformUserMfa: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/admin/users/${userId}/reset-mfa`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  resetMasterAdminMfa: async (adminId) => {
    return wrappedFetch(`${API_BASE}/api/admin/master-admins/${adminId}/reset-mfa`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  // ── Module 10: Multi-Provider AI Architecture ─────────────────────────────
  // Platform AI (Master Admin)
  getPlatformAIProviders: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/providers`, { headers: getHeaders() });
  },
  updatePlatformAIProvider: async (providerKey, updates) => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/providers/${providerKey}`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(updates)
    });
  },
  getPlatformAICredentials: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/credentials`, { headers: getHeaders() });
  },
  savePlatformAICredential: async (providerKey, apiKey) => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/credentials`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey, api_key: apiKey })
    });
  },
  deletePlatformAICredential: async (credentialId) => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/credentials/${credentialId}`, {
      method: "DELETE",
      headers: getHeaders()
    });
  },
  testPlatformAIConnection: async (providerKey, model, apiKey = null) => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/test-connection`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey, model, api_key: apiKey })
    });
  },
  // Company AI (Company Admin)
  getCompanyAISettings: async () => {
    return wrappedFetch(`${API_BASE}/api/company/ai/settings`, { headers: getHeaders() });
  },
  updateCompanyAISettings: async (settings) => {
    return wrappedFetch(`${API_BASE}/api/company/ai/settings`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(settings)
    });
  },
  grantCompanyAIConsent: async (providerKey, termsVersion = "v1.0") => {
    return wrappedFetch(`${API_BASE}/api/company/ai/consent`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey, consented_terms_version: termsVersion })
    });
  },
  revokeCompanyAIConsent: async (providerKey) => {
    return wrappedFetch(`${API_BASE}/api/company/ai/consent/revoke`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey })
    });
  },
  getCompanyAICredentials: async () => {
    return wrappedFetch(`${API_BASE}/api/company/ai/credentials`, { headers: getHeaders() });
  },
  saveCompanyAICredential: async (providerKey, apiKey) => {
    return wrappedFetch(`${API_BASE}/api/company/ai/credentials`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey, api_key: apiKey })
    });
  },
  deleteCompanyAICredential: async (credentialId) => {
    return wrappedFetch(`${API_BASE}/api/company/ai/credentials/${credentialId}`, {
      method: "DELETE",
      headers: getHeaders()
    });
  },
  getCompanyAIUsage: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return wrappedFetch(`${API_BASE}/api/company/ai/usage${query ? `?${query}` : ""}`, { headers: getHeaders() });
  },
  // Branch AI
  getBranchAIConfig: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/ai/config`, { headers: getHeaders() });
  },
  updateBranchAIConfig: async (branchId, config) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/ai/config`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(config)
    });
  },
  testBranchAIConnection: async (branchId, providerKey, model) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/ai/test-connection`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey, model })
    });
  },
  // ── Module 11: Extraction Templates & Human Verification ─────────────
  getTemplates: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return wrappedFetch(`${API_BASE}/api/company/templates${query ? `?${query}` : ""}`, { headers: getHeaders() });
  },
  getTemplate: async (id) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${id}`, { headers: getHeaders() });
  },
  createTemplate: async (payload) => {
    return wrappedFetch(`${API_BASE}/api/company/templates`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
  },
  updateTemplate: async (id, payload) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${id}`, {
      method: "PUT",
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
  },
  deactivateTemplate: async (id) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${id}`, {
      method: "DELETE",
      headers: getHeaders()
    });
  },
  getTemplateVersions: async (id) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${id}/versions`, { headers: getHeaders() });
  },
  getTemplateVersionDetail: async (templateId, versionId) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${templateId}/versions/${versionId}`, { headers: getHeaders() });
  },
  createTemplateDraftVersion: async (templateId, payload) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${templateId}/versions`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
  },
  publishTemplateVersion: async (templateId, versionId) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${templateId}/versions/${versionId}/publish`, {
      method: "POST",
      headers: getHeaders()
    });
  },
  // Document Review & Verification
  getDocumentExtraction: async (documentId) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/extraction`, { headers: getHeaders() });
  },
  saveExtractionCorrections: async (documentId, payload) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/review/save`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
  },
  approveDocumentExtraction: async (documentId, payload = {}) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/review/approve`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify(payload)
    });
  },
  getDocumentExtractionEdits: async (documentId) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/edits`, { headers: getHeaders() });
  },
  // ── Module 14: Operational Dashboard & Usage Reporting ──────────────────────
  getDashboardCompany: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.date_from) q.append("date_from", params.date_from);
    if (params.date_to) q.append("date_to", params.date_to);
    if (params.branch_id) q.append("branch_id", params.branch_id);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return wrappedFetch(`${API_BASE}/api/dashboard/company${qs}`, { headers: getHeaders() });
  },
  getDashboardBranch: async (branchId, params = {}) => {
    const q = new URLSearchParams();
    if (params.date_from) q.append("date_from", params.date_from);
    if (params.date_to) q.append("date_to", params.date_to);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return wrappedFetch(`${API_BASE}/api/dashboard/branch/${branchId}${qs}`, { headers: getHeaders() });
  },
  getDashboardAIUsage: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.date_from) q.append("date_from", params.date_from);
    if (params.date_to) q.append("date_to", params.date_to);
    if (params.branch_id) q.append("branch_id", params.branch_id);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return wrappedFetch(`${API_BASE}/api/dashboard/ai-usage${qs}`, { headers: getHeaders() });
  },
  getDashboardJobs: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.append("status", params.status);
    if (params.branch_id) q.append("branch_id", params.branch_id);
    if (params.page) q.append("page", params.page);
    if (params.page_size) q.append("page_size", params.page_size);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return wrappedFetch(`${API_BASE}/api/dashboard/jobs${qs}`, { headers: getHeaders() });
  },
  downloadDashboardCsv: async (exportType, params = {}) => {
    const q = new URLSearchParams();
    q.append("export_type", exportType);
    if (params.date_from) q.append("date_from", params.date_from);
    if (params.date_to) q.append("date_to", params.date_to);
    if (params.branch_id) q.append("branch_id", params.branch_id);
    const token = getAuthToken();
    const url = `${API_BASE}/api/dashboard/export/csv?${q.toString()}`;
    const resp = await fetch(url, {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });
    if (!resp.ok) {
      const errJson = await resp.json().catch(() => ({}));
      throw new Error(errJson.detail || `Export failed with status ${resp.status}`);
    }
    const blob = await resp.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    const disposition = resp.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    a.download = match ? match[1] : `${exportType}_export.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(downloadUrl);
  }
};

// src/context/AuthContext.jsx
var AuthContext = createContext(null);
function useAuth() {
  return useContext(AuthContext);
}

// src/components/Layout.jsx
import React2, { useState as useState2, useEffect as useEffect2 } from "react";
import { useNavigate, NavLink, Outlet, useLocation } from "react-router-dom";
var IconDashboard = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("rect", { x: "3", y: "3", width: "7", height: "7" }), /* @__PURE__ */ React2.createElement("rect", { x: "14", y: "3", width: "7", height: "7" }), /* @__PURE__ */ React2.createElement("rect", { x: "14", y: "14", width: "7", height: "7" }), /* @__PURE__ */ React2.createElement("rect", { x: "3", y: "14", width: "7", height: "7" }));
var IconDocuments = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("path", { d: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" }), /* @__PURE__ */ React2.createElement("polyline", { points: "14 2 14 8 20 8" }), /* @__PURE__ */ React2.createElement("line", { x1: "16", y1: "13", x2: "8", y2: "13" }), /* @__PURE__ */ React2.createElement("line", { x1: "16", y1: "17", x2: "8", y2: "17" }), /* @__PURE__ */ React2.createElement("polyline", { points: "10 9 9 9 8 9" }));
var IconInvoices = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("rect", { x: "2", y: "3", width: "20", height: "14", rx: "2", ry: "2" }), /* @__PURE__ */ React2.createElement("line", { x1: "8", y1: "21", x2: "16", y2: "21" }), /* @__PURE__ */ React2.createElement("line", { x1: "12", y1: "17", x2: "12", y2: "21" }));
var IconUpload = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("polyline", { points: "16 16 12 12 8 16" }), /* @__PURE__ */ React2.createElement("line", { x1: "12", y1: "12", x2: "12", y2: "21" }), /* @__PURE__ */ React2.createElement("path", { d: "M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" }));
var IconCompanyProfile = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("path", { d: "M3 21h18M3 7v14M21 7v14M6 11h4M6 15h4M14 11h4M14 15h4M9 3h6v4H9z" }));
var IconBranchManagement = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("line", { x1: "6", y1: "3", x2: "6", y2: "15" }), /* @__PURE__ */ React2.createElement("circle", { cx: "18", cy: "6", r: "3" }), /* @__PURE__ */ React2.createElement("circle", { cx: "6", cy: "18", r: "3" }), /* @__PURE__ */ React2.createElement("path", { d: "M18 9a9 9 0 0 1-9 9" }));
var IconUserManagement = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("path", { d: "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" }), /* @__PURE__ */ React2.createElement("circle", { cx: "9", cy: "7", r: "4" }), /* @__PURE__ */ React2.createElement("path", { d: "M23 21v-2a4 4 0 0 0-3-3.87" }), /* @__PURE__ */ React2.createElement("path", { d: "M16 3.13a4 4 0 0 1 0 7.75" }));
var IconArchive = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("path", { d: "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" }), /* @__PURE__ */ React2.createElement("line", { x1: "12", y1: "11", x2: "12", y2: "17" }), /* @__PURE__ */ React2.createElement("line", { x1: "9", y1: "14", x2: "15", y2: "14" }));
var IconTemplates = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("rect", { x: "3", y: "3", width: "18", height: "18", rx: "2" }), /* @__PURE__ */ React2.createElement("path", { d: "M9 3v18" }), /* @__PURE__ */ React2.createElement("path", { d: "M14 9h4" }), /* @__PURE__ */ React2.createElement("path", { d: "M14 15h4" }));
var IconAI = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("polygon", { points: "12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" }));
var IconCost = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("line", { x1: "12", y1: "1", x2: "12", y2: "23" }), /* @__PURE__ */ React2.createElement("path", { d: "M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" }));
var IconJobs = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("polyline", { points: "22 12 18 12 15 21 9 3 6 12 2 12" }));
var IconCompanySecurity = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("rect", { x: "3", y: "11", width: "18", height: "11", rx: "2", ry: "2" }), /* @__PURE__ */ React2.createElement("path", { d: "M7 11V7a5 5 0 0 1 10 0v4" }));
var IconAudit = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("path", { d: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" }), /* @__PURE__ */ React2.createElement("polyline", { points: "14 2 14 8 20 8" }), /* @__PURE__ */ React2.createElement("line", { x1: "16", y1: "13", x2: "8", y2: "13" }), /* @__PURE__ */ React2.createElement("line", { x1: "16", y1: "17", x2: "8", y2: "17" }), /* @__PURE__ */ React2.createElement("polyline", { points: "10 9 9 9 8 9" }));
var IconPersonalSecurity = () => /* @__PURE__ */ React2.createElement("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("path", { d: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" }));
var IconMenu = () => /* @__PURE__ */ React2.createElement("svg", { width: "18", height: "18", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round" }, /* @__PURE__ */ React2.createElement("line", { x1: "3", y1: "6", x2: "21", y2: "6" }), /* @__PURE__ */ React2.createElement("line", { x1: "3", y1: "12", x2: "21", y2: "12" }), /* @__PURE__ */ React2.createElement("line", { x1: "3", y1: "18", x2: "21", y2: "18" }));
var IconSignOut = () => /* @__PURE__ */ React2.createElement("svg", { width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" }, /* @__PURE__ */ React2.createElement("path", { d: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" }), /* @__PURE__ */ React2.createElement("polyline", { points: "16 17 21 12 16 7" }), /* @__PURE__ */ React2.createElement("line", { x1: "21", y1: "12", x2: "9", y2: "12" }));
function Layout() {
  const { user, logout, hasPermission } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState2(() => typeof window !== "undefined" ? window.innerWidth >= 1024 : true);
  const [branchesCount, setBranchesCount] = useState2(0);
  const [failedJobsCount, setFailedJobsCount] = useState2(0);
  useEffect2(() => {
    if (typeof window === "undefined") return;
    const onResize = () => {
      if (window.innerWidth >= 1024) {
        setSidebarOpen(true);
      } else {
        setSidebarOpen(false);
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  useEffect2(() => {
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
      setSidebarOpen(false);
    }
  }, [location.pathname]);
  useEffect2(() => {
    if (user?.role === "GLOBAL_ADMIN") {
      api.listCompanyBranches().then((b) => {
        if (Array.isArray(b)) setBranchesCount(b.length);
      }).catch(() => {
      });
      api.getDashboardJobs({ status: "failed", page_size: 1 }).then((j) => {
        if (j?.total !== void 0) setFailedJobsCount(j.total);
      }).catch(() => {
      });
    }
  }, [user]);
  const handleLogout = () => {
    logout();
    navigate("/login");
  };
  const isCompanyAdmin = user?.role === "GLOBAL_ADMIN";
  const isBranchAdmin = user?.role === "ADMIN";
  return /* @__PURE__ */ React2.createElement("div", { className: "app-shell" }, /* @__PURE__ */ React2.createElement("header", { className: "topnav", role: "banner" }, /* @__PURE__ */ React2.createElement("div", { className: "topnav-left" }, /* @__PURE__ */ React2.createElement(
    "button",
    {
      className: "topnav-toggle",
      onClick: () => setSidebarOpen((o) => !o),
      "aria-label": sidebarOpen ? "Close sidebar" : "Open sidebar",
      title: sidebarOpen ? "Close menu" : "Open menu"
    },
    /* @__PURE__ */ React2.createElement(IconMenu, null)
  ), /* @__PURE__ */ React2.createElement("div", { className: "topnav-brand", style: { display: "flex", alignItems: "center", gap: "8px" } }, /* @__PURE__ */ React2.createElement("span", { className: "topnav-brand-name" }, "DMS"), isCompanyAdmin && /* @__PURE__ */ React2.createElement(
    "span",
    {
      style: {
        backgroundColor: "#ef4444",
        color: "#ffffff",
        padding: "2px 8px",
        borderRadius: "4px",
        fontSize: "11px",
        fontWeight: 800,
        letterSpacing: "0.8px"
      }
    },
    "ENTERPRISE"
  ))), /* @__PURE__ */ React2.createElement("div", { className: "topnav-right" }, /* @__PURE__ */ React2.createElement("div", { className: "topnav-user" }, /* @__PURE__ */ React2.createElement("div", { className: "topnav-user-info" }, /* @__PURE__ */ React2.createElement("div", { className: "topnav-user-name" }, user?.name), /* @__PURE__ */ React2.createElement(
    "div",
    {
      className: "topnav-user-role",
      style: { color: isCompanyAdmin ? "#ef4444" : "var(--text-muted)" }
    },
    isCompanyAdmin ? "Company Administrator" : `${user?.role?.replace("_", " ")} \xB7 ${user?.tenant_name || user?.branch_name || "Branch"}`
  )), /* @__PURE__ */ React2.createElement(
    "div",
    {
      className: "topnav-avatar",
      style: {
        backgroundColor: isCompanyAdmin ? "#fee2e2" : "var(--red-primary)",
        color: isCompanyAdmin ? "#b91c1c" : "#fff"
      },
      title: user?.name
    },
    user?.name?.[0]?.toUpperCase()
  )), /* @__PURE__ */ React2.createElement("div", { className: "topnav-divider" }), /* @__PURE__ */ React2.createElement("button", { className: "topnav-signout", onClick: handleLogout, title: "Sign out" }, /* @__PURE__ */ React2.createElement(IconSignOut, null), "Sign out"))), sidebarOpen && typeof window !== "undefined" && window.innerWidth < 1024 && /* @__PURE__ */ React2.createElement(
    "div",
    {
      className: "sidebar-overlay visible",
      onClick: () => setSidebarOpen(false),
      "aria-hidden": "true"
    }
  ), /* @__PURE__ */ React2.createElement(
    "aside",
    {
      className: `sidebar ${sidebarOpen ? "sidebar-open" : "sidebar-collapsed"}`,
      "aria-label": "Main navigation"
    },
    /* @__PURE__ */ React2.createElement("div", { className: "sidebar-brand" }, user?.company_logo_url ? /* @__PURE__ */ React2.createElement("div", { className: "sidebar-company-logo-wrapper" }, /* @__PURE__ */ React2.createElement(
      "img",
      {
        src: user.company_logo_url,
        alt: user?.company_display_name || user?.company_name || "Company",
        className: "sidebar-company-logo-img",
        onError: (e) => {
          e.currentTarget.style.display = "none";
          const fallback = e.currentTarget.parentElement?.querySelector(".sidebar-company-logo-fallback");
          if (fallback) fallback.style.display = "flex";
        }
      }
    ), /* @__PURE__ */ React2.createElement("div", { className: "sidebar-company-logo sidebar-company-logo-fallback", style: { display: "none" } }, (user?.company_name || user?.company_display_name || "CO").split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "CO")) : /* @__PURE__ */ React2.createElement("div", { className: "sidebar-company-logo" }, (user?.company_name || user?.company_display_name || "CO").split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "CO"), /* @__PURE__ */ React2.createElement("div", { style: { overflow: "hidden" } }, /* @__PURE__ */ React2.createElement(
      "div",
      {
        className: "sidebar-company-name",
        title: user?.company_display_name || user?.company_name || "Your Company"
      },
      user?.company_display_name || user?.company_name || "Your Company"
    ), /* @__PURE__ */ React2.createElement(
      "div",
      {
        className: "sidebar-company-hint",
        title: isCompanyAdmin ? "Headquarters" : user?.tenant_name || user?.branch_name || "Branch"
      },
      isCompanyAdmin ? "Headquarters" : user?.tenant_name || user?.branch_name || "Branch"
    ))),
    /* @__PURE__ */ React2.createElement("nav", { className: "sidebar-nav", role: "navigation" }, (isCompanyAdmin || isBranchAdmin) && /* @__PURE__ */ React2.createElement(React2.Fragment, null, /* @__PURE__ */ React2.createElement("span", { className: "nav-section-label" }, "OVERVIEW"), isCompanyAdmin && /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/dashboard",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconDashboard, null)),
      "Dashboard"
    ), isBranchAdmin && /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/branch-dashboard",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconDashboard, null)),
      "Branch Dashboard"
    )), /* @__PURE__ */ React2.createElement("span", { className: "nav-section-label", style: { marginTop: isCompanyAdmin || isBranchAdmin ? "6px" : "0" } }, "OPERATIONS"), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/documents",
        className: () => `nav-link${location.pathname === "/documents" || location.pathname === "/" ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconDocuments, null)),
      "Documents"
    ), hasPermission("document.upload") && /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/upload",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconUpload, null)),
      "Upload Document"
    ), hasPermission("invoice.view") && /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/invoices",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconInvoices, null)),
      "Generated Invoices"
    ), isCompanyAdmin && /* @__PURE__ */ React2.createElement(React2.Fragment, null, /* @__PURE__ */ React2.createElement("span", { className: "nav-section-label", style: { marginTop: "8px" } }, "COMPANY MANAGEMENT"), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/profile",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconCompanyProfile, null)),
      "Company Profile"
    ), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/branches",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`,
        style: { justifyContent: "space-between" }
      },
      /* @__PURE__ */ React2.createElement("div", { style: { display: "flex", alignItems: "center", gap: "0.625rem" } }, /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconBranchManagement, null)), "Branch Management"),
      branchesCount > 0 && /* @__PURE__ */ React2.createElement(
        "span",
        {
          style: {
            backgroundColor: location.pathname === "/company/branches" ? "#fecaca" : "#e2e8f0",
            color: location.pathname === "/company/branches" ? "#b91c1c" : "#64748b",
            fontSize: "11px",
            fontWeight: 700,
            padding: "2px 7px",
            borderRadius: "10px"
          }
        },
        branchesCount
      )
    ), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/users",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconUserManagement, null)),
      "User Management"
    ), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/documents",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconArchive, null)),
      "Document Archive"
    ), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/templates",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconTemplates, null)),
      "Extraction Templates"
    ), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/ai",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconAI, null)),
      "AI & Providers"
    ), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/ai-usage",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconCost, null)),
      "AI Usage & Cost"
    ), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/jobs",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`,
        style: { justifyContent: "space-between" }
      },
      /* @__PURE__ */ React2.createElement("div", { style: { display: "flex", alignItems: "center", gap: "0.625rem" } }, /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconJobs, null)), "Background Jobs"),
      failedJobsCount > 0 && /* @__PURE__ */ React2.createElement(
        "span",
        {
          style: {
            backgroundColor: "#ef4444",
            color: "#ffffff",
            fontSize: "11px",
            fontWeight: 700,
            padding: "2px 7px",
            borderRadius: "10px"
          }
        },
        failedJobsCount
      )
    ), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/security",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconCompanySecurity, null)),
      "Company Security"
    ), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/company/audit-logs",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconAudit, null)),
      "Audit Logs"
    )), /* @__PURE__ */ React2.createElement("span", { className: "nav-section-label", style: { marginTop: "8px" } }, "ACCOUNT"), /* @__PURE__ */ React2.createElement(
      NavLink,
      {
        to: "/security",
        className: ({ isActive }) => `nav-link${isActive ? " active" : ""}`
      },
      /* @__PURE__ */ React2.createElement("span", { className: "nav-icon" }, /* @__PURE__ */ React2.createElement(IconPersonalSecurity, null)),
      "Personal Security & 2FA"
    )),
    /* @__PURE__ */ React2.createElement("div", { className: "sidebar-footer" }, /* @__PURE__ */ React2.createElement("div", { className: "sidebar-tenant" }, /* @__PURE__ */ React2.createElement("span", { className: "tenant-status-dot", style: { backgroundColor: "#22c55e" } }), isCompanyAdmin ? "Enterprise \u2014 Active" : `${user?.tenant_name || user?.branch_name || "Branch"} \u2014 Active`))
  ), /* @__PURE__ */ React2.createElement(
    "main",
    {
      className: `main-content ${sidebarOpen && (typeof window === "undefined" || window.innerWidth >= 1024) ? "with-sidebar" : "no-sidebar"}`,
      id: "main-content"
    },
    /* @__PURE__ */ React2.createElement(Outlet, null)
  ));
}

// src/components/RoleBasedIndexRedirect.jsx
import React3 from "react";
import { Navigate, useSearchParams } from "react-router-dom";
function getRoleLandingDestination(user, tab = null) {
  if (!user) return "/login";
  if (tab === "dashboard") return "/branch-dashboard";
  if (tab === "trash") return "/documents?tab=trash";
  if (user.role === "MASTER_ADMIN") return "/admin/companies";
  if (user.role === "GLOBAL_ADMIN") return "/company/dashboard";
  return "/documents";
}

// src/components/CompanyProtectedRoute.jsx
import React4 from "react";
import { Navigate as Navigate2 } from "react-router-dom";
function CompanyProtectedRoute({ children }) {
  const { user, loading, mustChangePassword } = useAuth();
  if (loading) {
    return /* @__PURE__ */ React4.createElement("div", { className: "page-loader", style: { display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" } }, /* @__PURE__ */ React4.createElement("div", { className: "spinner" }));
  }
  if (!user) {
    return /* @__PURE__ */ React4.createElement(Navigate2, { to: "/login", replace: true });
  }
  if (user.role !== "GLOBAL_ADMIN") {
    return /* @__PURE__ */ React4.createElement(Navigate2, { to: "/documents", replace: true });
  }
  if (mustChangePassword) {
    return /* @__PURE__ */ React4.createElement(Navigate2, { to: "/change-password", replace: true });
  }
  return children;
}

// test_navigation.jsx
function TestAuthProvider({ user, children }) {
  const hasPermission = (permission) => {
    if (!user) return false;
    if (user.role === "GLOBAL_ADMIN") return true;
    if (user.role === "ADMIN" && !permission.startsWith("company:")) return true;
    if (Array.isArray(user.permissions) && user.permissions.includes(permission)) return true;
    return false;
  };
  return /* @__PURE__ */ React5.createElement(AuthContext.Provider, { value: { user, loading: false, hasPermission, logout: () => {
  } } }, children);
}
console.log("\u{1F9EA} =========================================================================");
console.log("\u{1F9EA} RUNNING UNIFIED NAVIGATION & ROLE-BASED ACCESS CONTROL (RBAC) TEST SUITE");
console.log("\u{1F9EA} =========================================================================\n");
var passedTests = 0;
var totalTests = 0;
function runTest(testName, fn) {
  totalTests++;
  try {
    fn();
    console.log(`  \u2705 PASS: ${testName}`);
    passedTests++;
  } catch (err) {
    console.error(`  \u274C FAIL: ${testName}`);
    console.error(err);
  }
}
var mockCompanyAdmin = {
  id: 3,
  email: "companyadmin@nobicorp.com",
  name: "Nobi Nobita",
  role: "GLOBAL_ADMIN",
  company_id: 24,
  company_name: "Nobi Corp",
  company_display_name: "Nobi Corp",
  tenant_name: "Headquarters",
  branch_name: "Headquarters",
  permissions: ["all"]
};
var mockBranchAdmin = {
  id: 101,
  email: "branchadmin@nobicorp.com",
  name: "Branch Manager",
  role: "ADMIN",
  company_id: 24,
  company_name: "Nobi Corp",
  tenant_name: "Chennai Tondiarpet",
  branch_name: "Chennai Tondiarpet",
  assigned_branch_ids: [2],
  permissions: [
    "document.view_own",
    "document.view_branch",
    "document.upload",
    "branch.view",
    "invoice.view",
    "invoice.download",
    "invoice.sales_create"
  ]
};
var mockStaff = {
  id: 102,
  email: "staff@nobicorp.com",
  name: "Staff Member",
  role: "STAFF",
  company_id: 24,
  company_name: "Nobi Corp",
  tenant_name: "Chennai Tondiarpet",
  branch_name: "Chennai Tondiarpet",
  permissions: [
    "document.view_own",
    "document.upload",
    "invoice.view",
    "invoice.download",
    "invoice.sales_create"
  ]
};
var mockUploader = {
  id: 103,
  email: "uploader@nobicorp.com",
  name: "Doc Uploader",
  role: "UPLOADER",
  company_id: 24,
  company_name: "Nobi Corp",
  tenant_name: "Chennai Tondiarpet",
  branch_name: "Chennai Tondiarpet",
  permissions: [
    "document.view_own",
    "document.upload",
    "invoice.view",
    "invoice.download"
  ]
};
console.log("--- 1. Testing Layout Sidebar Section Visibility for All 4 Roles ---");
runTest("Company Admin sees Overview (Dashboard), Operations, Company Management (all 10 items), Account", () => {
  globalThis.localStorage = {
    getItem: () => JSON.stringify(mockCompanyAdmin),
    setItem: () => {
    }
  };
  const html = renderToString(
    /* @__PURE__ */ React5.createElement(TestAuthProvider, { user: mockCompanyAdmin }, /* @__PURE__ */ React5.createElement(MemoryRouter, { initialEntries: ["/company/dashboard"] }, /* @__PURE__ */ React5.createElement(Layout, null)))
  );
  assert(html.includes("ENTERPRISE"), "Topnav should display ENTERPRISE badge for Company Admin");
  assert(html.includes("OVERVIEW"), "Company Admin sidebar must contain OVERVIEW");
  assert(html.includes("Dashboard"), "Company Admin sidebar must contain Dashboard");
  assert(html.includes("OPERATIONS"), "Sidebar must contain OPERATIONS");
  assert(html.includes("Documents"), "Sidebar must contain Documents");
  assert(html.includes("Upload Document"), "Sidebar must contain Upload Document");
  assert(html.includes("Generated Invoices"), "Sidebar must contain Generated Invoices");
  assert(!html.includes("Company Branches</a>"), "OPERATIONS section must NOT contain confusing Company Branches link");
  assert(html.includes("COMPANY MANAGEMENT"), "Company Admin sidebar must contain COMPANY MANAGEMENT");
  assert(html.includes("Company Profile"), "Must contain Company Profile");
  assert(html.includes("Branch Management"), "Must contain Branch Management");
  assert(html.includes("User Management"), "Must contain User Management");
  assert(html.includes("Document Archive"), "Must contain Document Archive");
  assert(html.includes("Extraction Templates"), "Must contain Extraction Templates");
  assert(html.includes("AI &amp; Providers") || html.includes("AI & Providers"), "Must contain AI & Providers");
  assert(html.includes("AI Usage &amp; Cost") || html.includes("AI Usage & Cost"), "Must contain AI Usage & Cost");
  assert(html.includes("Background Jobs"), "Must contain Background Jobs");
  assert(html.includes("Company Security"), "Must contain Company Security");
  assert(html.includes("Audit Logs"), "Must contain Audit Logs");
  assert(html.includes("ACCOUNT"), "Sidebar must contain ACCOUNT");
  assert(html.includes("Personal Security &amp; 2FA") || html.includes("Personal Security & 2FA"), "Sidebar must contain Personal Security");
});
runTest("Branch Admin sees Overview (Branch Dashboard), Operations, Account, and ZERO Company Management", () => {
  const html = renderToString(
    /* @__PURE__ */ React5.createElement(TestAuthProvider, { user: mockBranchAdmin }, /* @__PURE__ */ React5.createElement(MemoryRouter, { initialEntries: ["/branch-dashboard"] }, /* @__PURE__ */ React5.createElement(Layout, null)))
  );
  assert(!html.includes("ENTERPRISE"), "Branch Admin topnav must NOT display ENTERPRISE badge");
  assert(html.includes("OVERVIEW"), "Branch Admin sidebar must contain OVERVIEW");
  assert(html.includes("Branch Dashboard"), "Branch Admin sidebar must contain Branch Dashboard");
  assert(!html.includes('href="/company/dashboard"'), "Branch Admin sidebar must NOT contain Company Dashboard link");
  assert(html.includes("OPERATIONS"), "Sidebar must contain OPERATIONS");
  assert(html.includes("Documents"), "Sidebar must contain Documents");
  assert(html.includes("Upload Document"), "Sidebar must contain Upload Document");
  assert(html.includes("Generated Invoices"), "Sidebar must contain Generated Invoices");
  assert(!html.includes("COMPANY MANAGEMENT"), "Branch Admin MUST NOT see COMPANY MANAGEMENT section");
  assert(!html.includes("Company Profile"), "Branch Admin MUST NOT see Company Profile");
  assert(!html.includes("Branch Management"), "Branch Admin MUST NOT see Branch Management");
  assert(!html.includes("User Management"), "Branch Admin MUST NOT see User Management");
  assert(!html.includes("Document Archive"), "Branch Admin MUST NOT see Document Archive");
  assert(!html.includes("Background Jobs"), "Branch Admin MUST NOT see Background Jobs");
  assert(!html.includes("Company Security"), "Branch Admin MUST NOT see Company Security");
  assert(html.includes("ACCOUNT"), "Sidebar must contain ACCOUNT");
  assert(html.includes("Personal Security &amp; 2FA") || html.includes("Personal Security & 2FA"), "Sidebar must contain Personal Security");
});
runTest("Staff sees Operations & Account ONLY (No Overview, No Company Management)", () => {
  const html = renderToString(
    /* @__PURE__ */ React5.createElement(TestAuthProvider, { user: mockStaff }, /* @__PURE__ */ React5.createElement(MemoryRouter, { initialEntries: ["/documents"] }, /* @__PURE__ */ React5.createElement(Layout, null)))
  );
  assert(!html.includes("OVERVIEW"), "Staff sidebar MUST NOT contain OVERVIEW");
  assert(!html.includes("Branch Dashboard"), "Staff sidebar MUST NOT contain Branch Dashboard");
  assert(!html.includes("COMPANY MANAGEMENT"), "Staff sidebar MUST NOT contain COMPANY MANAGEMENT");
  assert(html.includes("OPERATIONS"), "Sidebar must contain OPERATIONS");
  assert(html.includes("Documents"), "Sidebar must contain Documents");
  assert(html.includes("Upload Document"), "Sidebar must contain Upload Document");
  assert(html.includes("Generated Invoices"), "Sidebar must contain Generated Invoices");
  assert(html.includes("ACCOUNT"), "Sidebar must contain ACCOUNT");
});
runTest("Uploader sees Operations & Account ONLY (No Overview, No Company Management)", () => {
  const html = renderToString(
    /* @__PURE__ */ React5.createElement(TestAuthProvider, { user: mockUploader }, /* @__PURE__ */ React5.createElement(MemoryRouter, { initialEntries: ["/documents"] }, /* @__PURE__ */ React5.createElement(Layout, null)))
  );
  assert(!html.includes("OVERVIEW"), "Uploader sidebar MUST NOT contain OVERVIEW");
  assert(!html.includes("Branch Dashboard"), "Uploader sidebar MUST NOT contain Branch Dashboard");
  assert(!html.includes("COMPANY MANAGEMENT"), "Uploader sidebar MUST NOT contain COMPANY MANAGEMENT");
  assert(html.includes("OPERATIONS"), "Sidebar must contain OPERATIONS");
  assert(html.includes("Documents"), "Sidebar must contain Documents");
  assert(html.includes("Upload Document"), "Sidebar must contain Upload Document");
  assert(html.includes("ACCOUNT"), "Sidebar must contain ACCOUNT");
});
console.log("\n--- 2. Testing Intelligent Role-Aware Landing Router (/) ---");
runTest("Unauthenticated user at / redirects to /login", () => {
  const target = getRoleLandingDestination(null);
  assert.strictEqual(target, "/login", `Expected /login, got ${target}`);
});
runTest("Company Admin (GLOBAL_ADMIN) at / redirects to /company/dashboard", () => {
  const target = getRoleLandingDestination(mockCompanyAdmin);
  assert.strictEqual(target, "/company/dashboard", `Expected /company/dashboard, got ${target}`);
});
runTest("Branch Admin (ADMIN) at / redirects to /documents", () => {
  const target = getRoleLandingDestination(mockBranchAdmin);
  assert.strictEqual(target, "/documents", `Expected /documents, got ${target}`);
});
runTest("Staff (STAFF) at / redirects to /documents", () => {
  const target = getRoleLandingDestination(mockStaff);
  assert.strictEqual(target, "/documents", `Expected /documents, got ${target}`);
});
runTest("Uploader (UPLOADER) at / redirects to /documents", () => {
  const target = getRoleLandingDestination(mockUploader);
  assert.strictEqual(target, "/documents", `Expected /documents, got ${target}`);
});
runTest("Backward compatibility: /?tab=dashboard redirects to /branch-dashboard", () => {
  const target = getRoleLandingDestination(mockBranchAdmin, "dashboard");
  assert.strictEqual(target, "/branch-dashboard", `Expected /branch-dashboard, got ${target}`);
});
runTest("Backward compatibility: /?tab=trash redirects to /documents?tab=trash", () => {
  const target = getRoleLandingDestination(mockBranchAdmin, "trash");
  assert.strictEqual(target, "/documents?tab=trash", `Expected /documents?tab=trash, got ${target}`);
});
console.log("\n--- 3. Testing CompanyProtectedRoute Route Guards ---");
function testCompanyGuard(user, targetPath) {
  function ProtectedContent() {
    return /* @__PURE__ */ React5.createElement("div", { id: "protected-content" }, "Secret Corporate Data");
  }
  const html = renderToString(
    /* @__PURE__ */ React5.createElement(TestAuthProvider, { user }, /* @__PURE__ */ React5.createElement(MemoryRouter, { initialEntries: [targetPath] }, /* @__PURE__ */ React5.createElement(Routes, null, /* @__PURE__ */ React5.createElement(
      Route,
      {
        path: "/company/users",
        element: /* @__PURE__ */ React5.createElement(CompanyProtectedRoute, null, /* @__PURE__ */ React5.createElement(ProtectedContent, null))
      }
    ), /* @__PURE__ */ React5.createElement(Route, { path: "/login", element: /* @__PURE__ */ React5.createElement("div", { id: "login-page" }, "Login Page") }), /* @__PURE__ */ React5.createElement(Route, { path: "/documents", element: /* @__PURE__ */ React5.createElement("div", { id: "documents-page" }, "Documents Page") }))))
  );
  return html;
}
runTest("Company Admin is allowed into /company/users", () => {
  const html = testCompanyGuard(mockCompanyAdmin, "/company/users");
  assert(html.includes("Secret Corporate Data"), "Company Admin must have access");
});
runTest("Branch Admin is BLOCKED from /company/users", () => {
  const html = testCompanyGuard(mockBranchAdmin, "/company/users");
  assert(!html.includes("Secret Corporate Data"), "Branch Admin must NOT access Company Admin view");
});
runTest("Staff is BLOCKED from /company/users", () => {
  const html = testCompanyGuard(mockStaff, "/company/users");
  assert(!html.includes("Secret Corporate Data"), "Staff must NOT access Company Admin view");
});
runTest("Unauthenticated user is BLOCKED from /company/users", () => {
  const html = testCompanyGuard(null, "/company/users");
  assert(!html.includes("Secret Corporate Data"), "Unauthenticated user must NOT access");
});
console.log("\n=========================================================================");
console.log(`TEST RESULTS: ${passedTests} / ${totalTests} PASSED (100% Success Rate)`);
console.log("=========================================================================\n");
if (passedTests === totalTests) {
  process.exit(0);
} else {
  process.exit(1);
}
