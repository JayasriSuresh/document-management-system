import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { api } from '../api';
import ConfirmModal from '../components/ConfirmModal';
import MfaModal from '../components/MfaModal';
import CompanyAIProvidersView from '../components/CompanyAIProvidersView';
import BranchAIConfigModal from '../components/BranchAIConfigModal';
import TemplateManagementView from '../components/TemplateManagementView';
import CompanyAIUsageReportView from '../components/CompanyAIUsageReportView';
import CompanyJobsView from '../components/CompanyJobsView';
import DocumentsPage from './DocumentsPage';

const INDIAN_STATES = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chandigarh',
  'Chhattisgarh', 'Dadra and Nagar Haveli and Daman and Diu', 'Delhi', 'Goa',
  'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jammu and Kashmir', 'Jharkhand',
  'Karnataka', 'Kerala', 'Ladakh', 'Lakshadweep', 'Madhya Pradesh',
  'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha',
  'Puducherry', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana',
  'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal', 'Andaman and Nicobar Islands'
];

const BRANCH_TYPES = [
  'Head Office', 'Regional Office', 'Branch', 'Warehouse', 'Sales Office',
  'Service Center', 'Distribution Center', 'Factory', 'Retail Outlet'
];

const GST_REGISTRATION_TYPES = [
  'Regular', 'Composition', 'Casual Taxable Person', 'Input Service Distributor (ISD)',
  'Non-Resident Taxable Person', 'Special Economic Zone (SEZ)', 'Government Entity'
];

