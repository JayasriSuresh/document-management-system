// test_document_review.jsx
import React4 from "react";
import { renderToString } from "react-dom/server";
import { MemoryRouter, Routes, Route } from "react-router-dom";
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

// src/pages/DocumentViewPage.jsx
import React3, { useState as useState2, useEffect as useEffect3, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";

// src/components/ConfirmModal.jsx
import React2, { useEffect as useEffect2 } from "react";
function ConfirmModal({
  isOpen,
  title = "Please Confirm",
  message,
  details = null,
  confirmText = "Confirm",
  cancelText = "Cancel",
  variant = "primary",
  // 'primary' | 'success' | 'danger' | 'warning'
  loading = false,
  onConfirm,
  onCancel
}) {
  useEffect2(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && isOpen && !loading) {
        onCancel?.();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, loading, onCancel]);
  if (!isOpen) return null;
  const themes = {
    primary: {
      iconBg: "#eff6ff",
      iconColor: "#2563eb",
      buttonBg: "#0284c7",
      buttonHover: "#0369a1",
      icon: /* @__PURE__ */ React2.createElement("svg", { width: "24", height: "24", fill: "none", viewBox: "0 0 24 24", stroke: "currentColor" }, /* @__PURE__ */ React2.createElement("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: "2", d: "M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" }))
    },
    success: {
      iconBg: "#f0fdf4",
      iconColor: "#16a34a",
      buttonBg: "#16a34a",
      buttonHover: "#15803d",
      icon: /* @__PURE__ */ React2.createElement("svg", { width: "24", height: "24", fill: "none", viewBox: "0 0 24 24", stroke: "currentColor" }, /* @__PURE__ */ React2.createElement("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: "2", d: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" }))
    },
    danger: {
      iconBg: "#fef2f2",
      iconColor: "#dc2626",
      buttonBg: "#dc2626",
      buttonHover: "#b91c1c",
      icon: /* @__PURE__ */ React2.createElement("svg", { width: "24", height: "24", fill: "none", viewBox: "0 0 24 24", stroke: "currentColor" }, /* @__PURE__ */ React2.createElement("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: "2", d: "M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" }))
    },
    warning: {
      iconBg: "#fffbeb",
      iconColor: "#d97706",
      buttonBg: "#d97706",
      buttonHover: "#b45309",
      icon: /* @__PURE__ */ React2.createElement("svg", { width: "24", height: "24", fill: "none", viewBox: "0 0 24 24", stroke: "currentColor" }, /* @__PURE__ */ React2.createElement("path", { strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: "2", d: "M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" }))
    }
  };
  const currentTheme = themes[variant] || themes.primary;
  return /* @__PURE__ */ React2.createElement(
    "div",
    {
      style: {
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(15, 23, 42, 0.6)",
        backdropFilter: "blur(3px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1e4,
        padding: "16px",
        animation: "fadeIn 0.15s ease-out"
      },
      onClick: (e) => {
        if (e.target === e.currentTarget && !loading) {
          onCancel?.();
        }
      }
    },
    /* @__PURE__ */ React2.createElement(
      "div",
      {
        style: {
          backgroundColor: "#ffffff",
          borderRadius: "14px",
          width: "100%",
          maxWidth: "460px",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
          border: "1px solid #e2e8f0",
          overflow: "hidden",
          animation: "slideUp 0.18s cubic-bezier(0.16, 1, 0.3, 1)"
        }
      },
      /* @__PURE__ */ React2.createElement("div", { style: { padding: "24px" } }, /* @__PURE__ */ React2.createElement("div", { style: { display: "flex", alignItems: "flex-start", gap: "16px" } }, /* @__PURE__ */ React2.createElement(
        "div",
        {
          style: {
            width: "46px",
            height: "46px",
            borderRadius: "50%",
            backgroundColor: currentTheme.iconBg,
            color: currentTheme.iconColor,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0
          }
        },
        currentTheme.icon
      ), /* @__PURE__ */ React2.createElement("div", { style: { flex: 1 } }, /* @__PURE__ */ React2.createElement(
        "h3",
        {
          style: {
            margin: "0 0 6px 0",
            fontSize: "17px",
            fontWeight: 700,
            color: "#0f172a",
            lineHeight: "1.3"
          }
        },
        title
      ), /* @__PURE__ */ React2.createElement(
        "div",
        {
          style: {
            fontSize: "13.5px",
            color: "#475569",
            lineHeight: "1.5",
            margin: 0
          }
        },
        message
      ))), details && /* @__PURE__ */ React2.createElement(
        "div",
        {
          style: {
            marginTop: "16px",
            backgroundColor: "#f8fafc",
            border: "1px solid #e2e8f0",
            borderRadius: "8px",
            padding: "12px 14px",
            fontSize: "12.5px",
            color: "#334155"
          }
        },
        details
      )),
      /* @__PURE__ */ React2.createElement(
        "div",
        {
          style: {
            padding: "14px 20px",
            backgroundColor: "#f8fafc",
            borderTop: "1px solid #e2e8f0",
            display: "flex",
            justifyContent: "flex-end",
            gap: "10px"
          }
        },
        /* @__PURE__ */ React2.createElement(
          "button",
          {
            type: "button",
            onClick: onCancel,
            disabled: loading,
            style: {
              padding: "9px 16px",
              borderRadius: "7px",
              border: "1px solid #cbd5e1",
              backgroundColor: "#ffffff",
              color: "#334155",
              fontWeight: 600,
              fontSize: "13px",
              cursor: loading ? "not-allowed" : "pointer",
              transition: "background-color 0.15s"
            },
            onMouseOver: (e) => {
              if (!loading) e.currentTarget.style.backgroundColor = "#f1f5f9";
            },
            onMouseOut: (e) => {
              if (!loading) e.currentTarget.style.backgroundColor = "#ffffff";
            }
          },
          cancelText
        ),
        /* @__PURE__ */ React2.createElement(
          "button",
          {
            type: "button",
            onClick: onConfirm,
            disabled: loading,
            style: {
              padding: "9px 18px",
              borderRadius: "7px",
              border: "none",
              backgroundColor: currentTheme.buttonBg,
              color: "#ffffff",
              fontWeight: 600,
              fontSize: "13px",
              cursor: loading ? "not-allowed" : "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              boxShadow: "0 1px 2px rgba(0, 0, 0, 0.05)",
              transition: "background-color 0.15s"
            },
            onMouseOver: (e) => {
              if (!loading) e.currentTarget.style.backgroundColor = currentTheme.buttonHover;
            },
            onMouseOut: (e) => {
              if (!loading) e.currentTarget.style.backgroundColor = currentTheme.buttonBg;
            }
          },
          loading && /* @__PURE__ */ React2.createElement(
            "span",
            {
              style: {
                display: "inline-block",
                width: "12px",
                height: "12px",
                border: "2px solid rgba(255,255,255,0.3)",
                borderTopColor: "#ffffff",
                borderRadius: "50%",
                animation: "spin 0.6s linear infinite"
              }
            }
          ),
          confirmText
        )
      )
    )
  );
}

// src/pages/DocumentViewPage.jsx
var STATUS_INFO = {
  UPLOADED: { label: "Uploaded", cls: "status-uploaded" },
  PROCESSING: { label: "Processing OCR", cls: "status-processing" },
  COMPLETED: { label: "OCR Completed", cls: "status-completed" },
  FAILED: { label: "OCR Failed", cls: "status-failed" }
};
function formatBytes(bytes) {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
function formatDate(isoStr) {
  if (!isoStr) return "\u2014";
  return new Date(isoStr).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}
function formatCurrency(amount, currency = "INR") {
  if (amount === null || amount === void 0 || amount === "") return "\u2014";
  const num = typeof amount === "number" ? amount : parseFloat(amount);
  if (isNaN(num)) return "\u2014";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: currency || "INR",
    maximumFractionDigits: 2
  }).format(num);
}
function DocumentViewPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();
  const [doc, setDoc] = useState2(null);
  const [extraction, setExtraction] = useState2(null);
  const [formData, setFormData] = useState2({});
  const [loading, setLoading] = useState2(true);
  const [loadingExtraction, setLoadingExtraction] = useState2(false);
  const [error, setError] = useState2("");
  const [toast, setToast] = useState2(null);
  const [isEditing, setIsEditing] = useState2(false);
  const [saving, setSaving] = useState2(false);
  const [approving, setApproving] = useState2(false);
  const [reprocessing, setReprocessing] = useState2(false);
  const [deleting, setDeleting] = useState2(false);
  const [restoring, setRestoring] = useState2(false);
  const [showOverrideModal, setShowOverrideModal] = useState2(false);
  const [overrideReason, setOverrideReason] = useState2("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState2(false);
  const [viewMode, setViewMode] = useState2("original");
  const [copies, setCopies] = useState2([]);
  const [selectedCopyVersion, setSelectedCopyVersion] = useState2(null);
  const [regeneratingCopy, setRegeneratingCopy] = useState2(false);
  const [copyMsg, setCopyMsg] = useState2("");
  const [zoom, setZoom] = useState2(1);
  const [rotation, setRotation] = useState2(0);
  const [isFullScreen, setIsFullScreen] = useState2(false);
  const [isDragging, setIsDragging] = useState2(false);
  const [dragStart, setDragStart] = useState2({ x: 0, y: 0, scrollLeft: 0, scrollTop: 0 });
  const imageContainerRef = useRef(null);
  const fullScreenImageRef = useRef(null);
  const [showDetails, setShowDetails] = useState2(false);
  const [showRawData, setShowRawData] = useState2(false);
  const [rawTab, setRawTab] = useState2("json");
  const [editsHistory, setEditsHistory] = useState2([]);
  const [loadingHistory, setLoadingHistory] = useState2(false);
  const [copiedHash, setCopiedHash] = useState2(false);
  const [copiedJson, setCopiedJson] = useState2(false);
  const [copiedText, setCopiedText] = useState2(false);
  const showToast = (message, type = "info") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4e3);
  };
  const handleZoomIn = () => setZoom((prev) => Math.min(Number((prev + 0.25).toFixed(2)), 3.5));
  const handleZoomOut = () => setZoom((prev) => Math.max(Number((prev - 0.25).toFixed(2)), 0.5));
  const handleZoomReset = () => {
    setZoom(1);
    setRotation(0);
    if (imageContainerRef.current) {
      imageContainerRef.current.scrollLeft = 0;
      imageContainerRef.current.scrollTop = 0;
    }
  };
  const handleRotate = () => {
    setRotation((prev) => (prev + 90) % 360);
  };
  const handleMouseDown = (e, containerRef) => {
    const targetRef = containerRef || imageContainerRef;
    if (zoom <= 1 || !targetRef.current) return;
    setIsDragging(true);
    setDragStart({
      x: e.clientX,
      y: e.clientY,
      scrollLeft: targetRef.current.scrollLeft,
      scrollTop: targetRef.current.scrollTop
    });
  };
  const handleMouseMove = (e, containerRef) => {
    const targetRef = containerRef || imageContainerRef;
    if (!isDragging || !targetRef.current) return;
    e.preventDefault();
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    targetRef.current.scrollLeft = dragStart.scrollLeft - dx;
    targetRef.current.scrollTop = dragStart.scrollTop - dy;
  };
  const handleMouseUp = () => {
    setIsDragging(false);
  };
  const fetchDoc = async () => {
    try {
      const data = await api.getDocument(id);
      setDoc(data);
      if (data.ocr_status === "COMPLETED") {
        fetchExtraction();
      }
    } catch (err) {
      setError(err.message || "Failed to load document");
    } finally {
      setLoading(false);
    }
  };
  const fetchExtraction = async () => {
    try {
      setLoadingExtraction(true);
      const data = await api.getDocumentExtraction(id);
      setExtraction(data);
      setFormData(data?.data || {});
    } catch (err) {
      console.warn("Extraction fetch error or not ready:", err);
    } finally {
      setLoadingExtraction(false);
    }
  };
  const fetchCopies = async () => {
    try {
      const data = await api.listDocumentCopies(id);
      setCopies(data || []);
      if (data && data.length > 0 && !selectedCopyVersion) {
        const current = data.find((c) => c.is_current) || data[0];
        setSelectedCopyVersion(current.copy_version);
      }
    } catch {
    }
  };
  const fetchHistory = async () => {
    try {
      setLoadingHistory(true);
      const edits = await api.getDocumentExtractionEdits(id);
      setEditsHistory(edits || []);
    } catch (err) {
      showToast(err.message || "Failed to load edit history", "error");
    } finally {
      setLoadingHistory(false);
    }
  };
  useEffect3(() => {
    fetchDoc();
    const interval = setInterval(async () => {
      const data = await api.getDocument(id).catch(() => null);
      if (data) {
        setDoc(data);
        if (data.ocr_status === "COMPLETED" || data.ocr_status === "FAILED") {
          clearInterval(interval);
          if (data.ocr_status === "COMPLETED" && !extraction) {
            fetchExtraction();
          }
        }
      }
    }, 3e3);
    return () => clearInterval(interval);
  }, [id]);
  useEffect3(() => {
    if (viewMode === "standardised") {
      fetchCopies();
    }
  }, [id, viewMode]);
  useEffect3(() => {
    if (showRawData && rawTab === "history") {
      fetchHistory();
    }
  }, [showRawData, rawTab]);
  const handleRegenerateCopy = async () => {
    setRegeneratingCopy(true);
    setCopyMsg("");
    setError("");
    try {
      const res = await api.regenerateDocumentCopy(id);
      setCopyMsg(`Standardised copy updated to v${res.copy_version}!`);
      fetchCopies();
      setSelectedCopyVersion(res.copy_version);
    } catch (err) {
      setError(err.message || "Failed to regenerate standardised copy");
    } finally {
      setRegeneratingCopy(false);
    }
  };
  const handleReprocess = async () => {
    setReprocessing(true);
    try {
      const updated = await api.reprocessDocument(id);
      setDoc(updated);
      setError("");
      showToast("OCR re-processing initiated", "info");
    } catch (err) {
      if (err.status === 409 || err.message?.includes("active job")) {
        setError("Document is currently being processed by an active job. Please wait a moment.");
      } else {
        setError(err.message || "Failed to reprocess document.");
      }
    } finally {
      setReprocessing(false);
    }
  };
  const handleRestore = async () => {
    setRestoring(true);
    try {
      const updated = await api.restoreDocument(id);
      setDoc(updated);
      setError("");
      showToast("Document restored successfully", "success");
    } catch (err) {
      setError(err.message || "Failed to restore document.");
    } finally {
      setRestoring(false);
    }
  };
  const handleDelete = () => {
    setShowDeleteConfirm(true);
  };
  const confirmDelete = async () => {
    try {
      setDeleting(true);
      await api.deleteDocument(id);
      navigate("/documents");
    } catch (err) {
      setError(err.message || "Failed to delete document.");
      setShowDeleteConfirm(false);
    } finally {
      setDeleting(false);
    }
  };
  const handleFieldChange = (path, val) => {
    const updated = JSON.parse(JSON.stringify(formData));
    const parts = path.split(".");
    let curr = updated;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!curr[parts[i]]) curr[parts[i]] = {};
      curr = curr[parts[i]];
    }
    curr[parts[parts.length - 1]] = val;
    setFormData(updated);
  };
  const handleLineItemChange = (index, fieldKey, val) => {
    const updated = JSON.parse(JSON.stringify(formData));
    const items = [...updated.items || []];
    if (items[index]) {
      const item = { ...items[index] };
      item[fieldKey] = val;
      if (fieldKey === "hsn") item.hsn_sac = val;
      if (fieldKey === "hsn_sac") item.hsn = val;
      if (fieldKey === "unit") item.batch = val;
      if (fieldKey === "batch") item.unit = val;
      items[index] = item;
      updated.items = items;
      setFormData(updated);
    }
  };
  const handleAddLineItem = () => {
    const updated = JSON.parse(JSON.stringify(formData));
    const items = [...updated.items || []];
    items.push({
      sl: items.length + 1,
      description: "",
      hsn: "",
      hsn_sac: "",
      qty: "1",
      unit: "nos",
      batch: "",
      rate: 0,
      discount: 0,
      gst_rate: 18,
      amount: 0
    });
    updated.items = items;
    setFormData(updated);
  };
  const handleDeleteLineItem = (index) => {
    const updated = JSON.parse(JSON.stringify(formData));
    const items = [...updated.items || []];
    items.splice(index, 1);
    updated.items = items;
    setFormData(updated);
  };
  const handleSaveCorrections = async () => {
    if (!extraction) return;
    try {
      setSaving(true);
      const res = await api.saveExtractionCorrections(id, {
        version: extraction.version,
        data: formData
      });
      setExtraction(res);
      setFormData(res.data || {});
      setIsEditing(false);
      showToast("Corrections saved and revalidated successfully!", "success");
      if (showRawData && rawTab === "history") fetchHistory();
    } catch (err) {
      showToast(err.message || "Failed to save corrections", "error");
      if (err.message && err.message.includes("409")) {
        fetchExtraction();
      }
    } finally {
      setSaving(false);
    }
  };
  const handleApprove = async (override = false) => {
    if (!extraction) return;
    try {
      setApproving(true);
      const payload = { override, override_reason: override ? overrideReason : void 0 };
      const res = await api.approveDocumentExtraction(id, payload);
      setExtraction(res);
      setShowOverrideModal(false);
      setOverrideReason("");
      showToast("Document extraction verified and approved!", "success");
    } catch (err) {
      showToast(err.message || "Failed to approve extraction", "error");
    } finally {
      setApproving(false);
    }
  };
  const getFieldFlag = (path) => {
    if (!extraction?.validation_flags) return null;
    return extraction.validation_flags.find((f) => f.field_path === path);
  };
  if (loading) {
    return /* @__PURE__ */ React3.createElement("div", { className: "page-content" }, /* @__PURE__ */ React3.createElement("div", { className: "loading-state" }, /* @__PURE__ */ React3.createElement("div", { className: "spinner" }), /* @__PURE__ */ React3.createElement("p", null, "Loading document review workspace\u2026")));
  }
  if (error && !doc) {
    return /* @__PURE__ */ React3.createElement("div", { className: "page-content" }, /* @__PURE__ */ React3.createElement("div", { className: "alert alert-error" }, error), /* @__PURE__ */ React3.createElement("button", { className: "btn btn-ghost", onClick: () => navigate("/documents") }, "\u2190 Back to Documents"));
  }
  const fileUrl = api.getFileUrl(id);
  const isPdf = doc?.mime_type === "application/pdf";
  const statusInfo = STATUS_INFO[doc?.ocr_status] || STATUS_INFO.UPLOADED;
  const isApproved = extraction?.status === "approved";
  const hasErrors = extraction?.has_errors || (extraction?.validation_flags || []).some((f) => f.severity === "error");
  const activeData = extraction && extraction.data ? formData : doc?.structured_data ? JSON.parse(doc.structured_data || "{}") : {};
  const canReprocess = !doc?.deleted_at && (doc?.ocr_status === "COMPLETED" || doc?.ocr_status === "FAILED") && (hasPermission("document.reprocess") || user?.role === "GLOBAL_ADMIN" || user?.role === "ADMIN" || doc?.uploaded_by === user?.id);
  const canDelete = !doc?.deleted_at && (hasPermission("document.delete") || user?.role === "GLOBAL_ADMIN" || user?.role === "ADMIN" || doc?.uploaded_by === user?.id);
  const canRestore = Boolean(doc?.deleted_at) && (hasPermission("document.restore") || user?.role === "GLOBAL_ADMIN" || user?.role === "ADMIN");
  const displayTitle = activeData?.invoice?.number || doc?.invoice_number ? `Invoice: ${activeData?.invoice?.number || doc.invoice_number}` : `Document #${doc.id}`;
  return /* @__PURE__ */ React3.createElement("div", { className: "page-content", style: { maxWidth: "1600px", margin: "0 auto", paddingBottom: "3rem" } }, toast && /* @__PURE__ */ React3.createElement(
    "div",
    {
      style: {
        position: "fixed",
        top: "1.25rem",
        right: "1.5rem",
        zIndex: 1e4,
        padding: "0.75rem 1.25rem",
        borderRadius: "8px",
        backgroundColor: toast.type === "error" ? "#ef4444" : toast.type === "success" ? "#16a34a" : "#2563eb",
        color: "#ffffff",
        fontWeight: 600,
        fontSize: "0.875rem",
        boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
        display: "flex",
        alignItems: "center",
        gap: "0.5rem"
      }
    },
    /* @__PURE__ */ React3.createElement("span", null, toast.type === "error" ? "\u26A0\uFE0F" : toast.type === "success" ? "\u2713" : "\u2139\uFE0F"),
    /* @__PURE__ */ React3.createElement("span", null, toast.message)
  ), error && /* @__PURE__ */ React3.createElement("div", { className: "alert alert-error", style: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" } }, /* @__PURE__ */ React3.createElement("span", null, error), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-ghost btn-sm",
      onClick: () => setError(""),
      style: { padding: "0.1rem 0.4rem", color: "#dc2626", fontWeight: "bold" },
      title: "Dismiss error"
    },
    "\u2715"
  )), doc.deleted_at && /* @__PURE__ */ React3.createElement("div", { className: "alert alert-warning", style: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1.25rem", padding: "0.85rem 1.25rem" } }, /* @__PURE__ */ React3.createElement("div", null, /* @__PURE__ */ React3.createElement("strong", null, "\u26A0\uFE0F Document in Trash"), " \u2014 Soft-deleted on ", formatDate(doc.deleted_at), "."), canRestore && /* @__PURE__ */ React3.createElement("button", { className: "btn btn-primary btn-sm", onClick: handleRestore, disabled: restoring }, restoring ? "Restoring\u2026" : "Restore Document")), /* @__PURE__ */ React3.createElement(
    "div",
    {
      style: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        flexWrap: "wrap",
        gap: "1rem",
        marginBottom: "1.25rem",
        paddingBottom: "1rem",
        borderBottom: "1px solid var(--border)"
      }
    },
    /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", alignItems: "flex-start", gap: "0.875rem" } }, /* @__PURE__ */ React3.createElement(
      "button",
      {
        type: "button",
        className: "btn btn-secondary",
        onClick: () => navigate("/documents"),
        style: { padding: "0.4rem 0.75rem", fontSize: "0.8125rem", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "0.25rem" }
      },
      "\u2190 Documents"
    ), /* @__PURE__ */ React3.createElement("div", null, /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", alignItems: "center", gap: "0.625rem", flexWrap: "wrap" } }, /* @__PURE__ */ React3.createElement("h1", { style: { fontSize: "1.35rem", fontWeight: 700, margin: 0, color: "#0f172a" } }, displayTitle), isApproved ? /* @__PURE__ */ React3.createElement("span", { style: { fontSize: "0.72rem", fontWeight: 700, padding: "3px 9px", borderRadius: "12px", backgroundColor: "#dcfce7", color: "#15803d", border: "1px solid #bbf7d0", textTransform: "uppercase" } }, "\u2713 Approved") : extraction?.status === "needs_review" ? /* @__PURE__ */ React3.createElement("span", { style: { fontSize: "0.72rem", fontWeight: 700, padding: "3px 9px", borderRadius: "12px", backgroundColor: "#fef3c7", color: "#b45309", border: "1px solid #fde68a", textTransform: "uppercase" } }, "\u26A0\uFE0F Needs Review") : /* @__PURE__ */ React3.createElement("span", { className: `status-badge ${statusInfo.cls}` }, statusInfo.label), extraction?.version && /* @__PURE__ */ React3.createElement("span", { style: { fontSize: "0.72rem", color: "#64748b", backgroundColor: "#f1f5f9", padding: "2px 7px", borderRadius: "4px", border: "1px solid #e2e8f0" } }, "Lock #", extraction.version)), /* @__PURE__ */ React3.createElement("div", { style: { fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.35rem", display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" } }, /* @__PURE__ */ React3.createElement("span", { title: doc.original_filename, style: { maxWidth: "320px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, "\u{1F4C4} ", doc.original_filename), /* @__PURE__ */ React3.createElement("span", null, "\u2022"), /* @__PURE__ */ React3.createElement("span", null, "Uploaded ", formatDate(doc.created_at)), /* @__PURE__ */ React3.createElement("span", null, "\u2022"), /* @__PURE__ */ React3.createElement("span", null, formatBytes(doc.file_size)), doc.uploader_name && /* @__PURE__ */ React3.createElement(React3.Fragment, null, /* @__PURE__ */ React3.createElement("span", null, "\u2022"), /* @__PURE__ */ React3.createElement("span", null, "By ", doc.uploader_name))))),
    /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" } }, canReprocess && /* @__PURE__ */ React3.createElement(
      "button",
      {
        type: "button",
        className: "btn btn-secondary",
        onClick: handleReprocess,
        disabled: reprocessing || doc.ocr_status === "PROCESSING" || doc.ocr_status === "UPLOADED",
        title: "Re-run OCR and extraction pipeline",
        style: { display: "inline-flex", alignItems: "center", gap: "0.35rem", fontWeight: 600, fontSize: "0.8125rem" }
      },
      reprocessing ? /* @__PURE__ */ React3.createElement(React3.Fragment, null, /* @__PURE__ */ React3.createElement("span", { className: "spinner-sm", style: { borderTopColor: "var(--brand)" } }), " Reprocessing\u2026") : /* @__PURE__ */ React3.createElement(React3.Fragment, null, "\u21BB Re-process OCR")
    ), doc.ocr_status === "COMPLETED" && /* @__PURE__ */ React3.createElement(React3.Fragment, null, isEditing ? /* @__PURE__ */ React3.createElement(React3.Fragment, null, /* @__PURE__ */ React3.createElement(
      "button",
      {
        type: "button",
        className: "btn btn-secondary",
        onClick: () => {
          setFormData(extraction?.data || {});
          setIsEditing(false);
        },
        disabled: saving,
        style: { fontSize: "0.8125rem", fontWeight: 600 }
      },
      "Cancel"
    ), /* @__PURE__ */ React3.createElement(
      "button",
      {
        type: "button",
        className: "btn btn-primary",
        onClick: handleSaveCorrections,
        disabled: saving,
        style: { fontSize: "0.8125rem", fontWeight: 600 }
      },
      saving ? "Saving\u2026" : "\u{1F4BE} Save Changes"
    )) : !isApproved && /* @__PURE__ */ React3.createElement(
      "button",
      {
        type: "button",
        className: "btn btn-secondary",
        onClick: () => setIsEditing(true),
        style: { fontSize: "0.8125rem", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "0.3rem" }
      },
      "\u270F\uFE0F Edit Fields"
    ), !isApproved && !isEditing && /* @__PURE__ */ React3.createElement(
      "button",
      {
        type: "button",
        className: "btn btn-primary",
        onClick: () => {
          if (hasErrors) {
            setShowOverrideModal(true);
          } else {
            handleApprove(false);
          }
        },
        disabled: approving,
        style: {
          backgroundColor: hasErrors ? "#f59e0b" : "#16a34a",
          borderColor: hasErrors ? "#f59e0b" : "#16a34a",
          color: "#ffffff",
          fontWeight: 600,
          fontSize: "0.8125rem"
        }
      },
      approving ? "Approving\u2026" : hasErrors ? "\u26A0\uFE0F Override & Approve" : "\u2713 Approve Extraction"
    ), /* @__PURE__ */ React3.createElement(
      "button",
      {
        type: "button",
        className: `btn ${viewMode === "standardised" ? "btn-primary" : "btn-secondary"}`,
        onClick: () => setViewMode(viewMode === "standardised" ? "original" : "standardised"),
        style: { fontSize: "0.8125rem", fontWeight: 600 },
        title: "View generated standardised invoice copy"
      },
      "\u{1F4C4} ",
      viewMode === "standardised" ? "Original Document" : "Standardised Invoice"
    )), canDelete && /* @__PURE__ */ React3.createElement(
      "button",
      {
        type: "button",
        className: "btn btn-secondary",
        onClick: handleDelete,
        disabled: deleting,
        style: { color: "#ef4444", borderColor: "#fca5a5", fontSize: "0.8125rem", fontWeight: 600 },
        title: "Delete document"
      },
      "\u{1F5D1}\uFE0F Delete"
    ))
  ), /* @__PURE__ */ React3.createElement("div", { className: "doc-review-layout" }, /* @__PURE__ */ React3.createElement("div", { className: "doc-review-panel" }, /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", borderBottom: "1px solid var(--border)", background: "#f8fafc" } }, /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      onClick: () => setViewMode("original"),
      style: {
        flex: 1,
        padding: "0.625rem 1rem",
        border: "none",
        background: viewMode === "original" ? "#ffffff" : "transparent",
        borderBottom: viewMode === "original" ? "2px solid var(--brand)" : "none",
        color: viewMode === "original" ? "var(--brand)" : "var(--text-muted)",
        fontWeight: 600,
        fontSize: "0.84rem",
        cursor: "pointer"
      }
    },
    "Original Document"
  ), doc?.ocr_status === "COMPLETED" && /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      onClick: () => setViewMode("standardised"),
      style: {
        flex: 1,
        padding: "0.625rem 1rem",
        border: "none",
        background: viewMode === "standardised" ? "#ffffff" : "transparent",
        borderBottom: viewMode === "standardised" ? "2px solid var(--brand)" : "none",
        color: viewMode === "standardised" ? "var(--brand)" : "var(--text-muted)",
        fontWeight: 600,
        fontSize: "0.84rem",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.4rem"
      }
    },
    /* @__PURE__ */ React3.createElement("span", null, "Standardised Copy"),
    copies.some((c) => c.is_current && c.is_stale) && /* @__PURE__ */ React3.createElement("span", { style: { fontSize: "0.68rem", background: "#fef3c7", color: "#b45309", padding: "0.1rem 0.35rem", borderRadius: "4px" } }, "Stale")
  )), viewMode === "standardised" && /* @__PURE__ */ React3.createElement("div", { style: { padding: "0.6rem 0.875rem", background: "#ffffff", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: "0.5rem" } }, copyMsg && /* @__PURE__ */ React3.createElement("div", { className: "alert alert-success", style: { fontSize: "0.8rem", padding: "0.4rem 0.6rem", margin: 0 } }, copyMsg), copies.find((c) => c.is_current)?.is_stale && /* @__PURE__ */ React3.createElement("div", { style: { background: "#fffbeb", border: "1px solid #fde68a", borderRadius: "6px", padding: "0.5rem 0.75rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" } }, /* @__PURE__ */ React3.createElement("div", { style: { fontSize: "0.75rem", color: "#92400e" } }, "\u26A0\uFE0F Document OCR data was modified after this copy was rendered."), /* @__PURE__ */ React3.createElement(
    "button",
    {
      className: "btn btn-sm btn-primary",
      style: { fontSize: "0.75rem", padding: "0.2rem 0.5rem", whiteSpace: "nowrap" },
      onClick: handleRegenerateCopy,
      disabled: regeneratingCopy
    },
    regeneratingCopy ? "Regenerating\u2026" : "Regenerate Copy"
  )), copies.length > 1 && /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem" } }, /* @__PURE__ */ React3.createElement("span", { style: { color: "var(--text-muted)" } }, "Version History:"), /* @__PURE__ */ React3.createElement(
    "select",
    {
      className: "form-control",
      style: { width: "auto", padding: "0.2rem 0.5rem", fontSize: "0.78rem" },
      value: selectedCopyVersion || "",
      onChange: (e) => setSelectedCopyVersion(parseInt(e.target.value, 10))
    },
    copies.map((c) => /* @__PURE__ */ React3.createElement("option", { key: c.id, value: c.copy_version }, "v", c.copy_version, " ", c.is_current ? "(Current)" : "(Historical)", " ", c.is_stale ? "[Stale]" : ""))
  ))), /* @__PURE__ */ React3.createElement("div", { className: "doc-preview-toolbar" }, /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", alignItems: "center", gap: "0.4rem" } }, /* @__PURE__ */ React3.createElement("span", { style: { fontSize: "0.72rem", backgroundColor: "#f1f5f9", color: "#475569", padding: "0.15rem 0.5rem", borderRadius: "4px", border: "1px solid #e2e8f0", fontWeight: 600 } }, viewMode === "original" ? doc.mime_type || "image/jpeg" : "PDF Copy"), viewMode === "original" ? /* @__PURE__ */ React3.createElement(
    "a",
    {
      href: fileUrl,
      target: "_blank",
      rel: "noreferrer",
      download: doc.original_filename,
      style: { fontSize: "0.75rem", color: "var(--brand)", textDecoration: "none", fontWeight: 600, padding: "0.2rem 0.45rem", borderRadius: "4px", backgroundColor: "#fff1f2" },
      title: "Download original uploaded file"
    },
    "\u{1F4E5} Download Original"
  ) : /* @__PURE__ */ React3.createElement(
    "a",
    {
      href: selectedCopyVersion ? api.getDocumentCopyPdfUrl(id, selectedCopyVersion, true) : `${api.getInvoiceUrl(id)}&download=true`,
      target: "_blank",
      rel: "noreferrer",
      download: `supplier_copy_${id}_v${selectedCopyVersion || 1}.pdf`,
      style: { fontSize: "0.75rem", color: "var(--brand)", textDecoration: "none", fontWeight: 600, padding: "0.2rem 0.45rem", borderRadius: "4px", backgroundColor: "#fff1f2" },
      title: "Download standardised invoice PDF"
    },
    "\u{1F4E5} Download PDF"
  )), !isPdf && viewMode === "original" && /* @__PURE__ */ React3.createElement("div", { style: { display: "inline-flex", alignItems: "center", gap: "0.25rem" } }, /* @__PURE__ */ React3.createElement("div", { style: { display: "inline-flex", alignItems: "center", backgroundColor: "#f8fafc", borderRadius: "6px", border: "1px solid #cbd5e1", overflow: "hidden" } }, /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      onClick: handleZoomOut,
      disabled: zoom <= 0.5,
      title: "Zoom Out (\u2212)",
      style: { border: "none", background: "none", padding: "0.2rem 0.5rem", cursor: zoom <= 0.5 ? "not-allowed" : "pointer", fontSize: "0.85rem", fontWeight: "bold", color: "#334155" }
    },
    "\u2212"
  ), /* @__PURE__ */ React3.createElement("span", { style: { padding: "0.15rem 0.35rem", fontSize: "0.72rem", fontWeight: 700, minWidth: "3.2rem", textAlign: "center", color: "#0f172a", borderLeft: "1px solid #e2e8f0", borderRight: "1px solid #e2e8f0" } }, Math.round(zoom * 100), "%"), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      onClick: handleZoomIn,
      disabled: zoom >= 3.5,
      title: "Zoom In (+)",
      style: { border: "none", background: "none", padding: "0.2rem 0.5rem", cursor: zoom >= 3.5 ? "not-allowed" : "pointer", fontSize: "0.85rem", fontWeight: "bold", color: "#334155" }
    },
    "+"
  ), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      onClick: handleZoomReset,
      title: "Reset to 100% Fit",
      style: { border: "none", borderLeft: "1px solid #e2e8f0", background: "none", padding: "0.2rem 0.45rem", cursor: "pointer", fontSize: "0.72rem", fontWeight: 600, color: "var(--brand)" }
    },
    "Fit"
  )), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      onClick: handleRotate,
      title: "Rotate 90 degrees",
      style: { padding: "0.25rem 0.5rem", fontSize: "0.75rem", fontWeight: 600, borderRadius: "6px", border: "1px solid #cbd5e1", backgroundColor: "#ffffff", cursor: "pointer", color: "#334155" }
    },
    "\u21BB Rotate ",
    rotation > 0 ? `(${rotation}\xB0)` : ""
  ), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      onClick: () => setIsFullScreen(true),
      title: "Expand to Fullscreen",
      style: { padding: "0.25rem 0.5rem", fontSize: "0.75rem", fontWeight: 600, borderRadius: "6px", border: "1px solid #cbd5e1", backgroundColor: "#ffffff", cursor: "pointer", color: "#334155" }
    },
    "\u26F6 Fullscreen"
  ))), /* @__PURE__ */ React3.createElement(
    "div",
    {
      ref: imageContainerRef,
      onMouseDown: (e) => handleMouseDown(e, imageContainerRef),
      onMouseMove: (e) => handleMouseMove(e, imageContainerRef),
      onMouseUp: handleMouseUp,
      onMouseLeave: handleMouseUp,
      className: "doc-preview-viewport",
      style: {
        cursor: zoom > 1 ? isDragging ? "grabbing" : "grab" : "default",
        userSelect: isDragging ? "none" : "auto"
      }
    },
    viewMode === "original" ? isPdf ? /* @__PURE__ */ React3.createElement("div", { style: { width: "100%", height: "620px" } }, /* @__PURE__ */ React3.createElement("iframe", { src: `${fileUrl}#toolbar=0`, title: doc.original_filename, className: "pdf-iframe", style: { width: "100%", height: "100%", border: "none", borderRadius: "6px", backgroundColor: "#ffffff" } })) : /* @__PURE__ */ React3.createElement(
      "div",
      {
        style: {
          transform: `scale(${zoom}) rotate(${rotation}deg)`,
          transformOrigin: "top center",
          transition: isDragging ? "none" : "transform 0.12s ease-out",
          maxWidth: zoom <= 1 ? "100%" : "none",
          display: "flex",
          justifyContent: "center"
        }
      },
      /* @__PURE__ */ React3.createElement(
        "img",
        {
          src: fileUrl,
          alt: doc.original_filename,
          draggable: false,
          style: {
            maxWidth: "100%",
            height: "auto",
            objectFit: "contain",
            borderRadius: "6px",
            boxShadow: "0 4px 10px rgba(0, 0, 0, 0.08)",
            backgroundColor: "#ffffff",
            display: "block"
          }
        }
      )
    ) : /* @__PURE__ */ React3.createElement("div", { style: { width: "100%", height: "620px" } }, /* @__PURE__ */ React3.createElement(
      "iframe",
      {
        src: selectedCopyVersion ? `${api.getDocumentCopyPdfUrl(id, selectedCopyVersion)}#toolbar=0` : `${api.getInvoiceUrl(id)}#toolbar=0`,
        title: "Standardised Supplier Copy",
        style: { width: "100%", height: "100%", border: "none", borderRadius: "6px", backgroundColor: "#ffffff" }
      }
    ))
  )), /* @__PURE__ */ React3.createElement("div", { className: "doc-extracted-container" }, extraction?.validation_flags && extraction.validation_flags.length > 0 && /* @__PURE__ */ React3.createElement(
    "div",
    {
      style: {
        backgroundColor: hasErrors ? "#fef2f2" : "#fffbeb",
        border: `1px solid ${hasErrors ? "#fecaca" : "#fde68a"}`,
        borderRadius: "8px",
        padding: "0.875rem 1rem"
      }
    },
    /* @__PURE__ */ React3.createElement("div", { style: { fontWeight: 700, fontSize: "0.85rem", color: hasErrors ? "#b91c1c" : "#b45309", marginBottom: "0.35rem", display: "flex", alignItems: "center", gap: "0.4rem" } }, /* @__PURE__ */ React3.createElement("span", null, hasErrors ? "\u26A0\uFE0F" : "\u2139\uFE0F"), /* @__PURE__ */ React3.createElement("span", null, hasErrors ? `${extraction.validation_flags.filter((f) => f.severity === "error").length} Validation Error(s) Detected` : `${extraction.validation_flags.length} Validation Warning(s)`)),
    /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", flexDirection: "column", gap: "0.3rem" } }, extraction.validation_flags.map((flag, idx) => /* @__PURE__ */ React3.createElement(
      "div",
      {
        key: idx,
        style: {
          fontSize: "0.78rem",
          color: flag.severity === "error" ? "#991b1b" : "#92400e",
          padding: "0.2rem 0.4rem",
          backgroundColor: flag.severity === "error" ? "#fee2e2" : "#fef3c7",
          borderRadius: "4px"
        }
      },
      /* @__PURE__ */ React3.createElement("strong", null, flag.field_path || "General", ":"),
      " ",
      flag.message
    )))
  ), doc.ocr_status === "FAILED" && /* @__PURE__ */ React3.createElement("div", { className: "alert alert-error" }, /* @__PURE__ */ React3.createElement("div", { style: { fontWeight: 700, marginBottom: "0.25rem" } }, "OCR Processing Failed"), /* @__PURE__ */ React3.createElement("div", { style: { fontSize: "0.825rem" } }, doc.ocr_text || "OCR pipeline could not extract text from this document."), doc.ocr_text && doc.ocr_text.includes("consent") && /* @__PURE__ */ React3.createElement("div", { style: { marginTop: "0.5rem", fontSize: "0.8rem", background: "#ffffff", padding: "0.5rem", borderRadius: "4px", color: "#991b1b" } }, "\u{1F4A1} ", /* @__PURE__ */ React3.createElement("strong", null, "Action Required:"), " A Company Administrator must grant external AI consent in ", /* @__PURE__ */ React3.createElement("strong", null, "Company Admin \u2192 AI & Providers"), " before reprocessing.")), doc.ocr_status === "PROCESSING" && /* @__PURE__ */ React3.createElement("div", { style: { padding: "2rem", textAlign: "center", background: "#ffffff", border: "1px solid var(--border)", borderRadius: "8px" } }, /* @__PURE__ */ React3.createElement("div", { className: "spinner", style: { margin: "0 auto 0.75rem" } }), /* @__PURE__ */ React3.createElement("div", { style: { fontWeight: 600, color: "#0f172a" } }, "OCR Extraction in Progress\u2026"), /* @__PURE__ */ React3.createElement("div", { style: { fontSize: "0.8125rem", color: "var(--text-muted)", marginTop: "0.25rem" } }, "This workspace will automatically refresh once field analysis completes.")), /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-card" }, /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-header" }, /* @__PURE__ */ React3.createElement("h3", { className: "extracted-section-title" }, "\u{1F3E2} Supplier Details"), activeData.seller?.state_code && /* @__PURE__ */ React3.createElement("span", { style: { fontSize: "0.72rem", backgroundColor: "#f1f5f9", color: "#475569", padding: "0.15rem 0.45rem", borderRadius: "4px" } }, "State Code: ", activeData.seller.state_code)), isEditing ? /* @__PURE__ */ React3.createElement("div", { className: "field-grid-2" }, /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Supplier Name"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.seller?.name || "",
      onChange: (e) => handleFieldChange("seller.name", e.target.value)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "GSTIN"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.seller?.gstin || "",
      onChange: (e) => handleFieldChange("seller.gstin", e.target.value)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell", style: { gridColumn: "span 2" } }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Address"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.seller?.address || "",
      onChange: (e) => handleFieldChange("seller.address", e.target.value)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Phone"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.seller?.phone || "",
      onChange: (e) => handleFieldChange("seller.phone", e.target.value)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Email"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.seller?.email || "",
      onChange: (e) => handleFieldChange("seller.email", e.target.value)
    }
  ))) : /* @__PURE__ */ React3.createElement("div", { className: "field-grid-2" }, /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Supplier Name"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontWeight: 700, fontSize: "0.92rem" } }, activeData.seller?.name || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "Not detected"))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "GSTIN"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontFamily: "monospace", fontWeight: 600 } }, activeData.seller?.gstin || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "Not detected"))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell", style: { gridColumn: "span 2" } }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Address"), /* @__PURE__ */ React3.createElement("span", { className: "field-value" }, activeData.seller?.address || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "Not detected"))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Phone"), /* @__PURE__ */ React3.createElement("span", { className: "field-value" }, activeData.seller?.phone || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "\u2014"))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Email"), /* @__PURE__ */ React3.createElement("span", { className: "field-value" }, activeData.seller?.email || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "\u2014"))))), /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-card" }, /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-header" }, /* @__PURE__ */ React3.createElement("h3", { className: "extracted-section-title" }, "\u{1F4D1} Invoice Details")), isEditing ? /* @__PURE__ */ React3.createElement("div", { className: "field-grid-2" }, /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Invoice Number"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.invoice?.number || "",
      onChange: (e) => handleFieldChange("invoice.number", e.target.value)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Invoice Date"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.invoice?.date || "",
      onChange: (e) => handleFieldChange("invoice.date", e.target.value)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Due Date"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.invoice?.due_date || "",
      onChange: (e) => handleFieldChange("invoice.due_date", e.target.value)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Place of Supply / Terms"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.invoice?.place_of_supply || formData.invoice?.payment_terms || "",
      onChange: (e) => handleFieldChange("invoice.place_of_supply", e.target.value)
    }
  ))) : /* @__PURE__ */ React3.createElement("div", { className: "field-grid-2" }, /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Invoice Number"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontWeight: 700 } }, activeData.invoice?.number || doc?.invoice_number || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "Not detected"))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Invoice Date"), /* @__PURE__ */ React3.createElement("span", { className: "field-value" }, activeData.invoice?.date || (doc?.invoice_date ? formatDate(doc.invoice_date) : /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "Not detected")))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Due Date"), /* @__PURE__ */ React3.createElement("span", { className: "field-value" }, activeData.invoice?.due_date || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "\u2014"))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Place of Supply / Terms"), /* @__PURE__ */ React3.createElement("span", { className: "field-value" }, activeData.invoice?.place_of_supply || activeData.invoice?.payment_terms || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "\u2014"))))), /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-card" }, /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-header" }, /* @__PURE__ */ React3.createElement("h3", { className: "extracted-section-title" }, "\u{1F464} Customer / Buyer Details")), isEditing ? /* @__PURE__ */ React3.createElement("div", { className: "field-grid-2" }, /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Customer Name"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.buyer?.name || "",
      onChange: (e) => handleFieldChange("buyer.name", e.target.value)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Customer GSTIN"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.buyer?.gstin || "",
      onChange: (e) => handleFieldChange("buyer.gstin", e.target.value)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell", style: { gridColumn: "span 2" } }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Billing Address"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "text",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.buyer?.address || "",
      onChange: (e) => handleFieldChange("buyer.address", e.target.value)
    }
  ))) : /* @__PURE__ */ React3.createElement("div", { className: "field-grid-2" }, /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Customer Name"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontWeight: 600 } }, activeData.buyer?.name || doc?.buyer_name || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "Not detected"))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Customer GSTIN"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontFamily: "monospace" } }, activeData.buyer?.gstin || doc?.buyer_gstin || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "Not detected"))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell", style: { gridColumn: "span 2" } }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Billing Address"), /* @__PURE__ */ React3.createElement("span", { className: "field-value" }, activeData.buyer?.address || /* @__PURE__ */ React3.createElement("span", { className: "field-value-empty" }, "\u2014"))))), /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-card" }, /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-header" }, /* @__PURE__ */ React3.createElement("h3", { className: "extracted-section-title" }, "\u{1F4E6} Line Items (", Array.isArray(activeData.items) ? activeData.items.length : 0, ")"), isEditing && /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-sm btn-secondary",
      onClick: handleAddLineItem,
      style: { fontSize: "0.75rem", padding: "0.2rem 0.5rem", fontWeight: 600 }
    },
    "+ Add Line Item"
  )), /* @__PURE__ */ React3.createElement("div", { style: { overflowX: "auto" } }, /* @__PURE__ */ React3.createElement("table", { className: "doc-table-compact" }, /* @__PURE__ */ React3.createElement("thead", null, /* @__PURE__ */ React3.createElement("tr", null, /* @__PURE__ */ React3.createElement("th", { style: { width: "28px" } }, "#"), /* @__PURE__ */ React3.createElement("th", { style: { minWidth: "150px" } }, "Description"), /* @__PURE__ */ React3.createElement("th", { style: { width: "70px" } }, "HSN"), /* @__PURE__ */ React3.createElement("th", { style: { width: "60px" } }, "Qty"), /* @__PURE__ */ React3.createElement("th", { style: { width: "60px" } }, "Unit"), /* @__PURE__ */ React3.createElement("th", { style: { width: "85px", textAlign: "right" } }, "Rate (\u20B9)"), /* @__PURE__ */ React3.createElement("th", { style: { width: "55px", textAlign: "right" } }, "Disc %"), /* @__PURE__ */ React3.createElement("th", { style: { width: "55px", textAlign: "right" } }, "GST %"), /* @__PURE__ */ React3.createElement("th", { style: { width: "95px", textAlign: "right" } }, "Amount (\u20B9)"), isEditing && /* @__PURE__ */ React3.createElement("th", { style: { width: "32px", textAlign: "center" } }))), /* @__PURE__ */ React3.createElement("tbody", null, Array.isArray(activeData.items) && activeData.items.length > 0 ? activeData.items.map((item, idx) => {
    const flag = getFieldFlag(`items[${idx}].amount`);
    return /* @__PURE__ */ React3.createElement("tr", { key: idx, style: { backgroundColor: flag ? "#fef2f2" : "transparent" } }, /* @__PURE__ */ React3.createElement("td", { style: { color: "#94a3b8", fontSize: "0.75rem" } }, idx + 1), /* @__PURE__ */ React3.createElement("td", null, isEditing ? /* @__PURE__ */ React3.createElement(
      "input",
      {
        type: "text",
        className: "form-control",
        style: { fontSize: "0.78rem", padding: "0.2rem 0.4rem" },
        value: item.description || "",
        onChange: (e) => handleLineItemChange(idx, "description", e.target.value)
      }
    ) : /* @__PURE__ */ React3.createElement("span", { style: { fontWeight: 600 } }, item.description || "\u2014")), /* @__PURE__ */ React3.createElement("td", null, isEditing ? /* @__PURE__ */ React3.createElement(
      "input",
      {
        type: "text",
        className: "form-control",
        style: { fontSize: "0.78rem", padding: "0.2rem 0.4rem" },
        value: item.hsn ?? item.hsn_sac ?? "",
        onChange: (e) => handleLineItemChange(idx, "hsn", e.target.value)
      }
    ) : /* @__PURE__ */ React3.createElement("span", { style: { fontFamily: "monospace", fontSize: "0.78rem" } }, item.hsn || item.hsn_sac || "\u2014")), /* @__PURE__ */ React3.createElement("td", null, isEditing ? /* @__PURE__ */ React3.createElement(
      "input",
      {
        type: "text",
        className: "form-control",
        style: { fontSize: "0.78rem", padding: "0.2rem 0.4rem" },
        value: item.qty ?? "",
        onChange: (e) => handleLineItemChange(idx, "qty", e.target.value)
      }
    ) : /* @__PURE__ */ React3.createElement("span", null, item.qty || "\u2014")), /* @__PURE__ */ React3.createElement("td", null, isEditing ? /* @__PURE__ */ React3.createElement(
      "input",
      {
        type: "text",
        className: "form-control",
        style: { fontSize: "0.78rem", padding: "0.2rem 0.4rem" },
        value: item.unit ?? item.batch ?? "",
        onChange: (e) => handleLineItemChange(idx, "unit", e.target.value)
      }
    ) : /* @__PURE__ */ React3.createElement("span", { style: { color: "var(--text-muted)" } }, item.unit || item.batch || "\u2014")), /* @__PURE__ */ React3.createElement("td", { style: { textAlign: "right" } }, isEditing ? /* @__PURE__ */ React3.createElement(
      "input",
      {
        type: "number",
        step: "any",
        className: "form-control",
        style: { fontSize: "0.78rem", padding: "0.2rem 0.4rem", textAlign: "right" },
        value: item.rate ?? "",
        onChange: (e) => handleLineItemChange(idx, "rate", parseFloat(e.target.value) || 0)
      }
    ) : /* @__PURE__ */ React3.createElement("span", { style: { fontVariantNumeric: "tabular-nums" } }, formatCurrency(item.rate))), /* @__PURE__ */ React3.createElement("td", { style: { textAlign: "right" } }, isEditing ? /* @__PURE__ */ React3.createElement(
      "input",
      {
        type: "number",
        step: "any",
        className: "form-control",
        style: { fontSize: "0.78rem", padding: "0.2rem 0.4rem", textAlign: "right" },
        value: item.discount ?? item.discount_percent ?? "",
        onChange: (e) => handleLineItemChange(idx, "discount", parseFloat(e.target.value) || 0)
      }
    ) : /* @__PURE__ */ React3.createElement("span", null, item.discount !== null && item.discount !== void 0 ? `${item.discount}%` : "\u2014")), /* @__PURE__ */ React3.createElement("td", { style: { textAlign: "right" } }, isEditing ? /* @__PURE__ */ React3.createElement(
      "input",
      {
        type: "number",
        step: "any",
        className: "form-control",
        style: { fontSize: "0.78rem", padding: "0.2rem 0.4rem", textAlign: "right" },
        value: item.gst_rate ?? item.tax_rate ?? "",
        onChange: (e) => handleLineItemChange(idx, "gst_rate", parseFloat(e.target.value) || 0)
      }
    ) : /* @__PURE__ */ React3.createElement("span", { style: { fontSize: "0.75rem", backgroundColor: "#f1f5f9", padding: "0.1rem 0.35rem", borderRadius: "4px" } }, item.gst_rate !== null && item.gst_rate !== void 0 ? `${item.gst_rate}%` : "\u2014")), /* @__PURE__ */ React3.createElement("td", { style: { textAlign: "right" } }, isEditing ? /* @__PURE__ */ React3.createElement(
      "input",
      {
        type: "number",
        step: "any",
        className: "form-control",
        style: {
          fontSize: "0.78rem",
          padding: "0.2rem 0.4rem",
          textAlign: "right",
          fontWeight: 600,
          borderColor: flag ? "#ef4444" : void 0,
          backgroundColor: flag ? "#fef2f2" : void 0
        },
        value: item.amount ?? "",
        onChange: (e) => handleLineItemChange(idx, "amount", parseFloat(e.target.value) || 0)
      }
    ) : /* @__PURE__ */ React3.createElement("span", { style: { fontWeight: 700, fontVariantNumeric: "tabular-nums", color: flag ? "#dc2626" : void 0 } }, formatCurrency(item.amount))), isEditing && /* @__PURE__ */ React3.createElement("td", { style: { textAlign: "center" } }, /* @__PURE__ */ React3.createElement(
      "button",
      {
        type: "button",
        onClick: () => handleDeleteLineItem(idx),
        style: { border: "none", background: "none", cursor: "pointer", color: "#ef4444", fontSize: "0.85rem" },
        title: "Remove line item"
      },
      "\u2715"
    )));
  }) : /* @__PURE__ */ React3.createElement("tr", null, /* @__PURE__ */ React3.createElement("td", { colSpan: isEditing ? 10 : 9, style: { textAlign: "center", padding: "1.25rem", color: "#94a3b8" } }, "No individual line items parsed.")))))), /* @__PURE__ */ React3.createElement("div", { className: "totals-summary-box" }, /* @__PURE__ */ React3.createElement("h4", { style: { fontSize: "0.85rem", fontWeight: 700, margin: "0 0 0.75rem 0", color: "#1e293b" } }, "\u{1F4B0} Invoice Summary & Taxes"), isEditing ? /* @__PURE__ */ React3.createElement("div", { className: "field-grid-3", style: { marginBottom: "0.75rem" } }, /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Taxable Subtotal"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "number",
      step: "any",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.totals?.taxable_value ?? "",
      onChange: (e) => handleFieldChange("totals.taxable_value", parseFloat(e.target.value) || 0)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "CGST"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "number",
      step: "any",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.totals?.cgst ?? "",
      onChange: (e) => handleFieldChange("totals.cgst", parseFloat(e.target.value) || 0)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "SGST"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "number",
      step: "any",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.totals?.sgst ?? "",
      onChange: (e) => handleFieldChange("totals.sgst", parseFloat(e.target.value) || 0)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "IGST"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "number",
      step: "any",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.totals?.igst ?? "",
      onChange: (e) => handleFieldChange("totals.igst", parseFloat(e.target.value) || 0)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Round Off"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "number",
      step: "any",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem" },
      value: formData.totals?.round_off ?? "",
      onChange: (e) => handleFieldChange("totals.round_off", parseFloat(e.target.value) || 0)
    }
  )), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Grand Total (\u20B9)"), /* @__PURE__ */ React3.createElement(
    "input",
    {
      type: "number",
      step: "any",
      className: "form-control",
      style: { fontSize: "0.8125rem", padding: "0.35rem 0.5rem", fontWeight: 700 },
      value: formData.totals?.grand_total ?? "",
      onChange: (e) => handleFieldChange("totals.grand_total", parseFloat(e.target.value) || 0)
    }
  ))) : /* @__PURE__ */ React3.createElement("div", { className: "field-grid-3", style: { marginBottom: "0.75rem" } }, /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Taxable Subtotal"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontVariantNumeric: "tabular-nums" } }, formatCurrency(activeData.totals?.taxable_value))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "CGST"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontVariantNumeric: "tabular-nums" } }, formatCurrency(activeData.totals?.cgst))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "SGST"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontVariantNumeric: "tabular-nums" } }, formatCurrency(activeData.totals?.sgst))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "IGST"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontVariantNumeric: "tabular-nums" } }, formatCurrency(activeData.totals?.igst))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Round Off"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontVariantNumeric: "tabular-nums" } }, formatCurrency(activeData.totals?.round_off))), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Total Quantity"), /* @__PURE__ */ React3.createElement("span", { className: "field-value" }, activeData.totals?.total_qty || "\u2014"))), /* @__PURE__ */ React3.createElement("div", { className: "totals-grand-row" }, /* @__PURE__ */ React3.createElement("div", null, /* @__PURE__ */ React3.createElement("span", { className: "totals-grand-label" }, "Total Amount Payable"), activeData.totals?.amount_in_words && /* @__PURE__ */ React3.createElement("div", { style: { fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "2px", fontStyle: "italic" } }, activeData.totals.amount_in_words)), /* @__PURE__ */ React3.createElement("div", { className: "totals-grand-value" }, formatCurrency(activeData.totals?.grand_total || doc?.grand_total)))), (activeData.bank || activeData.bank_details) && /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-card" }, /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-header" }, /* @__PURE__ */ React3.createElement("h3", { className: "extracted-section-title" }, "\u{1F3E6} Bank & Payment Details")), /* @__PURE__ */ React3.createElement("div", { className: "field-grid-2" }, /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Bank Name"), /* @__PURE__ */ React3.createElement("span", { className: "field-value" }, (activeData.bank || activeData.bank_details)?.bank_name || "\u2014")), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Account Number"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontFamily: "monospace" } }, (activeData.bank || activeData.bank_details)?.account_no || "\u2014")), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "IFSC Code"), /* @__PURE__ */ React3.createElement("span", { className: "field-value", style: { fontFamily: "monospace" } }, (activeData.bank || activeData.bank_details)?.ifsc || "\u2014")), /* @__PURE__ */ React3.createElement("div", { className: "field-cell" }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Branch"), /* @__PURE__ */ React3.createElement("span", { className: "field-value" }, (activeData.bank || activeData.bank_details)?.branch || "\u2014")))), (activeData.declaration || activeData.warranty_note) && /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-card" }, /* @__PURE__ */ React3.createElement("div", { className: "extracted-section-header" }, /* @__PURE__ */ React3.createElement("h3", { className: "extracted-section-title" }, "\u{1F4DD} Declarations & Warranty Terms")), activeData.declaration && /* @__PURE__ */ React3.createElement("div", { style: { marginBottom: "0.5rem" } }, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Declaration"), /* @__PURE__ */ React3.createElement("p", { style: { margin: "0.2rem 0 0", fontSize: "0.78rem", color: "#475569", lineHeight: 1.45 } }, activeData.declaration)), activeData.warranty_note && /* @__PURE__ */ React3.createElement("div", null, /* @__PURE__ */ React3.createElement("span", { className: "field-label" }, "Warranty Note"), /* @__PURE__ */ React3.createElement("p", { style: { margin: "0.2rem 0 0", fontSize: "0.78rem", color: "#475569", lineHeight: 1.45 } }, activeData.warranty_note))), /* @__PURE__ */ React3.createElement("div", { className: "accordion-card" }, /* @__PURE__ */ React3.createElement(
    "div",
    {
      className: `accordion-header ${showDetails ? "open" : ""}`,
      onClick: () => setShowDetails(!showDetails)
    },
    /* @__PURE__ */ React3.createElement("span", { className: "accordion-title" }, "\u2139\uFE0F Technical Document Details & Checksums"),
    /* @__PURE__ */ React3.createElement("span", { style: { fontSize: "0.8rem", color: "#64748b" } }, showDetails ? "\u25B2 Hide" : "\u25BC View Technical Details")
  ), showDetails && /* @__PURE__ */ React3.createElement("div", { className: "accordion-body" }, /* @__PURE__ */ React3.createElement("dl", { className: "info-list", style: { display: "grid", gridTemplateColumns: "120px 1fr", gap: "0.5rem 1rem", margin: 0 } }, /* @__PURE__ */ React3.createElement("dt", { style: { fontWeight: 600, color: "var(--text-muted)", fontSize: "0.75rem" } }, "Original Filename"), /* @__PURE__ */ React3.createElement("dd", { style: { margin: 0, fontSize: "0.8125rem", wordBreak: "break-all" } }, doc.original_filename), /* @__PURE__ */ React3.createElement("dt", { style: { fontWeight: 600, color: "var(--text-muted)", fontSize: "0.75rem" } }, "Uploaded By"), /* @__PURE__ */ React3.createElement("dd", { style: { margin: 0, fontSize: "0.8125rem" } }, doc.uploader_name || `User #${doc.uploaded_by}`), /* @__PURE__ */ React3.createElement("dt", { style: { fontWeight: 600, color: "var(--text-muted)", fontSize: "0.75rem" } }, "Upload Timestamp"), /* @__PURE__ */ React3.createElement("dd", { style: { margin: 0, fontSize: "0.8125rem" } }, formatDate(doc.created_at)), /* @__PURE__ */ React3.createElement("dt", { style: { fontWeight: 600, color: "var(--text-muted)", fontSize: "0.75rem" } }, "MIME Content Type"), /* @__PURE__ */ React3.createElement("dd", { style: { margin: 0, fontSize: "0.8125rem" } }, doc.mime_type), /* @__PURE__ */ React3.createElement("dt", { style: { fontWeight: 600, color: "var(--text-muted)", fontSize: "0.75rem" } }, "File Size"), /* @__PURE__ */ React3.createElement("dd", { style: { margin: 0, fontSize: "0.8125rem" } }, formatBytes(doc.file_size)), doc.page_count !== void 0 && doc.page_count !== null && /* @__PURE__ */ React3.createElement(React3.Fragment, null, /* @__PURE__ */ React3.createElement("dt", { style: { fontWeight: 600, color: "var(--text-muted)", fontSize: "0.75rem" } }, "Page Count"), /* @__PURE__ */ React3.createElement("dd", { style: { margin: 0, fontSize: "0.8125rem" } }, doc.page_count)), doc.sha256 && /* @__PURE__ */ React3.createElement(React3.Fragment, null, /* @__PURE__ */ React3.createElement("dt", { style: { fontWeight: 600, color: "var(--text-muted)", fontSize: "0.75rem" } }, "SHA-256 Hash"), /* @__PURE__ */ React3.createElement("dd", { style: { margin: 0, fontSize: "0.8125rem", display: "flex", alignItems: "center", gap: "0.4rem" } }, /* @__PURE__ */ React3.createElement("span", { style: { fontFamily: "monospace", fontSize: "0.75rem", wordBreak: "break-all" } }, doc.sha256), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-ghost",
      style: { padding: "0.1rem 0.35rem", fontSize: "0.72rem" },
      onClick: () => {
        navigator.clipboard.writeText(doc.sha256);
        setCopiedHash(true);
        setTimeout(() => setCopiedHash(false), 2e3);
      },
      title: "Copy SHA-256 Checksum"
    },
    copiedHash ? "\u2713 Copied" : "\u{1F4CB} Copy"
  ))), doc.error_code && /* @__PURE__ */ React3.createElement(React3.Fragment, null, /* @__PURE__ */ React3.createElement("dt", { style: { fontWeight: 600, color: "var(--text-muted)", fontSize: "0.75rem" } }, "Error Code"), /* @__PURE__ */ React3.createElement("dd", { style: { margin: 0, color: "#ef4444", fontWeight: 600, fontSize: "0.8125rem" } }, doc.error_code))))), /* @__PURE__ */ React3.createElement("div", { className: "accordion-card" }, /* @__PURE__ */ React3.createElement(
    "div",
    {
      className: `accordion-header ${showRawData ? "open" : ""}`,
      onClick: () => setShowRawData(!showRawData)
    },
    /* @__PURE__ */ React3.createElement("span", { className: "accordion-title" }, "{ }", " Advanced: Raw OCR Data & Field Audit Trail"),
    /* @__PURE__ */ React3.createElement("span", { style: { fontSize: "0.8rem", color: "#64748b" } }, showRawData ? "\u25B2 Hide" : "\u25BC View Raw Data & History")
  ), showRawData && /* @__PURE__ */ React3.createElement("div", { className: "accordion-body" }, /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", gap: "0.5rem", marginBottom: "0.75rem", borderBottom: "1px solid #e2e8f0", paddingBottom: "0.5rem" } }, /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      onClick: () => setRawTab("json"),
      style: {
        border: "none",
        background: rawTab === "json" ? "#e2e8f0" : "transparent",
        padding: "0.25rem 0.6rem",
        borderRadius: "4px",
        fontSize: "0.78rem",
        fontWeight: 600,
        cursor: "pointer",
        color: rawTab === "json" ? "#0f172a" : "#64748b"
      }
    },
    "Structured JSON"
  ), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      onClick: () => setRawTab("text"),
      style: {
        border: "none",
        background: rawTab === "text" ? "#e2e8f0" : "transparent",
        padding: "0.25rem 0.6rem",
        borderRadius: "4px",
        fontSize: "0.78rem",
        fontWeight: 600,
        cursor: "pointer",
        color: rawTab === "text" ? "#0f172a" : "#64748b"
      }
    },
    "Raw OCR Text (",
    doc.ocr_text ? doc.ocr_text.split(/\s+/).filter(Boolean).length : 0,
    " words)"
  ), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      onClick: () => setRawTab("history"),
      style: {
        border: "none",
        background: rawTab === "history" ? "#e2e8f0" : "transparent",
        padding: "0.25rem 0.6rem",
        borderRadius: "4px",
        fontSize: "0.78rem",
        fontWeight: 600,
        cursor: "pointer",
        color: rawTab === "history" ? "#0f172a" : "#64748b"
      }
    },
    "Edit Audit History (",
    extraction?.edits_count || editsHistory.length,
    ")"
  )), rawTab === "json" && /* @__PURE__ */ React3.createElement("div", null, /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", justifyContent: "flex-end", marginBottom: "0.4rem" } }, /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-sm btn-secondary",
      onClick: () => {
        navigator.clipboard.writeText(JSON.stringify(extraction?.data || activeData, null, 2));
        setCopiedJson(true);
        setTimeout(() => setCopiedJson(false), 2e3);
      },
      style: { fontSize: "0.72rem", padding: "0.15rem 0.45rem" }
    },
    copiedJson ? "\u2713 Copied" : "\u{1F4CB} Copy JSON"
  )), /* @__PURE__ */ React3.createElement(
    "pre",
    {
      style: {
        margin: 0,
        maxHeight: "360px",
        overflow: "auto",
        padding: "0.75rem",
        backgroundColor: "#0f172a",
        color: "#f8fafc",
        borderRadius: "6px",
        fontSize: "0.75rem",
        fontFamily: "monospace",
        lineHeight: 1.45
      }
    },
    JSON.stringify(extraction?.data || activeData, null, 2)
  )), rawTab === "text" && /* @__PURE__ */ React3.createElement("div", null, /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", justifyContent: "flex-end", marginBottom: "0.4rem" } }, /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-sm btn-secondary",
      onClick: () => {
        navigator.clipboard.writeText(doc.ocr_text || "");
        setCopiedText(true);
        setTimeout(() => setCopiedText(false), 2e3);
      },
      style: { fontSize: "0.72rem", padding: "0.15rem 0.45rem" }
    },
    copiedText ? "\u2713 Copied" : "\u{1F4CB} Copy Text"
  )), /* @__PURE__ */ React3.createElement(
    "pre",
    {
      style: {
        margin: 0,
        maxHeight: "360px",
        overflow: "auto",
        padding: "0.75rem",
        backgroundColor: "#f8fafc",
        color: "#334155",
        border: "1px solid #e2e8f0",
        borderRadius: "6px",
        fontSize: "0.75rem",
        fontFamily: "monospace",
        lineHeight: 1.45,
        whiteSpace: "pre-wrap"
      }
    },
    doc.ocr_text || "No raw OCR text available."
  )), rawTab === "history" && /* @__PURE__ */ React3.createElement("div", null, loadingHistory ? /* @__PURE__ */ React3.createElement("div", { style: { fontSize: "0.8rem", color: "#64748b" } }, "Loading field edit history\u2026") : editsHistory.length === 0 ? /* @__PURE__ */ React3.createElement("div", { style: { fontSize: "0.8rem", color: "#94a3b8", fontStyle: "italic", padding: "1rem", textAlign: "center" } }, "No human review adjustments recorded yet.") : /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", flexDirection: "column", gap: "0.5rem" } }, editsHistory.map((edit) => /* @__PURE__ */ React3.createElement("div", { key: edit.id, style: { padding: "0.5rem 0.75rem", border: "1px solid #e2e8f0", borderRadius: "4px", background: "#f8fafc", fontSize: "0.78rem" } }, /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", justifyContent: "space-between", marginBottom: "0.2rem" } }, /* @__PURE__ */ React3.createElement("span", { style: { fontWeight: 700, color: "#0f172a" } }, edit.field_path), /* @__PURE__ */ React3.createElement("span", { style: { color: "#64748b" } }, formatDate(edit.edited_at))), /* @__PURE__ */ React3.createElement("div", { style: { color: "#64748b", fontSize: "0.72rem", marginBottom: "0.2rem" } }, "By: ", /* @__PURE__ */ React3.createElement("strong", null, edit.editor_name || `User #${edit.edited_by}`)), /* @__PURE__ */ React3.createElement("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", fontSize: "0.72rem" } }, /* @__PURE__ */ React3.createElement("div", { style: { backgroundColor: "#fee2e2", padding: "0.25rem", borderRadius: "4px", color: "#991b1b" } }, /* @__PURE__ */ React3.createElement("strong", null, "Old:"), " ", JSON.stringify(edit.old_value)), /* @__PURE__ */ React3.createElement("div", { style: { backgroundColor: "#dcfce7", padding: "0.25rem", borderRadius: "4px", color: "#166534" } }, /* @__PURE__ */ React3.createElement("strong", null, "New:"), " ", JSON.stringify(edit.new_value))))))))))), isFullScreen && /* @__PURE__ */ React3.createElement("div", { className: "fullscreen-overlay" }, /* @__PURE__ */ React3.createElement("div", { className: "fullscreen-header" }, /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", alignItems: "center", gap: "0.75rem" } }, /* @__PURE__ */ React3.createElement("span", { style: { fontWeight: 700, fontSize: "0.95rem" } }, displayTitle, " \u2014 Original Document View"), /* @__PURE__ */ React3.createElement("span", { style: { fontSize: "0.75rem", opacity: 0.8 } }, Math.round(zoom * 100), "% ", rotation > 0 ? `\u2022 Rotated ${rotation}\xB0` : "")), /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", alignItems: "center", gap: "0.5rem" } }, /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-sm btn-secondary",
      onClick: handleZoomOut,
      disabled: zoom <= 0.5,
      style: { color: "#ffffff", borderColor: "rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.1)" }
    },
    "\u2212"
  ), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-sm btn-secondary",
      onClick: handleZoomIn,
      disabled: zoom >= 3.5,
      style: { color: "#ffffff", borderColor: "rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.1)" }
    },
    "+"
  ), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-sm btn-secondary",
      onClick: handleRotate,
      style: { color: "#ffffff", borderColor: "rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.1)" }
    },
    "\u21BB Rotate"
  ), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-sm btn-secondary",
      onClick: handleZoomReset,
      style: { color: "#ffffff", borderColor: "rgba(255,255,255,0.2)", background: "rgba(255,255,255,0.1)" }
    },
    "Reset"
  ), /* @__PURE__ */ React3.createElement(
    "button",
    {
      type: "button",
      className: "btn btn-sm btn-primary",
      onClick: () => setIsFullScreen(false),
      style: { marginLeft: "0.5rem" }
    },
    "\u2715 Close"
  ))), /* @__PURE__ */ React3.createElement(
    "div",
    {
      ref: fullScreenImageRef,
      onMouseDown: (e) => handleMouseDown(e, fullScreenImageRef),
      onMouseMove: (e) => handleMouseMove(e, fullScreenImageRef),
      onMouseUp: handleMouseUp,
      onMouseLeave: handleMouseUp,
      className: "fullscreen-body",
      style: {
        cursor: zoom > 1 ? isDragging ? "grabbing" : "grab" : "default",
        userSelect: isDragging ? "none" : "auto"
      }
    },
    isPdf ? /* @__PURE__ */ React3.createElement(
      "iframe",
      {
        src: `${fileUrl}#toolbar=0`,
        title: doc.original_filename,
        style: { width: "90%", height: "90%", border: "none", backgroundColor: "#ffffff", borderRadius: "8px" }
      }
    ) : /* @__PURE__ */ React3.createElement(
      "div",
      {
        style: {
          transform: `scale(${zoom}) rotate(${rotation}deg)`,
          transformOrigin: "center center",
          transition: isDragging ? "none" : "transform 0.12s ease-out"
        }
      },
      /* @__PURE__ */ React3.createElement(
        "img",
        {
          src: fileUrl,
          alt: doc.original_filename,
          draggable: false,
          style: {
            maxHeight: "85vh",
            maxWidth: "85vw",
            objectFit: "contain",
            borderRadius: "8px",
            boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)"
          }
        }
      )
    )
  )), showOverrideModal && /* @__PURE__ */ React3.createElement(
    "div",
    {
      style: {
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(15, 23, 42, 0.6)",
        backdropFilter: "blur(2px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1e4,
        padding: "1rem"
      }
    },
    /* @__PURE__ */ React3.createElement(
      "div",
      {
        style: {
          backgroundColor: "#ffffff",
          borderRadius: "12px",
          maxWidth: "520px",
          width: "100%",
          padding: "1.5rem",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)"
        }
      },
      /* @__PURE__ */ React3.createElement("h3", { style: { fontSize: "1.1rem", fontWeight: 700, margin: "0 0 0.5rem 0", color: "#b91c1c" } }, "\u26A0\uFE0F Override Validation Errors & Approve"),
      /* @__PURE__ */ React3.createElement("p", { style: { fontSize: "0.84rem", color: "#64748b", margin: "0 0 1rem 0", lineHeight: 1.45 } }, "This document contains active validation errors (e.g. calculation mismatch). To approve and finalize extraction anyway, please provide an authoritative audit justification."),
      /* @__PURE__ */ React3.createElement(
        "textarea",
        {
          rows: 3,
          required: true,
          placeholder: "e.g. Vendor arithmetic confirmed against signed physical purchase order...",
          value: overrideReason,
          onChange: (e) => setOverrideReason(e.target.value),
          className: "form-control",
          style: {
            width: "100%",
            padding: "0.5rem",
            fontSize: "0.84rem",
            marginBottom: "1rem"
          }
        }
      ),
      /* @__PURE__ */ React3.createElement("div", { style: { display: "flex", justifyContent: "flex-end", gap: "0.75rem" } }, /* @__PURE__ */ React3.createElement(
        "button",
        {
          type: "button",
          className: "btn btn-secondary",
          onClick: () => setShowOverrideModal(false)
        },
        "Cancel"
      ), /* @__PURE__ */ React3.createElement(
        "button",
        {
          type: "button",
          className: "btn btn-primary",
          disabled: overrideReason.trim().length < 5 || approving,
          onClick: () => handleApprove(true),
          style: { backgroundColor: "#dc2626", borderColor: "#dc2626" }
        },
        approving ? "Overriding\u2026" : "Confirm Override & Approve"
      ))
    )
  ), /* @__PURE__ */ React3.createElement(
    ConfirmModal,
    {
      isOpen: showDeleteConfirm,
      title: "Delete Document",
      message: `Are you sure you want to delete "${doc?.original_filename || "this document"}"?`,
      details: /* @__PURE__ */ React3.createElement("span", { style: { color: "#dc2626" } }, "This document will be soft-deleted and moved to trash."),
      confirmText: "Delete Document",
      variant: "danger",
      loading: deleting,
      onConfirm: confirmDelete,
      onCancel: () => setShowDeleteConfirm(false)
    }
  ));
}

