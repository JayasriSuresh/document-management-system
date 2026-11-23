import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';
import ConfirmModal from '../components/ConfirmModal';
import BranchDashboardView from '../components/BranchDashboardView';

const STATUS_COLORS = {
  UPLOADED:   'status-uploaded',
  PROCESSING: 'status-processing',
  COMPLETED:  'status-completed',
  FAILED:     'status-failed',
};

const STATUS_LABELS = {
  UPLOADED:   'Uploaded',
  PROCESSING: 'Processing',
  COMPLETED:  'Completed',
  FAILED:     'Failed',
};

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  try {
    return new Date(isoStr).toLocaleDateString('en-IN', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  } catch {
    return isoStr;
  }
}

function formatIndianCurrency(amount, currency = 'INR') {
  if (amount === null || amount === undefined || isNaN(amount)) return null;
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: currency || 'INR',
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `₹${Number(amount).toFixed(2)}`;
  }
}

/**
 * Safely parses and renders search snippets without dangerouslySetInnerHTML.
 * Backend emits snippets with [[HL]]matched term[[/HL]].
 */
function SearchSnippet({ snippet }) {
  if (!snippet) return null;

  const parts = [];
  const regex = /\[\[HL\]\](.*?)\[\[\/HL\]\]/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(snippet)) !== null) {
    if (match.index > lastIndex) {
      parts.push(snippet.substring(lastIndex, match.index));
    }
    parts.push(
      <mark
        key={match.index}
        style={{
          backgroundColor: '#fef08a',
          color: '#854d0e',
          fontWeight: 600,
          padding: '1px 3px',
          borderRadius: 2,
        }}
      >
        {match[1]}
      </mark>
    );
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < snippet.length) {
    parts.push(snippet.substring(lastIndex));
  }

  return (
    <div
      style={{
        fontSize: 12,
        color: '#475569',
        marginTop: 5,
        lineHeight: 1.4,
        background: '#f8fafc',
        padding: '4px 8px',
        borderRadius: 4,
        borderLeft: '3px solid #3b82f6',
      }}
    >
      <span style={{ color: '#94a3b8', marginRight: 4 }}>Snippet:</span>
      "{parts}"
    </div>
  );
}

// SVG icons
const IconSearch = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
);
const IconFilter = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
  </svg>
);
const IconFilePdf = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
  </svg>
);
const IconFileImg = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
  </svg>
);
const IconFolder = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
  </svg>
);
const IconArrow = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
  </svg>
);
const IconRestore = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
  </svg>
);

export const INVOICE_TYPES = [
  'Tax Invoice',
  'Invoice',
  'Bill of Supply',
  'Cash Memo',
  'Retail Invoice',
  'Export Invoice',
  'Proforma Invoice',
  'Credit Note',
  'Debit Note',
  'Receipt Voucher',
  'Payment Voucher',
  'Refund Voucher',
  'Revised Invoice',
  'Delivery Challan',
  'Other',
];

const EMPTY_FILTERS = {
  dateFrom: '',
  dateTo: '',
  vendorName: '',
  invoiceNumber: '',
  gstin: '',
  amountMin: '',
  amountMax: '',
  documentType: '',
  invoiceType: '',
  branchId: '',
  status: '',
};