export default function CompanyAdminPortalPage({ defaultTab = 'dashboard' }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Active view tab: 'dashboard' | 'profile' | 'branches' | 'users' | 'documents' | 'templates' | 'ai' | 'ai-usage' | 'jobs' | 'security' | 'audit'
  const validTabs = ['dashboard', 'profile', 'branches', 'users', 'documents', 'templates', 'ai', 'ai-usage', 'jobs', 'security', 'audit'];
  const tabFromUrl = searchParams.get('tab');
  const [activeTab, setActiveTab] = useState(
    validTabs.includes(tabFromUrl) ? tabFromUrl : (validTabs.includes(defaultTab) ? defaultTab : 'dashboard')
  );

  useEffect(() => {
    if (defaultTab && validTabs.includes(defaultTab) && defaultTab !== activeTab) {
      setActiveTab(defaultTab);
    }
  }, [defaultTab]);

  useEffect(() => {
    const t = searchParams.get('tab');
    if (t && validTabs.includes(t) && t !== activeTab) {
      setActiveTab(t);
    }
  }, [searchParams]);

  const tabToPath = {
    dashboard: '/company/dashboard',
    profile: '/company/profile',
    branches: '/company/branches',
    users: '/company/users',
    documents: '/company/documents',
    templates: '/company/templates',
    ai: '/company/ai',
    'ai-usage': '/company/ai-usage',
    jobs: '/company/jobs',
    security: '/company/security',
    audit: '/company/audit-logs',
  };

  const switchTab = (tab) => {
    setActiveTab(tab);
    if (tabToPath[tab]) {
      navigate(tabToPath[tab]);
    } else {
      setSearchParams({ tab });
    }
  };

  // ── Global Dialog & Notification State ─────────────────────────────────────
  const [confirmDialog, setConfirmDialog] = useState(null);
  const [toastMessage, setToastMessage] = useState(null);

  const showToast = (message, type = 'success') => {
    setToastMessage({ message, type });
    setTimeout(() => setToastMessage(null), 5000);
  };

  // ── Shared Company Profile & Branches for dropdown selectors ──────────────
  const [companyProfile, setCompanyProfile] = useState(null);
  const [branchesList, setBranchesList] = useState([]);
  const [failedJobsCount, setFailedJobsCount] = useState(0);

  const refreshCompanyMeta = useCallback(async () => {
    try {
      const [prof, bList, jobsRes] = await Promise.all([
        api.getCompanyProfile().catch(() => null),
        api.listCompanyBranches().catch(() => []),
        api.getDashboardJobs({ status: 'failed', page_size: 1 }).catch(() => null),
      ]);
      if (prof) setCompanyProfile(prof);
      if (Array.isArray(bList)) setBranchesList(bList);
      if (jobsRes?.total !== undefined) setFailedJobsCount(jobsRes.total);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    refreshCompanyMeta();
  }, [refreshCompanyMeta]);

  return (
    <div className="company-portal-view" style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box', padding: '1.5rem 2rem' }}>
      {/* Toast Notification Banner */}
      {toastMessage && (
            <div style={{
              position: 'fixed',
              top: '74px',
              right: '24px',
              zIndex: 9999,
              backgroundColor: toastMessage.type === 'error' ? '#fef2f2' : '#f0fdf4',
              color: toastMessage.type === 'error' ? '#991b1b' : '#166534',
              border: `1px solid ${toastMessage.type === 'error' ? '#f87171' : '#86efac'}`,
              padding: '12px 18px',
              borderRadius: '8px',
              boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
              fontSize: '14px',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}>
              {toastMessage.type === 'error' ? (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
              )}
              <span>{toastMessage.message}</span>
            </div>
          )}

          {activeTab === 'dashboard' && (
            <CompanyDashboardView
              switchTab={switchTab}
              showToast={showToast}
              branchesList={branchesList}
            />
          )}

          {activeTab === 'profile' && (
            <CompanyProfileView
              showToast={showToast}
              onProfileUpdated={refreshCompanyMeta}
            />
          )}

          {activeTab === 'branches' && (
            <BranchManagementView
              showToast={showToast}
              onBranchesChanged={refreshCompanyMeta}
            />
          )}

          {activeTab === 'users' && (
            <UserManagementView
              branchesList={branchesList}
              showToast={showToast}
              setConfirmDialog={setConfirmDialog}
            />
          )}

          {activeTab === 'documents' && (
            <DocumentsPage isArchiveView={true} />
          )}

          {activeTab === 'templates' && (
            <TemplateManagementView
              branchesList={branchesList}
              showToast={showToast}
            />
          )}

          {activeTab === 'ai' && (
            <CompanyAIProvidersView
              branchesList={branchesList}
              showToast={showToast}
            />
          )}

          {activeTab === 'ai-usage' && (
            <CompanyAIUsageReportView
              branchesList={branchesList}
              showToast={showToast}
            />
          )}

          {activeTab === 'jobs' && (
            <CompanyJobsView
              branchesList={branchesList}
              showToast={showToast}
            />
          )}

          {activeTab === 'security' && (
            <CompanySecurityView
              showToast={showToast}
            />
          )}

          {activeTab === 'audit' && (
            <CompanyAuditLogsView
              branchesList={branchesList}
              showToast={showToast}
            />
          )}

      {/* ── Global Confirm Dialog ────────────────────────────────────────── */}
      {confirmDialog && (
        <ConfirmModal
          isOpen={true}
          title={confirmDialog.title}
          message={confirmDialog.message}
          details={confirmDialog.details}
          confirmText={confirmDialog.confirmText || 'Confirm'}
          cancelText={confirmDialog.cancelText || 'Cancel'}
          variant={confirmDialog.variant || 'primary'}
          loading={confirmDialog.loading}
          onConfirm={confirmDialog.onConfirm}
          onCancel={() => setConfirmDialog(null)}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 1: COMPANY DASHBOARD VIEW (Module 14 Enhanced Operational Intelligence)
// ─────────────────────────────────────────────────────────────────────────────
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

function CompanyDashboardView({ switchTab, showToast, branchesList = [] }) {
  // Legacy Dashboard Data (quotas, security, recent activity)
  const [data, setData] = useState(null);
  // Module 14 Operational Metrics (document throughput, invoices, AI usage, branch distribution, jobs)
  const [operationalData, setOperationalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Date and Branch Filters
  const [datePreset, setDatePreset] = useState('last30');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [selectedBranch, setSelectedBranch] = useState('');
  const [exportingReport, setExportingReport] = useState(null);

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

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { from, to } = calculateDateRange();
      const [legacyRes, opRes] = await Promise.all([
        api.getCompanyDashboard().catch(() => null),
        api.getDashboardCompany({
          date_from: from,
          date_to: to,
          branch_id: selectedBranch || null,
        }),
      ]);
      if (legacyRes) setData(legacyRes);
      setOperationalData(opRes);
    } catch (err) {
      setError(err.message || 'Failed to load company dashboard.');
    } finally {
      setLoading(false);
    }
  }, [calculateDateRange, selectedBranch]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const handleExportCsv = async (reportType) => {
    setExportingReport(reportType);
    try {
      const { from, to } = calculateDateRange();
      await api.downloadDashboardCsv(reportType, {
        date_from: from,
        date_to: to,
        branch_id: selectedBranch || null,
      });
      showToast?.(`Company ${reportType} report exported successfully.`, 'success');
    } catch (err) {
      showToast?.(err.message || `Failed to export ${reportType} CSV.`, 'error');
    } finally {
      setExportingReport(null);
    }
  };

  if (loading && !data && !operationalData) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}>
        <div style={{ textAlign: 'center', color: '#64748b' }}>
          <div className="spinner" style={{ margin: '0 auto 12px' }} />
          Loading company metrics...
        </div>
      </div>
    );
  }

  if (error && !data && !operationalData) {
    return (
      <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '16px', borderRadius: '8px', color: '#991b1b', marginBottom: '24px' }}>
        <strong>Error:</strong> {error}
        <button onClick={loadDashboard} style={{ marginLeft: '12px', textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer', color: '#991b1b', fontWeight: 600 }}>
          Retry
        </button>
      </div>
    );
  }

  const { company, stats, quotas, security, recent_activity } = data || {};
  const {
    documents = {},
    invoices = {},
    branch_distribution = [],
    jobs = {},
  } = operationalData || {};

  const docStatus = documents.by_status || {};
  const docTotal = documents.total_count || 0;
  const pctCompleted = docTotal > 0 ? Math.round(((docStatus.completed || 0) / docTotal) * 100) : 0;
  const pctProcessing = docTotal > 0 ? Math.round(((docStatus.processing || 0) / docTotal) * 100) : 0;
  const pctUploaded = docTotal > 0 ? Math.round(((docStatus.uploaded || 0) / docTotal) * 100) : 0;
  const pctFailed = docTotal > 0 ? Math.round(((docStatus.failed || 0) / docTotal) * 100) : 0;

  return (
    <div>
      {/* ── Section Header ────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 3px 0', color: '#0f172a', letterSpacing: '-0.01em' }}>
            Company Operational Dashboard
          </h2>
          <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
            Operational health, branch distribution, OCR throughput, and financial visibility for <strong>{company?.display_name || company?.name}</strong>.
          </p>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={() => switchTab('branches')}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: '#ef233c',
              color: '#ffffff',
              padding: '9px 18px',
              borderRadius: '8px',
              border: 'none',
              fontWeight: 600,
              fontSize: '13px',
              cursor: 'pointer',
              boxShadow: '0 2px 8px rgba(239, 35, 60, 0.25)',
              transition: 'background-color 0.2s',
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add Branch
          </button>

          <button
            onClick={() => switchTab('users')}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: '#ffffff',
              color: '#475569',
              padding: '9px 16px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontWeight: 600,
              fontSize: '13px',
              cursor: 'pointer',
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><line x1="20" y1="8" x2="20" y2="14" /><line x1="23" y1="11" x2="17" y2="11" />
            </svg>
            Invite User
          </button>
        </div>
      </div>

      {/* ── Direct CSV Exports Toolbar ────────────────────────────────── */}
      <div style={{
        backgroundColor: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: '12px',
        padding: '12px 18px',
        marginBottom: '20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Export Reports (CSV):
          </span>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            onClick={() => handleExportCsv('documents')}
            disabled={exportingReport !== null}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#ffffff',
              color: '#334155',
              padding: '7px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '12px',
              fontWeight: 600,
              cursor: exportingReport ? 'not-allowed' : 'pointer',
            }}
            title="Export all documents across branches matching filters"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {exportingReport === 'documents' ? 'Exporting...' : 'Documents CSV'}
          </button>

          <button
            onClick={() => handleExportCsv('invoices')}
            disabled={exportingReport !== null}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#ffffff',
              color: '#334155',
              padding: '7px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '12px',
              fontWeight: 600,
              cursor: exportingReport ? 'not-allowed' : 'pointer',
            }}
            title="Export all invoices across branches matching filters"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {exportingReport === 'invoices' ? 'Exporting...' : 'Invoices CSV'}
          </button>

          <button
            onClick={() => handleExportCsv('ai-usage')}
            disabled={exportingReport !== null}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#ffffff',
              color: '#334155',
              padding: '7px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '12px',
              fontWeight: 600,
              cursor: exportingReport ? 'not-allowed' : 'pointer',
            }}
            title="Export AI token and cost breakdown matching filters"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {exportingReport === 'ai-usage' ? 'Exporting...' : 'AI Usage CSV'}
          </button>

          <button
            onClick={() => handleExportCsv('failed-jobs')}
            disabled={exportingReport !== null}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#ffffff',
              color: '#991b1b',
              padding: '7px 12px',
              borderRadius: '6px',
              border: '1px solid #fecaca',
              fontSize: '12px',
              fontWeight: 600,
              cursor: exportingReport ? 'not-allowed' : 'pointer',
            }}
            title="Export failed processing jobs diagnostics matching filters"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {exportingReport === 'failed-jobs' ? 'Exporting...' : 'Failed Jobs CSV'}
          </button>
        </div>
      </div>

      {/* ── Filters Bar (Time Window & Branch) ────────────────────────── */}
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

        {/* Branch Filter & Refresh */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {branchesList.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <label style={{ fontSize: '13px', fontWeight: 600, color: '#475569' }}>
                Branch:
              </label>
              <select
                value={selectedBranch}
                onChange={(e) => setSelectedBranch(e.target.value)}
                style={{
                  padding: '6px 10px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '13px',
                  color: '#0f172a',
                  backgroundColor: '#ffffff',
                  cursor: 'pointer',
                }}
              >
                <option value="">All Branches</option>
                {branchesList.map(b => (
                  <option key={b.id} value={b.id}>{b.name} ({b.code})</option>
                ))}
              </select>
            </div>
          )}

          <button
            onClick={loadDashboard}
            disabled={loading}
            style={{
              padding: '6px 12px',
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
      </div>

      {/* ── Failed Background Jobs Alert Banner ──────────────────────── */}
      {jobs.failed > 0 && (
        <div style={{
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
        }}>
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
                {jobs.failed} Background Processing {jobs.failed === 1 ? 'Job' : 'Jobs'} Require Attention
              </div>
              <div style={{ fontSize: '12px', color: '#be123c', marginTop: '2px' }}>
                Background OCR/indexing jobs encountered errors. Review diagnostics and reprocess from the Background Jobs tab.
              </div>
            </div>
          </div>

          <button
            onClick={() => switchTab('jobs')}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              backgroundColor: '#e11d48',
              border: 'none',
              color: '#ffffff',
              fontSize: '13px',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: '0 1px 3px rgba(225, 29, 72, 0.3)',
            }}
          >
            Review Failed Jobs &rarr;
          </button>
        </div>
      )}

      {/* ── Key Metric Cards ─────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '28px' }}>
        {/* Card 1: Branches */}
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Provisioned Branches
            </span>
            <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#fee2e2', color: '#dc2626', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="6" y1="3" x2="6" y2="15" /><circle cx="18" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><path d="M18 9a9 9 0 0 1-9 9" /></svg>
            </div>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a' }}>
            {stats?.active_branches ?? quotas?.active_branches ?? 0} <span style={{ fontSize: '14px', fontWeight: 500, color: '#64748b' }}>active / {stats?.total_branches ?? quotas?.total_branches ?? 0} total</span>
          </div>
          <div style={{ fontSize: '12px', color: '#16a34a', marginTop: '4px', fontWeight: 500 }}>
            Quota: {quotas?.branches_used ?? quotas?.total_branches ?? 0} / {quotas?.max_branches ?? 0} ({quotas?.branches_remaining ?? Math.max(0, (quotas?.max_branches || 0) - (quotas?.total_branches || 0))} available)
          </div>
        </div>

        {/* Card 2: Users */}
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Company Personnel
            </span>
            <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#eff6ff', color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            </div>
          </div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a' }}>
            {stats?.active_users ?? quotas?.active_users ?? 0} <span style={{ fontSize: '14px', fontWeight: 500, color: '#64748b' }}>active / {stats?.total_users ?? quotas?.total_users ?? 0} total</span>
          </div>
          <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
            Quota: {quotas?.users_used ?? quotas?.total_users ?? 0} / {quotas?.max_users ?? 0} users assigned
          </div>
        </div>

        {/* Card 3: Storage */}
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Storage Volume
            </span>
            <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#fff7ed', color: '#ea580c', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
            </div>
          </div>
          <div style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>
            {documents.storage_used_mb !== undefined ? documents.storage_used_mb : ((quotas?.storage_used_bytes || 0) / (1024 * 1024)).toFixed(1)} MB
            <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}> / {((quotas?.storage_limit_bytes || 0) / (1024 * 1024 * 1024)).toFixed(0)} GB</span>
          </div>
          <div style={{ marginTop: '10px', height: '5px', width: '100%', backgroundColor: '#f1f5f9', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${Math.min(quotas?.storage_usage_pct || 0, 100)}%`, backgroundColor: quotas?.storage_usage_pct > 80 ? '#ef233c' : '#10b981' }} />
          </div>
        </div>

        {/* Card 4: Monthly AI Spend (Dual Currency: INR + USD) */}
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Monthly AI Spend
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
          <div style={{ fontSize: '22px', fontWeight: 700, color: '#0f172a', display: 'flex', alignItems: 'baseline', flexWrap: 'wrap', gap: '4px' }}>
            <span>₹{Number(quotas?.ai_spent_inr ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}>
              / ₹{Number(quotas?.monthly_ai_budget_inr ?? 4250).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <div style={{ fontSize: '12px', fontWeight: 600, color: '#475569', marginTop: '2px' }}>
            ${(quotas?.ai_spent_usd ?? ((quotas?.ai_budget_used_cents || 0) / 100)).toFixed(2)}
            <span style={{ fontWeight: 400, color: '#64748b' }}> / ${(quotas?.monthly_ai_budget_usd ?? ((quotas?.monthly_ai_budget_cents || 5000) / 100)).toFixed(2)} USD</span>
          </div>
          <div style={{ marginTop: '8px', height: '5px', width: '100%', backgroundColor: '#f1f5f9', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${Math.min(quotas?.ai_budget_usage_pct || 0, 100)}%`, backgroundColor: quotas?.ai_budget_usage_pct > 80 ? '#f59e0b' : '#10b981' }} />
          </div>
          <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: '#64748b' }}>
            <span>Rate: 1 USD = ₹{(quotas?.exchange_rate || 85).toFixed(2)}</span>
            <span style={{ color: '#059669', fontWeight: 500 }}>{quotas?.ai_budget_usage_pct || 0}% used</span>
          </div>
        </div>
      </div>

      {/* ── Document OCR Status & Progress ───────────────────────────── */}
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
              Status of all documents across active branches for the selected window.
            </p>
          </div>

          <button
            onClick={() => switchTab('documents')}
            style={{
              fontSize: '13px',
              fontWeight: 600,
              color: '#ef233c',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            Open Document Archive &rarr;
          </button>
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

      {/* ── Invoice Financial Summary ────────────────────────────────── */}
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
              Invoice &amp; Billing Aggregates
            </h3>
            <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
              Consolidated financial totals across supplier copies and generated sales invoices.
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
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
            <thead>
              <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                <th style={{ padding: '8px 10px' }}>Invoice Kind</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Count</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Taxable Value</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>GST Tax</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Grand Total</th>
              </tr>
            </thead>
            <tbody>
              <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ padding: '7px 10px', fontWeight: 600, color: '#0f172a' }}>
                  Supplier Invoices (Uploaded Copies)
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                  {formatNumber(invoices.by_kind?.copy?.count || 0)}
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'monospace' }}>
                  {formatCurrencyINR(invoices.by_kind?.copy?.taxable || 0)}
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'monospace' }}>
                  {formatCurrencyINR(invoices.by_kind?.copy?.tax || 0)}
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                  {formatCurrencyINR(invoices.by_kind?.copy?.grand_total || 0)}
                </td>
              </tr>

              <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ padding: '7px 10px', fontWeight: 600, color: '#0f172a' }}>
                  Outbound Sales Invoices (Generated)
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                  {formatNumber(invoices.by_kind?.generated?.count || 0)}
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'monospace' }}>
                  {formatCurrencyINR(invoices.by_kind?.generated?.taxable || 0)}
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'right', fontFamily: 'monospace' }}>
                  {formatCurrencyINR(invoices.by_kind?.generated?.tax || 0)}
                </td>
                <td style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                  {formatCurrencyINR(invoices.by_kind?.generated?.grand_total || 0)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Branch Distribution and Activity Table ───────────────────── */}
      {branch_distribution.length > 0 && (
        <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '24px', marginBottom: '28px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div>
              <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 4px 0', color: '#0f172a' }}>
                Branch Distribution &amp; Operational Throughput
              </h3>
              <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
                Document volume, storage footprint, and processing health per branch.
              </p>
            </div>
            <button
              onClick={() => switchTab('branches')}
              style={{ fontSize: '13px', fontWeight: 600, color: '#ef233c', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              Manage Branches &rarr;
            </button>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                  <th style={{ padding: '8px 10px' }}>Branch Name</th>
                  <th style={{ padding: '8px 10px' }}>Code</th>
                  <th style={{ padding: '8px 10px' }}>Status</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right' }}>Documents</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right' }}>Storage Volume</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right' }}>Failed Jobs</th>
                </tr>
              </thead>
              <tbody>
                {branch_distribution.map((b) => (
                  <tr key={b.branch_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '7px 10px', fontWeight: 600, color: '#0f172a' }}>
                      {b.branch_name}
                    </td>
                    <td style={{ padding: '7px 10px', color: '#64748b', fontFamily: 'monospace' }}>
                      {b.branch_code}
                    </td>
                    <td style={{ padding: '7px 10px' }}>
                      <span style={{
                        padding: '1px 6px',
                        borderRadius: '4px',
                        fontSize: '10.5px',
                        fontWeight: 700,
                        backgroundColor: b.status === 'active' ? '#dcfce7' : '#fee2e2',
                        color: b.status === 'active' ? '#166534' : '#991b1b',
                      }}>
                        {b.status || 'active'}
                      </span>
                    </td>
                    <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                      {formatNumber(b.document_count)}
                    </td>
                    <td style={{ padding: '7px 10px', textAlign: 'right', color: '#475569' }}>
                      {b.storage_mb} MB
                    </td>
                    <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                      {b.failed_count > 0 ? (
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '10px',
                          fontSize: '11px',
                          fontWeight: 700,
                          backgroundColor: '#fee2e2',
                          color: '#dc2626',
                        }}>
                          {b.failed_count}
                        </span>
                      ) : (
                        <span style={{ color: '#16a34a', fontWeight: 600 }}>0</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Security Status Box */}
      <div style={{
        backgroundColor: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: '12px',
        padding: '20px',
        marginBottom: '28px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '16px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            width: '42px',
            height: '42px',
            borderRadius: '8px',
            backgroundColor: security?.effective_mfa_required ? '#ecfdf5' : '#fee2e2',
            border: `1px solid ${security?.effective_mfa_required ? '#a7f3d0' : '#fecaca'}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: security?.effective_mfa_required ? '#059669' : '#dc2626',
          }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /></svg>
          </div>
          <div>
            <div style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a' }}>
              Multi-Factor Authentication (MFA) Policy
            </div>
            <div style={{ fontSize: '13px', color: '#64748b', marginTop: '2px' }}>
              {security?.effective_mfa_required ? (
                <span style={{ color: '#059669', fontWeight: 500 }}>
                  Active &middot; MFA is strictly enforced for all users across this company.
                  {security?.platform_mfa_enforced && ' (Overridden by Platform Master Policy)'}
                </span>
              ) : (
                <span>Optional &middot; Individual staff and branch administrators can self-enroll authenticator apps.</span>
              )}
            </div>
          </div>
        </div>

        <button
          onClick={() => switchTab('security')}
          style={{
            padding: '9px 16px',
            borderRadius: '8px',
            border: '1px solid #cbd5e1',
            backgroundColor: '#ffffff',
            color: '#334155',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Security Policies &rarr;
        </button>
      </div>

      {/* Recent Activity Table */}
      <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px' }}>
          <h3 style={{ fontSize: '17px', fontWeight: 700, margin: 0, color: '#0f172a' }}>
            Recent Administrative Activity
          </h3>
          <button
            onClick={() => switchTab('audit')}
            style={{ fontSize: '13px', fontWeight: 600, color: '#ef233c', background: 'none', border: 'none', cursor: 'pointer' }}
          >
            View Complete Audit Logs &rarr;
          </button>
        </div>

        {(!recent_activity || recent_activity.length === 0) ? (
          <div style={{ padding: '24px 0', textAlign: 'center', color: '#94a3b8', fontSize: '14px' }}>
            No recent activity logged.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                  <th style={{ padding: '8px 10px' }}>Timestamp</th>
                  <th style={{ padding: '8px 10px' }}>Action</th>
                  <th style={{ padding: '8px 10px' }}>Actor</th>
                  <th style={{ padding: '8px 10px' }}>Target Object</th>
                  <th style={{ padding: '8px 10px' }}>IP Address</th>
                </tr>
              </thead>
              <tbody>
                {recent_activity.map((act) => (
                  <tr key={act.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '7px 10px', color: '#64748b' }}>
                      {act.occurred_at ? new Date(act.occurred_at).toLocaleString() : '—'}
                    </td>
                    <td style={{ padding: '7px 10px' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        fontSize: '11px',
                        fontWeight: 700,
                        backgroundColor: '#f1f5f9',
                        color: '#334155',
                      }}>
                        {act.action}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', color: '#1e293b' }}>
                      {act.actor_type} #{act.actor_id}
                    </td>
                    <td style={{ padding: '10px 12px', color: '#64748b' }}>
                      {act.object_type || '—'} {act.object_id ? `(${act.object_id})` : ''}
                    </td>
                    <td style={{ padding: '10px 12px', color: '#94a3b8', fontFamily: 'monospace' }}>
                      {act.ip || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 2: COMPANY PROFILE VIEW
// ─────────────────────────────────────────────────────────────────────────────
function CompanyProfileView({ showToast, onProfileUpdated }) {
  const { user, refreshUser } = useAuth();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [deletingLogo, setDeletingLogo] = useState(false);
  const [formError, setFormError] = useState('');
  const [logoError, setLogoError] = useState('');
  const fileInputRef = useRef(null);

  const [form, setForm] = useState({
    name: '',
    display_name: '',
    gstin: '',
    pan: '',
    contact_person: '',
    contact_email: '',
    contact_phone: '',
    website: '',
    registered_address: '',
  });

  const loadProfile = async () => {
    setLoading(true);
    setFormError('');
    setLogoError('');
    try {
      const res = await api.getCompanyProfile();
      setProfile(res);
      setForm({
        name: res.name || res.legal_company_name || '',
        display_name: res.display_name || res.trade_name || '',
        gstin: res.gstin || '',
        pan: res.pan || res.pan_number || '',
        contact_person: res.contact_person || res.auth_contact_name || res.contact_name || '',
        contact_email: res.contact_email || res.auth_contact_email || '',
        contact_phone: res.contact_phone || res.auth_contact_mobile || '',
        website: res.website || res.company_website || '',
        registered_address: res.address || res.registered_address || '',
      });
    } catch (err) {
      setFormError(err.message || 'Failed to load company profile.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, []);

  const handleLogoUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setLogoError('');
    const allowed = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/svg+xml'];
    if (!allowed.includes(file.type)) {
      setLogoError('Unsupported image format. Please select a PNG, JPG, WEBP, or SVG file.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    if (file.size > 2 * 1024 * 1024) {
      setLogoError('Logo image size exceeds 2 MB limit.');
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setUploadingLogo(true);
    try {
      const res = await api.uploadCompanyLogo(file);
      setProfile((prev) => ({ ...prev, logo_url: res.logo_url }));
      await refreshUser();
      onProfileUpdated?.();
      showToast('Company logo updated successfully.');
    } catch (err) {
      setLogoError(err.message || 'Failed to upload logo.');
    } finally {
      setUploadingLogo(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleRemoveLogo = async () => {
    if (!window.confirm('Are you sure you want to remove the company logo? The sidebar will fall back to company initials.')) {
      return;
    }
    setLogoError('');
    setDeletingLogo(true);
    try {
      await api.deleteCompanyLogo();
      setProfile((prev) => ({ ...prev, logo_url: null }));
      await refreshUser();
      onProfileUpdated?.();
      showToast('Company logo removed.');
    } catch (err) {
      setLogoError(err.message || 'Failed to remove company logo.');
    } finally {
      setDeletingLogo(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setFormError('');

    if (!form.name.trim()) {
      setFormError('Legal Company Name is required.');
      return;
    }

    if (form.gstin.trim()) {
      const cleanGst = form.gstin.trim().toUpperCase();
      if (cleanGst.length !== 15) {
        setFormError('Indian GSTIN must be exactly 15 characters (e.g. 33AABCA1234F1Z5).');
        return;
      }
    }
    if (form.pan.trim()) {
      const cleanPan = form.pan.trim().toUpperCase();
      if (cleanPan.length !== 10) {
        setFormError('Indian PAN must be exactly 10 characters (e.g. AABCA1234F).');
        return;
      }
    }

    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        display_name: form.display_name.trim() || null,
        gstin: form.gstin.trim().toUpperCase() || null,
        pan: form.pan.trim().toUpperCase() || null,
        contact_person: form.contact_person.trim() || null,
        contact_email: form.contact_email.trim().toLowerCase() || null,
        contact_phone: form.contact_phone.trim() || null,
        website: form.website.trim() || null,
        address: form.registered_address.trim() || null,
      };
      const updated = await api.updateCompanyProfile(payload);
      setProfile(updated);
      await refreshUser();
      showToast('Company profile updated successfully.');
      onProfileUpdated?.();
    } catch (err) {
      setFormError(err.message || 'Failed to update company profile.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}>
        <div style={{ textAlign: 'center', color: '#64748b' }}>
          <div className="spinner" style={{ margin: '0 auto 12px' }} />
          Loading company profile...
        </div>
      </div>
    );
  }

  // Fallback initials for preview
  const previewInitials = (form.display_name || form.name || 'CO')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase() || 'CO';

  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div>
        <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 4px 0', color: '#0f172a' }}>
          Company Profile &amp; Settings
        </h2>
        <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
          Manage your organization branding, official logo, company name, and registration records.
        </p>
      </div>

      {formError && (
        <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '10px 14px', borderRadius: '6px', color: '#991b1b', fontSize: '13px' }}>
          <strong>Error:</strong> {formError}
        </div>
      )}

      {/* ── Visual Branding & Logo Card ──────────────────────── */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '20px 24px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
        <div style={{ borderBottom: '1px solid #f1f5f9', paddingBottom: '12px', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 700, margin: '0 0 4px', color: '#1e293b' }}>
            Company Logo &amp; Navigation Sidebar Brand
          </h3>
          <p style={{ margin: 0, color: '#64748b', fontSize: '12.5px' }}>
            Upload your company logo to display in the main navigation sidebar, issued invoices, and portal headers.
          </p>
        </div>

        {logoError && (
          <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '10px 14px', borderRadius: '6px', color: '#991b1b', marginBottom: '16px', fontSize: '13px' }}>
            <strong>Logo Error:</strong> {logoError}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) minmax(300px, 1fr)', gap: '24px', alignItems: 'center' }}>
          {/* Logo Uploader */}
          <div style={{ display: 'flex', gap: '18px', alignItems: 'center' }}>
            {/* Logo Preview Box */}
            <div style={{
              width: '84px',
              height: '84px',
              borderRadius: '12px',
              border: profile?.logo_url ? '2px solid #e2e8f0' : '2px dashed #cbd5e1',
              backgroundColor: '#f8fafc',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
              flexShrink: 0,
              boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
            }}>
              {profile?.logo_url ? (
                <img
                  src={profile.logo_url}
                  alt={form.display_name || form.name || 'Company Logo'}
                  style={{ width: '100%', height: '100%', objectFit: 'contain', padding: '4px' }}
                />
              ) : (
                <div style={{ textAlign: 'center', color: '#94a3b8' }}>
                  <div style={{ fontSize: '22px', fontWeight: 800, color: '#64748b' }}>{previewInitials}</div>
                  <div style={{ fontSize: '10px', marginTop: '2px' }}>No Logo</div>
                </div>
              )}
            </div>

            {/* Upload Controls */}
            <div>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleLogoUpload}
                accept="image/png,image/jpeg,image/webp,image/svg+xml"
                style={{ display: 'none' }}
              />
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '6px' }}>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadingLogo || deletingLogo}
                  style={{
                    padding: '8px 16px',
                    borderRadius: '7px',
                    border: '1px solid #0284c7',
                    backgroundColor: '#0284c7',
                    color: '#ffffff',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: uploadingLogo || deletingLogo ? 'not-allowed' : 'pointer',
                    opacity: uploadingLogo ? 0.7 : 1,
                  }}
                >
                  {uploadingLogo ? 'Uploading...' : (profile?.logo_url ? 'Change Logo' : 'Upload Logo')}
                </button>

                {profile?.logo_url && (
                  <button
                    type="button"
                    onClick={handleRemoveLogo}
                    disabled={uploadingLogo || deletingLogo}
                    style={{
                      padding: '8px 14px',
                      borderRadius: '7px',
                      border: '1px solid #fecaca',
                      backgroundColor: '#fff',
                      color: '#dc2626',
                      fontSize: '13px',
                      fontWeight: 600,
                      cursor: uploadingLogo || deletingLogo ? 'not-allowed' : 'pointer',
                      opacity: deletingLogo ? 0.7 : 1,
                    }}
                  >
                    {deletingLogo ? 'Removing...' : 'Remove'}
                  </button>
                )}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b', lineHeight: 1.4 }}>
                Supports PNG, JPG, WEBP, or SVG. Max 2 MB.<br />
                Displayed at the top of the sidebar.
              </div>
            </div>
          </div>

          {/* Live Preview Box */}
          <div style={{
            backgroundColor: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '10px',
            padding: '14px 16px',
          }}>
            <div style={{ fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#10b981' }}></span>
              Live Sidebar Display Preview
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '10px 14px',
              backgroundColor: '#ffffff',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
              {profile?.logo_url ? (
                <div style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: '8px',
                  overflow: 'hidden',
                  border: '1px solid #e2e8f0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  backgroundColor: '#ffffff',
                  flexShrink: 0,
                }}>
                  <img src={profile.logo_url} alt="Logo" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                </div>
              ) : (
                <div style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: '8px',
                  backgroundColor: '#f1f5f9',
                  border: '1px solid #cbd5e1',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: '14px',
                  color: '#475569',
                  flexShrink: 0,
                }}>
                  {previewInitials}
                </div>
              )}
              <div style={{ overflow: 'hidden', minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: '14px', color: '#0f172a', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                  {form.display_name || form.name || 'Your Company'}
                </div>
                <div style={{ fontSize: '12px', color: '#64748b', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                  {user?.tenant_name || user?.branch_name || 'Headquarters — Active'}
                </div>
              </div>
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '6px' }}>
              Changes reflect immediately on all application pages after saving.
            </div>
          </div>
        </div>
      </div>

      <form onSubmit={handleSave} style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '20px 24px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
        {/* Section 1: Entity Identity */}
        <div style={{ borderBottom: '1px solid #f1f5f9', paddingBottom: '18px', marginBottom: '20px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 700, margin: '0 0 14px', color: '#1e293b' }}>
            Enterprise Identification &amp; Names
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                Legal Company Name <span style={{ color: '#ef233c' }}>*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Acme Corporation Pvt Ltd"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
              />
              <span style={{ fontSize: '11px', color: '#94a3b8' }}>Registered legal entity name used on official documents.</span>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                Display / Brand Name
              </label>
              <input
                type="text"
                placeholder="e.g. Acme Retail"
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
              />
              <span style={{ fontSize: '11px', color: '#94a3b8' }}>Brand or trade name shown in the sidebar and portal header.</span>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#64748b', marginBottom: '6px' }}>
                Company Tenant Code
              </label>
              <input
                type="text"
                value={profile?.code || ''}
                disabled
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #e2e8f0', backgroundColor: '#f8fafc', color: '#64748b', fontSize: '14px', fontWeight: 600, boxSizing: 'border-box' }}
              />
              <span style={{ fontSize: '11px', color: '#94a3b8' }}>System-maintained tenant code (immutable).</span>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                Website URL
              </label>
              <input
                type="text"
                placeholder="https://example.com"
                value={form.website}
                onChange={(e) => setForm({ ...form, website: e.target.value })}
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
              />
            </div>
          </div>
        </div>

        {/* Section 2: Tax & Legal Identifiers */}
        <div style={{ borderBottom: '1px solid #f1f5f9', paddingBottom: '20px', marginBottom: '24px' }}>
          <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 16px', color: '#1e293b' }}>
            Tax &amp; Regulatory Identifiers
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                GSTIN (Goods and Services Tax ID)
              </label>
              <input
                type="text"
                maxLength={15}
                placeholder="33AABCA1234F1Z5"
                value={form.gstin}
                onChange={(e) => setForm({ ...form, gstin: e.target.value.toUpperCase() })}
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', textTransform: 'uppercase', fontFamily: 'monospace', boxSizing: 'border-box' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                Company PAN
              </label>
              <input
                type="text"
                maxLength={10}
                placeholder="AABCA1234F"
                value={form.pan}
                onChange={(e) => setForm({ ...form, pan: e.target.value.toUpperCase() })}
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', textTransform: 'uppercase', fontFamily: 'monospace', boxSizing: 'border-box' }}
              />
            </div>
          </div>
        </div>

        {/* Section 3: Official Contact Person & Address */}
        <div style={{ marginBottom: '28px' }}>
          <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 16px', color: '#1e293b' }}>
            Primary Contact &amp; Registered Office
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '18px', marginBottom: '18px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                Contact Person
              </label>
              <input
                type="text"
                placeholder="Full name"
                value={form.contact_person}
                onChange={(e) => setForm({ ...form, contact_person: e.target.value })}
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                Contact Email
              </label>
              <input
                type="email"
                placeholder="contact@company.com"
                value={form.contact_email}
                onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                Contact Phone
              </label>
              <input
                type="text"
                placeholder="+91 9876543210"
                value={form.contact_phone}
                onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
                style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
              Registered Office Address
            </label>
            <textarea
              rows={3}
              placeholder="Door No, Building, Street, City, State, PIN"
              value={form.registered_address}
              onChange={(e) => setForm({ ...form, registered_address: e.target.value })}
              style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', resize: 'vertical', boxSizing: 'border-box' }}
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
          <button
            type="button"
            onClick={loadProfile}
            disabled={saving}
            style={{ padding: '9px 18px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontSize: '14px', fontWeight: 600, cursor: 'pointer' }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            style={{
              padding: '10px 24px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: '#ef233c',
              color: '#ffffff',
              fontSize: '14px',
              fontWeight: 600,
              cursor: saving ? 'not-allowed' : 'pointer',
              boxShadow: '0 2px 8px rgba(239, 35, 60, 0.25)',
              opacity: saving ? 0.7 : 1,
            }}
          >
            {saving ? 'Saving...' : 'Save Profile Changes'}
          </button>
        </div>
      </form>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 3: BRANCH MANAGEMENT VIEW
// ─────────────────────────────────────────────────────────────────────────────
function BranchManagementView({ showToast, onBranchesChanged }) {
  const [branches, setBranches] = useState([]);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  // Add Branch Modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState({
    branch_name: '',
    branch_code: '',
    branch_type: 'Branch',
    branch_email: '',
    branch_contact_number: '',
    address_line1: '',
    address_line2: '',
    city: '',
    district: '',
    state: 'Tamil Nadu',
    pincode: '',
    country: 'India',
    gst_registered: false,
    gstin: '',
    gst_type: 'Regular',
    admin_name: '',
    admin_email: '',
    admin_mobile: '',
  });
  const [addError, setAddError] = useState('');
  const [adding, setAdding] = useState(false);
  const [createdBranchData, setCreatedBranchData] = useState(null);

  // Edit Branch Modal
  const [editingBranch, setEditingBranch] = useState(null);
  const [editForm, setEditForm] = useState({
    name: '',
    address: '',
    contact_person: '',
    contact_email: '',
    contact_phone: '',
  });
  const [editing, setEditing] = useState(false);
  const [editError, setEditError] = useState('');

  // View Details Modal
  const [viewBranch, setViewBranch] = useState(null);

  // AI Configuration Modal
  const [aiConfigBranch, setAiConfigBranch] = useState(null);

  // Action loading state
  const [actionLoadingId, setActionLoadingId] = useState(null);

  const loadData = async () => {
    setLoading(true);
    setError('');
    try {
      const [profRes, bRes] = await Promise.all([
        api.getCompanyProfile().catch(() => null),
        api.listCompanyBranches(),
      ]);
      if (profRes) setProfile(profRes);
      setBranches(bRes || []);
    } catch (err) {
      setError(err.message || 'Failed to load branches.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredBranches = useMemo(() => {
    return branches.filter((b) => {
      if (statusFilter !== 'all' && b.status !== statusFilter) return false;
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        (b.name && b.name.toLowerCase().includes(q)) ||
        (b.code && b.code.toLowerCase().includes(q)) ||
        (b.city && b.city.toLowerCase().includes(q)) ||
        (b.gstin && b.gstin.toLowerCase().includes(q)) ||
        (b.contact_person && b.contact_person.toLowerCase().includes(q)) ||
        (b.primary_admin?.name && b.primary_admin.name.toLowerCase().includes(q)) ||
        (b.branch_email && b.branch_email.toLowerCase().includes(q))
      );
    });
  }, [branches, statusFilter, searchQuery]);

  const handleAddBranch = async (e) => {
    e.preventDefault();
    setAddError('');

    if (!addForm.branch_name.trim() || !addForm.branch_code.trim()) {
      setAddError('Branch Name and unique Branch Code are required.');
      return;
    }
    if (!addForm.branch_contact_number.trim() || !addForm.address_line1.trim() || !addForm.city.trim() || !addForm.pincode.trim()) {
      setAddError('Contact number, Address line 1, City, and 6-digit PIN code are required.');
      return;
    }
    if (addForm.gst_registered && !addForm.gstin.trim()) {
      setAddError('GSTIN is required when marked as GST registered.');
      return;
    }
    if (!addForm.admin_name.trim() || !addForm.admin_email.trim() || !addForm.admin_mobile.trim()) {
      setAddError('Primary Administrator name, email, and mobile are required.');
      return;
    }

    setAdding(true);
    try {
      const payload = {
        branch_name: addForm.branch_name.trim(),
        branch_code: addForm.branch_code.trim().toUpperCase(),
        branch_type: addForm.branch_type,
        branch_email: addForm.branch_email.trim() || null,
        branch_contact_number: addForm.branch_contact_number.trim(),
        address_line1: addForm.address_line1.trim(),
        address_line2: addForm.address_line2.trim() || null,
        city: addForm.city.trim(),
        district: addForm.district.trim() || addForm.city.trim(),
        state: addForm.state.trim(),
        pincode: addForm.pincode.trim(),
        country: addForm.country.trim() || 'India',
        gst_registered: Boolean(addForm.gst_registered),
        gstin: addForm.gst_registered ? addForm.gstin.trim().toUpperCase() : null,
        gst_type: addForm.gst_registered ? addForm.gst_type : null,
        admin_name: addForm.admin_name.trim(),
        admin_email: addForm.admin_email.trim().toLowerCase(),
        admin_mobile: addForm.admin_mobile.trim(),
      };

      const result = await api.createCompanyBranch(payload);
      setCreatedBranchData(result);
      setShowAddModal(false);
      showToast('Branch provisioned successfully.');
      loadData();
      onBranchesChanged?.();
    } catch (err) {
      setAddError(err.message || 'Failed to create branch.');
    } finally {
      setAdding(false);
    }
  };

  const handleOpenEdit = (branch) => {
    setEditingBranch(branch);
    setEditForm({
      name: branch.name || '',
      address: branch.address || branch.address_line1 || '',
      contact_person: branch.contact_person || branch.primary_admin?.name || '',
      contact_email: branch.contact_email || branch.branch_email || branch.primary_admin?.email || '',
      contact_phone: branch.contact_phone || branch.branch_contact_number || branch.primary_admin?.mobile || '',
    });
    setEditError('');
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editForm.name.trim()) {
      setEditError('Branch name is required.');
      return;
    }

    setEditing(true);
    try {
      await api.updateCompanyBranch(editingBranch.id, {
        name: editForm.name.trim(),
        address: editForm.address.trim() || null,
        address_line1: editForm.address.trim() || null,
        contact_person: editForm.contact_person.trim() || null,
        contact_email: editForm.contact_email.trim().toLowerCase() || null,
        branch_email: editForm.contact_email.trim().toLowerCase() || null,
        contact_phone: editForm.contact_phone.trim() || null,
        branch_contact_number: editForm.contact_phone.trim() || null,
      });
      setEditingBranch(null);
      showToast('Branch details updated.');
      loadData();
      onBranchesChanged?.();
    } catch (err) {
      setEditError(err.message || 'Failed to update branch.');
    } finally {
      setEditing(false);
    }
  };

  const handleToggleStatus = async (branch) => {
    const isDeactivating = branch.status === 'active';
    const activeCount = branch.active_user_count ?? branch.user_count ?? 0;

    if (isDeactivating && (activeCount > 0)) {
      alert(`Cannot deactivate branch "${branch.name}" because it currently has ${activeCount} active user(s). Please reassign or deactivate those users before deactivating this branch.`);
      return;
    }

    const confirmMsg = isDeactivating
      ? `Are you sure you want to deactivate branch "${branch.name}" (${branch.code})?\n\n• New document uploads will be blocked immediately.\n• Existing documents will remain archived and accessible.`
      : `Reactivate branch "${branch.name}" (${branch.code})? Full operational access will be restored.`;

    if (!window.confirm(confirmMsg)) return;

    setActionLoadingId(branch.id);
    try {
      if (isDeactivating) {
        await api.deactivateCompanyBranch(branch.id);
        showToast(`Branch ${branch.code} deactivated.`);
      } else {
        await api.activateCompanyBranch(branch.id);
        showToast(`Branch ${branch.code} reactivated.`);
      }
      loadData();
      onBranchesChanged?.();
    } catch (err) {
      alert(err.message || 'Operation failed.');
    } finally {
      setActionLoadingId(null);
    }
  };

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 3px 0', color: '#0f172a', letterSpacing: '-0.01em' }}>
            Branch Management
          </h2>
          <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
            Provision, inspect, and maintain regional branches, offices, and GST entities under your enterprise.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            fontSize: '13px',
            fontWeight: 600,
            padding: '7px 14px',
            borderRadius: '8px',
            backgroundColor: '#ffffff',
            border: '1px solid #e2e8f0',
            color: '#475569',
            boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
          }}>
            Quota: <strong style={{ color: '#ef233c' }}>{branches.length}</strong> / {profile?.max_branches || '∞'} provisioned
          </div>

          <button
            onClick={() => {
              setAddError('');
              setShowAddModal(true);
            }}
            disabled={profile?.max_branches && branches.length >= profile.max_branches}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: '#ef233c',
              color: '#ffffff',
              padding: '10px 20px',
              borderRadius: '8px',
              border: 'none',
              fontWeight: 600,
              fontSize: '14px',
              cursor: (profile?.max_branches && branches.length >= profile.max_branches) ? 'not-allowed' : 'pointer',
              opacity: (profile?.max_branches && branches.length >= profile.max_branches) ? 0.6 : 1,
              boxShadow: '0 2px 8px rgba(239, 35, 60, 0.25)',
              transition: 'background-color 0.2s',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add Branch
          </button>
        </div>
      </div>

      {/* Quota warning */}
      {profile?.max_branches && branches.length >= profile.max_branches && (
        <div style={{ backgroundColor: '#fffbeb', border: '1px solid #fef3c7', padding: '12px 16px', borderRadius: '8px', color: '#b45309', fontSize: '13px', marginBottom: '20px' }}>
          <strong>Branch Quota Reached:</strong> Your organization has utilized all {profile.max_branches} allocated branch slots. Contact platform Master Administration to request an increase.
        </div>
      )}

      {/* Search and Filters */}
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e2e8f0',
        padding: '14px 18px',
        marginBottom: '20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '12px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}>
        <input
          type="text"
          placeholder="Search by branch name, code, city, GSTIN..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ flex: 1, minWidth: '240px', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
        />

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Status:</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff' }}
          >
            <option value="all">All Branches</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
          </select>
        </div>
      </div>

      {/* Branches Table */}
      <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '12px', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
        {loading ? (
          <div style={{ padding: '60px 0', textAlign: 'center', color: '#64748b' }}>
            <div className="spinner" style={{ margin: '0 auto 12px' }} />
            Loading branches...
          </div>
        ) : filteredBranches.length === 0 ? (
          <div style={{ padding: '48px 0', textAlign: 'center', color: '#94a3b8', fontSize: '14px' }}>
            No branches match your filters.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
            <thead>
              <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                <th style={{ padding: '8px 10px' }}>Branch</th>
                <th style={{ padding: '8px 10px' }}>Code</th>
                <th style={{ padding: '8px 10px' }}>Location / State</th>
                <th style={{ padding: '8px 10px' }}>GSTIN</th>
                <th style={{ padding: '8px 10px' }}>Users</th>
                <th style={{ padding: '8px 10px' }}>Status</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredBranches.map((b) => (
                <tr key={b.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '7px 10px' }}>
                    <div style={{ fontWeight: 600, color: '#0f172a' }}>{b.name}</div>
                    <div style={{ fontSize: '10.5px', color: '#64748b' }}>{b.branch_type || 'Branch'}</div>
                  </td>
                  <td style={{ padding: '7px 10px' }}>
                    <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#b91c1c', backgroundColor: '#fee2e2', padding: '1px 5px', borderRadius: '4px', fontSize: '11px' }}>
                      {b.code}
                    </span>
                  </td>
                  <td style={{ padding: '7px 10px', color: '#334155' }}>
                    <div>{b.city || '—'}, {b.state || '—'}</div>
                    <div style={{ fontSize: '10.5px', color: '#94a3b8' }}>{b.pincode}</div>
                  </td>
                  <td style={{ padding: '7px 10px', fontFamily: 'monospace', fontSize: '11.5px', color: b.gstin ? '#0f172a' : '#94a3b8' }}>
                    {b.gstin || 'Non-GST'}
                  </td>
                  <td style={{ padding: '7px 10px' }}>
                    <span style={{ fontWeight: 600, color: '#1e293b' }}>{b.active_user_count ?? b.user_count ?? 0}</span> active
                    {(b.total_user_count || b.user_count || 0) > (b.active_user_count ?? b.user_count ?? 0) && ` (${b.total_user_count || b.user_count} total)`}
                  </td>
                  <td style={{ padding: '7px 10px' }}>
                    <span style={{
                      padding: '1px 6px',
                      borderRadius: '10px',
                      fontSize: '10.5px',
                      fontWeight: 700,
                      backgroundColor: b.status === 'active' ? '#ecfdf5' : '#fef2f2',
                      color: b.status === 'active' ? '#047857' : '#b91c1c',
                      border: `1px solid ${b.status === 'active' ? '#a7f3d0' : '#fecaca'}`,
                    }}>
                      {(b.status || 'active').toUpperCase()}
                    </span>
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', gap: '8px' }}>
                      <button
                        onClick={() => setViewBranch(b)}
                        style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#334155', fontSize: '12px', fontWeight: 500, cursor: 'pointer' }}
                      >
                        Details
                      </button>
                      <button
                        onClick={() => handleOpenEdit(b)}
                        style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#334155', fontSize: '12px', fontWeight: 500, cursor: 'pointer' }}
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => setAiConfigBranch(b)}
                        style={{
                          padding: '5px 10px',
                          borderRadius: '6px',
                          border: '1px solid #c084fc',
                          backgroundColor: '#faf5ff',
                          color: '#7e22ce',
                          fontSize: '12px',
                          fontWeight: 600,
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                        AI Config
                      </button>
                      <button
                        onClick={() => handleToggleStatus(b)}
                        disabled={actionLoadingId === b.id}
                        style={{
                          padding: '5px 10px',
                          borderRadius: '6px',
                          border: `1px solid ${b.status === 'active' ? '#fecaca' : '#a7f3d0'}`,
                          backgroundColor: b.status === 'active' ? '#fff5f5' : '#f0fdf4',
                          color: b.status === 'active' ? '#b91c1c' : '#15803d',
                          fontSize: '12px',
                          fontWeight: 600,
                          cursor: actionLoadingId === b.id ? 'not-allowed' : 'pointer',
                        }}
                      >
                        {b.status === 'active' ? 'Deactivate' : 'Activate'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Add Branch Modal */}
      {showAddModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', maxWidth: '780px', width: '100%', maxHeight: '90vh', overflowY: 'auto', padding: '28px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid #e2e8f0', paddingBottom: '14px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 700, margin: 0, color: '#0f172a' }}>Provision New Branch &amp; Primary Administrator</h3>
              <button onClick={() => setShowAddModal(false)} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#94a3b8' }}>&times;</button>
            </div>

            {addError && (
              <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '12px 16px', borderRadius: '8px', color: '#991b1b', fontSize: '13px', marginBottom: '16px' }}>
                {addError}
              </div>
            )}

            <form onSubmit={handleAddBranch}>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#ef233c', textTransform: 'uppercase', marginBottom: '12px' }}>
                Section 1: Branch Details &amp; Address
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '14px', marginBottom: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Branch Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Coimbatore Regional Office"
                    value={addForm.branch_name}
                    onChange={(e) => setAddForm({ ...addForm, branch_name: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Branch Code *</label>
                  <input
                    type="text"
                    required
                    placeholder="CBE01"
                    value={addForm.branch_code}
                    onChange={(e) => setAddForm({ ...addForm, branch_code: e.target.value.toUpperCase() })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', textTransform: 'uppercase', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Branch Type</label>
                  <select
                    value={addForm.branch_type}
                    onChange={(e) => setAddForm({ ...addForm, branch_type: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                  >
                    {BRANCH_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Contact Phone *</label>
                  <input
                    type="text"
                    required
                    placeholder="+91 9876543210"
                    value={addForm.branch_contact_number}
                    onChange={(e) => setAddForm({ ...addForm, branch_contact_number: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Branch Email</label>
                  <input
                    type="email"
                    placeholder="branch@company.com"
                    value={addForm.branch_email}
                    onChange={(e) => setAddForm({ ...addForm, branch_email: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Address Line 1 *</label>
                  <input
                    type="text"
                    required
                    placeholder="Door No, Street"
                    value={addForm.address_line1}
                    onChange={(e) => setAddForm({ ...addForm, address_line1: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>City *</label>
                  <input
                    type="text"
                    required
                    placeholder="Coimbatore"
                    value={addForm.city}
                    onChange={(e) => setAddForm({ ...addForm, city: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '18px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>State *</label>
                  <select
                    value={addForm.state}
                    onChange={(e) => setAddForm({ ...addForm, state: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                  >
                    {INDIAN_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>PIN Code (6 digits) *</label>
                  <input
                    type="text"
                    required
                    maxLength={6}
                    placeholder="641001"
                    value={addForm.pincode}
                    onChange={(e) => setAddForm({ ...addForm, pincode: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              {/* GST Checkbox */}
              <div style={{ backgroundColor: '#f8fafc', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '18px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: 600, color: '#1e293b' }}>
                  <input
                    type="checkbox"
                    checked={addForm.gst_registered}
                    onChange={(e) => setAddForm({ ...addForm, gst_registered: e.target.checked })}
                  />
                  This branch possesses a distinct GSTIN registration
                </label>
                {addForm.gst_registered && (
                  <div style={{ marginTop: '10px', display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '12px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>Branch GSTIN *</label>
                      <input
                        type="text"
                        maxLength={15}
                        placeholder="33AABCA1234F1Z5"
                        value={addForm.gstin}
                        onChange={(e) => setAddForm({ ...addForm, gstin: e.target.value.toUpperCase() })}
                        style={{ width: '100%', padding: '7px 10px', borderRadius: '5px', border: '1px solid #cbd5e1', fontSize: '12px', textTransform: 'uppercase', fontFamily: 'monospace', boxSizing: 'border-box' }}
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>GST Type</label>
                      <select
                        value={addForm.gst_type}
                        onChange={(e) => setAddForm({ ...addForm, gst_type: e.target.value })}
                        style={{ width: '100%', padding: '7px 10px', borderRadius: '5px', border: '1px solid #cbd5e1', fontSize: '12px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                      >
                        {GST_REGISTRATION_TYPES.map((gt) => <option key={gt} value={gt}>{gt}</option>)}
                      </select>
                    </div>
                  </div>
                )}
              </div>

              {/* Section 2: Primary Admin */}
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#ef233c', textTransform: 'uppercase', marginBottom: '12px' }}>
                Section 2: Primary Branch Administrator
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '14px', marginBottom: '24px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Admin Full Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="Senthil Kumar"
                    value={addForm.admin_name}
                    onChange={(e) => setAddForm({ ...addForm, admin_name: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Admin Email *</label>
                  <input
                    type="email"
                    required
                    placeholder="senthil@company.com"
                    value={addForm.admin_email}
                    onChange={(e) => setAddForm({ ...addForm, admin_email: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Admin Mobile *</label>
                  <input
                    type="text"
                    required
                    placeholder="+91 9876543210"
                    value={addForm.admin_mobile}
                    onChange={(e) => setAddForm({ ...addForm, admin_mobile: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  disabled={adding}
                  style={{ padding: '9px 18px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={adding}
                  style={{
                    padding: '10px 24px',
                    borderRadius: '8px',
                    border: 'none',
                    backgroundColor: '#ef233c',
                    color: '#ffffff',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: adding ? 'not-allowed' : 'pointer',
                    boxShadow: '0 2px 8px rgba(239, 35, 60, 0.25)',
                    opacity: adding ? 0.7 : 1,
                  }}
                >
                  {adding ? 'Provisioning...' : 'Provision Branch & Send Invite'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Branch Created Modal */}
      {createdBranchData && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', maxWidth: '580px', width: '100%', padding: '28px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <div style={{ width: '48px', height: '48px', borderRadius: '50%', backgroundColor: '#ecfdf5', color: '#10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px' }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12" /></svg>
              </div>
              <h3 style={{ fontSize: '18px', fontWeight: 700, margin: '0 0 4px', color: '#0f172a' }}>Branch Provisioned Successfully!</h3>
              <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
                Branch <strong>{createdBranchData.branch?.name}</strong> ({createdBranchData.branch?.code}) has been created.
              </p>
            </div>

            <div style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '16px', marginBottom: '20px', fontSize: '13px' }}>
              <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>Primary Administrator Activation Details:</div>
              <div style={{ color: '#475569' }}>Name: <strong>{createdBranchData.primary_admin?.name}</strong></div>
              <div style={{ color: '#475569' }}>Email: <strong>{createdBranchData.primary_admin?.email}</strong></div>
              <div style={{ marginTop: '10px', wordBreak: 'break-all' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Activation URL:</label>
                <div style={{ padding: '8px', backgroundColor: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '4px', marginTop: '4px', fontFamily: 'monospace', fontSize: '12px' }}>
                  {createdBranchData.invitation?.activation_url || 'Dispatched via invitation email.'}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              {createdBranchData.invitation?.activation_url && (
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(createdBranchData.invitation.activation_url);
                    showToast('Activation link copied.');
                  }}
                  style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#334155', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Copy Activation Link
                </button>
              )}
              <button
                onClick={() => setCreatedBranchData(null)}
                style={{ padding: '8px 18px', borderRadius: '8px', border: 'none', backgroundColor: '#ef233c', color: '#ffffff', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Branch Modal */}
      {editingBranch && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', maxWidth: '540px', width: '100%', padding: '28px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', borderBottom: '1px solid #e2e8f0', paddingBottom: '12px' }}>
              <h3 style={{ fontSize: '17px', fontWeight: 700, margin: 0, color: '#0f172a' }}>Edit Branch: {editingBranch.code}</h3>
              <button onClick={() => setEditingBranch(null)} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#94a3b8' }}>&times;</button>
            </div>

            {editError && (
              <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '10px 14px', borderRadius: '6px', color: '#991b1b', fontSize: '13px', marginBottom: '14px' }}>
                {editError}
              </div>
            )}

            <form onSubmit={handleSaveEdit}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Branch Name *</label>
                <input
                  type="text"
                  required
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Full Address</label>
                <textarea
                  rows={2}
                  value={editForm.address}
                  onChange={(e) => setEditForm({ ...editForm, address: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Contact Person</label>
                  <input
                    type="text"
                    value={editForm.contact_person}
                    onChange={(e) => setEditForm({ ...editForm, contact_person: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Contact Phone</label>
                  <input
                    type="text"
                    value={editForm.contact_phone}
                    onChange={(e) => setEditForm({ ...editForm, contact_phone: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '24px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Contact Email</label>
                <input
                  type="email"
                  value={editForm.contact_email}
                  onChange={(e) => setEditForm({ ...editForm, contact_email: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setEditingBranch(null)}
                  style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editing}
                  style={{ padding: '8px 20px', borderRadius: '8px', border: 'none', backgroundColor: '#ef233c', color: '#ffffff', fontSize: '13px', fontWeight: 600, cursor: editing ? 'not-allowed' : 'pointer' }}
                >
                  {editing ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* View Branch Details Modal */}
      {viewBranch && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', maxWidth: '580px', width: '100%', padding: '28px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', borderBottom: '1px solid #e2e8f0', paddingBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 700, margin: 0, color: '#0f172a' }}>{viewBranch.name}</h3>
                <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#b91c1c', backgroundColor: '#fee2e2', padding: '2px 6px', borderRadius: '4px', fontSize: '12px' }}>{viewBranch.code}</span>
              </div>
              <button onClick={() => setViewBranch(null)} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#94a3b8' }}>&times;</button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', fontSize: '13px', marginBottom: '20px' }}>
              <div><strong style={{ color: '#64748b' }}>Branch Type:</strong> <div>{viewBranch.branch_type || 'Branch'}</div></div>
              <div><strong style={{ color: '#64748b' }}>Status:</strong> <div>{(viewBranch.status || 'active').toUpperCase()}</div></div>
              <div><strong style={{ color: '#64748b' }}>GSTIN:</strong> <div style={{ fontFamily: 'monospace' }}>{viewBranch.gstin || 'Non-GST Registered'}</div></div>
              <div><strong style={{ color: '#64748b' }}>Active Users:</strong> <div>{viewBranch.active_user_count ?? viewBranch.user_count ?? 0} assigned</div></div>
              <div><strong style={{ color: '#64748b' }}>Contact Person:</strong> <div>{viewBranch.contact_person || viewBranch.primary_admin?.name || '—'}</div></div>
              <div><strong style={{ color: '#64748b' }}>Contact Phone:</strong> <div>{viewBranch.contact_phone || viewBranch.branch_contact_number || viewBranch.primary_admin?.mobile || '—'}</div></div>
              <div style={{ gridColumn: 'span 2' }}><strong style={{ color: '#64748b' }}>Contact Email:</strong> <div>{viewBranch.contact_email || viewBranch.branch_email || viewBranch.primary_admin?.email || '—'}</div></div>
              <div style={{ gridColumn: 'span 2' }}>
                <strong style={{ color: '#64748b' }}>Address:</strong>
                <div>
                  {(() => {
                    const street = viewBranch.address || viewBranch.address_line1;
                    const parts = [
                      street,
                      viewBranch.address_line2,
                      viewBranch.city,
                      viewBranch.state,
                      viewBranch.pincode,
                    ].filter(Boolean);
                    return parts.length > 0 ? parts.join(', ') : '—';
                  })()}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setViewBranch(null)}
                style={{ padding: '8px 18px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#334155', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Branch AI Config Modal */}
      {aiConfigBranch && (
        <BranchAIConfigModal
          branch={aiConfigBranch}
          onClose={() => setAiConfigBranch(null)}
          showToast={showToast}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 4: USER MANAGEMENT VIEW
// ─────────────────────────────────────────────────────────────────────────────
function UserManagementView({ branchesList, showToast, setConfirmDialog }) {
  const [activeSubTab, setActiveSubTab] = useState('users');

  const [users, setUsers] = useState([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loadingUsers, setLoadingUsers] = useState(true);

  // Filters
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [branchFilter, setBranchFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Invitations
  const [invitations, setInvitations] = useState([]);
  const [loadingInvitations, setLoadingInvitations] = useState(false);

  // Invite Modal
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteForm, setInviteForm] = useState({
    name: '',
    email: '',
    mobile: '',
    role: 'STAFF',
    branch_id: '',
    additional_branch_ids: [],
  });
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState('');
  const [inviteSuccessLink, setInviteSuccessLink] = useState(null);

  // Edit User Modal
  const [editingUser, setEditingUser] = useState(null);
  const [editForm, setEditForm] = useState({
    name: '',
    mobile: '',
    role: '',
    primary_branch_id: '',
    additional_branch_ids: [],
  });
  const [savingEdit, setSavingEdit] = useState(false);
  const [editUserError, setEditUserError] = useState('');

  const loadUsers = async () => {
    setLoadingUsers(true);
    try {
      const res = await api.getCompanyUsers({
        search,
        role: roleFilter || undefined,
        branch_id: branchFilter || undefined,
        status: statusFilter || undefined,
        page,
        page_size: 20,
      });
      setUsers(res.items || []);
      setTotalUsers(res.total_count || 0);
      setTotalPages(res.total_pages || 1);
    } catch (err) {
      showToast(err.message || 'Failed to load users.', 'error');
    } finally {
      setLoadingUsers(false);
    }
  };

  const loadInvitations = async () => {
    setLoadingInvitations(true);
    try {
      const res = await api.getCompanyInvitations();
      setInvitations(res || []);
    } catch (err) {
      showToast(err.message || 'Failed to load invitations.', 'error');
    } finally {
      setLoadingInvitations(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, [search, roleFilter, branchFilter, statusFilter, page]);

  useEffect(() => {
    if (activeSubTab === 'invitations') {
      loadInvitations();
    }
  }, [activeSubTab]);

  const handleInviteSubmit = async (e) => {
    e.preventDefault();
    setInviteError('');

    if (!inviteForm.name.trim() || !inviteForm.email.trim()) {
      setInviteError('Name and Email are required.');
      return;
    }
    if (!inviteForm.branch_id) {
      setInviteError('Please select a Primary Branch for the user.');
      return;
    }

    setInviting(true);
    try {
      const payload = {
        name: inviteForm.name.trim(),
        email: inviteForm.email.trim().toLowerCase(),
        mobile: inviteForm.mobile.trim() || null,
        role: inviteForm.role,
        branch_id: parseInt(inviteForm.branch_id, 10),
        additional_branch_ids: inviteForm.role === 'ADMIN' ? inviteForm.additional_branch_ids : [],
      };
      const res = await api.inviteCompanyUser(payload);
      setShowInviteModal(false);
      setInviteSuccessLink(res.activation_url || 'Invitation email dispatched.');
      showToast('Invitation issued successfully.');
      loadUsers();
      if (activeSubTab === 'invitations') loadInvitations();
    } catch (err) {
      setInviteError(err.message || 'Failed to send invitation.');
    } finally {
      setInviting(false);
    }
  };

  const handleOpenEditUser = (u) => {
    setEditingUser(u);
    const primId = u.branch_id || u.primary_branch_id || '';
    const assignedIds = (u.assigned_branches || [])
      .map((ab) => ab.branch_id || ab.id)
      .filter((id) => id && String(id) !== String(primId));
    setEditForm({
      name: u.name || '',
      mobile: u.mobile || '',
      role: u.role || 'STAFF',
      primary_branch_id: String(primId),
      additional_branch_ids: assignedIds,
    });
    setEditUserError('');
  };

  const handleSaveEditUser = async (e) => {
    e.preventDefault();
    setEditUserError('');
    setSavingEdit(true);
    try {
      const pBranchId = editForm.primary_branch_id ? parseInt(editForm.primary_branch_id, 10) : undefined;
      const payload = {
        name: editForm.name.trim(),
        mobile: editForm.mobile.trim() || null,
        role: editForm.role,
        branch_id: pBranchId,
        primary_branch_id: pBranchId,
        additional_branch_ids: editForm.role === 'ADMIN' ? editForm.additional_branch_ids : [],
      };
      await api.updateCompanyUser(editingUser.id, payload);
      setEditingUser(null);
      showToast('User profile updated successfully.');
      loadUsers();
    } catch (err) {
      setEditUserError(err.message || 'Failed to update user.');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleForceLogout = (u) => {
    setConfirmDialog({
      title: 'Force Logout User Sessions',
      message: `Terminate all active sessions for "${u.name}" (${u.email}) immediately?`,
      details: (
        <div style={{ color: '#b45309', fontSize: '13px' }}>
          This will revoke their current JWTs and refresh tokens. The user will be required to re-authenticate on their next request.
        </div>
      ),
      confirmText: 'Force Logout',
      variant: 'warning',
      onConfirm: async () => {
        try {
          await api.forceLogoutCompanyUser(u.id);
          showToast(`Forced logout for ${u.email}. All sessions terminated.`);
          loadUsers();
        } catch (err) {
          showToast(err.message || 'Force logout failed.', 'error');
        }
      },
    });
  };

  const handleMfaResetRequest = (u) => {
    setConfirmDialog({
      title: 'Admin-Assisted MFA Reset',
      message: `Reset multi-factor authentication credentials for "${u.name}" (${u.email})?`,
      details: (
        <div style={{ color: '#0369a1', fontSize: '13px' }}>
          This will clear the user's registered authenticator app and failed login lockouts without exposing TOTP secrets. The user will be prompted to re-enroll a new authenticator upon their next login.
        </div>
      ),
      confirmText: 'Reset MFA',
      variant: 'primary',
      onConfirm: async () => {
        try {
          await api.requestCompanyUserMfaReset(u.id);
          showToast(`MFA credentials reset for ${u.email}. User must re-enroll.`);
          loadUsers();
        } catch (err) {
          showToast(err.message || 'MFA reset failed.', 'error');
        }
      },
    });
  };

  const handleDeactivateUser = (u) => {
    setConfirmDialog({
      title: 'Deactivate User Account',
      message: `Are you sure you want to deactivate "${u.name}" (${u.email})?`,
      details: (
        <div style={{ color: '#b91c1c', fontSize: '13px' }}>
          The user will be immediately logged out and blocked from signing in until reactivated.
          {u.role === 'GLOBAL_ADMIN' && (
            <div style={{ marginTop: '6px', fontWeight: 600 }}>
              Notice: The last active Company Administrator cannot be deactivated.
            </div>
          )}
        </div>
      ),
      confirmText: 'Deactivate Account',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await api.deactivateCompanyUser(u.id);
          showToast(`User ${u.email} deactivated.`);
          loadUsers();
        } catch (err) {
          showToast(err.message || 'Deactivation failed.', 'error');
        }
      },
    });
  };

  const handleActivateUser = async (u) => {
    try {
      await api.activateCompanyUser(u.id);
      showToast(`User ${u.email} reactivated.`);
      loadUsers();
    } catch (err) {
      showToast(err.message || 'Activation failed.', 'error');
    }
  };

  const handleResendInvitation = async (inv) => {
    try {
      const res = await api.resendCompanyInvitation(inv.id);
      showToast(`Invitation resent to ${inv.email}.`);
      if (res.activation_url) {
        setInviteSuccessLink(res.activation_url);
      }
      loadInvitations();
    } catch (err) {
      showToast(err.message || 'Failed to resend invitation.', 'error');
    }
  };

  const handleRevokeInvitation = (inv) => {
    setConfirmDialog({
      title: 'Revoke Invitation',
      message: `Revoke pending invitation for "${inv.email}"?`,
      confirmText: 'Revoke Invite',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await api.revokeCompanyInvitation(inv.id);
          showToast(`Invitation for ${inv.email} revoked.`);
          loadInvitations();
        } catch (err) {
          showToast(err.message || 'Failed to revoke invitation.', 'error');
        }
      },
    });
  };

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 3px 0', color: '#0f172a', letterSpacing: '-0.01em' }}>
            User Management &amp; Role Assignments
          </h2>
          <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
            Invite, supervise, and configure multi-branch authorizations for all personnel across your enterprise.
          </p>
        </div>

        <button
          onClick={() => {
            setInviteError('');
            setInviteForm({
              name: '',
              email: '',
              mobile: '',
              role: 'STAFF',
              branch_id: branchesList[0]?.id ? String(branchesList[0].id) : '',
              additional_branch_ids: [],
            });
            setShowInviteModal(true);
          }}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: '#ef233c',
            color: '#ffffff',
            padding: '10px 20px',
            borderRadius: '8px',
            border: 'none',
            fontWeight: 600,
            fontSize: '14px',
            cursor: 'pointer',
            boxShadow: '0 2px 8px rgba(239, 35, 60, 0.25)',
            transition: 'background-color 0.2s',
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><line x1="20" y1="8" x2="20" y2="14" /><line x1="23" y1="11" x2="17" y2="11" />
          </svg>
          Invite User
        </button>
      </div>

      {/* Sub Tabs */}
      <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #e2e8f0', marginBottom: '20px' }}>
        <button
          onClick={() => setActiveSubTab('users')}
          style={{
            padding: '10px 18px',
            background: 'none',
            border: 'none',
            borderBottom: activeSubTab === 'users' ? '2px solid #ef233c' : '2px solid transparent',
            color: activeSubTab === 'users' ? '#ef233c' : '#64748b',
            fontWeight: 600,
            fontSize: '14px',
            cursor: 'pointer',
          }}
        >
          Active Personnel ({totalUsers})
        </button>
        <button
          onClick={() => setActiveSubTab('invitations')}
          style={{
            padding: '10px 18px',
            background: 'none',
            border: 'none',
            borderBottom: activeSubTab === 'invitations' ? '2px solid #ef233c' : '2px solid transparent',
            color: activeSubTab === 'invitations' ? '#ef233c' : '#64748b',
            fontWeight: 600,
            fontSize: '14px',
            cursor: 'pointer',
          }}
        >
          Pending Invitations
        </button>
      </div>

      {activeSubTab === 'users' && (
        <>
          {/* Filters Bar */}
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: '1px solid #e2e8f0',
            padding: '14px 18px',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
          }}>
            <input
              type="text"
              placeholder="Search user by name or email..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              style={{ flex: 1, minWidth: '220px', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
            />

            <select
              value={roleFilter}
              onChange={(e) => { setRoleFilter(e.target.value); setPage(1); }}
              style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff' }}
            >
              <option value="">All Roles</option>
              <option value="GLOBAL_ADMIN">Company Admin (HQ)</option>
              <option value="ADMIN">Branch Administrator</option>
              <option value="STAFF">Staff / Uploader</option>
            </select>

            <select
              value={branchFilter}
              onChange={(e) => { setBranchFilter(e.target.value); setPage(1); }}
              style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff' }}
            >
              <option value="">All Branches</option>
              {branchesList.map((b) => (
                <option key={b.id} value={b.id}>{b.name} ({b.code})</option>
              ))}
            </select>

            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
              style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff' }}
            >
              <option value="">All Statuses</option>
              <option value="active">Active Only</option>
              <option value="inactive">Inactive Only</option>
            </select>
          </div>

          {/* Users Table */}
          <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '12px', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            {loadingUsers ? (
              <div style={{ padding: '60px 0', textAlign: 'center', color: '#64748b' }}>
                <div className="spinner" style={{ margin: '0 auto 12px' }} />
                Loading users...
              </div>
            ) : users.length === 0 ? (
              <div style={{ padding: '48px 0', textAlign: 'center', color: '#94a3b8', fontSize: '14px' }}>
                No personnel found matching the criteria.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                    <th style={{ padding: '8px 10px' }}>User Details</th>
                    <th style={{ padding: '8px 10px' }}>Role</th>
                    <th style={{ padding: '8px 10px' }}>Branch Scopes</th>
                    <th style={{ padding: '8px 10px' }}>MFA Security</th>
                    <th style={{ padding: '8px 10px' }}>Status</th>
                    <th style={{ padding: '8px 10px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '7px 10px' }}>
                        <div style={{ fontWeight: 600, color: '#0f172a' }}>{u.name}</div>
                        <div style={{ fontSize: '11px', color: '#64748b' }}>{u.email}</div>
                        {u.mobile && <div style={{ fontSize: '10.5px', color: '#94a3b8' }}>{u.mobile}</div>}
                      </td>
                      <td style={{ padding: '7px 10px' }}>
                        <span style={{
                          padding: '2px 7px',
                          borderRadius: '4px',
                          fontSize: '10.5px',
                          fontWeight: 700,
                          backgroundColor: u.role === 'GLOBAL_ADMIN' ? '#fee2e2' : u.role === 'ADMIN' ? '#eff6ff' : '#f1f5f9',
                          color: u.role === 'GLOBAL_ADMIN' ? '#b91c1c' : u.role === 'ADMIN' ? '#1d4ed8' : '#475569',
                          border: `1px solid ${u.role === 'GLOBAL_ADMIN' ? '#fecaca' : u.role === 'ADMIN' ? '#bfdbfe' : '#e2e8f0'}`,
                        }}>
                          {u.role === 'GLOBAL_ADMIN' ? 'Company Admin' : u.role === 'ADMIN' ? 'Branch Admin' : 'Staff / Uploader'}
                        </span>
                      </td>
                      <td style={{ padding: '7px 10px' }}>
                        {u.role === 'GLOBAL_ADMIN' ? (
                          <span style={{ color: '#b91c1c', fontWeight: 600, fontSize: '11.5px' }}>Company-Wide (All Branches)</span>
                        ) : (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                            <span style={{ backgroundColor: '#f1f5f9', color: '#334155', padding: '1px 5px', borderRadius: '4px', fontSize: '10.5px', fontWeight: 600 }}>
                              {u.branch_name || u.primary_branch_name || (u.branch_id || u.primary_branch_id ? `Branch #${u.branch_id || u.primary_branch_id}` : 'Unassigned')} (Primary)
                            </span>
                            {u.assigned_branches && u.assigned_branches
                              .filter(ab => (ab.branch_id || ab.id) && String(ab.branch_id || ab.id) !== String(u.branch_id || u.primary_branch_id))
                              .map((ab) => (
                                <span key={ab.branch_id || ab.id} style={{ backgroundColor: '#eef2ff', color: '#4338ca', padding: '1px 5px', borderRadius: '4px', fontSize: '10.5px' }}>
                                  {ab.branch_name || ab.name || ab.branch_code || ab.code || `Branch #${ab.branch_id || ab.id}`}
                                </span>
                              ))}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: '7px 10px' }}>
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '5px',
                          fontSize: '11px',
                          fontWeight: 600,
                          color: u.mfa_enabled ? '#15803d' : '#94a3b8',
                        }}>
                          <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: u.mfa_enabled ? '#10b981' : '#cbd5e1' }} />
                          {u.mfa_enabled ? 'Enrolled' : 'Not Configured'}
                        </span>
                      </td>
                      <td style={{ padding: '14px 16px' }}>
                        <span style={{
                          padding: '2px 7px',
                          borderRadius: '10px',
                          fontSize: '11px',
                          fontWeight: 700,
                          backgroundColor: u.status === 'active' ? '#ecfdf5' : '#fef2f2',
                          color: u.status === 'active' ? '#047857' : '#b91c1c',
                        }}>
                          {(u.status || 'active').toUpperCase()}
                        </span>
                      </td>
                      <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '6px' }}>
                          <button
                            onClick={() => handleOpenEditUser(u)}
                            style={{ padding: '5px 9px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#334155', fontSize: '12px', fontWeight: 500, cursor: 'pointer' }}
                            title="Edit User Profile & Role"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleForceLogout(u)}
                            style={{ padding: '5px 9px', borderRadius: '6px', border: '1px solid #fed7aa', backgroundColor: '#fffaf5', color: '#c2410c', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
                            title="Force Logout All Sessions"
                          >
                            Force Logout
                          </button>
                          {u.role !== 'GLOBAL_ADMIN' && (
                            <button
                              onClick={() => handleMfaResetRequest(u)}
                              style={{ padding: '5px 9px', borderRadius: '6px', border: '1px solid #bae6fd', backgroundColor: '#f0f9ff', color: '#0369a1', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
                              title="Reset User MFA"
                            >
                              Reset MFA
                            </button>
                          )}
                          {u.status === 'active' ? (
                            <button
                              onClick={() => handleDeactivateUser(u)}
                              style={{ padding: '5px 9px', borderRadius: '6px', border: '1px solid #fecaca', backgroundColor: '#fff5f5', color: '#b91c1c', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
                              title="Deactivate Account"
                            >
                              Deactivate
                            </button>
                          ) : (
                            <button
                              onClick={() => handleActivateUser(u)}
                              style={{ padding: '5px 9px', borderRadius: '6px', border: '1px solid #a7f3d0', backgroundColor: '#f0fdf4', color: '#15803d', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
                              title="Reactivate Account"
                            >
                              Activate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #e2e8f0', fontSize: '13px' }}>
                <span style={{ color: '#64748b' }}>Page {page} of {totalPages} ({totalUsers} total)</span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    style={{ padding: '5px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', cursor: page <= 1 ? 'not-allowed' : 'pointer' }}
                  >
                    Previous
                  </button>
                  <button
                    disabled={page >= totalPages}
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    style={{ padding: '5px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', cursor: page >= totalPages ? 'not-allowed' : 'pointer' }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* Invitations Subtab */}
      {activeSubTab === 'invitations' && (
        <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '12px', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
          {loadingInvitations ? (
            <div style={{ padding: '48px 0', textAlign: 'center', color: '#64748b' }}>
              <div className="spinner" style={{ margin: '0 auto 12px' }} />
              Loading invitations...
            </div>
          ) : invitations.length === 0 ? (
            <div style={{ padding: '48px 0', textAlign: 'center', color: '#94a3b8', fontSize: '14px' }}>
              No pending invitations found.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                  <th style={{ padding: '8px 10px' }}>Invited Email</th>
                  <th style={{ padding: '8px 10px' }}>Assigned Role</th>
                  <th style={{ padding: '8px 10px' }}>Branch</th>
                  <th style={{ padding: '8px 10px' }}>Expires At</th>
                  <th style={{ padding: '8px 10px' }}>Status</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {invitations.map((inv) => {
                  const roleCode = inv.role || inv.invited_role || 'STAFF';
                  const isAccepted = inv.accepted || inv.status === 'accepted';
                  const isRevoked = inv.revoked || inv.status === 'revoked';
                  const isPending = inv.is_valid || inv.status === 'pending';
                  const statusLabel = isAccepted ? 'Accepted' : isRevoked ? 'Revoked' : isPending ? 'Pending' : 'Expired';
                  const statusBg = isAccepted ? '#ecfdf5' : isRevoked ? '#fef2f2' : isPending ? '#fffbeb' : '#f1f5f9';
                  const statusColor = isAccepted ? '#047857' : isRevoked ? '#b91c1c' : isPending ? '#b45309' : '#64748b';

                  return (
                    <tr key={inv.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '7px 10px', fontWeight: 600, color: '#0f172a' }}>{inv.email}</td>
                      <td style={{ padding: '7px 10px' }}>
                        <span style={{
                          padding: '2px 7px',
                          borderRadius: '4px',
                          fontSize: '10.5px',
                          fontWeight: 700,
                          backgroundColor: roleCode === 'GLOBAL_ADMIN' ? '#fee2e2' : roleCode === 'ADMIN' ? '#eff6ff' : '#f1f5f9',
                          color: roleCode === 'GLOBAL_ADMIN' ? '#b91c1c' : roleCode === 'ADMIN' ? '#1d4ed8' : '#475569',
                          border: `1px solid ${roleCode === 'GLOBAL_ADMIN' ? '#fecaca' : roleCode === 'ADMIN' ? '#bfdbfe' : '#e2e8f0'}`,
                        }}>
                          {roleCode === 'GLOBAL_ADMIN' ? 'Company Admin' : roleCode === 'ADMIN' ? 'Branch Admin' : 'Staff / Uploader'}
                        </span>
                      </td>
                      <td style={{ padding: '7px 10px', color: '#475569' }}>
                        {inv.branch_name
                          ? (inv.branch_code ? `${inv.branch_name} (${inv.branch_code})` : inv.branch_name)
                          : (inv.branch_id ? `Branch #${inv.branch_id}` : 'Unassigned')}
                      </td>
                      <td style={{ padding: '7px 10px', color: '#64748b' }}>
                        {inv.expires_at ? new Date(inv.expires_at).toLocaleString() : '—'}
                      </td>
                      <td style={{ padding: '14px 16px' }}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '10px',
                          fontSize: '11px',
                          fontWeight: 700,
                          backgroundColor: statusBg,
                          color: statusColor,
                        }}>
                          {statusLabel}
                        </span>
                      </td>
                      <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                        {isPending && (
                          <div style={{ display: 'inline-flex', gap: '8px' }}>
                            <button
                              onClick={() => handleResendInvitation(inv)}
                              style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#334155', fontSize: '12px', fontWeight: 500, cursor: 'pointer' }}
                            >
                              Resend
                            </button>
                            <button
                              onClick={() => handleRevokeInvitation(inv)}
                              style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid #fecaca', backgroundColor: '#fff5f5', color: '#b91c1c', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
                            >
                              Revoke
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Invite Modal */}
      {showInviteModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', maxWidth: '580px', width: '100%', padding: '28px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', borderBottom: '1px solid #e2e8f0', paddingBottom: '12px' }}>
              <h3 style={{ fontSize: '18px', fontWeight: 700, margin: 0, color: '#0f172a' }}>Invite New Company User</h3>
              <button onClick={() => setShowInviteModal(false)} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#94a3b8' }}>&times;</button>
            </div>

            {inviteError && (
              <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '10px 14px', borderRadius: '6px', color: '#991b1b', fontSize: '13px', marginBottom: '14px' }}>
                {inviteError}
              </div>
            )}

            <form onSubmit={handleInviteSubmit}>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Full Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Ramesh Kannan"
                  value={inviteForm.name}
                  onChange={(e) => setInviteForm({ ...inviteForm, name: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '12px', marginBottom: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Email Address *</label>
                  <input
                    type="email"
                    required
                    placeholder="ramesh@company.com"
                    value={inviteForm.email}
                    onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Mobile Number</label>
                  <input
                    type="text"
                    placeholder="+91 9876543210"
                    value={inviteForm.mobile}
                    onChange={(e) => setInviteForm({ ...inviteForm, mobile: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Assign Role *</label>
                <select
                  value={inviteForm.role}
                  onChange={(e) => {
                    const newR = e.target.value;
                    setInviteForm({
                      ...inviteForm,
                      role: newR,
                      additional_branch_ids: newR === 'ADMIN' ? inviteForm.additional_branch_ids : [],
                    });
                  }}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                >
                  <option value="STAFF">Staff / Document Uploader (Single Branch)</option>
                  <option value="ADMIN">Branch Administrator (Multi-Branch Eligible)</option>
                  <option value="GLOBAL_ADMIN">Company Administrator (Enterprise HQ Scope)</option>
                </select>
                <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
                  {inviteForm.role === 'GLOBAL_ADMIN' && 'Company Administrators possess company-wide visibility across all branches.'}
                  {inviteForm.role === 'ADMIN' && 'Branch Administrators can be assigned to multiple branches simultaneously.'}
                  {inviteForm.role === 'STAFF' && 'Staff & Uploaders are strictly constrained to a single primary branch workspace.'}
                </div>
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Primary Branch *</label>
                <select
                  required
                  value={inviteForm.branch_id}
                  onChange={(e) => setInviteForm({ ...inviteForm, branch_id: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                >
                  <option value="">Select Primary Branch</option>
                  {branchesList.map((b) => (
                    <option key={b.id} value={b.id}>{b.name} ({b.code}) - {b.city}</option>
                  ))}
                </select>
              </div>

              {inviteForm.role === 'ADMIN' && (
                <div style={{ backgroundColor: '#f8fafc', padding: '12px 14px', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '20px' }}>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#1e293b', marginBottom: '6px' }}>
                    Additional Branches (Multi-Branch Assignment)
                  </label>
                  <div style={{ maxHeight: '120px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {branchesList.filter(b => String(b.id) !== String(inviteForm.branch_id)).map((b) => {
                      const checked = inviteForm.additional_branch_ids.includes(b.id);
                      return (
                        <label key={b.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: '#334155', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setInviteForm({ ...inviteForm, additional_branch_ids: [...inviteForm.additional_branch_ids, b.id] });
                              } else {
                                setInviteForm({ ...inviteForm, additional_branch_ids: inviteForm.additional_branch_ids.filter(id => id !== b.id) });
                              }
                            }}
                          />
                          <span>{b.name} ({b.code})</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setShowInviteModal(false)}
                  disabled={inviting}
                  style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={inviting}
                  style={{ padding: '8px 22px', borderRadius: '8px', border: 'none', backgroundColor: '#ef233c', color: '#ffffff', fontSize: '13px', fontWeight: 600, cursor: inviting ? 'not-allowed' : 'pointer', boxShadow: '0 2px 8px rgba(239, 35, 60, 0.25)' }}
                >
                  {inviting ? 'Sending...' : 'Send Invitation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit User Modal */}
      {editingUser && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', maxWidth: '580px', width: '100%', padding: '28px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', borderBottom: '1px solid #e2e8f0', paddingBottom: '12px' }}>
              <h3 style={{ fontSize: '17px', fontWeight: 700, margin: 0, color: '#0f172a' }}>Edit User: {editingUser.email}</h3>
              <button onClick={() => setEditingUser(null)} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#94a3b8' }}>&times;</button>
            </div>

            {editUserError && (
              <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '10px 14px', borderRadius: '6px', color: '#991b1b', fontSize: '13px', marginBottom: '14px' }}>
                {editUserError}
              </div>
            )}

            <form onSubmit={handleSaveEditUser}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Full Name *</label>
                  <input
                    type="text"
                    required
                    value={editForm.name}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Mobile Number</label>
                  <input
                    type="text"
                    value={editForm.mobile}
                    onChange={(e) => setEditForm({ ...editForm, mobile: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Role</label>
                <select
                  value={editForm.role}
                  onChange={(e) => {
                    const newR = e.target.value;
                    setEditForm({
                      ...editForm,
                      role: newR,
                      additional_branch_ids: newR === 'ADMIN' ? editForm.additional_branch_ids : [],
                    });
                  }}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                >
                  <option value="STAFF">Staff / Document Uploader</option>
                  <option value="ADMIN">Branch Administrator</option>
                  <option value="GLOBAL_ADMIN">Company Administrator</option>
                </select>
                {editingUser.role === 'GLOBAL_ADMIN' && editForm.role !== 'GLOBAL_ADMIN' && (
                  <div style={{ fontSize: '11px', color: '#b45309', marginTop: '4px' }}>
                    Notice: Demoting an administrator is protected. The system prevents removing the last active Company Administrator.
                  </div>
                )}
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Primary Branch</label>
                <select
                  value={editForm.primary_branch_id}
                  onChange={(e) => setEditForm({ ...editForm, primary_branch_id: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                >
                  {branchesList.map((b) => (
                    <option key={b.id} value={b.id}>{b.name} ({b.code})</option>
                  ))}
                </select>
              </div>

              {editForm.role === 'ADMIN' && (
                <div style={{ backgroundColor: '#f8fafc', padding: '12px 14px', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '20px' }}>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#1e293b', marginBottom: '6px' }}>
                    Additional Branches (Multi-Branch Scopes)
                  </label>
                  <div style={{ maxHeight: '120px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {branchesList.filter(b => String(b.id) !== String(editForm.primary_branch_id)).map((b) => {
                      const checked = (editForm.additional_branch_ids || []).map(Number).includes(Number(b.id));
                      return (
                        <label key={b.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: '#334155', cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) => {
                              const bId = Number(b.id);
                              if (e.target.checked) {
                                setEditForm({ ...editForm, additional_branch_ids: [...(editForm.additional_branch_ids || []), bId] });
                              } else {
                                setEditForm({ ...editForm, additional_branch_ids: (editForm.additional_branch_ids || []).filter(id => Number(id) !== bId) });
                              }
                            }}
                          />
                          <span>{b.name} ({b.code})</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setEditingUser(null)}
                  disabled={savingEdit}
                  style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingEdit}
                  style={{ padding: '8px 20px', borderRadius: '8px', border: 'none', backgroundColor: '#ef233c', color: '#ffffff', fontSize: '13px', fontWeight: 600, cursor: savingEdit ? 'not-allowed' : 'pointer' }}
                >
                  {savingEdit ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Invite Success Token Modal */}
      {inviteSuccessLink && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', maxWidth: '520px', width: '100%', padding: '24px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 10px', color: '#0f172a' }}>Invitation Generated</h3>
            <p style={{ margin: '0 0 12px', fontSize: '13px', color: '#64748b' }}>
              The activation link below can be provided to the invited user to establish their account credentials:
            </p>
            <div style={{ padding: '10px', backgroundColor: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '6px', fontFamily: 'monospace', fontSize: '12px', wordBreak: 'break-all', marginBottom: '18px' }}>
              {inviteSuccessLink}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              {inviteSuccessLink.startsWith('http') && (
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(inviteSuccessLink);
                    showToast('Invitation link copied.');
                  }}
                  style={{ padding: '8px 14px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#334155', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Copy Link
                </button>
              )}
              <button
                onClick={() => setInviteSuccessLink(null)}
                style={{ padding: '8px 18px', borderRadius: '8px', border: 'none', backgroundColor: '#ef233c', color: '#ffffff', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 5: COMPANY DOCUMENT ARCHIVE VIEW
// ─────────────────────────────────────────────────────────────────────────────
function DocumentArchiveView({ branchesList, showToast }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [branchFilter, setBranchFilter] = useState('');

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const res = await api.getCompanyDocumentsArchive({
        search: search || undefined,
        branch_id: branchFilter || undefined,
        limit: 50,
      });
      setDocuments(res || []);
    } catch (err) {
      showToast(err.message || 'Failed to load document archive.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, [search, branchFilter]);

  return (
    <div>
      <div style={{ marginBottom: '14px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 3px 0', color: '#0f172a', letterSpacing: '-0.01em' }}>
          Company Document Archive
        </h2>
        <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
          Company-wide repository archive across all branches with OCR metadata and indexing.
        </p>
      </div>

      {/* Filter and Search Bar */}
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '8px',
        border: '1px solid #e2e8f0',
        padding: '8px 12px',
        marginBottom: '12px',
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '8px',
      }}>
        <input
          type="text"
          placeholder="Search documents by filename or OCR extracted text..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1, minWidth: '240px', padding: '5px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '12px', height: '34px' }}
        />

        <select
          value={branchFilter}
          onChange={(e) => setBranchFilter(e.target.value)}
          style={{ padding: '5px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '12px', backgroundColor: '#ffffff', height: '34px' }}
        >
          <option value="">All Branches</option>
          {branchesList.map((b) => (
            <option key={b.id} value={b.id}>{b.name} ({b.code})</option>
          ))}
        </select>
      </div>

      {/* Documents Table */}
      <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', overflow: 'hidden' }}>
        <div style={{ padding: '8px 14px', backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: '#0f172a' }}>
            Archived Documents
          </span>
          <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '12px', backgroundColor: '#f1f5f9', color: '#64748b' }}>
            {documents.length} records
          </span>
        </div>

        {loading ? (
          <div style={{ padding: '40px 0', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
            <div className="spinner" style={{ margin: '0 auto 10px' }} />
            Loading archive...
          </div>
        ) : documents.length === 0 ? (
          <div style={{ padding: '36px 0', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
            No documents found in company archive.
          </div>
        ) : (
          <div style={{ overflowX: 'auto', width: '100%' }}>
            <table className="doc-table" style={{ width: '100%', tableLayout: 'fixed', minWidth: 840, borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                  <th style={{ width: 48, padding: '8px 10px' }}>Preview</th>
                  <th style={{ padding: '8px 10px' }}>Document Details</th>
                  <th style={{ width: 140, padding: '8px 10px' }}>Branch</th>
                  <th style={{ width: 100, padding: '8px 10px' }}>Type</th>
                  <th style={{ width: 105, padding: '8px 10px' }}>OCR Status</th>
                  <th style={{ width: 80, padding: '8px 10px' }}>File Size</th>
                  <th style={{ width: 110, whiteSpace: 'nowrap', padding: '8px 10px' }}>Upload Date</th>
                  <th style={{ width: 55, textAlign: 'center', padding: '8px 10px' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => {
                  const isPdf = doc.mime_type === 'application/pdf' || (doc.original_filename && doc.original_filename.toLowerCase().endsWith('.pdf'));
                  return (
                    <tr
                      key={doc.id}
                      className="doc-row"
                      style={{ borderBottom: '1px solid #f1f5f9' }}
                    >
                      {/* Thumbnail Preview */}
                      <td style={{ verticalAlign: 'middle', padding: '7px 10px', width: 48 }}>
                        <div
                          style={{
                            width: 36,
                            height: 36,
                            borderRadius: 4,
                            overflow: 'hidden',
                            backgroundColor: '#f1f5f9',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            border: '1px solid #e2e8f0',
                            flexShrink: 0,
                          }}
                        >
                          <img
                            src={api.getThumbnailUrl(doc.id)}
                            alt={doc.original_filename}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            onError={(e) => {
                              e.target.style.display = 'none';
                              if (e.target.nextSibling) {
                                e.target.nextSibling.style.display = 'flex';
                              }
                            }}
                          />
                          <div
                            style={{
                              display: 'none',
                              width: '100%',
                              height: '100%',
                              alignItems: 'center',
                              justifyContent: 'center',
                              color: isPdf ? '#dc2626' : '#2563eb',
                            }}
                          >
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
                            </svg>
                          </div>
                        </div>
                      </td>

                      {/* Document Details */}
                      <td style={{ verticalAlign: 'middle', padding: '7px 10px' }}>
                        <div>
                          <span
                            style={{
                              fontWeight: 600,
                              color: '#0f172a',
                              fontSize: '12.5px',
                              display: 'block',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                            title={doc.original_filename}
                          >
                            {doc.original_filename}
                          </span>
                          <span style={{ fontSize: '10.5px', color: '#94a3b8' }}>ID: #{doc.id}</span>
                        </div>
                      </td>

                      <td style={{ verticalAlign: 'middle', padding: '7px 10px', fontSize: '12px', color: '#334155', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <span style={{ backgroundColor: '#f1f5f9', color: '#334155', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>
                          {doc.branch_name || `Branch #${doc.branch_id}`}
                        </span>
                      </td>

                      <td style={{ verticalAlign: 'middle', padding: '7px 10px', fontSize: '12px', color: '#64748b' }}>
                        {doc.document_type || 'General'}
                      </td>

                      <td style={{ verticalAlign: 'middle', padding: '7px 10px' }}>
                        <span style={{
                          padding: '2px 7px',
                          borderRadius: '4px',
                          fontSize: '10.5px',
                          fontWeight: 700,
                          backgroundColor: doc.ocr_status === 'COMPLETED' ? '#ecfdf5' : doc.ocr_status === 'FAILED' ? '#fef2f2' : '#f0f9ff',
                          color: doc.ocr_status === 'COMPLETED' ? '#047857' : doc.ocr_status === 'FAILED' ? '#b91c1c' : '#0369a1',
                        }}>
                          {doc.ocr_status}
                        </span>
                      </td>

                      <td style={{ verticalAlign: 'middle', padding: '7px 10px', fontSize: '12px', color: '#64748b', whiteSpace: 'nowrap' }}>
                        {doc.file_size_bytes ? `${(doc.file_size_bytes / 1024).toFixed(1)} KB` : '—'}
                      </td>

                      <td style={{ verticalAlign: 'middle', padding: '7px 10px', fontSize: '12px', color: '#475569', whiteSpace: 'nowrap' }}>
                        {doc.created_at ? new Date(doc.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}
                      </td>

                      <td style={{ verticalAlign: 'middle', padding: '7px 10px', textAlign: 'center' }}>
                        <Link
                          to={`/documents/${doc.id}`}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            width: 24,
                            height: 24,
                            borderRadius: '50%',
                            backgroundColor: '#f1f5f9',
                            color: '#64748b',
                            textDecoration: 'none',
                          }}
                          title="View document"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
                          </svg>
                        </Link>
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
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 6: SECURITY SETTINGS VIEW
// ─────────────────────────────────────────────────────────────────────────────
function CompanySecurityView({ showToast }) {
  const [policy, setPolicy] = useState(null);
  const [mfaStatus, setMfaStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [updatingPolicy, setUpdatingPolicy] = useState(false);

  const [showEnrollModal, setShowEnrollModal] = useState(false);

  const loadSecurity = async () => {
    setLoading(true);
    try {
      const [polRes, statusRes] = await Promise.all([
        api.getCompanyMfaPolicy().catch(() => null),
        api.mfaStatus().catch(() => null),
      ]);
      if (polRes) setPolicy(polRes);
      if (statusRes) setMfaStatus(statusRes);
    } catch (err) {
      showToast(err.message || 'Failed to load security settings.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSecurity();
  }, []);

  const handleTogglePolicy = async () => {
    if (policy?.platform_mfa_enforced) return;
    const nextVal = !policy?.mfa_required_for_all;
    setUpdatingPolicy(true);
    try {
      const res = await api.updateCompanyMfaPolicy(nextVal);
      setPolicy(res);
      showToast(`MFA requirement for company users set to ${nextVal ? 'ENFORCED' : 'OPTIONAL'}.`);
    } catch (err) {
      showToast(err.message || 'Failed to update company MFA policy.', 'error');
    } finally {
      setUpdatingPolicy(false);
    }
  };

  const handleToggleDelegation = async () => {
    const nextVal = !policy?.allow_branch_mfa_control;
    setUpdatingPolicy(true);
    try {
      const res = await api.updateCompanyMfaPolicy({ allow_branch_mfa_control: nextVal });
      setPolicy(res);
      showToast(`Branch MFA policy delegation ${nextVal ? 'ENABLED' : 'DISABLED'}.`);
    } catch (err) {
      showToast(err.message || 'Failed to update branch MFA delegation.', 'error');
    } finally {
      setUpdatingPolicy(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '60px 0', textAlign: 'center', color: '#64748b' }}>
        <div className="spinner" style={{ margin: '0 auto 12px' }} />
        Loading security configuration...
      </div>
    );
  }

  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div>
        <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 4px 0', color: '#0f172a' }}>
          Security &amp; Authentication Policies
        </h2>
        <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
          Configure enterprise two-factor authentication rules and manage personal credentials.
        </p>
      </div>

      {/* Enterprise-Wide MFA Policy Card */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '16px 20px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }}>
          <div>
            <h3 style={{ fontSize: '14px', fontWeight: 700, margin: '0 0 4px', color: '#0f172a' }}>
              Enforce Multi-Factor Authentication (MFA) for All Company Users
            </h3>
            <p style={{ margin: 0, fontSize: '12.5px', color: '#64748b', lineHeight: '1.4' }}>
              When enabled, all Branch Administrators, Staff members, and Uploaders in your enterprise will be required to enroll and verify an authenticator app (Microsoft Authenticator, Google Authenticator) upon login.
            </p>

            {policy?.platform_mfa_enforced && (
              <div style={{ marginTop: '8px', display: 'inline-flex', alignItems: 'center', gap: '6px', backgroundColor: '#eff6ff', color: '#1e40af', padding: '4px 10px', borderRadius: '5px', fontSize: '11.5px', fontWeight: 600 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
                Locked by Platform Policy: Master Admin has mandated MFA platform-wide across all tenants.
              </div>
            )}
          </div>

          <button
            onClick={handleTogglePolicy}
            disabled={updatingPolicy || policy?.platform_mfa_enforced}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: policy?.mfa_required_for_all ? '#10b981' : '#cbd5e1',
              color: '#ffffff',
              fontSize: '11.5px',
              fontWeight: 700,
              cursor: (updatingPolicy || policy?.platform_mfa_enforced) ? 'not-allowed' : 'pointer',
              whiteSpace: 'nowrap',
              transition: 'background 0.2s',
            }}
          >
            {updatingPolicy ? 'Updating...' : (policy?.mfa_required_for_all ? 'ENFORCED' : 'OPTIONAL')}
          </button>
        </div>
      </div>

      {/* Branch MFA Delegation Policy Card */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '16px 20px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px' }}>
          <div>
            <h3 style={{ fontSize: '14px', fontWeight: 700, margin: '0 0 4px', color: '#0f172a' }}>
              Branch MFA Policy Delegation
            </h3>
            <p style={{ margin: 0, fontSize: '12.5px', color: '#64748b', lineHeight: '1.4' }}>
              Allow assigned Branch Administrators to mandate and configure MFA policies independently for their branches.
            </p>
          </div>

          <button
            onClick={handleToggleDelegation}
            disabled={updatingPolicy}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: policy?.allow_branch_mfa_control ? '#2563eb' : '#cbd5e1',
              color: '#ffffff',
              fontSize: '11.5px',
              fontWeight: 700,
              cursor: updatingPolicy ? 'not-allowed' : 'pointer',
              whiteSpace: 'nowrap',
              transition: 'background 0.2s',
            }}
          >
            {updatingPolicy ? 'Updating...' : (policy?.allow_branch_mfa_control ? 'DELEGATED' : 'DISABLED')}
          </button>
        </div>
      </div>

      {/* Personal MFA Setup for this Company Admin */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '16px 20px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 700, margin: '0 0 4px', color: '#0f172a' }}>
          Personal Administrator Authenticator (TOTP)
        </h3>
        <p style={{ margin: '0 0 12px', fontSize: '12.5px', color: '#64748b' }}>
          Protect your Company Administrator credentials with a time-based one-time password authenticator.
        </p>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 14px',
          borderRadius: '6px',
          backgroundColor: '#f8fafc',
          border: '1px solid #e2e8f0',
        }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: '12.5px', color: '#1e293b' }}>
              Status: {mfaStatus?.mfa_enabled ? (
                <span style={{ color: '#15803d' }}>Enabled &amp; Verified</span>
              ) : (
                <span style={{ color: '#64748b' }}>Not Configured</span>
              )}
            </div>
            <div style={{ fontSize: '11.5px', color: '#64748b', marginTop: '2px' }}>
              {mfaStatus?.mfa_enabled
                ? 'Your administrator login is protected with 2FA.'
                : 'Add extra protection against credential compromise.'}
            </div>
          </div>

          {!mfaStatus?.mfa_enabled ? (
            <button
              onClick={() => setShowEnrollModal(true)}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: '#ef233c',
                color: '#ffffff',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                boxShadow: '0 1px 3px rgba(239, 35, 60, 0.25)',
              }}
            >
              Set Up Authenticator App
            </button>
          ) : (
            <span style={{ fontSize: '11px', fontWeight: 700, color: '#047857', backgroundColor: '#ecfdf5', padding: '3px 8px', borderRadius: '10px' }}>
              ACTIVE
            </span>
          )}
        </div>
      </div>

      {showEnrollModal && (
        <MfaModal
          mode="self_enroll"
          onSuccess={() => {
            setShowEnrollModal(false);
            showToast('Personal MFA configured successfully.');
            loadSecurity();
          }}
          onCancel={() => setShowEnrollModal(false)}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 7: COMPANY AUDIT LOGS VIEW
// ─────────────────────────────────────────────────────────────────────────────
function CompanyAuditLogsView({ branchesList, showToast }) {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);

  // Filters
  const [actionFilter, setActionFilter] = useState('');
  const [branchFilter, setBranchFilter] = useState('');
  const [actorTypeFilter, setActorTypeFilter] = useState('');
  const [objectTypeFilter, setObjectTypeFilter] = useState('');

  const [selectedLog, setSelectedLog] = useState(null);

  const loadAuditLogs = async () => {
    setLoading(true);
    try {
      const res = await api.getCompanyAuditLogs({
        action: actionFilter || undefined,
        branch_id: branchFilter || undefined,
        actor_type: actorTypeFilter || undefined,
        object_type: objectTypeFilter || undefined,
        page,
        page_size: 25,
      });
      setLogs(res.items || []);
      setTotal(res.total || res.total_count || 0);
      setPages(res.pages || res.total_pages || 1);
    } catch (err) {
      showToast(err.message || 'Failed to load audit logs.', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAuditLogs();
  }, [actionFilter, branchFilter, actorTypeFilter, objectTypeFilter, page]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div>
        <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 4px 0', color: '#0f172a' }}>
          Company Audit Logs
        </h2>
        <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
          Immutable, tamper-resistant trail of all security, operational, and administrative actions within your enterprise.
        </p>
      </div>

      {/* Filter Bar */}
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '8px',
        border: '1px solid #e2e8f0',
        padding: '10px 14px',
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '10px',
        boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
      }}>
        <select
          value={actionFilter}
          onChange={(e) => { setActionFilter(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', borderRadius: '5px', border: '1px solid #cbd5e1', fontSize: '12px', backgroundColor: '#ffffff' }}
        >
          <option value="">All Actions</option>
          <option value="USER_LOGIN">User Login</option>
          <option value="USER_LOGOUT">User Logout</option>
          <option value="USER_INVITE">User Invite</option>
          <option value="USER_UPDATE">User Update</option>
          <option value="USER_DEACTIVATE">User Deactivate</option>
          <option value="USER_FORCE_LOGOUT">Force Logout</option>
          <option value="USER_MFA_RESET">MFA Reset</option>
          <option value="BRANCH_CREATE">Branch Create</option>
          <option value="BRANCH_UPDATE">Branch Update</option>
          <option value="BRANCH_TOGGLE">Branch Toggle</option>
          <option value="COMPANY_UPDATE">Company Profile Update</option>
        </select>

        <select
          value={branchFilter}
          onChange={(e) => { setBranchFilter(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', borderRadius: '5px', border: '1px solid #cbd5e1', fontSize: '12px', backgroundColor: '#ffffff' }}
        >
          <option value="">All Branches</option>
          {branchesList.map((b) => (
            <option key={b.id} value={b.id}>{b.name} ({b.code})</option>
          ))}
        </select>

        <select
          value={actorTypeFilter}
          onChange={(e) => { setActorTypeFilter(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', borderRadius: '5px', border: '1px solid #cbd5e1', fontSize: '12px', backgroundColor: '#ffffff' }}
        >
          <option value="">All Actor Types</option>
          <option value="user">User</option>
          <option value="company_admin">Company Admin</option>
          <option value="system">System</option>
        </select>

        <select
          value={objectTypeFilter}
          onChange={(e) => { setObjectTypeFilter(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', borderRadius: '5px', border: '1px solid #cbd5e1', fontSize: '12px', backgroundColor: '#ffffff' }}
        >
          <option value="">All Object Types</option>
          <option value="user">User</option>
          <option value="branch">Branch</option>
          <option value="company">Company</option>
          <option value="document">Document</option>
          <option value="invitation">Invitation</option>
        </select>
      </div>

      {/* Logs Table */}
      <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
        {loading ? (
          <div style={{ padding: '50px 0', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
            <div className="spinner" style={{ margin: '0 auto 10px' }} />
            Loading audit records...
          </div>
        ) : logs.length === 0 ? (
          <div style={{ padding: '40px 0', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
            No audit events found matching filters.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
            <thead>
              <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                <th style={{ padding: '8px 12px' }}>Timestamp</th>
                <th style={{ padding: '8px 12px' }}>Action</th>
                <th style={{ padding: '8px 12px' }}>Actor</th>
                <th style={{ padding: '8px 12px' }}>Target Object</th>
                <th style={{ padding: '8px 12px' }}>Branch</th>
                <th style={{ padding: '8px 12px' }}>IP Address</th>
                <th style={{ padding: '8px 12px', textAlign: 'right' }}>Details</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '8px 12px', color: '#64748b', whiteSpace: 'nowrap' }}>
                    {log.occurred_at ? new Date(log.occurred_at).toLocaleString() : '—'}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <span style={{
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '10.5px',
                      fontWeight: 600,
                      backgroundColor: '#f1f5f9',
                      color: '#1e293b',
                    }}>
                      {log.action}
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px', color: '#0f172a' }}>
                    {log.actor_type} #{log.actor_id}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#475569' }}>
                    {log.object_type || '—'} {log.object_id ? `(${log.object_id})` : ''}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#64748b' }}>
                    {log.branch_id ? `Branch #${log.branch_id}` : 'Company HQ'}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#94a3b8', fontFamily: 'monospace' }}>
                    {log.ip || '—'}
                  </td>
                  <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                    <button
                      onClick={() => setSelectedLog(log)}
                      style={{ padding: '3px 8px', borderRadius: '5px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontSize: '11px', fontWeight: 600, cursor: 'pointer' }}
                    >
                      Inspect
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        {pages > 1 && (
          <div style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #e2e8f0', fontSize: '13px' }}>
            <span style={{ color: '#64748b' }}>Page {page} of {pages} ({total} events)</span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                disabled={page <= 1}
                onClick={() => setPage(p => Math.max(1, p - 1))}
                style={{ padding: '5px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', cursor: page <= 1 ? 'not-allowed' : 'pointer' }}
              >
                Previous
              </button>
              <button
                disabled={page >= pages}
                onClick={() => setPage(p => Math.min(pages, p + 1))}
                style={{ padding: '5px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', cursor: page >= pages ? 'not-allowed' : 'pointer' }}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Inspect Audit Log Modal */}
      {selectedLog && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(3px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', maxWidth: '640px', width: '100%', padding: '28px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', borderBottom: '1px solid #e2e8f0', paddingBottom: '12px' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 2px', color: '#0f172a' }}>Audit Event #{selectedLog.id}</h3>
                <span style={{ fontSize: '12px', color: '#64748b' }}>{selectedLog.action} &middot; {new Date(selectedLog.occurred_at).toLocaleString()}</span>
              </div>
              <button onClick={() => setSelectedLog(null)} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#94a3b8' }}>&times;</button>
            </div>

            <div style={{ fontSize: '13px', marginBottom: '16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              <div><strong>Actor:</strong> {selectedLog.actor_type} #{selectedLog.actor_id}</div>
              <div><strong>IP:</strong> {selectedLog.ip || '—'}</div>
              <div><strong>Target Object:</strong> {selectedLog.object_type} #{selectedLog.object_id}</div>
              <div><strong>Branch:</strong> {selectedLog.branch_id ? `Branch #${selectedLog.branch_id}` : 'HQ'}</div>
              <div style={{ gridColumn: 'span 2' }}><strong>User Agent:</strong> <span style={{ color: '#64748b' }}>{selectedLog.user_agent || '—'}</span></div>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#475569', marginBottom: '6px' }}>Event Metadata (JSON):</div>
              <pre style={{
                backgroundColor: '#0f172a',
                color: '#f8fafc',
                padding: '12px',
                borderRadius: '6px',
                fontSize: '12px',
                fontFamily: 'monospace',
                overflowX: 'auto',
                maxHeight: '220px',
                margin: 0,
              }}>
                {JSON.stringify(selectedLog.metadata || {}, null, 2)}
              </pre>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setSelectedLog(null)}
                style={{ padding: '8px 18px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#334155', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
