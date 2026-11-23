import { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';

function formatNumber(num) {
  if (num === null || num === undefined) return '0';
  return Number(num).toLocaleString('en-IN');
}

function formatCurrencyINR(amount) {
  if (amount === null || amount === undefined || isNaN(amount)) return '₹0.00';
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `₹${Number(amount).toFixed(2)}`;
  }
}

function formatUSD(amount) {
  if (amount === null || amount === undefined) return '$0.00';
  return `$${Number(amount).toFixed(4)}`;
}

function formatDateTime(dateStr) {
  if (!dateStr) return '—';
  try {
    const str = String(dateStr).trim();
    const normalized = (!str.endsWith('Z') && !str.includes('+')) ? `${str}Z` : str;
    return new Date(normalized).toLocaleString();
  } catch {
    return String(dateStr);
  }
}

export default function BranchDashboardView({
  branchId: initialBranchId = null,
  branchesList: propBranchesList = null,
  showToast = null,
  onNavigateToDocs = null,
}) {
  const { user, hasPermission } = useAuth();

  const isCompanyAdmin =
    user?.role === 'GLOBAL_ADMIN' ||
    hasPermission('company.view') ||
    hasPermission('document.view_company');

  // Compute authorized branch IDs for the current user
  const authorizedBranchIds = useMemo(() => {
    if (!user) return [];
    if (isCompanyAdmin) return null; // null indicates unrestricted company-wide access
    const ids = new Set();
    if (user.branch_id) ids.add(Number(user.branch_id));
    if (user.tenant_id) ids.add(Number(user.tenant_id));
    if (Array.isArray(user.assigned_branch_ids)) {
      user.assigned_branch_ids.forEach((id) => ids.add(Number(id)));
    }
    if (Array.isArray(user.assignments)) {
      user.assignments.forEach((a) => {
        if (a.scope_type === 'branch' && a.scope_id) {
          ids.add(Number(a.scope_id));
        }
      });
    }
    return Array.from(ids);
  }, [user, isCompanyAdmin]);

  // Branch Selection State
  const [branches, setBranches] = useState([]);
  const [selectedBranchId, setSelectedBranchId] = useState(initialBranchId);

  // Date Filter State
  const [datePreset, setDatePreset] = useState('last30');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');

  // Dashboard Data State
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exportingReport, setExportingReport] = useState(null);
  const [reprocessingJobId, setReprocessingJobId] = useState(null);
  const [dismissedFailureAlert, setDismissedFailureAlert] = useState(false);

  // Load available branches for selector with strict authorization filtering
  useEffect(() => {
    const processBranches = (rawList) => {
      const list = Array.isArray(rawList) ? rawList : (rawList?.items || []);
      const filtered = isCompanyAdmin
        ? list
        : list.filter((b) => authorizedBranchIds?.includes(Number(b.id)));

      // If user has a branch_id but it was not returned by list, synthesize a fallback entry
      if (!isCompanyAdmin && filtered.length === 0 && user?.branch_id) {
        filtered.push({
          id: user.branch_id,
          name: user.branch_name || user.tenant_name || 'Assigned Branch',
          code: user.branch_code || 'BR',
        });
      }

      setBranches(filtered);

      // Determine initial/default selected branch
      // Priority:
      // 1. If current selection is valid and authorized, retain it
      // 2. If initialBranchId is valid and authorized, use it
      // 3. User's own branch_id
      // 4. First authorized branch in list
      setSelectedBranchId((currentId) => {
        const isCurrentValid = currentId && (isCompanyAdmin || authorizedBranchIds?.includes(Number(currentId)));
        if (isCurrentValid) return currentId;

        if (initialBranchId && (isCompanyAdmin || authorizedBranchIds?.includes(Number(initialBranchId)))) {
          return Number(initialBranchId);
        }
        if (user?.branch_id && (isCompanyAdmin || authorizedBranchIds?.includes(Number(user.branch_id)))) {
          return Number(user.branch_id);
        }
        return filtered[0]?.id || null;
      });
    };

    if (propBranchesList && propBranchesList.length > 0) {
      processBranches(propBranchesList);
      return;
    }

    const fetchBranches = async () => {
      try {
        const res = await api.listCompanyBranches();
        processBranches(res);
      } catch (err) {
        console.error('Failed to load branches:', err);
      }
    };

    fetchBranches();
  }, [propBranchesList, initialBranchId, user, isCompanyAdmin, authorizedBranchIds]);

  // Compute UTC date strings for query params
  const calculateDateRange = useCallback(() => {
    const now = new Date();
    const toIso = (d) => d.toISOString().split('T')[0];

    if (datePreset === 'last7') {
      const from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      return { from: toIso(from), to: toIso(now) };
    }
    if (datePreset === 'last30') {
      const from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      return { from: toIso(from), to: toIso(now) };
    }
    if (datePreset === 'month') {
      const from = new Date(now.getFullYear(), now.getMonth(), 1);
      return { from: toIso(from), to: toIso(now) };
    }
    if (datePreset === 'custom') {
      return { from: customFrom || null, to: customTo || null };
    }
    return { from: null, to: null };
  }, [datePreset, customFrom, customTo]);

  // Load Dashboard Data for Selected Branch
  const loadDashboard = useCallback(async () => {
    if (!selectedBranchId) return;

    // Authorization safeguard: never request an unauthorized branch
    if (!isCompanyAdmin && authorizedBranchIds && !authorizedBranchIds.includes(Number(selectedBranchId))) {
      setError('You are not authorized to view metrics for this branch.');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');
    try {
      const { from, to } = calculateDateRange();
      const res = await api.getDashboardBranch(selectedBranchId, {
        date_from: from,
        date_to: to,
      });
      setData(res);
    } catch (err) {
      setError(err.message || 'Failed to load branch operational dashboard.');
    } finally {
      setLoading(false);
    }
  }, [selectedBranchId, calculateDateRange, isCompanyAdmin, authorizedBranchIds]);

  useEffect(() => {
    if (selectedBranchId) {
      setDismissedFailureAlert(false);
      loadDashboard();
    }
  }, [selectedBranchId, loadDashboard]);

  // CSV Export Action
  const handleExportCsv = async (reportType) => {
    if (!selectedBranchId) return;
    setExportingReport(reportType);
    try {
      const { from, to } = calculateDateRange();
      await api.downloadDashboardCsv(reportType, {
        date_from: from,
        date_to: to,
        branch_id: selectedBranchId,
      });
      showToast?.(`Branch ${reportType} report exported successfully.`, 'success');
    } catch (err) {
      showToast?.(err.message || `Failed to export ${reportType} CSV.`, 'error');
    } finally {
      setExportingReport(null);
    }
  };

  // Reprocess Document Action
  const handleReprocess = async (docId, jobId) => {
    setReprocessingJobId(jobId);
    try {
      await api.reprocessDocument(docId);
      showToast?.(`Reprocessing job queued for document #${docId}.`, 'success');
      loadDashboard();
    } catch (err) {
      showToast?.(err.message || 'Failed to reprocess document.', 'error');
    } finally {
      setReprocessingJobId(null);
    }
  };

  const {
    branch_info = {},
    documents = {},
    invoices = {},
    ai_usage = {},
    jobs = {},
    recent_failed_jobs = [],
  } = data || {};

  const docStatus = documents.by_status || {};
  const docTotal = documents.total_count || 0;

  // Percentage calculations for document status bar
  const pctCompleted = docTotal > 0 ? Math.round(((docStatus.completed || 0) / docTotal) * 100) : 0;
  const pctProcessing = docTotal > 0 ? Math.round(((docStatus.processing || 0) / docTotal) * 100) : 0;
  const pctUploaded = docTotal > 0 ? Math.round(((docStatus.uploaded || 0) / docTotal) * 100) : 0;
  const pctFailed = docTotal > 0 ? Math.round(((docStatus.failed || 0) / docTotal) * 100) : 0;

  return (
    <div style={{ maxWidth: '1280px', margin: '0 auto' }}>
      {/* ── Section Header & Branch Switcher ─────────────────────────── */}
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        marginBottom: '24px',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <h2 style={{ fontSize: '24px', fontWeight: 700, margin: 0, color: '#0f172a' }}>
              Branch Operational Dashboard
            </h2>
            {branch_info.code && (
              <span style={{
                fontSize: '12px',
                fontWeight: 700,
                color: '#2563eb',
                backgroundColor: '#eff6ff',
                padding: '2px 8px',
                borderRadius: '6px',
                border: '1px solid #bfdbfe',
              }}>
                {branch_info.code}
              </span>
            )}
            <span style={{
              fontSize: '11px',
              fontWeight: 700,
              textTransform: 'uppercase',
              color: branch_info.status === 'active' ? '#166534' : '#991b1b',
              backgroundColor: branch_info.status === 'active' ? '#dcfce7' : '#fee2e2',
              padding: '2px 8px',
              borderRadius: '6px',
              border: `1px solid ${branch_info.status === 'active' ? '#bbf7d0' : '#fecaca'}`,
            }}>
              {branch_info.status || 'Active'}
            </span>
          </div>

          <p style={{ margin: 0, color: '#64748b', fontSize: '14px' }}>
            {branch_info.name ? (
              <span>
                <strong>{branch_info.name}</strong> &middot; {branch_info.branch_type || 'Branch'}
                {branch_info.city ? ` in ${branch_info.city}, ${branch_info.state || ''}` : ''}
              </span>
            ) : (
              'Operational metrics, OCR throughput, invoice billing, and background jobs.'
            )}
          </p>
        </div>

        {/* Branch Selector & Export Menu */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          {branches.length > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <label style={{ fontSize: '13px', fontWeight: 600, color: '#475569' }}>
                Branch:
              </label>
              <select
                value={selectedBranchId || ''}
                onChange={(e) => setSelectedBranchId(Number(e.target.value))}
                style={{
                  padding: '7px 12px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '13px',
                  fontWeight: 600,
                  color: '#0f172a',
                  backgroundColor: '#ffffff',
                  cursor: 'pointer',
                  minWidth: '180px',
                }}
              >
                {branches.map(b => (
                  <option key={b.id} value={b.id}>
                    {b.name} ({b.code})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Export Dropdown / Actions */}
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => handleExportCsv('documents')}
              disabled={exportingReport !== null || loading}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                backgroundColor: '#ffffff',
                color: '#334155',
                padding: '8px 14px',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                fontSize: '13px',
                fontWeight: 600,
                cursor: exportingReport ? 'not-allowed' : 'pointer',
                boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
              }}
              title="Export all documents in this branch as CSV"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              {exportingReport === 'documents' ? 'Exporting...' : 'Export Docs CSV'}
            </button>

            <button
              onClick={() => handleExportCsv('invoices')}
              disabled={exportingReport !== null || loading}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                backgroundColor: '#ffffff',
                color: '#334155',
                padding: '8px 14px',
                borderRadius: '8px',
                border: '1px solid #cbd5e1',
                fontSize: '13px',
                fontWeight: 600,
                cursor: exportingReport ? 'not-allowed' : 'pointer',
                boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
              }}
              title="Export all invoices in this branch as CSV"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              {exportingReport === 'invoices' ? 'Exporting...' : 'Export Invoices'}
            </button>
          </div>
        </div>
      </div>

      {/* ── Filters Bar ─────────────────────────────────────────────── */}
      <div style={{
        backgroundColor: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: '12px',
        padding: '16px 20px',
        marginBottom: '24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '14px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}>
        {/* Date Presets */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#475569' }}>
            Time Window:
          </span>
          {[
            { id: 'last7', label: 'Last 7 Days' },
            { id: 'last30', label: 'Last 30 Days' },
            { id: 'month', label: 'This Month' },
            { id: 'all', label: 'All Time' },
            { id: 'custom', label: 'Custom' },
          ].map(p => (
            <button
              key={p.id}
              onClick={() => setDatePreset(p.id)}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                border: datePreset === p.id ? '1px solid #ef233c' : '1px solid #cbd5e1',
                backgroundColor: datePreset === p.id ? '#fef2f2' : '#ffffff',
                color: datePreset === p.id ? '#b91c1c' : '#475569',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s ease-in-out',
              }}
            >
              {p.label}
            </button>
          ))}

          {/* Custom Date Pickers */}
          {datePreset === 'custom' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '6px' }}>
              <input
                type="date"
                value={customFrom}
                onChange={(e) => setCustomFrom(e.target.value)}
                style={{
                  padding: '5px 8px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '12px',
                  color: '#0f172a',
                }}
              />
              <span style={{ color: '#94a3b8', fontSize: '12px' }}>to</span>
              <input
                type="date"
                value={customTo}
                onChange={(e) => setCustomTo(e.target.value)}
                style={{
                  padding: '5px 8px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '12px',
                  color: '#0f172a',
                }}
              />
            </div>
          )}
        </div>

        <button
          onClick={loadDashboard}
          disabled={loading}
          style={{
            padding: '7px 14px',
            borderRadius: '6px',
            border: '1px solid #cbd5e1',
            backgroundColor: '#ffffff',
            color: '#334155',
            fontSize: '13px',
            fontWeight: 600,
            cursor: loading ? 'not-allowed' : 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}>
            <path d="M23 4v6h-6"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          Refresh
        </button>
      </div>

      {/* ── Error Banner ────────────────────────────────────────────── */}
      {error && (
        <div style={{
          backgroundColor: '#fef2f2',
          border: '1px solid #fecaca',
          borderRadius: '8px',
          padding: '14px 18px',
          color: '#991b1b',
          marginBottom: '24px',
          fontSize: '14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div><strong>Error:</strong> {error}</div>
          <button
            onClick={loadDashboard}
            style={{
              background: 'none',
              border: 'none',
              color: '#991b1b',
              fontWeight: 700,
              cursor: 'pointer',
              textDecoration: 'underline'
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Loading Spinner ─────────────────────────────────────────── */}
      {loading && !data && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}>
          <div style={{ textAlign: 'center', color: '#64748b' }}>
            <div className="spinner" style={{ margin: '0 auto 12px' }} />
            Loading branch operational metrics...
          </div>
        </div>
      )}

      {/* ── Content (When Data Loaded) ──────────────────────────────── */}
      {data && (
        <>
          {/* Failed Background Jobs Alert Banner */}
          {jobs.failed > 0 && recent_failed_jobs.length > 0 && !dismissedFailureAlert && (
            <div
              role="alert"
              style={{
                backgroundColor: '#fff1f2',
                border: '1px solid #fecdd3',
                borderRadius: '10px',
                padding: '14px 20px',
                marginBottom: '24px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  backgroundColor: '#fee2e2',
                  color: '#e11d48',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                </div>
                <div>
                  <div style={{ fontSize: '14px', fontWeight: 700, color: '#9f1239' }}>
                    {jobs.failed} Background Processing {jobs.failed === 1 ? 'Job' : 'Jobs'} Failed in this Branch
                  </div>
                  <div style={{ fontSize: '12px', color: '#be123c', marginTop: '2px' }}>
                    Review the diagnostic summaries below and reprocess affected documents.
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => {
                    const el = document.getElementById('recent-job-diagnostics');
                    if (el) el.scrollIntoView({ behavior: 'smooth' });
                  }}
                  style={{
                    padding: '7px 12px',
                    borderRadius: '6px',
                    backgroundColor: '#ffffff',
                    border: '1px solid #fecdd3',
                    color: '#9f1239',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  View Diagnostics ↓
                </button>

                <button
                  type="button"
                  onClick={() => handleExportCsv('failed-jobs')}
                  disabled={exportingReport !== null}
                  style={{
                    padding: '7px 12px',
                    borderRadius: '6px',
                    backgroundColor: '#ffffff',
                    border: '1px solid #fecdd3',
                    color: '#9f1239',
                    fontSize: '12px',
                    fontWeight: 700,
                    cursor: exportingReport ? 'not-allowed' : 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Export Failed Jobs
                </button>

                <button
                  type="button"
                  onClick={() => setDismissedFailureAlert(true)}
                  aria-label="Dismiss failure alert"
                  title="Close alert"
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '6px',
                    border: '1px solid #fecdd3',
                    backgroundColor: '#ffffff',
                    color: '#9f1239',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '16px',
                    fontWeight: 700,
                    lineHeight: 1,
                    transition: 'all 0.15s ease-in-out',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#fee2e2';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#ffffff';
                  }}
                >
                  ✕
                </button>
              </div>
            </div>
          )}

          {/* ── Key KPI Cards ────────────────────────────────────────── */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '16px',
            marginBottom: '28px',
          }}>
            {/* Card 1: Documents */}
            <div style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              padding: '20px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Branch Documents
                </span>
                <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#eff6ff', color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                </div>
              </div>
              <div style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a' }}>
                {formatNumber(docTotal)}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                <span style={{ color: '#16a34a', fontWeight: 600 }}>{docStatus.completed || 0} completed</span> &middot; {docStatus.failed || 0} failed
              </div>
            </div>

            {/* Card 2: Storage Used */}
            <div style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              padding: '20px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Storage Volume
                </span>
                <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#fff7ed', color: '#ea580c', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
                </div>
              </div>
              <div style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a' }}>
                {documents.storage_used_mb || 0} <span style={{ fontSize: '14px', fontWeight: 500, color: '#64748b' }}>MB</span>
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                {(documents.storage_used_bytes || 0).toLocaleString()} bytes stored
              </div>
            </div>

            {/* Card 3: Invoices Total */}
            <div style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              padding: '20px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Invoice Volume
                </span>
                <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#f0fdf4', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                </div>
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#0f172a' }}>
                {formatCurrencyINR(invoices.total_grand_amount || 0)}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                {invoices.total_invoices || 0} total invoices ({invoices.by_kind?.generated?.count || 0} outbound sales)
              </div>
            </div>

            {/* Card 4: AI Usage Spend */}
            <div style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              padding: '20px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Branch AI Spend
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#0284c7', backgroundColor: '#e0f2fe', padding: '2px 6px', borderRadius: '4px' }}>
                    ₹ / $ Dual
                  </span>
                  <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#fdf2f8', color: '#db2777', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '14px' }}>
                    ₹
                  </div>
                </div>
              </div>
              <div style={{ fontSize: '22px', fontWeight: 700, color: '#0f172a' }}>
                {formatCurrencyINR(ai_usage.cost_inr !== undefined ? ai_usage.cost_inr : (ai_usage.estimated_cost_usd || 0) * (ai_usage.exchange_rate || 85))}
              </div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: '#475569', marginTop: '2px' }}>
                {formatUSD(ai_usage.estimated_cost_usd || 0)} USD
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                {formatNumber(ai_usage.total_calls || 0)} calls &middot; {formatNumber(ai_usage.total_tokens || 0)} tokens
              </div>
            </div>
          </div>

          {/* ── Document OCR Status & Progress ───────────────────────── */}
          <div style={{
            backgroundColor: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '12px',
            padding: '24px',
            marginBottom: '28px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 4px 0', color: '#0f172a' }}>
                  Document Ingestion &amp; OCR Throughput
                </h3>
                <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
                  Distribution of documents by extraction pipeline status.
                </p>
              </div>

              {onNavigateToDocs && (
                <button
                  onClick={onNavigateToDocs}
                  style={{
                    fontSize: '13px',
                    fontWeight: 600,
                    color: '#ef233c',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  View Documents &rarr;
                </button>
              )}
            </div>

            {/* Visual Stacked Progress Bar */}
            <div style={{
              height: '12px',
              width: '100%',
              backgroundColor: '#f1f5f9',
              borderRadius: '6px',
              overflow: 'hidden',
              display: 'flex',
              marginBottom: '16px',
            }}>
              {pctCompleted > 0 && (
                <div
                  style={{ width: `${pctCompleted}%`, backgroundColor: '#10b981' }}
                  title={`Completed: ${docStatus.completed || 0} (${pctCompleted}%)`}
                />
              )}
              {pctProcessing > 0 && (
                <div
                  style={{ width: `${pctProcessing}%`, backgroundColor: '#3b82f6' }}
                  title={`Processing: ${docStatus.processing || 0} (${pctProcessing}%)`}
                />
              )}
              {pctUploaded > 0 && (
                <div
                  style={{ width: `${pctUploaded}%`, backgroundColor: '#f59e0b' }}
                  title={`Uploaded: ${docStatus.uploaded || 0} (${pctUploaded}%)`}
                />
              )}
              {pctFailed > 0 && (
                <div
                  style={{ width: `${pctFailed}%`, backgroundColor: '#ef4444' }}
                  title={`Failed: ${docStatus.failed || 0} (${pctFailed}%)`}
                />
              )}
            </div>

            {/* Status Breakdown Grid */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: '12px',
            }}>
              <div style={{ padding: '12px 16px', borderRadius: '8px', backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0' }}>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#166534', textTransform: 'uppercase' }}>Completed</div>
                <div style={{ fontSize: '20px', fontWeight: 700, color: '#14532d', marginTop: '2px' }}>
                  {formatNumber(docStatus.completed || 0)}
                </div>
                <div style={{ fontSize: '11px', color: '#166534', marginTop: '2px' }}>
                  {pctCompleted}% of total
                </div>
              </div>

              <div style={{ padding: '12px 16px', borderRadius: '8px', backgroundColor: '#eff6ff', border: '1px solid #bfdbfe' }}>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#1e40af', textTransform: 'uppercase' }}>Processing</div>
                <div style={{ fontSize: '20px', fontWeight: 700, color: '#1e3a8a', marginTop: '2px' }}>
                  {formatNumber(docStatus.processing || 0)}
                </div>
                <div style={{ fontSize: '11px', color: '#1e40af', marginTop: '2px' }}>
                  {pctProcessing}% in queue/OCR
                </div>
              </div>

              <div style={{ padding: '12px 16px', borderRadius: '8px', backgroundColor: '#fffbeb', border: '1px solid #fde68a' }}>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#92400e', textTransform: 'uppercase' }}>Uploaded</div>
                <div style={{ fontSize: '20px', fontWeight: 700, color: '#78350f', marginTop: '2px' }}>
                  {formatNumber(docStatus.uploaded || 0)}
                </div>
                <div style={{ fontSize: '11px', color: '#92400e', marginTop: '2px' }}>
                  {pctUploaded}% awaiting processing
                </div>
              </div>

              <div style={{ padding: '12px 16px', borderRadius: '8px', backgroundColor: '#fef2f2', border: '1px solid #fecaca' }}>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#991b1b', textTransform: 'uppercase' }}>Failed</div>
                <div style={{ fontSize: '20px', fontWeight: 700, color: '#7f1d1d', marginTop: '2px' }}>
                  {formatNumber(docStatus.failed || 0)}
                </div>
                <div style={{ fontSize: '11px', color: '#991b1b', marginTop: '2px' }}>
                  {pctFailed}% error rate
                </div>
              </div>
            </div>
          </div>

          {/* ── Invoice Financial Summary ────────────────────────────── */}
          <div style={{
            backgroundColor: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '12px',
            padding: '24px',
            marginBottom: '28px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 4px 0', color: '#0f172a' }}>
                  Branch Invoice &amp; Tax Summary
                </h3>
                <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
                  Financial aggregates for supplier copies and generated sales invoices.
                </p>
              </div>
            </div>

            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: '16px',
              marginBottom: '20px',
            }}>
              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Total Taxable Value</div>
                <div style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', marginTop: '4px' }}>
                  {formatCurrencyINR(invoices.total_taxable_amount || 0)}
                </div>
              </div>

              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Total GST Tax Amount</div>
                <div style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', marginTop: '4px' }}>
                  {formatCurrencyINR(invoices.total_tax_amount || 0)}
                </div>
              </div>

              <div style={{ padding: '16px', borderRadius: '8px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0' }}>
                <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Total Grand Amount</div>
                <div style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', marginTop: '4px' }}>
                  {formatCurrencyINR(invoices.total_grand_amount || 0)}
                </div>
              </div>
            </div>

            {/* Breakdown by Kind Table */}
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase' }}>
                    <th style={{ padding: '10px 12px' }}>Invoice Kind</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Count</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Taxable Value</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>GST Tax</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Grand Total</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '12px', fontWeight: 600, color: '#0f172a' }}>
                      Supplier Invoices (Uploaded Copies)
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right' }}>
                      {formatNumber(invoices.by_kind?.copy?.count || 0)}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right', fontFamily: 'monospace' }}>
                      {formatCurrencyINR(invoices.by_kind?.copy?.taxable || 0)}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right', fontFamily: 'monospace' }}>
                      {formatCurrencyINR(invoices.by_kind?.copy?.tax || 0)}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                      {formatCurrencyINR(invoices.by_kind?.copy?.grand_total || 0)}
                    </td>
                  </tr>

                  <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '12px', fontWeight: 600, color: '#0f172a' }}>
                      Outbound Sales Invoices (Generated)
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right' }}>
                      {formatNumber(invoices.by_kind?.generated?.count || 0)}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right', fontFamily: 'monospace' }}>
                      {formatCurrencyINR(invoices.by_kind?.generated?.taxable || 0)}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right', fontFamily: 'monospace' }}>
                      {formatCurrencyINR(invoices.by_kind?.generated?.tax || 0)}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                      {formatCurrencyINR(invoices.by_kind?.generated?.grand_total || 0)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Recent Failed Background Jobs Diagnostic ──────────────── */}
          <div
            id="recent-job-diagnostics"
            style={{
            backgroundColor: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '12px',
            padding: '24px',
            marginBottom: '28px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 4px 0', color: '#0f172a' }}>
                  Recent Background Job Diagnostics
                </h3>
                <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
                  Safe, sanitized failure reasons and one-click reprocessing for this branch.
                </p>
              </div>

              {recent_failed_jobs.length > 0 && (
                <button
                  onClick={() => handleExportCsv('failed-jobs')}
                  disabled={exportingReport !== null}
                  style={{
                    fontSize: '13px',
                    fontWeight: 600,
                    color: '#ef233c',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  Export Diagnostic Report &rarr;
                </button>
              )}
            </div>

            {recent_failed_jobs.length === 0 ? (
              <div style={{
                padding: '32px 0',
                textAlign: 'center',
                color: '#16a34a',
                fontSize: '14px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '8px',
              }}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                <span style={{ fontWeight: 600 }}>All background jobs completed successfully!</span>
                <span style={{ color: '#64748b', fontSize: '12px' }}>No failed jobs recorded for this branch.</span>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase' }}>
                      <th style={{ padding: '10px 12px' }}>Job ID</th>
                      <th style={{ padding: '10px 12px' }}>Document</th>
                      <th style={{ padding: '10px 12px' }}>Attempts</th>
                      <th style={{ padding: '10px 12px' }}>Error Diagnostic</th>
                      <th style={{ padding: '10px 12px' }}>Last Updated</th>
                      <th style={{ padding: '10px 12px', textAlign: 'right' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent_failed_jobs.map((job) => (
                      <tr key={job.job_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '12px', fontFamily: 'monospace', fontWeight: 600, color: '#0f172a' }}>
                          #{job.job_id}
                        </td>
                        <td style={{ padding: '12px', color: '#334155' }}>
                          {job.document_filename || (job.document_id ? `Document #${job.document_id}` : '—')}
                        </td>
                        <td style={{ padding: '12px', color: '#64748b' }}>
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: '10px',
                            fontSize: '11px',
                            fontWeight: 700,
                            backgroundColor: job.attempts >= job.max_attempts ? '#fee2e2' : '#fef3c7',
                            color: job.attempts >= job.max_attempts ? '#991b1b' : '#92400e',
                          }}>
                            {job.attempts} / {job.max_attempts}
                          </span>
                        </td>
                        <td style={{ padding: '12px', color: '#991b1b', maxWidth: '380px' }}>
                          <div style={{ fontWeight: 600, fontSize: '12px' }}>{job.error_code}</div>
                          <div style={{
                            fontSize: '11px',
                            color: '#64748b',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            maxWidth: '380px',
                          }} title={job.error_summary}>
                            {job.error_summary || 'Processing terminated unexpectedly.'}
                          </div>
                        </td>
                        <td style={{ padding: '12px', color: '#64748b', fontSize: '12px' }}>
                          {formatDateTime(job.updated_at)}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right' }}>
                          {job.can_reprocess && job.document_id ? (
                            <button
                              onClick={() => handleReprocess(job.document_id, job.job_id)}
                              disabled={reprocessingJobId === job.job_id}
                              style={{
                                padding: '6px 12px',
                                borderRadius: '6px',
                                border: '1px solid #cbd5e1',
                                backgroundColor: '#ffffff',
                                color: '#0f172a',
                                fontSize: '12px',
                                fontWeight: 600,
                                cursor: reprocessingJobId === job.job_id ? 'not-allowed' : 'pointer',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                              }}
                            >
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ animation: reprocessingJobId === job.job_id ? 'spin 1s linear infinite' : 'none' }}>
                                <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
                              </svg>
                              {reprocessingJobId === job.job_id ? 'Queuing...' : 'Reprocess'}
                            </button>
                          ) : (
                            <span style={{ fontSize: '11px', color: '#94a3b8' }}>N/A</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