export default function DocumentsPage() {
  const { user, hasPermission } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [docs, setDocs] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [search, setSearch] = useState('');
  const [inputVal, setInputVal] = useState('');
  
  const tabFromUrl = searchParams.get('tab');
  const [viewTab, setViewTab] = useState(
    tabFromUrl === 'dashboard' ? 'dashboard' : (tabFromUrl === 'trash' ? 'trash' : 'active')
  );

  useEffect(() => {
    const t = searchParams.get('tab');
    if (t === 'dashboard') {
      navigate('/branch-dashboard', { replace: true });
    } else if (t === 'trash' && viewTab !== 'trash') {
      setViewTab('trash');
    } else if (!t && viewTab !== 'active') {
      setViewTab('active');
    }
  }, [searchParams, navigate, viewTab]);

  // Filter Panel state
  const [filterPanelOpen, setFilterPanelOpen] = useState(false);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [activeFilters, setActiveFilters] = useState(EMPTY_FILTERS);
  const [branches, setBranches] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [restoreDocTarget, setRestoreDocTarget] = useState(null);
  const [restoring, setRestoring] = useState(false);

  // Load branches for filter if admin
  useEffect(() => {
    if (user?.role === 'GLOBAL_ADMIN' || user?.role === 'ADMIN') {
      api.listCompanyBranches().then(data => {
        if (Array.isArray(data)) setBranches(data);
        else if (data?.items) setBranches(data.items);
      }).catch(() => {});
    }
  }, [user]);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.listDocuments({
        page,
        pageSize,
        search,
        status: activeFilters.status || undefined,
        branchId: activeFilters.branchId || undefined,
        dateFrom: activeFilters.dateFrom || undefined,
        dateTo: activeFilters.dateTo || undefined,
        vendorName: activeFilters.vendorName || undefined,
        invoiceNumber: activeFilters.invoiceNumber || undefined,
        gstin: activeFilters.gstin || undefined,
        amountMin: activeFilters.amountMin || undefined,
        amountMax: activeFilters.amountMax || undefined,
        documentType: activeFilters.documentType || undefined,
        invoiceType: activeFilters.invoiceType || undefined,
        includeDeleted: viewTab === 'trash',
        paginate: true,
      });

      if (data && data.items) {
        setDocs(data.items);
        setTotalCount(data.total);
        setTotalPages(data.total_pages || 1);
      } else if (Array.isArray(data)) {
        setDocs(data);
        setTotalCount(data.length);
        setTotalPages(1);
      }
    } catch (err) {
      setError(err.message || 'Failed to fetch documents.');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, activeFilters, viewTab]);

  useEffect(() => {
    if (viewTab === 'dashboard') return;
    fetchDocs();
    const interval = setInterval(() => {
      fetchDocs();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchDocs, viewTab]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    setSearch(inputVal);
  };

  const handleApplyFilters = () => {
    setActiveFilters({ ...filters });
    setPage(1);
  };

  const handleResetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setActiveFilters(EMPTY_FILTERS);
    setInputVal('');
    setSearch('');
    setPage(1);
  };

  const handleRemoveSingleFilter = (key) => {
    const updated = { ...activeFilters, [key]: '' };
    setFilters(prev => ({ ...prev, [key]: '' }));
    setActiveFilters(updated);
    setPage(1);
  };

  const handleTabChange = (newTab) => {
    if (newTab === 'dashboard') {
      navigate('/branch-dashboard');
      return;
    }
    setViewTab(newTab);
    setPage(1);
    setDocs([]);
    setSearchParams(newTab === 'active' ? {} : { tab: newTab });
  };

  const handleRestore = async () => {
    if (!restoreDocTarget) return;
    setRestoring(true);
    try {
      await api.restoreDocument(restoreDocTarget.id);
      setRestoreDocTarget(null);
      fetchDocs();
    } catch (err) {
      setError(err.message || 'Failed to restore document.');
      setRestoreDocTarget(null);
    } finally {
      setRestoring(false);
    }
  };

  const activeFilterCount = Object.entries(activeFilters).filter(([_, v]) => Boolean(v)).length;
  const canViewBranchDashboard = hasPermission('branch.view') || user?.role === 'ADMIN' || user?.role === 'GLOBAL_ADMIN';

  return (
    <div className="page-content">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h2 className="page-title">
            {viewTab === 'dashboard'
              ? 'Branch Operational Dashboard'
              : (user?.role === 'GLOBAL_ADMIN' ? 'All Documents' : user?.role === 'ADMIN' ? `Documents — ${user?.tenant_name}` : 'My Documents')}
          </h2>
          <p className="page-subtitle">
            {viewTab === 'dashboard'
              ? `Operational metrics, OCR throughput, and background jobs for ${user?.tenant_name}`
              : (user?.role === 'STAFF' ? 'Your documents from the last 30 days' : `Documents across ${user?.tenant_name}`)}
          </p>
        </div>
        {hasPermission('document.upload') && (
          <button className="btn btn-primary" onClick={() => navigate('/upload')}>
            Upload Documents
          </button>
        )}
      </div>

      {/* Tabs: Active vs Trash vs Branch Dashboard */}
      <div style={{ display: 'flex', gap: 8, borderBottom: '1px solid #e2e8f0', marginBottom: 16 }}>
        <button
          onClick={() => handleTabChange('active')}
          style={{
            padding: '8px 16px',
            border: 'none',
            background: 'none',
            fontWeight: 600,
            fontSize: 14,
            cursor: 'pointer',
            borderBottom: viewTab === 'active' ? '2px solid var(--brand, #ef233c)' : '2px solid transparent',
            color: viewTab === 'active' ? 'var(--brand, #ef233c)' : '#64748b',
          }}
        >
          Active Documents
        </button>
        <button
          onClick={() => handleTabChange('trash')}
          style={{
            padding: '8px 16px',
            border: 'none',
            background: 'none',
            fontWeight: 600,
            fontSize: 14,
            cursor: 'pointer',
            borderBottom: viewTab === 'trash' ? '2px solid var(--brand, #ef233c)' : '2px solid transparent',
            color: viewTab === 'trash' ? 'var(--brand, #ef233c)' : '#64748b',
          }}
        >
          Trash &amp; Archive
        </button>
        {canViewBranchDashboard && (
          <button
            onClick={() => handleTabChange('dashboard')}
            style={{
              padding: '8px 16px',
              border: 'none',
              background: 'none',
              fontWeight: 600,
              fontSize: 14,
              cursor: 'pointer',
              borderBottom: viewTab === 'dashboard' ? '2px solid var(--brand, #ef233c)' : '2px solid transparent',
              color: viewTab === 'dashboard' ? 'var(--brand, #ef233c)' : '#64748b',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
            </svg>
            Branch Dashboard
          </button>
        )}
      </div>

      {viewTab === 'dashboard' ? (
        <BranchDashboardView
          branchesList={branches}
          onNavigateToDocs={() => handleTabChange('active')}
        />
      ) : (
        <>

      {/* Primary Search Bar & Controls */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <form onSubmit={handleSearchSubmit} className="search-bar" style={{ flex: 1, minWidth: 280, margin: 0 }}>
          <span className="search-icon"><IconSearch /></span>
          <input
            type="text"
            value={inputVal}
            onChange={e => setInputVal(e.target.value)}
            placeholder="Search OCR content, invoice #, vendor, GSTIN, filename…"
            className="search-input"
          />
          {inputVal && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => { setInputVal(''); setSearch(''); setPage(1); }}
            >
              Clear
            </button>
          )}
          <button type="submit" className="btn btn-primary btn-sm">Search</button>
        </form>

        {/* Filter Panel Toggle */}
        <button
          type="button"
          onClick={() => setFilterPanelOpen(open => !open)}
          className={`btn ${filterPanelOpen || activeFilterCount > 0 ? 'btn-primary' : 'btn-secondary'}`}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
        >
          <IconFilter />
          <span>Filters</span>
          {activeFilterCount > 0 && (
            <span
              style={{
                backgroundColor: filterPanelOpen || activeFilterCount > 0 ? '#fff' : 'var(--brand, #ef233c)',
                color: filterPanelOpen || activeFilterCount > 0 ? 'var(--brand, #ef233c)' : '#fff',
                fontSize: 11,
                fontWeight: 700,
                borderRadius: '50%',
                width: 18,
                height: 18,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginLeft: 2,
              }}
            >
              {activeFilterCount}
            </span>
          )}
        </button>

        {/* Quick Status Dropdown */}
        {viewTab === 'active' && (
          <select
            value={activeFilters.status}
            onChange={(e) => {
              const val = e.target.value;
              setFilters(f => ({ ...f, status: val }));
              setActiveFilters(f => ({ ...f, status: val }));
              setPage(1);
            }}
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              border: '1px solid #cbd5e1',
              background: '#fff',
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            <option value="">All Statuses</option>
            <option value="COMPLETED">Completed</option>
            <option value="PROCESSING">Processing</option>
            <option value="UPLOADED">Uploaded</option>
            <option value="FAILED">Failed</option>
          </select>
        )}

        {/* Page Size Selector */}
        <select
          value={pageSize}
          onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
          style={{
            padding: '8px 12px',
            borderRadius: 6,
            border: '1px solid #cbd5e1',
            background: '#fff',
            fontSize: 13,
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          <option value="10">10 / page</option>
          <option value="20">20 / page</option>
          <option value="50">50 / page</option>
          <option value="100">100 / page</option>
        </select>
      </div>

      {/* Expandable Advanced Filters Panel */}
      {filterPanelOpen && (
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid #cbd5e1',
            borderRadius: 8,
            padding: 16,
            marginBottom: 16,
            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: '#1e293b' }}>Structured Filters</h4>
            <span style={{ fontSize: 12, color: '#64748b' }}>Combine multiple filters to refine your search</span>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
              gap: 12,
              marginBottom: 14,
            }}
          >
            {/* Vendor Name */}
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#475569', marginBottom: 4 }}>
                Vendor / Seller Name
              </label>
              <input
                type="text"
                placeholder="e.g. Lucky Computers"
                value={filters.vendorName}
                onChange={e => setFilters({ ...filters, vendorName: e.target.value })}
                style={{ width: '100%', padding: '6px 10px', fontSize: 13, borderRadius: 6, border: '1px solid #cbd5e1' }}
              />
            </div>

            {/* Invoice Number */}
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#475569', marginBottom: 4 }}>
                Invoice Number
              </label>
              <input
                type="text"
                placeholder="e.g. LC-25-26/4280"
                value={filters.invoiceNumber}
                onChange={e => setFilters({ ...filters, invoiceNumber: e.target.value })}
                style={{ width: '100%', padding: '6px 10px', fontSize: 13, borderRadius: 6, border: '1px solid #cbd5e1' }}
              />
            </div>

            {/* GSTIN */}
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#475569', marginBottom: 4 }}>
                GSTIN
              </label>
              <input
                type="text"
                placeholder="e.g. 33BLAPS0819R1ZQ"
                value={filters.gstin}
                onChange={e => setFilters({ ...filters, gstin: e.target.value })}
                style={{ width: '100%', padding: '6px 10px', fontSize: 13, borderRadius: 6, border: '1px solid #cbd5e1' }}
              />
            </div>

            {/* Amount Min */}
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#475569', marginBottom: 4 }}>
                Min Amount (₹)
              </label>
              <input
                type="text"
                placeholder="e.g. 50,000 or 50000"
                value={filters.amountMin}
                onChange={e => setFilters({ ...filters, amountMin: e.target.value })}
                style={{ width: '100%', padding: '6px 10px', fontSize: 13, borderRadius: 6, border: '1px solid #cbd5e1' }}
              />
            </div>

            {/* Amount Max */}
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#475569', marginBottom: 4 }}>
                Max Amount (₹)
              </label>
              <input
                type="text"
                placeholder="e.g. 1,00,000 or 100000"
                value={filters.amountMax}
                onChange={e => setFilters({ ...filters, amountMax: e.target.value })}
                style={{ width: '100%', padding: '6px 10px', fontSize: 13, borderRadius: 6, border: '1px solid #cbd5e1' }}
              />
            </div>

            {/* Date From */}
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#475569', marginBottom: 4 }}>
                Date From
              </label>
              <input
                type="date"
                value={filters.dateFrom}
                onChange={e => setFilters({ ...filters, dateFrom: e.target.value })}
                style={{ width: '100%', padding: '6px 10px', fontSize: 13, borderRadius: 6, border: '1px solid #cbd5e1' }}
              />
            </div>

            {/* Date To */}
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#475569', marginBottom: 4 }}>
                Date To
              </label>
              <input
                type="date"
                value={filters.dateTo}
                onChange={e => setFilters({ ...filters, dateTo: e.target.value })}
                style={{ width: '100%', padding: '6px 10px', fontSize: 13, borderRadius: 6, border: '1px solid #cbd5e1' }}
              />
            </div>

            {/* Invoice Type */}
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#475569', marginBottom: 4 }}>
                Invoice Type
              </label>
              <select
                value={filters.invoiceType}
                onChange={e => setFilters({ ...filters, invoiceType: e.target.value })}
                style={{ width: '100%', padding: '6px 10px', fontSize: 13, borderRadius: 6, border: '1px solid #cbd5e1', background: '#fff' }}
              >
                <option value="">All Invoice Types</option>
                {INVOICE_TYPES.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            {/* Document / File Format */}
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#475569', marginBottom: 4 }}>
                File Format
              </label>
              <select
                value={filters.documentType}
                onChange={e => setFilters({ ...filters, documentType: e.target.value })}
                style={{ width: '100%', padding: '6px 10px', fontSize: 13, borderRadius: 6, border: '1px solid #cbd5e1', background: '#fff' }}
              >
                <option value="">All Formats</option>
                <option value="pdf">PDF Documents</option>
                <option value="image">Image Files</option>
              </select>
            </div>

            {/* Branch Selector (for Admins with branches) */}
            {branches.length > 0 && (
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#475569', marginBottom: 4 }}>
                  Branch
                </label>
                <select
                  value={filters.branchId}
                  onChange={e => setFilters({ ...filters, branchId: e.target.value })}
                  style={{ width: '100%', padding: '6px 10px', fontSize: 13, borderRadius: 6, border: '1px solid #cbd5e1', background: '#fff' }}
                >
                  <option value="">All Assigned Branches</option>
                  {branches.map(b => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', borderTop: '1px solid #f1f5f9', paddingTop: 12 }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleResetFilters}
            >
              Reset All
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleApplyFilters}
            >
              Apply Filters
            </button>
          </div>
        </div>
      )}

      {/* Active Filter Chips */}
      {activeFilterCount > 0 && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
          <span style={{ fontSize: 12, color: '#64748b', fontWeight: 600 }}>Active Filters:</span>
          {activeFilters.vendorName && (
            <span className="badge" style={{ backgroundColor: '#e0f2fe', color: '#0369a1', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 4, fontSize: 12 }}>
              Vendor: {activeFilters.vendorName}
              <button type="button" onClick={() => handleRemoveSingleFilter('vendorName')} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#0369a1', fontWeight: 'bold' }}>×</button>
            </span>
          )}
          {activeFilters.invoiceNumber && (
            <span className="badge" style={{ backgroundColor: '#e0f2fe', color: '#0369a1', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 4, fontSize: 12 }}>
              Invoice #: {activeFilters.invoiceNumber}
              <button type="button" onClick={() => handleRemoveSingleFilter('invoiceNumber')} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#0369a1', fontWeight: 'bold' }}>×</button>
            </span>
          )}
          {activeFilters.gstin && (
            <span className="badge" style={{ backgroundColor: '#e0f2fe', color: '#0369a1', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 4, fontSize: 12 }}>
              GSTIN: {activeFilters.gstin}
              <button type="button" onClick={() => handleRemoveSingleFilter('gstin')} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#0369a1', fontWeight: 'bold' }}>×</button>
            </span>
          )}
          {activeFilters.amountMin && (
            <span className="badge" style={{ backgroundColor: '#fef3c7', color: '#92400e', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 4, fontSize: 12 }}>
              Min: ₹{activeFilters.amountMin}
              <button type="button" onClick={() => handleRemoveSingleFilter('amountMin')} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#92400e', fontWeight: 'bold' }}>×</button>
            </span>
          )}
          {activeFilters.amountMax && (
            <span className="badge" style={{ backgroundColor: '#fef3c7', color: '#92400e', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 4, fontSize: 12 }}>
              Max: ₹{activeFilters.amountMax}
              <button type="button" onClick={() => handleRemoveSingleFilter('amountMax')} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#92400e', fontWeight: 'bold' }}>×</button>
            </span>
          )}
          {activeFilters.dateFrom && (
            <span className="badge" style={{ backgroundColor: '#f1f5f9', color: '#334155', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 4, fontSize: 12 }}>
              From: {activeFilters.dateFrom}
              <button type="button" onClick={() => handleRemoveSingleFilter('dateFrom')} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#334155', fontWeight: 'bold' }}>×</button>
            </span>
          )}
          {activeFilters.dateTo && (
            <span className="badge" style={{ backgroundColor: '#f1f5f9', color: '#334155', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 4, fontSize: 12 }}>
              To: {activeFilters.dateTo}
              <button type="button" onClick={() => handleRemoveSingleFilter('dateTo')} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#334155', fontWeight: 'bold' }}>×</button>
            </span>
          )}
          {activeFilters.invoiceType && (
            <span className="badge" style={{ backgroundColor: '#fef2f2', color: '#b91c1c', border: '1px solid #fecaca', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 4, fontSize: 12 }}>
              Invoice Type: {activeFilters.invoiceType}
              <button type="button" onClick={() => handleRemoveSingleFilter('invoiceType')} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#b91c1c', fontWeight: 'bold' }}>×</button>
            </span>
          )}
          {activeFilters.documentType && (
            <span className="badge" style={{ backgroundColor: '#f1f5f9', color: '#334155', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', borderRadius: 4, fontSize: 12 }}>
              Format: {activeFilters.documentType.toUpperCase()}
              <button type="button" onClick={() => handleRemoveSingleFilter('documentType')} style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#334155', fontWeight: 'bold' }}>×</button>
            </span>
          )}
          <button
            type="button"
            onClick={handleResetFilters}
            style={{ border: 'none', background: 'none', color: 'var(--brand, #ef233c)', fontSize: 12, textDecoration: 'underline', cursor: 'pointer' }}
          >
            Clear All
          </button>
        </div>
      )}

      {error && <div className="alert alert-error">{error}</div>}

      {/* Documents table */}
      {loading && docs.length === 0 ? (
        <div className="table-container">
          <div className="loading-state"><div className="spinner" /><p>Loading documents…</p></div>
        </div>
      ) : docs.length === 0 ? (
        <div className="table-container">
          <div className="empty-state">
            <div className="empty-icon"><IconFolder /></div>
            <h3>{viewTab === 'trash' ? 'Trash is empty' : search || activeFilterCount > 0 ? 'No matching documents' : 'No documents yet'}</h3>
            <p>
              {viewTab === 'trash'
                ? 'No soft-deleted documents found in your organization.'
                : search || activeFilterCount > 0
                ? 'No documents match the specified search or filter criteria. Try adjusting your query.'
                : 'Upload your first document to begin.'}
            </p>
            {viewTab === 'active' && !search && activeFilterCount === 0 && (
              <button className="btn btn-primary" onClick={() => navigate('/upload')}>
                Upload Documents
              </button>
            )}
            {(search || activeFilterCount > 0) && (
              <button className="btn btn-secondary" onClick={handleResetFilters}>
                Reset Search &amp; Filters
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="table-container">
          <div className="table-header-bar">
            <span className="table-header-bar-title">
              {viewTab === 'trash'
                ? 'Deleted Archive'
                : search
                ? `Results for "${search}"`
                : activeFilterCount > 0
                ? 'Filtered Documents'
                : 'Documents'}
            </span>
            <span className="table-header-bar-count">
              Showing {docs.length} of {totalCount} document{totalCount !== 1 ? 's' : ''}
            </span>
          </div>

          <table className="doc-table">
            <thead>
              <tr>
                <th style={{ width: 50 }}>Preview</th>
                <th>Document Details</th>
                <th>Branch</th>
                <th>Uploaded By</th>
                <th>Size</th>
                <th>Status</th>
                <th>{viewTab === 'trash' ? 'Deleted At' : 'Date'}</th>
                <th style={{ width: 60 }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => {
                const isPdf = doc.mime_type === 'application/pdf' || (doc.original_filename && doc.original_filename.toLowerCase().endsWith('.pdf'));
                const vendor = doc.vendor_name || doc.seller_name;
                const totalFormatted = formatIndianCurrency(doc.grand_total ?? doc.invoice_amount, doc.currency);

                return (
                  <tr
                    key={doc.id}
                    className="doc-row"
                    onClick={() => viewTab === 'active' && navigate(`/documents/${doc.id}`)}
                    style={{ cursor: viewTab === 'active' ? 'pointer' : 'default' }}
                  >
                    {/* Thumbnail preview cell */}
                    <td style={{ verticalAlign: 'middle', padding: '8px 12px' }}>
                      <div
                        style={{
                          width: 44,
                          height: 44,
                          borderRadius: 6,
                          overflow: 'hidden',
                          backgroundColor: '#f1f5f9',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          border: '1px solid #e2e8f0',
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
                          {isPdf ? <IconFilePdf /> : <IconFileImg />}
                        </div>
                      </div>
                    </td>

                    {/* Document details cell */}
                    <td>
                      <div>
                        <span className="filename" style={{ fontWeight: 600, color: '#0f172a' }}>
                          {doc.original_filename}
                        </span>

                        {/* Extracted metadata badges */}
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4, alignItems: 'center' }}>
                          {doc.invoice_type && (
                            <span
                              style={{
                                fontSize: 11,
                                fontWeight: 600,
                                padding: '2px 6px',
                                borderRadius: 4,
                                backgroundColor: '#fef2f2',
                                color: '#b91c1c',
                                border: '1px solid #fecaca',
                              }}
                            >
                              {doc.invoice_type}
                            </span>
                          )}
                          {doc.invoice_number && (
                            <span
                              style={{
                                fontSize: 11,
                                fontWeight: 600,
                                padding: '2px 6px',
                                borderRadius: 4,
                                backgroundColor: '#f1f5f9',
                                color: '#334155',
                                border: '1px solid #cbd5e1',
                              }}
                            >
                              INV: {doc.invoice_number}
                            </span>
                          )}
                          {vendor && (
                            <span
                              style={{
                                fontSize: 11,
                                fontWeight: 500,
                                padding: '2px 6px',
                                borderRadius: 4,
                                backgroundColor: '#ecfdf5',
                                color: '#065f46',
                                border: '1px solid #a7f3d0',
                              }}
                            >
                              {vendor}
                            </span>
                          )}
                          {totalFormatted && (
                            <span
                              style={{
                                fontSize: 11,
                                fontWeight: 700,
                                padding: '2px 6px',
                                borderRadius: 4,
                                backgroundColor: '#eff6ff',
                                color: '#1d4ed8',
                                border: '1px solid #bfdbfe',
                              }}
                            >
                              {totalFormatted}
                            </span>
                          )}
                        </div>

                        {/* Highlighted OCR snippet */}
                        <SearchSnippet snippet={doc.snippet} />
                      </div>
                    </td>

                    <td>{doc.branch_name || 'Main'}</td>
                    <td>{doc.uploader_name}</td>
                    <td>{formatBytes(doc.file_size)}</td>
                    <td>
                      <span className={`status-badge ${STATUS_COLORS[doc.ocr_status] || ''}`}>
                        {STATUS_LABELS[doc.ocr_status] || doc.ocr_status}
                      </span>
                    </td>
                    <td>{formatDate(viewTab === 'trash' ? doc.deleted_at : (doc.invoice_date || doc.created_at))}</td>
                    <td>
                      {viewTab === 'trash' ? (
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            setRestoreDocTarget(doc);
                          }}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
                        >
                          <IconRestore /> Restore
                        </button>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}><IconArrow /></span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Pagination bar */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '12px 16px',
              borderTop: '1px solid #e2e8f0',
              fontSize: 13,
              color: '#64748b',
            }}
          >
            <div>
              Page {page} of {totalPages} ({totalCount} total)
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
              >
                Previous
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
        </>
      )}

      {/* Restore Confirmation Modal */}
      {restoreDocTarget && (
        <ConfirmModal
          isOpen={!!restoreDocTarget}
          title="Restore Document"
          message={`Are you sure you want to restore "${restoreDocTarget.original_filename}"? It will be returned to active status and made available to authorized users.`}
          confirmLabel={restoring ? "Restoring..." : "Restore Document"}
          confirmVariant="primary"
          onConfirm={handleRestore}
          onCancel={() => setRestoreDocTarget(null)}
        />
      )}
    </div>
  );
}
