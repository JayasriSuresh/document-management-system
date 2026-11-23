import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';

function formatCurrency(amount, currency = 'INR') {
  if (amount === undefined || amount === null || amount === '') return '—';
  const num = parseFloat(String(amount).replace(/[^0-9.-]+/g, ''));
  if (isNaN(num)) return String(amount);
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: currency || 'INR',
    maximumFractionDigits: 2,
  }).format(num);
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleDateString('en-IN', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  } catch {
    return isoStr;
  }
}

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

export default function InvoicesPage() {
  const { user, hasPermission } = useAuth();
  const navigate = useNavigate();

  const [invoices, setInvoices] = useState([]);
  const [activeTab, setActiveTab] = useState('all'); // 'all' | 'copy' | 'generated'
  const [statusFilter, setStatusFilter] = useState('all');
  const [invoiceTypeFilter, setInvoiceTypeFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [inputVal, setInputVal] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');

  // Modals state
  const [previewInvoice, setPreviewInvoice] = useState(null);
  const [approvalModalInvoice, setApprovalModalInvoice] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [cancelModalInvoice, setCancelModalInvoice] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = {
        search: search || undefined,
        kind: activeTab === 'all' ? undefined : activeTab,
        status: statusFilter === 'all' ? undefined : statusFilter,
        invoice_type: invoiceTypeFilter === 'all' ? undefined : invoiceTypeFilter,
      };
      const data = await api.listInvoices(params);
      setInvoices(data || []);
    } catch (err) {
      setError(err.message || 'Failed to fetch invoices');
    } finally {
      setLoading(false);
    }
  }, [search, activeTab, statusFilter, invoiceTypeFilter]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const handleSearch = (e) => {
    e.preventDefault();
    setSearch(inputVal);
  };

  // Metrics calculation
  const totalCount = invoices.length;
  const copiesCount = invoices.filter((i) => i.kind === 'copy').length;
  const salesCount = invoices.filter((i) => i.kind === 'generated').length;
  const pendingCount = invoices.filter((i) => i.status === 'pending_approval').length;
  const totalBilledValue = invoices.reduce((sum, inv) => {
    if (!inv.grand_total) return sum;
    const n = parseFloat(String(inv.grand_total).replace(/[^0-9.-]+/g, ''));
    return sum + (isNaN(n) ? 0 : n);
  }, 0);

  // Approve action
  const handleApprove = async () => {
    if (!approvalModalInvoice) return;
    setActionLoading(true);
    setError('');
    setActionSuccess('');
    try {
      const res = await api.approveSalesInvoice(approvalModalInvoice.id);
      setActionSuccess(`Sales Invoice ${res.invoice_number || `#${approvalModalInvoice.id}`} approved and issued successfully!`);
      setApprovalModalInvoice(null);
      fetchInvoices();
    } catch (err) {
      setError(err.message || 'Failed to approve invoice');
    } finally {
      setActionLoading(false);
    }
  };

  // Reject action
  const handleReject = async () => {
    if (!approvalModalInvoice) return;
    setActionLoading(true);
    setError('');
    setActionSuccess('');
    try {
      await api.rejectSalesInvoice(approvalModalInvoice.id, rejectReason);
      setActionSuccess(`Invoice #${approvalModalInvoice.id} rejected.`);
      setApprovalModalInvoice(null);
      setRejectReason('');
      fetchInvoices();
    } catch (err) {
      setError(err.message || 'Failed to reject invoice');
    } finally {
      setActionLoading(false);
    }
  };

  // Cancel action
  const handleCancel = async () => {
    if (!cancelModalInvoice) return;
    if (!cancelReason.trim()) {
      setError('A cancellation reason is mandatory');
      return;
    }
    setActionLoading(true);
    setError('');
    setActionSuccess('');
    try {
      await api.cancelSalesInvoice(cancelModalInvoice.id, cancelReason);
      setActionSuccess(`Invoice ${cancelModalInvoice.invoice_number || `#${cancelModalInvoice.id}`} cancelled.`);
      setCancelModalInvoice(null);
      setCancelReason('');
      fetchInvoices();
    } catch (err) {
      setError(err.message || 'Failed to cancel invoice');
    } finally {
      setActionLoading(false);
    }
  };

  // Submit Draft for approval directly from table
  const handleSubmitDraft = async (invId) => {
    setActionLoading(true);
    setError('');
    setActionSuccess('');
    try {
      await api.submitSalesInvoice(invId);
      setActionSuccess(`Invoice #${invId} submitted for approval.`);
      fetchInvoices();
    } catch (err) {
      setError(err.message || 'Failed to submit invoice draft');
    } finally {
      setActionLoading(false);
    }
  };

  // Discard draft
  const handleDiscardDraft = async (invId) => {
    if (!window.confirm('Are you sure you want to discard this draft invoice?')) return;
    setActionLoading(true);
    setError('');
    setActionSuccess('');
    try {
      await api.discardSalesInvoiceDraft(invId);
      setActionSuccess(`Draft invoice #${invId} deleted.`);
      fetchInvoices();
    } catch (err) {
      setError(err.message || 'Failed to discard draft');
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="page-content">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h2 className="page-title">Invoices Repository</h2>
          <p className="page-subtitle">
            Manage incoming Standardised Copies (Supplier Invoices) and issue GST-compliant Outbound Sales Invoices.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button className="btn btn-secondary" onClick={() => navigate('/documents')}>
            View Documents
          </button>
          {hasPermission('invoice.sales_create') && (
            <button className="btn btn-primary" onClick={() => navigate('/invoices/new')}>
              + Create Sales Invoice
            </button>
          )}
        </div>
      </div>

      {actionSuccess && <div className="alert alert-success" style={{ marginBottom: '1.25rem' }}>{actionSuccess}</div>}
      {error && <div className="alert alert-error" style={{ marginBottom: '1.25rem' }}>{error}</div>}

      {/* Stats Cards */}
      <div className="stats-bar">
        <div className="stat-card">
          <div className="stat-label">Total Invoices</div>
          <div className="stat-value">{totalCount}</div>
          <div className="stat-sub">{copiesCount} Copies · {salesCount} Sales</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Total Billed Value</div>
          <div className="stat-value" style={{ color: 'var(--brand)' }}>
            {formatCurrency(totalBilledValue)}
          </div>
          <div className="stat-sub">cumulative grand total</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Pending Approval</div>
          <div className="stat-value" style={{ color: pendingCount > 0 ? '#d97706' : 'var(--text-primary)' }}>
            {pendingCount}
          </div>
          <div className="stat-sub">sales invoices awaiting review</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Active Branch</div>
          <div className="stat-value" style={{ fontSize: '1.15rem', color: 'var(--text-primary)' }}>
            {user?.tenant_name || 'Organization'}
          </div>
          <div className="stat-sub">{user?.role} Access</div>
        </div>
      </div>

      {/* Filter Tabs & Search Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', gap: '1rem', flexWrap: 'wrap' }}>
        {/* Tabs */}
        <div style={{ display: 'inline-flex', background: 'var(--bg-subtle)', padding: '0.25rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
          <button
            type="button"
            className={`btn btn-sm ${activeTab === 'all' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: 'var(--radius-sm)' }}
            onClick={() => setActiveTab('all')}
          >
            All Invoices ({totalCount})
          </button>
          <button
            type="button"
            className={`btn btn-sm ${activeTab === 'copy' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: 'var(--radius-sm)' }}
            onClick={() => setActiveTab('copy')}
          >
            Standardised Copies ({copiesCount})
          </button>
          <button
            type="button"
            className={`btn btn-sm ${activeTab === 'generated' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: 'var(--radius-sm)' }}
            onClick={() => setActiveTab('generated')}
          >
            Sales Invoices ({salesCount})
          </button>
        </div>

        {/* Filter Controls: Status and Invoice Type */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          {/* Status Dropdown Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Status:</label>
            <select
              className="form-control"
              style={{ width: 'auto', padding: '0.35rem 0.75rem', fontSize: '0.8125rem' }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All Statuses</option>
              <option value="available">Available</option>
              <option value="draft">Draft</option>
              <option value="pending_approval">Pending Approval</option>
              <option value="approved">Approved</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>

          {/* Invoice Type Dropdown Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Invoice Type:</label>
            <select
              className="form-control"
              style={{ width: 'auto', padding: '0.35rem 0.75rem', fontSize: '0.8125rem' }}
              value={invoiceTypeFilter}
              onChange={(e) => setInvoiceTypeFilter(e.target.value)}
            >
              <option value="all">All Types</option>
              {INVOICE_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Search Bar */}
      <form onSubmit={handleSearch} className="search-bar" style={{ marginBottom: '1.5rem' }}>
        <span className="search-icon">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        </span>
        <input
          type="text"
          className="search-input"
          placeholder="Search by Invoice Number, Customer, Seller, or original document..."
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
        />
        {inputVal && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setInputVal('');
              setSearch('');
            }}
          >
            Clear
          </button>
        )}
        <button type="submit" className="btn btn-primary btn-sm">
          Search
        </button>
      </form>

      {/* Invoices Table */}
      <div className="table-container">
        <div className="table-header-bar">
          <span className="table-header-bar-title">
            {activeTab === 'copy'
              ? 'Standardised Copies (Supplier Invoices)'
              : activeTab === 'generated'
              ? 'Outbound Sales Invoices'
              : 'All Invoices'}
          </span>
          <span className="table-header-bar-count">
            {invoices.length} {invoices.length === 1 ? 'record' : 'records'}
          </span>
        </div>

        {loading && invoices.length === 0 ? (
          <div className="loading-state" style={{ padding: '3rem', textAlign: 'center' }}>
            <div className="spinner" />
            <p style={{ marginTop: '1rem', color: 'var(--text-muted)' }}>Loading invoices…</p>
          </div>
        ) : invoices.length === 0 ? (
          <div style={{ padding: '3rem 2rem', textAlign: 'center' }}>
            <div style={{ width: '52px', height: '52px', margin: '0 auto 1rem', background: 'var(--bg-subtle)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
            </div>
            <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
              No invoices found
            </h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', maxWidth: '400px', margin: '0 auto 1.5rem auto' }}>
              {activeTab === 'generated'
                ? 'Create your first outbound sales invoice using the button below.'
                : 'Upload and process documents to generate standardised copies.'}
            </p>
            {activeTab === 'generated' ? (
              hasPermission('invoice.sales_create') ? (
                <button className="btn btn-primary" onClick={() => navigate('/invoices/new')}>
                  Create Sales Invoice
                </button>
              ) : null
            ) : (
              <button className="btn btn-primary" onClick={() => navigate('/documents')}>
                Browse Documents
              </button>
            )}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="doc-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Invoice No.</th>
                  <th>Date</th>
                  <th>Billed By (Seller)</th>
                  <th>Billed To (Buyer)</th>
                  <th>Grand Total</th>
                  <th>Status</th>
                  <th>Source / FY</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv) => {
                  const isCopy = inv.kind === 'copy';
                  const isSales = inv.kind === 'generated';

                  return (
                    <tr key={`${inv.kind}-${inv.id}`}>
                      {/* Type Badge */}
                      <td>
                        <div style={{ display: 'inline-flex', flexDirection: 'column', gap: '0.2rem' }}>
                          <span
                            style={{
                              fontSize: '0.72rem',
                              fontWeight: 700,
                              background: '#fef2f2',
                              color: '#b91c1c',
                              border: '1px solid #fecaca',
                              padding: '0.15rem 0.45rem',
                              borderRadius: 'var(--radius-sm)',
                              letterSpacing: '0.02em',
                              display: 'inline-block',
                            }}
                          >
                            {inv.invoice_type || 'Tax Invoice'}
                          </span>
                          <span
                            style={{
                              fontSize: '0.65rem',
                              fontWeight: 600,
                              color: isCopy ? '#0369a1' : '#047857',
                              background: isCopy ? '#e0f2fe' : '#ecfdf5',
                              padding: '0.08rem 0.35rem',
                              borderRadius: 'var(--radius-sm)',
                              display: 'inline-block',
                              width: 'fit-content',
                            }}
                          >
                            {isCopy ? (inv.copy_version ? `Copy v${inv.copy_version}` : 'Standardised Copy') : 'Sales Invoice'}
                          </span>
                          {inv.is_stale && (
                            <span
                              style={{
                                fontSize: '0.65rem',
                                fontWeight: 600,
                                background: '#fffbeb',
                                color: '#b45309',
                                border: '1px solid #fde68a',
                                padding: '0.08rem 0.35rem',
                                borderRadius: 'var(--radius-sm)',
                              }}
                            >
                              ⚠️ Stale
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Invoice Number */}
                      <td>
                        <span
                          style={{
                            fontFamily: 'monospace',
                            fontWeight: 700,
                            color: inv.invoice_number ? 'var(--brand)' : 'var(--text-muted)',
                            background: inv.invoice_number ? 'var(--brand-light)' : 'var(--bg-subtle)',
                            padding: '0.2rem 0.45rem',
                            borderRadius: 'var(--radius-sm)',
                            display: 'inline-block',
                            fontStyle: inv.invoice_number ? 'normal' : 'italic',
                          }}
                        >
                          {inv.invoice_number || `(Draft #${inv.id})`}
                        </span>
                      </td>

                      {/* Date */}
                      <td>
                        <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                          {inv.invoice_date || formatDate(inv.created_at)}
                        </span>
                      </td>

                      {/* Billed By */}
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.875rem' }}>
                          {inv.seller_name || '—'}
                        </div>
                        {inv.seller_gstin && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                            GST: {inv.seller_gstin}
                          </div>
                        )}
                      </td>

                      {/* Billed To */}
                      <td>
                        <div style={{ fontWeight: 500, color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                          {inv.buyer_name || inv.customer_name || '—'}
                        </div>
                      </td>

                      {/* Grand Total */}
                      <td>
                        <span
                          style={{
                            fontWeight: 700,
                            fontSize: '0.9375rem',
                            color: inv.status === 'cancelled' ? 'var(--text-muted)' : 'var(--success)',
                            textDecoration: inv.status === 'cancelled' ? 'line-through' : 'none',
                          }}
                        >
                          {formatCurrency(inv.grand_total, inv.currency)}
                        </span>
                      </td>

                      {/* Status */}
                      <td>
                        <span
                          style={{
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            padding: '0.2rem 0.5rem',
                            borderRadius: 'var(--radius-sm)',
                            textTransform: 'capitalize',
                            display: 'inline-block',
                            background:
                              inv.status === 'approved' || inv.status === 'available'
                                ? '#f0fdf4'
                                : inv.status === 'pending_approval'
                                ? '#fffbeb'
                                : inv.status === 'cancelled'
                                ? '#fef2f2'
                                : '#f3f4f6',
                            color:
                              inv.status === 'approved' || inv.status === 'available'
                                ? '#15803d'
                                : inv.status === 'pending_approval'
                                ? '#b45309'
                                : inv.status === 'cancelled'
                                ? '#b91c1c'
                                : '#4b5563',
                            border: `1px solid ${
                              inv.status === 'approved' || inv.status === 'available'
                                ? '#bbf7d0'
                                : inv.status === 'pending_approval'
                                ? '#fde68a'
                                : inv.status === 'cancelled'
                                ? '#fecaca'
                                : '#e5e7eb'
                            }`,
                          }}
                        >
                          {inv.status ? inv.status.replace('_', ' ') : 'available'}
                        </span>
                      </td>

                      {/* Source Document or FY */}
                      <td>
                        {isCopy && inv.document_id ? (
                          <button
                            onClick={() => navigate(`/documents/${inv.document_id}`)}
                            className="btn btn-ghost btn-sm"
                            style={{
                              textAlign: 'left',
                              padding: '0.2rem 0.4rem',
                              fontSize: '0.8125rem',
                              color: 'var(--text-secondary)',
                              textDecoration: 'underline',
                            }}
                            title={inv.original_filename}
                          >
                            📄 {inv.original_filename?.length > 18
                              ? inv.original_filename.slice(0, 16) + '…'
                              : inv.original_filename || `Doc #${inv.document_id}`}
                          </button>
                        ) : (
                          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                            {inv.financial_year ? `FY ${inv.financial_year}` : inv.tenant_name || '—'}
                          </span>
                        )}
                      </td>

                      {/* Actions */}
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '0.35rem', alignItems: 'center' }}>
                          {isCopy ? (
                            <>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => setPreviewInvoice(inv)}
                                title="Quick View Standardised Copy"
                              >
                                View
                              </button>
                              <a
                                href={api.getDirectInvoicePdfUrl(inv.id, true)}
                                download={`supplier_copy_${inv.id}.pdf`}
                                target="_blank"
                                rel="noreferrer"
                                className="btn btn-primary btn-sm"
                                title="Download PDF"
                              >
                                Download
                              </a>
                            </>
                          ) : (
                            /* Outbound Sales Invoice Actions */
                            <>
                              {inv.status === 'draft' && (
                                <>
                                  <button
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => navigate(`/invoices/${inv.id}/edit`)}
                                  >
                                    Edit
                                  </button>
                                  <button
                                    className="btn btn-primary btn-sm"
                                    onClick={() => handleSubmitDraft(inv.id)}
                                    disabled={actionLoading}
                                  >
                                    Submit
                                  </button>
                                  <button
                                    className="btn btn-ghost btn-sm"
                                    style={{ color: 'var(--danger)', padding: '0.2rem 0.4rem' }}
                                    onClick={() => handleDiscardDraft(inv.id)}
                                    title="Discard Draft"
                                  >
                                    🗑️
                                  </button>
                                </>
                              )}

                              {inv.status === 'pending_approval' && (
                                <button
                                  className="btn btn-primary btn-sm"
                                  style={{ background: '#d97706', borderColor: '#d97706' }}
                                  onClick={() => setApprovalModalInvoice(inv)}
                                >
                                  Review & Approve
                                </button>
                              )}

                              {inv.status === 'approved' && (
                                <>
                                  <button
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => setPreviewInvoice(inv)}
                                  >
                                    View
                                  </button>
                                  <a
                                    href={api.getSalesInvoicePdfUrl(inv.id, true)}
                                    download={`sales_invoice_${inv.invoice_number ? inv.invoice_number.replace(/\//g, '_') : inv.id}.pdf`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="btn btn-primary btn-sm"
                                  >
                                    Download
                                  </a>
                                  <button
                                    className="btn btn-ghost btn-sm"
                                    style={{ color: 'var(--danger)', fontSize: '0.75rem' }}
                                    onClick={() => setCancelModalInvoice(inv)}
                                  >
                                    Cancel
                                  </button>
                                </>
                              )}

                              {inv.status === 'cancelled' && (
                                <>
                                  <button
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => setPreviewInvoice(inv)}
                                  >
                                    View
                                  </button>
                                  <span style={{ fontSize: '0.75rem', color: 'var(--danger)', fontStyle: 'italic' }}>
                                    Cancelled
                                  </span>
                                </>
                              )}
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal Quick Preview */}
      {previewInvoice && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(4px)',
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1.5rem',
          }}
          onClick={() => setPreviewInvoice(null)}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: 'var(--radius-lg)',
              width: '100%',
              maxWidth: '960px',
              height: '85vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: 'var(--shadow-xl)',
              overflow: 'hidden',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '1rem 1.5rem',
                borderBottom: '1px solid var(--border)',
                background: 'var(--bg-subtle)',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      padding: '0.15rem 0.45rem',
                      borderRadius: 'var(--radius-sm)',
                      background: previewInvoice.kind === 'copy' ? '#e0f2fe' : '#ecfdf5',
                      color: previewInvoice.kind === 'copy' ? '#0369a1' : '#047857',
                    }}
                  >
                    {previewInvoice.kind === 'copy' ? 'Standardised Supplier Copy' : 'Outbound Sales Invoice'}
                  </span>
                  <h3 style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                    {previewInvoice.invoice_number || `Invoice #${previewInvoice.id}`}
                  </h3>
                </div>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', margin: '0.2rem 0 0 0' }}>
                  {previewInvoice.seller_name} → {previewInvoice.buyer_name || previewInvoice.customer_name} · {formatCurrency(previewInvoice.grand_total, previewInvoice.currency)}
                </p>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <a
                  href={
                    previewInvoice.kind === 'copy'
                      ? api.getDirectInvoicePdfUrl(previewInvoice.id, true)
                      : api.getSalesInvoicePdfUrl(previewInvoice.id, true)
                  }
                  download={`invoice_${previewInvoice.id}.pdf`}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-primary btn-sm"
                >
                  Download PDF
                </a>
                {previewInvoice.document_id && (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => navigate(`/documents/${previewInvoice.document_id}`)}
                  >
                    View Document
                  </button>
                )}
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ padding: '0.2rem 0.6rem' }}
                  onClick={() => setPreviewInvoice(null)}
                >
                  Close
                </button>
              </div>
            </div>

            {/* Modal Body / PDF iframe */}
            <div style={{ flex: 1, background: '#525659' }}>
              <iframe
                src={
                  previewInvoice.kind === 'copy'
                    ? `${api.getDirectInvoicePdfUrl(previewInvoice.id)}#toolbar=0`
                    : `${api.getSalesInvoicePdfUrl(previewInvoice.id)}#toolbar=0`
                }
                title={`Invoice ${previewInvoice.invoice_number || previewInvoice.id}`}
                style={{ width: '100%', height: '100%', border: 'none' }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Review & Approve Modal */}
      {approvalModalInvoice && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(4px)',
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1.5rem',
          }}
          onClick={() => setApprovalModalInvoice(null)}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: 'var(--radius-lg)',
              width: '100%',
              maxWidth: '600px',
              padding: '1.75rem',
              boxShadow: 'var(--shadow-xl)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.5rem 0', color: 'var(--text-primary)' }}>
              Approve Outbound Sales Invoice
            </h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Approval will lock the invoice, assign the next consecutive invoice number from the sequence inside a database transaction, and generate the immutable signed PDF.
            </p>

            <div style={{ background: 'var(--bg-subtle)', padding: '1rem', borderRadius: 'var(--radius-md)', marginBottom: '1.25rem', border: '1px solid var(--border)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', fontSize: '0.875rem' }}>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Customer:</span>{' '}
                  <strong style={{ color: 'var(--text-primary)' }}>{approvalModalInvoice.customer_name || approvalModalInvoice.buyer_name}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Grand Total:</span>{' '}
                  <strong style={{ color: 'var(--brand)' }}>{formatCurrency(approvalModalInvoice.grand_total)}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Created By:</span>{' '}
                  <span style={{ color: 'var(--text-secondary)' }}>User #{approvalModalInvoice.created_by}</span>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Financial Year:</span>{' '}
                  <span style={{ color: 'var(--text-secondary)' }}>{approvalModalInvoice.financial_year || 'Current'}</span>
                </div>
              </div>

              {user?.id === approvalModalInvoice.created_by && (
                <div style={{ marginTop: '0.75rem', padding: '0.5rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--radius-sm)', color: '#b91c1c', fontSize: '0.8125rem' }}>
                  ⚠️ <strong>Separation of Duties Enforced:</strong> You created this invoice. Per financial compliance controls, another authorized administrator must review and approve it.
                </div>
              )}
            </div>

            <div style={{ marginBottom: '1.25rem' }}>
              <label className="form-label" style={{ fontWeight: 600 }}>Rejection Reason (if rejecting)</label>
              <textarea
                className="form-control"
                rows="2"
                placeholder="Optional explanation if sending back to draft..."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setApprovalModalInvoice(null)}
              >
                Close
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                style={{ color: 'var(--danger)', border: '1px solid var(--border)' }}
                onClick={handleReject}
                disabled={actionLoading}
              >
                Reject to Draft
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleApprove}
                disabled={actionLoading || user?.id === approvalModalInvoice.created_by}
              >
                {actionLoading ? 'Issuing…' : 'Approve & Issue'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cancellation Modal */}
      {cancelModalInvoice && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(4px)',
            zIndex: 1000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1.5rem',
          }}
          onClick={() => setCancelModalInvoice(null)}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: 'var(--radius-lg)',
              width: '100%',
              maxWidth: '520px',
              padding: '1.75rem',
              boxShadow: 'var(--shadow-xl)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.5rem 0', color: 'var(--danger)' }}>
              Cancel Invoice {cancelModalInvoice.invoice_number}
            </h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Cancelled invoices remain permanently recorded for GST audit trails and cannot be reused or deleted. A cancellation reason is mandatory.
            </p>

            <div style={{ marginBottom: '1.25rem' }}>
              <label className="form-label" style={{ fontWeight: 600 }}>Cancellation Reason *</label>
              <textarea
                className="form-control"
                rows="3"
                placeholder="State the reason (e.g., Customer cancellation, clerical correction, duplicate order)..."
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                required
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setCancelModalInvoice(null)}
              >
                Back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                style={{ background: 'var(--danger)', borderColor: 'var(--danger)' }}
                onClick={handleCancel}
                disabled={actionLoading || !cancelReason.trim()}
              >
                {actionLoading ? 'Cancelling…' : 'Confirm Cancellation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