// test_document_review.jsx
function TestAuthProvider({ user, children }) {
  const hasPermission = (permission) => {
    if (!user) return false;
    if (user.role === "GLOBAL_ADMIN") return true;
    if (user.role === "ADMIN" && !permission.startsWith("company:")) return true;
    if (Array.isArray(user.permissions) && user.permissions.includes(permission)) return true;
    return false;
  };
  return /* @__PURE__ */ React4.createElement(AuthContext.Provider, { value: { user, loading: false, hasPermission, logout: () => {
  } } }, children);
}
console.log("\u{1F9EA} =========================================================================");
console.log("\u{1F9EA} RUNNING DOCUMENT DETAILS REDESIGN & REVIEW WORKSPACE TEST SUITE");
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
runTest("DocumentViewPage loads initial state without SSR errors", () => {
  const html = renderToString(
    /* @__PURE__ */ React4.createElement(TestAuthProvider, { user: mockCompanyAdmin }, /* @__PURE__ */ React4.createElement(MemoryRouter, { initialEntries: ["/documents/492"] }, /* @__PURE__ */ React4.createElement(Routes, null, /* @__PURE__ */ React4.createElement(Route, { path: "/documents/:id", element: /* @__PURE__ */ React4.createElement(DocumentViewPage, null) }))))
  );
  assert(
    html.includes("Loading document review workspace") || html.includes("page-content"),
    "Expected document view page or loading indicator to render"
  );
});
runTest("index.css contains required Document Review Workspace styles", async () => {
  const fs = await import("fs");
  const css = fs.readFileSync("./src/index.css", "utf8");
  assert(css.includes(".doc-review-layout"), "Missing .doc-review-layout in index.css");
  assert(css.includes(".doc-review-panel"), "Missing .doc-review-panel in index.css");
  assert(css.includes(".doc-preview-toolbar"), "Missing .doc-preview-toolbar in index.css");
  assert(css.includes(".doc-extracted-container"), "Missing .doc-extracted-container in index.css");
  assert(css.includes(".extracted-section-card"), "Missing .extracted-section-card in index.css");
  assert(css.includes(".doc-table-compact"), "Missing .doc-table-compact in index.css");
  assert(css.includes(".totals-summary-box"), "Missing .totals-summary-box in index.css");
  assert(css.includes(".totals-grand-value"), "Missing .totals-grand-value in index.css");
  assert(css.includes(".fullscreen-overlay"), "Missing .fullscreen-overlay in index.css");
});
runTest("DocumentViewPage source code implements all mandatory workspace sections", async () => {
  const fs = await import("fs");
  const code = fs.readFileSync("./src/pages/DocumentViewPage.jsx", "utf8");
  assert(code.includes("displayTitle"), "Header must calculate human-readable title");
  assert(code.includes("handleReprocess"), "Header must include OCR reprocess action");
  assert(code.includes("handleApprove"), "Header must include verification / approve action");
  assert(code.includes("handleDelete"), "Header must include delete action");
  assert(code.includes("Original Document"), "Preview must have Original Document tab");
  assert(code.includes("Standardised Copy") || code.includes("Standardised Invoice"), "Preview must support Standardised Copy");
  assert(code.includes("handleZoomIn"), "Preview must support zoom in");
  assert(code.includes("handleZoomOut"), "Preview must support zoom out");
  assert(code.includes("handleZoomReset"), "Preview must support zoom reset / fit");
  assert(code.includes("handleRotate"), "Preview must support image rotation");
  assert(code.includes("isFullScreen"), "Preview must support fullscreen viewing");
  assert(code.includes("handleMouseDown") && code.includes("handleMouseMove"), "Preview must support interactive pan & drag");
  assert(code.includes("pdf-iframe"), "Preview must support PDF documents");
  assert(code.includes("download="), "Preview must support download");
  assert(code.includes("Supplier Details"), "Extracted panel must include Supplier Details");
  assert(code.includes("Invoice Details"), "Extracted panel must include Invoice Details");
  assert(code.includes("Customer / Buyer Details"), "Extracted panel must include Customer Details");
  assert(code.includes("Line Items"), "Extracted panel must include Line Items table");
  assert(code.includes("Invoice Summary"), "Extracted panel must include Invoice Summary");
  assert(code.includes("Bank & Payment Details"), "Extracted panel must support Bank Details");
  assert(code.includes("Declarations"), "Extracted panel must support Declarations");
  assert(code.includes("validation_flags"), "Extracted panel must inspect validation flags");
  assert(code.includes("hasErrors"), "Extracted panel must handle error-level flags");
  assert(code.includes("showOverrideModal"), "Must support Override & Approve modal for validation errors");
  assert(code.includes("showDetails"), "Must provide collapsible Technical Document Details");
  assert(code.includes("SHA-256"), "Must display SHA-256 in technical section");
  assert(code.includes("showRawData"), "Must provide collapsible Raw Data & Audit section");
  assert(code.includes("Raw OCR Text"), "Must support viewing raw OCR text");
  assert(code.includes("Structured JSON"), "Must support viewing raw JSON");
  assert(code.includes("Edit Audit History"), "Must support viewing edit audit history");
});
runTest("Existing 15 Navigation & RBAC tests continue passing without regression", async () => {
  const { execSync } = await import("child_process");
  const output = execSync("node test_navigation.bundle.mjs", { cwd: "." }).toString();
  assert(output.includes("15 / 15 PASSED (100% Success Rate)"), "Navigation tests failed");
});
console.log(`
=========================================================================`);
console.log(`TEST EXECUTION SUMMARY: ${passedTests} / ${totalTests} Passed (${Math.round(passedTests / totalTests * 100)}%)`);
console.log(`=========================================================================
`);
