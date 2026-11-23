// DMS Frontend API Client (Module 3)
const API_BASE = '';

/**
 * Custom error class preserving HTTP status and backend Request ID.
 */
export class ApiError extends Error {
  constructor(message, status, requestId = null, raw = null, headers = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.requestId = requestId;
    this.raw = raw;
    this.headers = headers;
  }
}

// In-memory token storage (Module 3 requirement: do not persist exclusively in localStorage)
let inMemoryAccessToken = null;

export const setAuthToken = (token) => {
  inMemoryAccessToken = token;
  if (token) {
    localStorage.setItem('dms_token', token);
  } else {
    localStorage.removeItem('dms_token');
  }
};

export const getAuthToken = () => {
  if (inMemoryAccessToken) return inMemoryAccessToken;
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('dms_token') : null;
  if (stored) inMemoryAccessToken = stored;
  return inMemoryAccessToken;
};

function generateRequestId() {
  return `fe-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

function getHeaders(isFormData = false) {
  const token = getAuthToken();
  const headers = {
    'X-Request-ID': generateRequestId(),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (!isFormData) headers['Content-Type'] = 'application/json';
  return headers;
}

// ── Single-flight refresh token queue ────────────────────────────────────────
let isRefreshing = false;
let refreshSubscribers = [];

function subscribeTokenRefresh(callback) {
  refreshSubscribers.push(callback);
}

function onRefreshed(newAccessToken) {
  refreshSubscribers.forEach((cb) => cb(newAccessToken));
  refreshSubscribers = [];
}

function getLoginRedirectForCurrentPath() {
  if (typeof window === 'undefined') return '/login';
  const path = window.location.pathname;
  // Public onboarding, invitation, and password recovery pages must never redirect to login
  if (
    path.startsWith('/company/onboard') ||
    path.startsWith('/onboard') ||
    path.startsWith('/accept-invite') ||
    path.startsWith('/reset-password') ||
    path.startsWith('/forgot-password')
  ) {
    return null;
  }
  if (path.startsWith('/admin')) return '/admin/login';
  if (path.startsWith('/company')) return '/company/login';
  return '/login';
}

function sanitizeErrorMessage(detail, status) {
  if (!detail) {
    if (status === 400) return 'Invalid request. Please verify the submitted information.';
    if (status === 401) return 'Session expired or unauthorized. Please sign in again.';
    if (status === 403) return 'Permission denied: You do not have permission to perform this action.';
    if (status === 404) return 'The requested resource was not found.';
    if (status >= 500) return 'A server error occurred. Please try again later.';
    return 'An error occurred while processing your request.';
  }

  // Handle array of validation errors (e.g. FastAPI / Pydantic)
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
          const msg = item.msg || '';
          if (
            msg.includes('model_attributes_type') ||
            msg.includes('valid dictionary or object') ||
            msg.includes('JSON decode error')
          ) {
            return 'Invalid input format';
          }
          const field = Array.isArray(item.loc) && item.loc.length > 0 ? item.loc[item.loc.length - 1] : null;
          if (field && field !== 'body') {
            const cleanFieldName = String(field).replace(/_/g, ' ');
            return `${cleanFieldName}: ${msg}`;
          }
          return msg;
        }
        return '';
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join('. ');
    }
    return 'Invalid information provided. Please check the form fields.';
  }

  // Handle nested object
  if (typeof detail === 'object') {
    if (detail.message && typeof detail.message === 'string') {
      return sanitizeErrorMessage(detail.message, status);
    }
    if (detail.detail) {
      return sanitizeErrorMessage(detail.detail, status);
    }
    return sanitizeErrorMessage(null, status);
  }

  let str = String(detail).trim();

  // If string contains a JSON array or object, parse and re-sanitize
  if (str.startsWith('[') || str.startsWith('{')) {
    try {
      const parsed = JSON.parse(str);
      return sanitizeErrorMessage(parsed, status);
    } catch {
      // Not valid JSON, continue with string sanitization
    }
  }

  // Hide internal exceptions, stack traces, database and framework details
  if (
    str.includes('Traceback') ||
    str.includes('Internal Server Error') ||
    str.includes('psycopg2') ||
    str.includes('IntegrityError') ||
    str.includes('model_attributes_type') ||
    str.includes('syntax error') ||
    str.includes('FastAPI') ||
    str.includes('SQLAlchemy')
  ) {
    return 'A server error occurred. Please try again later.';
  }

  return str;
}

async function handleResponse(res, originalRequest = null) {
  const requestId = res.headers.get('X-Request-ID');

  if (!res.ok) {
    // 401 Handling: Attempt single-flight refresh before giving up
    const isAuthRoute =
      originalRequest?.url?.includes('/api/auth/login') ||
      originalRequest?.url?.includes('/api/auth/refresh');

    if (res.status === 401 && !isAuthRoute && originalRequest) {
      if (!isRefreshing) {
        isRefreshing = true;
        try {
          const refreshRes = await fetch(`${API_BASE}/api/auth/refresh`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Request-ID': generateRequestId(),
            },
            credentials: 'include',
          });

          if (refreshRes.ok) {
            const data = await refreshRes.json();
            setAuthToken(data.access_token);
            isRefreshing = false;
            onRefreshed(data.access_token);

            // Retry original request with new token
            const retryHeaders = {
              ...originalRequest.options.headers,
              Authorization: `Bearer ${data.access_token}`,
            };
            const retryRes = await fetch(originalRequest.url, {
              ...originalRequest.options,
              headers: retryHeaders,
            });
            return handleResponse(retryRes, null);
          } else {
            throw new Error('Refresh failed');
          }
        } catch {
          isRefreshing = false;
          refreshSubscribers = [];
          setAuthToken(null);
          localStorage.removeItem('dms_user');
          const redirectUrl = getLoginRedirectForCurrentPath();
          if (redirectUrl && typeof window !== 'undefined' && !window.location.pathname.includes('/login')) {
            window.location.href = redirectUrl;
          }
        }
      } else {
        // Queue parallel requests until refresh completes
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh(async (newToken) => {
            try {
              const retryHeaders = {
                ...originalRequest.options.headers,
                Authorization: `Bearer ${newToken}`,
              };
              const retryRes = await fetch(originalRequest.url, {
                ...originalRequest.options,
                headers: retryHeaders,
              });
              resolve(await handleResponse(retryRes, null));
            } catch (err) {
              reject(err);
            }
          });
        });
      }
    }

    let errorDetail = 'Request failed';
    let rawPayload = null;
    try {
      rawPayload = await res.json();
      if (rawPayload?.error?.detail) {
        errorDetail = sanitizeErrorMessage(rawPayload.error.detail, res.status);
      } else if (rawPayload?.detail) {
        errorDetail = sanitizeErrorMessage(rawPayload.detail, res.status);
      } else if (rawPayload?.message) {
        errorDetail = sanitizeErrorMessage(rawPayload.message, res.status);
      } else {
        errorDetail = sanitizeErrorMessage(null, res.status);
      }
    } catch {
      errorDetail = sanitizeErrorMessage(null, res.status);
    }

    throw new ApiError(errorDetail, res.status, requestId, rawPayload, res.headers);
  }

  return res.json();
}

async function wrappedFetch(url, options = {}) {
  const finalOptions = {
    ...options,
    credentials: 'include',
  };
  const res = await fetch(url, finalOptions);
  return handleResponse(res, { url, options: finalOptions });
}

export const api = {
  // ── Authentication ─────────────────────────────────────────────────────────
  login: async (email, password, portal = 'app') => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': generateRequestId(),
      },
      credentials: 'include',
      body: JSON.stringify({ email, password, portal }),
    });
    const data = await handleResponse(res);
    if (data.access_token) {
      setAuthToken(data.access_token);
    }
    return data;
  },

  refresh: async () => {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': generateRequestId(),
      },
      credentials: 'include',
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
        method: 'POST',
        headers: getHeaders(),
        credentials: 'include',
      });
    } finally {
      setAuthToken(null);
      localStorage.removeItem('dms_user');
    }
  },

  logoutAll: async () => {
    try {
      await fetch(`${API_BASE}/api/auth/logout-all`, {
        method: 'POST',
        headers: getHeaders(),
        credentials: 'include',
      });
    } finally {
      setAuthToken(null);
      localStorage.removeItem('dms_user');
    }
  },

  me: async () => {
    return wrappedFetch(`${API_BASE}/api/auth/me`, { headers: getHeaders() });
  },

  // ── User Invitations ───────────────────────────────────────────────────────
  inviteUser: async ({ email, branch_id, invited_role }) => {
    return wrappedFetch(`${API_BASE}/api/auth/invite`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ email, branch_id, invited_role }),
    });
  },

  acceptInvite: async ({ token, name, password }) => {
    const res = await fetch(`${API_BASE}/api/auth/invite/accept`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': generateRequestId(),
      },
      credentials: 'include',
      body: JSON.stringify({ token, name, password }),
    });
    return handleResponse(res);
  },

  // ── Password Reset & Change ────────────────────────────────────────────────
  requestPasswordReset: async ({ email, portal = 'app' }) => {
    const res = await fetch(`${API_BASE}/api/auth/password/reset-request`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': generateRequestId(),
      },
      credentials: 'include',
      body: JSON.stringify({ email, portal }),
    });
    return handleResponse(res);
  },

  resetPassword: async ({ token, new_password }) => {
    const res = await fetch(`${API_BASE}/api/auth/password/reset`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': generateRequestId(),
      },
      credentials: 'include',
      body: JSON.stringify({ token, new_password }),
    });
    return handleResponse(res);
  },

  changePassword: async ({ current_password, new_password }) => {
    return wrappedFetch(`${API_BASE}/api/auth/password/change`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ current_password, new_password }),
    });
  },

  // ── Documents ──────────────────────────────────────────────────────────────
  listDocuments: async (params = {}) => {
    const url = new URL(`${API_BASE}/api/documents`, window.location.origin);
    if (typeof params === 'string') {
      if (params) url.searchParams.set('search', params);
    } else if (params && typeof params === 'object') {
      if (params.search) url.searchParams.set('search', params.search);
      if (params.q) url.searchParams.set('search', params.q);
      if (params.page !== undefined) url.searchParams.set('page', params.page);
      if (params.pageSize !== undefined) url.searchParams.set('page_size', params.pageSize);
      if (params.status) url.searchParams.set('status', params.status);
      if (params.branchId) url.searchParams.set('branch_id', params.branchId);
      if (params.dateFrom) url.searchParams.set('date_from', params.dateFrom);
      if (params.dateTo) url.searchParams.set('date_to', params.dateTo);
      if (params.vendorName) url.searchParams.set('vendor_name', params.vendorName);
      if (params.invoiceNumber) url.searchParams.set('invoice_number', params.invoiceNumber);
      if (params.gstin) url.searchParams.set('gstin', params.gstin);
      if (params.amountMin) url.searchParams.set('amount_min', params.amountMin);
      if (params.amountMax) url.searchParams.set('amount_max', params.amountMax);
      if (params.documentType) url.searchParams.set('document_type', params.documentType);
      if (params.invoiceType) url.searchParams.set('invoice_type', params.invoiceType);
      if (params.includeDeleted) url.searchParams.set('include_deleted', 'true');
      if (params.paginate) url.searchParams.set('paginate', 'true');
    }
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },

  searchDocuments: async (params = {}) => {
    const url = new URL(`${API_BASE}/api/documents/search`, window.location.origin);
    if (typeof params === 'string') {
      if (params) url.searchParams.set('q', params);
    } else if (params && typeof params === 'object') {
      if (params.q) url.searchParams.set('q', params.q);
      if (params.search) url.searchParams.set('q', params.search);
      if (params.dateFrom) url.searchParams.set('date_from', params.dateFrom);
      if (params.dateTo) url.searchParams.set('date_to', params.dateTo);
      if (params.vendorName) url.searchParams.set('vendor_name', params.vendorName);
      if (params.invoiceNumber) url.searchParams.set('invoice_number', params.invoiceNumber);
      if (params.gstin) url.searchParams.set('gstin', params.gstin);
      if (params.amountMin) url.searchParams.set('amount_min', params.amountMin);
      if (params.amountMax) url.searchParams.set('amount_max', params.amountMax);
      if (params.branchId) url.searchParams.set('branch_id', params.branchId);
      if (params.status) url.searchParams.set('status', params.status);
      if (params.documentType) url.searchParams.set('document_type', params.documentType);
      if (params.invoiceType) url.searchParams.set('invoice_type', params.invoiceType);
      if (params.includeDeleted) url.searchParams.set('include_deleted', 'true');
      if (params.page !== undefined) url.searchParams.set('page', params.page);
      if (params.pageSize !== undefined) url.searchParams.set('page_size', params.pageSize);
    }
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },

  getDocument: async (id) => {
    return wrappedFetch(`${API_BASE}/api/documents/${id}`, { headers: getHeaders() });
  },

  uploadDocument: async (file, allowDuplicate = false, invoiceType = 'Tax Invoice') => {
    const formData = new FormData();
    formData.append('file', file);
    if (invoiceType) formData.append('invoice_type', invoiceType);
    const query = allowDuplicate === true ? '?allow_duplicate=true' : '';
    return wrappedFetch(`${API_BASE}/api/documents${query}`, {
      method: 'POST',
      headers: getHeaders(true),
      body: formData,
    });
  },

  uploadDocuments: async (files, allowDuplicate = false, invoiceType = 'Tax Invoice') => {
    const formData = new FormData();
    for (const f of files) {
      formData.append('files', f);
    }
    if (invoiceType) formData.append('invoice_type', invoiceType);
    const query = allowDuplicate === true ? '?allow_duplicate=true' : '';
    return wrappedFetch(`${API_BASE}/api/documents/batch${query}`, {
      method: 'POST',
      headers: getHeaders(true),
      body: formData,
    });
  },

  reprocessDocument: async (id) => {
    return wrappedFetch(`${API_BASE}/api/documents/${id}/reprocess`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  deleteDocument: async (id) => {
    return wrappedFetch(`${API_BASE}/api/documents/${id}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
  },

  restoreDocument: async (id) => {
    return wrappedFetch(`${API_BASE}/api/documents/${id}/restore`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  getFileUrl: (id, download = false) => {
    const token = getAuthToken();
    const tokenPart = token ? `token=${encodeURIComponent(token)}` : '';
    const dlPart = download ? 'download=true' : '';
    const query = [tokenPart, dlPart].filter(Boolean).join('&');
    return `${API_BASE}/api/documents/${id}/file${query ? `?${query}` : ''}`;
  },

  getThumbnailUrl: (id) => {
    const token = getAuthToken();
    return `${API_BASE}/api/documents/${id}/thumbnail${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  },

  getInvoiceUrl: (docId) => {
    const token = getAuthToken();
    return `${API_BASE}/api/documents/${docId}/invoice.pdf${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  },

  // ── Invoices ───────────────────────────────────────────────────────────────
  listInvoices: async (params = {}) => {
    const url = new URL(`${API_BASE}/api/invoices`, window.location.origin);
    if (typeof params === 'string') {
      if (params) url.searchParams.set('search', params);
    } else if (params && typeof params === 'object') {
      if (params.search) url.searchParams.set('search', params.search);
      if (params.kind) url.searchParams.set('kind', params.kind);
      if (params.status) url.searchParams.set('status', params.status);
      if (params.invoice_type && params.invoice_type !== 'all') url.searchParams.set('invoice_type', params.invoice_type);
      if (params.invoiceType && params.invoiceType !== 'all') url.searchParams.set('invoice_type', params.invoiceType);
      if (params.page) url.searchParams.set('page', params.page);
      if (params.limit) url.searchParams.set('limit', params.limit);
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
    return `${API_BASE}/api/invoices/${invoiceId}/pdf?${download ? 'download=true&' : ''}${token ? `token=${encodeURIComponent(token)}` : ''}`;
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
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data),
    });
  },

  updateGstRegistration: async (id, data) => {
    return wrappedFetch(`${API_BASE}/api/gst-registrations/${id}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(data),
    });
  },

  // ── Customers ───────────────────────────────────────────────────────────────
  listCustomers: async (search = '') => {
    const url = new URL(`${API_BASE}/api/customers`, window.location.origin);
    if (search) url.searchParams.set('search', search);
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },

  getCustomer: async (id) => {
    return wrappedFetch(`${API_BASE}/api/customers/${id}`, { headers: getHeaders() });
  },

  createCustomer: async (data) => {
    return wrappedFetch(`${API_BASE}/api/customers`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data),
    });
  },

  updateCustomer: async (id, data) => {
    return wrappedFetch(`${API_BASE}/api/customers/${id}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(data),
    });
  },

  addCustomerAddress: async (customerId, data) => {
    return wrappedFetch(`${API_BASE}/api/customers/${customerId}/addresses`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data),
    });
  },

  // ── Outbound Sales Invoices ─────────────────────────────────────────────────
  previewSalesTax: async (payload) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/tax-preview`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },

  listSalesInvoices: async (params = {}) => {
    const url = new URL(`${API_BASE}/api/sales-invoices`, window.location.origin);
    if (params.status) url.searchParams.set('status', params.status);
    if (params.branch_id) url.searchParams.set('branch_id', params.branch_id);
    if (params.customer_id) url.searchParams.set('customer_id', params.customer_id);
    if (params.financial_year) url.searchParams.set('financial_year', params.financial_year);
    if (params.search) url.searchParams.set('search', params.search);
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },

  getSalesInvoice: async (id) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}`, { headers: getHeaders() });
  },

  createSalesInvoiceDraft: async (payload) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },

  updateSalesInvoiceDraft: async (id, payload) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },

  discardSalesInvoiceDraft: async (id) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
  },

  submitSalesInvoice: async (id) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}/submit`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  approveSalesInvoice: async (id) => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}/approve`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  rejectSalesInvoice: async (id, reason = '') => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}/reject`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ reason }),
    });
  },

  cancelSalesInvoice: async (id, reason = '') => {
    return wrappedFetch(`${API_BASE}/api/sales-invoices/${id}/cancel`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ reason }),
    });
  },

  getSalesInvoicePdfUrl: (id, download = false) => {
    const token = getAuthToken();
    return `${API_BASE}/api/sales-invoices/${id}/pdf?${download ? 'download=true&' : ''}${token ? `token=${encodeURIComponent(token)}` : ''}`;
  },

  // ── Signature Management for Sales Invoices ────────────────────────────────
  uploadTemporarySignature: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const token = getAuthToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}/api/sales-invoices/signatures/temporary`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.message || `Upload failed with status ${res.status}`);
    }
    return res.json();
  },

  getDraftPreviewPageUrl: (invoiceId, page = 1) => {
    const token = getAuthToken();
    return `${API_BASE}/api/sales-invoices/drafts/${invoiceId}/preview-page?page=${page}${token ? `&token=${encodeURIComponent(token)}` : ''}`;
  },

  fetchDraftPreviewPageBlob: async (invoiceId, page = 1) => {
    const res = await fetch(`${API_BASE}/api/sales-invoices/drafts/${invoiceId}/preview-page?page=${page}`, {
      headers: getHeaders(),
    });
    if (!res.ok) {
      throw new Error(`Failed to load page preview (HTTP ${res.status})`);
    }
    const totalPages = parseInt(res.headers.get('X-Total-Pages') || '1', 10);
    const currentPage = parseInt(res.headers.get('X-Current-Page') || String(page), 10);
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    return { objectUrl, totalPages, currentPage };
  },

  getSignatureImageUrl: (sigId) => {
    const token = getAuthToken();
    return `${API_BASE}/api/sales-invoices/signatures/${sigId}/image${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  },

  getTemporarySignatureImageUrl: (tokenVal) => {
    const token = getAuthToken();
    return `${API_BASE}/api/sales-invoices/signatures/temp/${tokenVal}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  },

  // ── Supplier Invoice Copies (Versioning & Regeneration) ─────────────────────
  listDocumentCopies: async (documentId) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/copies`, { headers: getHeaders() });
  },

  regenerateDocumentCopy: async (documentId) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/copies/regenerate`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  getDocumentCopyPdfUrl: (documentId, copyVersion, download = false) => {
    const token = getAuthToken();
    return `${API_BASE}/api/documents/${documentId}/copies/${copyVersion}/pdf?${download ? 'download=true&' : ''}${token ? `token=${encodeURIComponent(token)}` : ''}`;
  },

  // ── Company Onboarding (Public Applicant Endpoints) ────────────────────────
  getOnboarding: async (token) => {
    return wrappedFetch(`${API_BASE}/api/onboarding/${encodeURIComponent(token)}`);
  },

  uploadOnboardingDocument: async (token, documentType, file) => {
    const formData = new FormData();
    formData.append('document_type', documentType);
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/onboarding/${encodeURIComponent(token)}/upload-document`, {
      method: 'POST',
      body: formData,
    });
    return handleResponse(res);
  },

  getOnboardingDocumentUrl: (token, documentType) => {
    return `${API_BASE}/api/onboarding/${encodeURIComponent(token)}/documents/${encodeURIComponent(documentType)}`;
  },

  submitOnboarding: async (token, payload) => {
    const res = await fetch(`${API_BASE}/api/onboarding/${encodeURIComponent(token)}/submit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': generateRequestId(),
      },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  },

  // ── Master Admin Portal Endpoints (require_platform) ───────────────────────
  initiateOnboarding: async ({ company_name, contact_name, contact_email }) => {
    return wrappedFetch(`${API_BASE}/api/admin/onboarding/initiate`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ company_name, contact_name, contact_email }),
    });
  },

  listOnboardings: async (status = null) => {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
    const url = new URL(`${API_BASE}/api/admin/onboarding`, origin);
    if (status && status !== 'all') url.searchParams.set('status', status);
    return wrappedFetch(url.toString(), { headers: getHeaders() });
  },

  getOnboardingDetail: async (onboardingId) => {
    return wrappedFetch(`${API_BASE}/api/admin/onboarding/${onboardingId}`, {
      headers: getHeaders(),
    });
  },

  requestOnboardingChanges: async (onboardingId, comments) => {
    return wrappedFetch(`${API_BASE}/api/admin/onboarding/${onboardingId}/request-changes`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ comments }),
    });
  },

  rejectOnboarding: async (onboardingId, reason) => {
    return wrappedFetch(`${API_BASE}/api/admin/onboarding/${onboardingId}/reject`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ reason }),
    });
  },

  approveOnboarding: async (onboardingId) => {
    return wrappedFetch(`${API_BASE}/api/admin/onboarding/${onboardingId}/approve`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  getAdminDocumentUrl: (onboardingId, documentType) => {
    const token = getAuthToken();
    return `${API_BASE}/api/admin/onboarding/${onboardingId}/documents/${encodeURIComponent(documentType)}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  },

  listAdminCompanies: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/companies`, {
      headers: getHeaders(),
    });
  },

  toggleCompanyStatus: async (companyId) => {
    return wrappedFetch(`${API_BASE}/api/admin/companies/${companyId}/toggle-status`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  getPlatformDashboard: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/dashboard`, {
      headers: getHeaders(),
    });
  },

  getCompanyDetail: async (companyId) => {
    return wrappedFetch(`${API_BASE}/api/admin/companies/${companyId}`, {
      headers: getHeaders(),
    });
  },

  getCompanyOnboardingDossier: async (companyId) => {
    return wrappedFetch(`${API_BASE}/api/admin/companies/${companyId}/onboarding`, {
      headers: getHeaders(),
    });
  },

  updateCompany: async (companyId, payload) => {
    return wrappedFetch(`${API_BASE}/api/admin/companies/${companyId}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },

  getSystemSettings: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/settings`, {
      headers: getHeaders(),
    });
  },

  updateSystemSettings: async (payload) => {
    return wrappedFetch(`${API_BASE}/api/admin/settings`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },

  // ── Company Admin Endpoints (require_company) ─────────────────────────────
  getCompanyDashboard: async () => {
    return wrappedFetch(`${API_BASE}/api/company/dashboard`, {
      headers: getHeaders(),
    });
  },

  getCompanyProfile: async () => {
    return wrappedFetch(`${API_BASE}/api/company/profile`, {
      headers: getHeaders(),
    });
  },

  updateCompanyProfile: async (profileData) => {
    return wrappedFetch(`${API_BASE}/api/company/profile`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(profileData),
    });
  },

  uploadCompanyLogo: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return wrappedFetch(`${API_BASE}/api/company/logo`, {
      method: 'POST',
      headers: getHeaders(true),
      body: formData,
    });
  },

  deleteCompanyLogo: async () => {
    return wrappedFetch(`${API_BASE}/api/company/logo`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
  },

  listCompanyBranches: async () => {
    return wrappedFetch(`${API_BASE}/api/company/branches`, {
      headers: getHeaders(),
    });
  },

  createCompanyBranch: async (branchData) => {
    return wrappedFetch(`${API_BASE}/api/company/branches`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(branchData),
    });
  },

  getCompanyBranch: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}`, {
      headers: getHeaders(),
    });
  },

  updateCompanyBranch: async (branchId, branchData) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(branchData),
    });
  },

  deactivateCompanyBranch: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/deactivate`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  activateCompanyBranch: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/activate`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  toggleBranchStatus: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/toggle-status`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  getCompanyUsers: async (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        query.append(key, val);
      }
    });
    const qs = query.toString() ? `?${query.toString()}` : '';
    return wrappedFetch(`${API_BASE}/api/company/users${qs}`, {
      headers: getHeaders(),
    });
  },

  inviteCompanyUser: async (userData) => {
    return wrappedFetch(`${API_BASE}/api/company/users/invite`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(userData),
    });
  },

  getCompanyInvitations: async () => {
    return wrappedFetch(`${API_BASE}/api/company/invitations`, {
      headers: getHeaders(),
    });
  },

  resendCompanyInvitation: async (invitationId) => {
    return wrappedFetch(`${API_BASE}/api/company/invitations/${invitationId}/resend`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  revokeCompanyInvitation: async (invitationId) => {
    return wrappedFetch(`${API_BASE}/api/company/invitations/${invitationId}/revoke`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  updateCompanyUser: async (userId, userData) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(userData),
    });
  },

  deactivateCompanyUser: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}/deactivate`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  activateCompanyUser: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}/activate`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  forceLogoutCompanyUser: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}/force-logout`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  requestCompanyUserMfaReset: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}/mfa-reset-request`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  getCompanyDocumentsArchive: async (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        query.append(key, val);
      }
    });
    const qs = query.toString() ? `?${query.toString()}` : '';
    return wrappedFetch(`${API_BASE}/api/company/documents${qs}`, {
      headers: getHeaders(),
    });
  },

  getCompanyAuditLogs: async (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        query.append(key, val);
      }
    });
    const qs = query.toString() ? `?${query.toString()}` : '';
    return wrappedFetch(`${API_BASE}/api/company/audit-logs${qs}`, {
      headers: getHeaders(),
    });
  },

  // ── Audit Logging (Module 5) ───────────────────────────────────────────────
  getAuditLogs: async (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        query.append(key, val);
      }
    });
    const qs = query.toString() ? `?${query.toString()}` : '';
    return wrappedFetch(`${API_BASE}/api/audit${qs}`, {
      headers: getHeaders(),
    });
  },

  getPlatformAuditLogs: async (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== '') {
        query.append(key, val);
      }
    });
    const qs = query.toString() ? `?${query.toString()}` : '';
    return wrappedFetch(`${API_BASE}/api/admin/audit${qs}`, {
      headers: getHeaders(),
    });
  },

  // ── Multi-Factor Authentication (Module 6) ─────────────────────────────────
  mfaVerify: async (mfaPendingToken, code) => {
    const res = await fetch(`${API_BASE}/api/auth/mfa/verify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': generateRequestId(),
      },
      credentials: 'include',
      body: JSON.stringify({ mfa_pending_token: mfaPendingToken, code }),
    });
    const data = await handleResponse(res);
    if (data.access_token) {
      setAuthToken(data.access_token);
    }
    return data;
  },

  mfaRecoveryVerify: async (mfaPendingToken, recoveryCode) => {
    const res = await fetch(`${API_BASE}/api/auth/mfa/recovery/verify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': generateRequestId(),
      },
      credentials: 'include',
      body: JSON.stringify({ mfa_pending_token: mfaPendingToken, recovery_code: recoveryCode }),
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
      headers['Authorization'] = `Bearer ${enrollmentToken}`;
    }
    const url = regenerate
      ? `${API_BASE}/api/auth/mfa/enroll/start?regenerate=true`
      : `${API_BASE}/api/auth/mfa/enroll/start`;
    return wrappedFetch(url, {
      method: 'POST',
      headers,
    });
  },

  mfaEnrollVerify: async (code, enrollmentToken = null) => {
    const token = enrollmentToken || getAuthToken();
    const headers = {
      'Content-Type': 'application/json',
      'X-Request-ID': generateRequestId(),
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}/api/auth/mfa/enroll/verify`, {
      method: 'POST',
      headers,
      credentials: 'include',
      body: JSON.stringify({ code, enrollment_token: token }),
    });
    const data = await handleResponse(res);
    if (data.access_token) {
      setAuthToken(data.access_token);
    }
    return data;
  },

  mfaStatus: async () => {
    return wrappedFetch(`${API_BASE}/api/auth/mfa/status`, {
      headers: getHeaders(),
    });
  },

  mfaDisable: async (password, code) => {
    return wrappedFetch(`${API_BASE}/api/auth/mfa/disable`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ password, code }),
    });
  },

  mfaRegenerateRecovery: async ({ password, code }) => {
    return wrappedFetch(`${API_BASE}/api/auth/mfa/recovery/regenerate`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ password, code }),
    });
  },

  getCompanyMfaPolicy: async () => {
    return wrappedFetch(`${API_BASE}/api/company/security/mfa-policy`, {
      headers: getHeaders(),
    });
  },

  updateCompanyMfaPolicy: async (payloadOrRequired, allowBranchMfaControl) => {
    let body = {};
    if (typeof payloadOrRequired === 'object' && payloadOrRequired !== null) {
      body = payloadOrRequired;
    } else {
      if (payloadOrRequired !== undefined) body.mfa_required_for_all = payloadOrRequired;
      if (allowBranchMfaControl !== undefined) body.allow_branch_mfa_control = allowBranchMfaControl;
    }
    return wrappedFetch(`${API_BASE}/api/company/security/mfa-policy`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(body),
    });
  },

  getBranchMfaPolicy: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/branch/${branchId}/security/mfa-policy`, {
      headers: getHeaders(),
    });
  },

  updateBranchMfaPolicy: async (branchId, mfaRequiredForAll) => {
    return wrappedFetch(`${API_BASE}/api/branch/${branchId}/security/mfa-policy`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ mfa_required_for_all: mfaRequiredForAll }),
    });
  },

  branchResetUserMfa: async (userId, confirmPassword = null, reason = null) => {
    return wrappedFetch(`${API_BASE}/api/branch/users/${userId}/reset-mfa`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        confirm_password: confirmPassword,
        reason: reason || 'Branch Admin Reset',
      }),
    });
  },

  getPlatformMfaPolicy: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/security/mfa-policy`, {
      headers: getHeaders(),
    });
  },

  updatePlatformMfaPolicy: async (policyUpdates) => {
    return wrappedFetch(`${API_BASE}/api/admin/security/mfa-policy`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(policyUpdates),
    });
  },

  resetCompanyUserMfa: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/company/users/${userId}/reset-mfa`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  resetPlatformUserMfa: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/admin/users/${userId}/reset-mfa`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  resetMasterAdminMfa: async (adminId) => {
    return wrappedFetch(`${API_BASE}/api/admin/master-admins/${adminId}/reset-mfa`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  // ── Module 10: Multi-Provider AI Architecture ─────────────────────────────
  // Platform AI (Master Admin)
  getPlatformAIProviders: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/providers`, { headers: getHeaders() });
  },
  updatePlatformAIProvider: async (providerKey, updates) => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/providers/${providerKey}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(updates),
    });
  },
  getPlatformAICredentials: async () => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/credentials`, { headers: getHeaders() });
  },
  savePlatformAICredential: async (providerKey, apiKey) => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/credentials`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey, api_key: apiKey }),
    });
  },
  deletePlatformAICredential: async (credentialId) => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/credentials/${credentialId}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
  },
  testPlatformAIConnection: async (providerKey, model, apiKey = null) => {
    return wrappedFetch(`${API_BASE}/api/admin/ai/test-connection`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey, model, api_key: apiKey }),
    });
  },

  // Company AI (Company Admin)
  getCompanyAISettings: async () => {
    return wrappedFetch(`${API_BASE}/api/company/ai/settings`, { headers: getHeaders() });
  },
  updateCompanyAISettings: async (settings) => {
    return wrappedFetch(`${API_BASE}/api/company/ai/settings`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(settings),
    });
  },
  grantCompanyAIConsent: async (providerKey, termsVersion = 'v1.0') => {
    return wrappedFetch(`${API_BASE}/api/company/ai/consent`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey, consented_terms_version: termsVersion }),
    });
  },
  revokeCompanyAIConsent: async (providerKey) => {
    return wrappedFetch(`${API_BASE}/api/company/ai/consent/revoke`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey }),
    });
  },
  getCompanyAICredentials: async () => {
    return wrappedFetch(`${API_BASE}/api/company/ai/credentials`, { headers: getHeaders() });
  },
  saveCompanyAICredential: async (providerKey, apiKey) => {
    return wrappedFetch(`${API_BASE}/api/company/ai/credentials`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey, api_key: apiKey }),
    });
  },
  deleteCompanyAICredential: async (credentialId) => {
    return wrappedFetch(`${API_BASE}/api/company/ai/credentials/${credentialId}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
  },
  getCompanyAIUsage: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return wrappedFetch(`${API_BASE}/api/company/ai/usage${query ? `?${query}` : ''}`, { headers: getHeaders() });
  },

  // Branch AI
  getBranchAIConfig: async (branchId) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/ai/config`, { headers: getHeaders() });
  },
  updateBranchAIConfig: async (branchId, config) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/ai/config`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(config),
    });
  },
  testBranchAIConnection: async (branchId, providerKey, model) => {
    return wrappedFetch(`${API_BASE}/api/company/branches/${branchId}/ai/test-connection`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ provider_key: providerKey, model }),
    });
  },

  // ── Module 11: Extraction Templates & Human Verification ─────────────
  getTemplates: async (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return wrappedFetch(`${API_BASE}/api/company/templates${query ? `?${query}` : ''}`, { headers: getHeaders() });
  },
  getTemplate: async (id) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${id}`, { headers: getHeaders() });
  },
  createTemplate: async (payload) => {
    return wrappedFetch(`${API_BASE}/api/company/templates`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },
  updateTemplate: async (id, payload) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${id}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },
  deactivateTemplate: async (id) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${id}`, {
      method: 'DELETE',
      headers: getHeaders(),
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
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },
  publishTemplateVersion: async (templateId, versionId) => {
    return wrappedFetch(`${API_BASE}/api/company/templates/${templateId}/versions/${versionId}/publish`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  // Document Review & Verification
  getDocumentExtraction: async (documentId) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/extraction`, { headers: getHeaders() });
  },
  saveExtractionCorrections: async (documentId, payload) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/review/save`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },
  approveDocumentExtraction: async (documentId, payload = {}) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/review/approve`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },
  getDocumentExtractionEdits: async (documentId) => {
    return wrappedFetch(`${API_BASE}/api/documents/${documentId}/edits`, { headers: getHeaders() });
  },

  // ── Module 14: Operational Dashboard & Usage Reporting ──────────────────────
  getDashboardCompany: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.date_from) q.append('date_from', params.date_from);
    if (params.date_to) q.append('date_to', params.date_to);
    if (params.branch_id) q.append('branch_id', params.branch_id);
    const qs = q.toString() ? `?${q.toString()}` : '';
    return wrappedFetch(`${API_BASE}/api/dashboard/company${qs}`, { headers: getHeaders() });
  },

  getDashboardBranch: async (branchId, params = {}) => {
    const q = new URLSearchParams();
    if (params.date_from) q.append('date_from', params.date_from);
    if (params.date_to) q.append('date_to', params.date_to);
    const qs = q.toString() ? `?${q.toString()}` : '';
    return wrappedFetch(`${API_BASE}/api/dashboard/branch/${branchId}${qs}`, { headers: getHeaders() });
  },

  getDashboardAIUsage: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.date_from) q.append('date_from', params.date_from);
    if (params.date_to) q.append('date_to', params.date_to);
    if (params.branch_id) q.append('branch_id', params.branch_id);
    const qs = q.toString() ? `?${q.toString()}` : '';
    return wrappedFetch(`${API_BASE}/api/dashboard/ai-usage${qs}`, { headers: getHeaders() });
  },

  getDashboardJobs: async (params = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.append('status', params.status);
    if (params.branch_id) q.append('branch_id', params.branch_id);
    if (params.page) q.append('page', params.page);
    if (params.page_size) q.append('page_size', params.page_size);
    const qs = q.toString() ? `?${q.toString()}` : '';
    return wrappedFetch(`${API_BASE}/api/dashboard/jobs${qs}`, { headers: getHeaders() });
  },

  downloadDashboardCsv: async (exportType, params = {}) => {
    const q = new URLSearchParams();
    q.append('export_type', exportType);
    if (params.date_from) q.append('date_from', params.date_from);
    if (params.date_to) q.append('date_to', params.date_to);
    if (params.branch_id) q.append('branch_id', params.branch_id);
    const token = getAuthToken();
    const url = `${API_BASE}/api/dashboard/export/csv?${q.toString()}`;
    const resp = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });
    if (!resp.ok) {
      const errJson = await resp.json().catch(() => ({}));
      throw new Error(errJson.detail || `Export failed with status ${resp.status}`);
    }
    const blob = await resp.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    const disposition = resp.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    a.download = match ? match[1] : `${exportType}_export.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(downloadUrl);
  },

  downloadBlobUrl: async (url, fallbackFilename = 'download') => {
    const token = getAuthToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const resp = await fetch(url, { headers });
    if (!resp.ok) {
      const errJson = await resp.json().catch(() => ({}));
      throw new Error(errJson.detail || `Download failed with status ${resp.status}`);
    }
    const blob = await resp.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    const disposition = resp.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    a.download = match ? match[1] : fallbackFilename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(downloadUrl);
  },

  downloadDocumentOriginal: async (id, filename) => {
    return api.downloadBlobUrl(`${API_BASE}/api/documents/${id}/file?download=true`, filename || `document_${id}`);
  },

  downloadDocumentInvoicePdf: async (docId, filename) => {
    return api.downloadBlobUrl(`${API_BASE}/api/documents/${docId}/invoice.pdf?download=true`, filename || `invoice_${docId}.pdf`);
  },

  downloadDocumentCopyPdf: async (docId, version, filename) => {
    return api.downloadBlobUrl(`${API_BASE}/api/documents/${docId}/copies/${version}/pdf?download=true`, filename || `copy_v${version}.pdf`);
  },

  // ── Branch User Management API ─────────────────────────────────────────────
  getBranchAuthorizedBranches: async () => {
    return wrappedFetch(`${API_BASE}/api/branch/branches`, {
      headers: getHeaders(),
    });
  },

  getBranchUsers: async ({ page = 1, pageSize = 25, branchId = null, role = null, status = null, search = '' } = {}) => {
    const params = new URLSearchParams();
    params.set('page', page);
    params.set('page_size', pageSize);
    if (branchId) params.set('branch_id', branchId);
    if (role) params.set('role', role);
    if (status) params.set('status', status);
    if (search && search.trim()) params.set('search', search.trim());
    return wrappedFetch(`${API_BASE}/api/branch/users?${params.toString()}`, {
      headers: getHeaders(),
    });
  },

  inviteBranchUser: async (payload) => {
    return wrappedFetch(`${API_BASE}/api/branch/users/invite`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },

  updateBranchUser: async (userId, payload) => {
    return wrappedFetch(`${API_BASE}/api/branch/users/${userId}`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });
  },

  deactivateBranchUser: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/branch/users/${userId}/deactivate`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  activateBranchUser: async (userId) => {
    return wrappedFetch(`${API_BASE}/api/branch/users/${userId}/activate`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  getBranchInvitations: async ({ branchId = null } = {}) => {
    const params = new URLSearchParams();
    if (branchId) params.set('branch_id', branchId);
    return wrappedFetch(`${API_BASE}/api/branch/invitations?${params.toString()}`, {
      headers: getHeaders(),
    });
  },

  resendBranchInvitation: async (invitationId) => {
    return wrappedFetch(`${API_BASE}/api/branch/invitations/${invitationId}/resend`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },

  revokeBranchInvitation: async (invitationId) => {
    return wrappedFetch(`${API_BASE}/api/branch/invitations/${invitationId}/revoke`, {
      method: 'POST',
      headers: getHeaders(),
    });
  },
};
