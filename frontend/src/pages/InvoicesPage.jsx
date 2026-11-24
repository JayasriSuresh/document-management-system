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
      <div className="page-header" style={{ marginBottom: 14 }}>
        <div>
          <h2 className="page-title" style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 3px 0', color: '#0f172a', letterSpacing: '-0.01em' }}>Invoices Repository</h2>
          <p className="page-subtitle" style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>
            Manage incoming Standardised Copies (Supplier Invoices) and issue GST-compliant Outbound Sales Invoices.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-secondary" onClick={() => navigate('/documents')} style={{ fontSize: '12px', padding: '6px 12px', borderRadius: '6px' }}>
            View Documents
          </button>
          {hasPermission('invoice.sales_create') && (
            <button className="btn btn-primary" onClick={() => navigate('/invoices/new')} style={{ fontSize: '12px', padding: '6px 14px', borderRadius: '6px', fontWeight: 500 }}>
              + Create Sales Invoice
            </button>
          )}
        </div>
      </div>

      {actionSuccess && <div className="alert alert-success" style={{ marginBottom: '1.25rem' }}>{actionSuccess}</div>}
      {error && <div className="alert alert-error" style={{ marginBottom: '1.25rem' }}>{error}</div>}

      {/* Stats Cards */}
      <div className="stats-bar" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '14px' }}>
        <div className="stat-card" style={{ padding: '12px 14px', borderRadius: '8px', border: '1px solid #e2e8f0', backgroundColor: '#ffffff' }}>
          <div className="stat-label" style={{ fontSize: '10.5px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#64748b', marginBottom: '2px' }}>Total Invoices</div>
          <div className="stat-value" style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>{totalCount}</div>
          <div className="stat-sub" style={{ fontSize: '11px', color: '#94a3b8' }}>{copiesCount} Copies · {salesCount} Sales</div>
        </div>

        <div className="stat-card" style={{ padding: '12px 14px', borderRadius: '8px', border: '1px solid #e2e8f0', backgroundColor: '#ffffff' }}>
          <div className="stat-label" style={{ fontSize: '10.5px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#64748b', marginBottom: '2px' }}>Total Billed Value</div>
          <div className="stat-value" style={{ fontSize: '20px', fontWeight: 700, color: '#ef233c' }}>
            {formatCurrency(totalBilledValue)}
          </div>
          <div className="stat-sub" style={{ fontSize: '11px', color: '#94a3b8' }}>cumulative grand total</div>
        </div>

        <div className="stat-card" style={{ padding: '12px 14px', borderRadius: '8px', border: '1px solid #e2e8f0', backgroundColor: '#ffffff' }}>
          <div className="stat-label" style={{ fontSize: '10.5px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#64748b', marginBottom: '2px' }}>Pending Approval</div>
          <div className="stat-value" style={{ fontSize: '20px', fontWeight: 700, color: pendingCount > 0 ? '#d97706' : '#0f172a' }}>
            {pendingCount}
          </div>
          <div className="stat-sub" style={{ fontSize: '11px', color: '#94a3b8' }}>sales invoices awaiting review</div>
        </div>

        <div className="stat-card" style={{ padding: '12px 14px', borderRadius: '8px', border: '1px solid #e2e8f0', backgroundColor: '#ffffff' }}>
          <div className="stat-label" style={{ fontSize: '10.5px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#64748b', marginBottom: '2px' }}>Active Branch</div>
          <div className="stat-value" style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
            {user?.tenant_name || 'Organization'}
          </div>
          <div className="stat-sub" style={{ fontSize: '11px', color: '#94a3b8' }}>{user?.role} Access</div>
        </div>
      </div>

      {/* Filter Tabs & Search Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', gap: '8px', flexWrap: 'wrap' }}>
        {/* Tabs */}
        <div style={{ display: 'inline-flex', background: '#f1f5f9', padding: '3px', borderRadius: '6px', border: '1px solid #e2e8f0', gap: '2px' }}>
          <button
            type="button"
            className={`btn btn-sm ${activeTab === 'all' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: '4px', fontSize: '12px', padding: '4px 10px', height: '28px' }}
            onClick={() => setActiveTab('all')}
          >
            All Invoices ({totalCount})
          </button>
          <button
            type="button"
            className={`btn btn-sm ${activeTab === 'copy' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: '4px', fontSize: '12px', padding: '4px 10px', height: '28px' }}
            onClick={() => setActiveTab('copy')}
          >
            Standardised Copies ({copiesCount})
          </button>
          <button
            type="button"
            className={`btn btn-sm ${activeTab === 'generated' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ borderRadius: '4px', fontSize: '12px', padding: '4px 10px', height: '28px' }}
            onClick={() => setActiveTab('generated')}
          >
            Sales Invoices ({salesCount})
          </button>
        </div>

        {/* Filter Controls: Status and Invoice Type */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {/* Status Dropdown Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <label style={{ fontSize: '12px', color: '#64748b', fontWeight: 500 }}>Status:</label>
            <select
              style={{ width: 'auto', padding: '5px 10px', fontSize: '12px', height: '34px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff' }}
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <label style={{ fontSize: '12px', color: '#64748b', fontWeight: 500 }}>Type:</label>
            <select
              style={{ width: 'auto', padding: '5px 10px', fontSize: '12px', height: '34px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff' }}
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
      <form onSubmit={handleSearch} style={{ display: 'flex', gap: '8px', marginBottom: '12px', alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: 1, display: 'flex', alignItems: 'center' }}>
          <span style={{ position: 'absolute', left: '10px', color: '#94a3b8', display: 'flex', alignItems: 'center' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          </span>
          <input
            type="text"
            placeholder="Search by Invoice Number, Customer, Seller, or original document..."
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            style={{ width: '100%', height: '34px', fontSize: '12px', padding: '5px 10px 5px 32px', borderRadius: '6px', border: '1px solid #cbd5e1' }}
          />
        </div>
        {inputVal && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setInputVal('');
              setSearch('');
            }}
            style={{ height: '34px', fontSize: '12px', padding: '0 10px' }}
          >
            Clear
          </button>
        )}
        <button
          type="submit"
          className="btn btn-primary btn-sm"
          style={{ height: '34px', fontSize: '12px', padding: '0 14px', borderRadius: '6px' }}
        >
          Search
        </button>
      </form>

      {/* Invoices Table */}
      <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', overflow: 'hidden' }}>
        <div style={{ padding: '8px 14px', backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: '#0f172a' }}>
            {activeTab === 'copy'
              ? 'Standardised Copies (Supplier Invoices)'
              : activeTab === 'generated'
              ? 'Outbound Sales Invoices'
              : 'All Invoices'}
          </span>
          <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '12px', backgroundColor: '#f1f5f9', color: '#64748b' }}>
            {invoices.length} {invoices.length === 1 ? 'record' : 'records'}
          </span>
        </div>

        {loading && invoices.length === 0 ? (
          <div className="loading-state" style={{ padding: '3rem', textAlign: 'center' }}>
            <div className="spinner" />
            <p style={{ marginTop: '1rem', color: '#64748b', fontSize: '13px' }}>Loading invoices…</p>
          </div>
        ) : invoices.length === 0 ? (
          <div style={{ padding: '3rem 2rem', textAlign: 'center' }}>
            <div style={{ width: '48px', height: '48px', margin: '0 auto 1rem', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
            </div>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#0f172a', marginBottom: '0.25rem' }}>
              No invoices found
            </h3>
            <p style={{ color: '#64748b', fontSize: '13px', maxWidth: '400px', margin: '0 auto 1.5rem auto' }}>
              {activeTab === 'generated'
                ? 'Create your first outbound sales invoice using the button below.'
                : 'Upload and process documents to generate standardised copies.'}
            </p>
            {activeTab === 'generated' ? (
              hasPermission('invoice.sales_create') ? (
                <button className="btn btn-primary" onClick={() => navigate('/invoices/new')} style={{ fontSize: '12px', padding: '6px 14px', borderRadius: '6px' }}>
                  Create Sales Invoice
                </button>
              ) : null
            ) : (
              <button className="btn btn-primary" onClick={() => navigate('/documents')} style={{ fontSize: '12px', padding: '6px 14px', borderRadius: '6px' }}>
                Browse Documents
              </button>
            )}
          </div>
        ) : (
          <div style={{ overflowX: 'auto', width: '100%' }}>
            <table style={{ width: '100%', tableLayout: 'fixed', minWidth: '840px', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                  <th style={{ padding: '8px 10px', width: '10%' }}>Type</th>
                  <th style={{ padding: '8px 10px', width: '13%' }}>Invoice No.</th>
                  <th style={{ padding: '8px 10px', width: '8%' }}>Date</th>
                  <th style={{ padding: '8px 10px', width: '17%' }}>Billed By (Seller)</th>
                  <th style={{ padding: '8px 10px', width: '15%' }}>Billed To (Buyer)</th>
                  <th style={{ padding: '8px 10px', width: '10%' }}>Grand Total</th>
                  <th style={{ padding: '8px 10px', width: '8%' }}>Status</th>
                  <th style={{ padding: '8px 10px', width: '10%' }}>Source / FY</th>
                  <th style={{ padding: '8px 10px', width: '9%', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv) => {
                  const isCopy = inv.kind === 'copy';
                  const isSales = inv.kind === 'generated';

                  return (
                    <tr key={`${inv.kind}-${inv.id}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      {/* Type Badge */}
                      <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                        <div style={{ fontWeight: 600, color: '#0f172a', fontSize: '11.5px', whiteSpace: 'nowrap' }}>
                          {inv.invoice_type || 'Tax Invoice'}
                        </div>
                        <div style={{ fontSize: '10px', color: isCopy ? '#0284c7' : '#16a34a', fontWeight: 500, whiteSpace: 'nowrap' }}>
                          {isCopy ? (inv.copy_version ? `Copy v${inv.copy_version}` : 'Standardised') : 'Sales Invoice'}
                        </div>
                        {inv.is_stale && (
                          <span
                            style={{
                              fontSize: '9.5px',
                              fontWeight: 600,
                              background: '#fffbeb',
                              color: '#b45309',
                              border: '1px solid #fde68a',
                              padding: '1px 4px',
                              borderRadius: '3px',
                              display: 'inline-block',
                              marginTop: '2px',
                            }}
                          >
                            ⚠️ Stale
                          </span>
                        )}
                      </td>

                      {/* Invoice Number */}
                      <td style={{ padding: '7px 10px', verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
                        <span
                          style={{
                            fontFamily: 'monospace',
                            fontWeight: 600,
                            fontSize: '11px',
                            color: inv.invoice_number ? '#ef233c' : '#64748b',
                            backgroundColor: inv.invoice_number ? '#fff1f2' : '#f8fafc',
                            padding: '1px 5px',
                            borderRadius: '4px',
                            border: inv.invoice_number ? '1px solid #fecdd3' : '1px solid #e2e8f0',
                            display: 'inline-block',
                            whiteSpace: 'nowrap',
                            fontStyle: inv.invoice_number ? 'normal' : 'italic',
                          }}
                        >
                          {inv.invoice_number || `(Draft #${inv.id})`}
                        </span>
                      </td>

                      {/* Date */}
                      <td style={{ padding: '7px 10px', verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
                        <span style={{ fontSize: '11.5px', color: '#475569', whiteSpace: 'nowrap' }}>
                          {inv.invoice_date || formatDate(inv.created_at)}
                        </span>
                      </td>

                      {/* Billed By */}
                      <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                        <div style={{ fontWeight: 600, color: '#0f172a', fontSize: '12px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '170px' }} title={inv.seller_name}>
                          {inv.seller_name || '—'}
                        </div>
                        {inv.seller_gstin && (
                          <div style={{ fontSize: '10.5px', color: '#64748b', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                            GST: {inv.seller_gstin}
                          </div>
                        )}
                      </td>

                      {/* Billed To */}
                      <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                        <div style={{ fontWeight: 500, color: '#334155', fontSize: '12px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '150px' }} title={inv.buyer_name || inv.customer_name}>
                          {inv.buyer_name || inv.customer_name || '—'}
                        </div>
                      </td>

                      {/* Grand Total */}
                      <td style={{ padding: '7px 10px', verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
                        <span
                          style={{
                            fontWeight: 700,
                            fontSize: '12px',
                            color: inv.status === 'cancelled' ? '#94a3b8' : '#166534',
                            textDecoration: inv.status === 'cancelled' ? 'line-through' : 'none',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {formatCurrency(inv.grand_total, inv.currency)}
                        </span>
                      </td>

                      {/* Status */}
                      <td style={{ padding: '7px 10px', verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
                        <span
                          style={{
                            fontSize: '10.5px',
                            fontWeight: 600,
                            padding: '1px 6px',
                            borderRadius: '4px',
                            textTransform: 'capitalize',
                            display: 'inline-block',
                            whiteSpace: 'nowrap',
                            backgroundColor:
                              inv.status === 'approved' || inv.status === 'available'
                                ? '#f0fdf4'
                                : inv.status === 'pending_approval'
                                ? '#fffbeb'
                                : inv.status === 'cancelled'
                                ? '#fef2f2'
                                : '#f1f5f9',
                            color:
                              inv.status === 'approved' || inv.status === 'available'
                                ? '#15803d'
                                : inv.status === 'pending_approval'
                                ? '#b45309'
                                : inv.status === 'cancelled'
                                ? '#b91c1c'
                                : '#475569',
                            border: `1px solid ${
                              inv.status === 'approved' || inv.status === 'available'
                                ? '#bbf7d0'
                                : inv.status === 'pending_approval'
                                ? '#fde68a'
                                : inv.status === 'cancelled'
                                ? '#fecaca'
                                : '#cbd5e1'
                            }`,
                          }}
                        >
                          {inv.status ? inv.status.replace('_', ' ') : 'available'}
                        </span>
                      </td>

                      {/* Source Document or FY */}
                      <td style={{ padding: '7px 10px', verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
                        {isCopy && inv.document_id ? (
                          <button
                            onClick={() => navigate(`/documents/${inv.document_id}`)}
                            style={{
                              background: 'none',
                              border: 'none',
                              textAlign: 'left',
                              padding: 0,
                              fontSize: '11px',
                              color: '#ef233c',
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              maxWidth: '120px',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                            title={inv.original_filename}
                          >
                            📄 {inv.original_filename || `Doc #${inv.document_id}`}
                          </button>
                        ) : (
                          <span style={{ fontSize: '11px', color: '#64748b', whiteSpace: 'nowrap' }}>
                            {inv.financial_year ? `FY ${inv.financial_year}` : inv.tenant_name || '—'}
                          </span>
                        )}
                      </td>

                      {/* Actions */}
                      <td style={{ padding: '7px 10px', textAlign: 'right', verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
                        <div style={{ display: 'inline-flex', gap: '4px', alignItems: 'center' }}>
                          {isCopy ? (
                            <>
                              <button
                                onClick={() => setPreviewInvoice(inv)}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: '5px',
                                  border: '1px solid #cbd5e1',
                                  backgroundColor: '#ffffff',
                                  color: '#334155',
                                  fontSize: '11.5px',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                                title="Quick View Standardised Copy"
                              >
                                View
                              </button>
                              <a
                                href={api.getDirectInvoicePdfUrl(inv.id, true)}
                                download={`supplier_copy_${inv.id}.pdf`}
                                target="_blank"
                                rel="noreferrer"
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: '5px',
                                  border: '1px solid #cbd5e1',
                                  backgroundColor: '#ffffff',
                                  color: '#ef233c',
                                  fontSize: '11.5px',
                                  fontWeight: 600,
                                  textDecoration: 'none',
                                  display: 'inline-block',
                                }}
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
                                    onClick={() => navigate(`/invoices/${inv.id}/edit`)}
                                    style={{
                                      padding: '4px 8px',
                                      borderRadius: '5px',
                                      border: '1px solid #cbd5e1',
                                      backgroundColor: '#ffffff',
                                      color: '#334155',
                                      fontSize: '11.5px',
                                      fontWeight: 600,
                                      cursor: 'pointer',
                                    }}
                                  >
                                    Edit
                                  </button>
                                  <button
                                    onClick={() => handleSubmitDraft(inv.id)}
                                    disabled={actionLoading}
                                    style={{
                                      padding: '4px 8px',
                                      borderRadius: '5px',
                                      border: 'none',
                                      backgroundColor: '#ef233c',
                                      color: '#ffffff',
                                      fontSize: '11.5px',
                                      fontWeight: 600,
                                      cursor: 'pointer',
                                    }}
                                  >
                                    Submit
                                  </button>
                                  <button
                                    onClick={() => handleDiscardDraft(inv.id)}
                                    title="Discard Draft"
                                    style={{
                                      background: 'none',
                                      border: 'none',
                                      color: '#dc2626',
                                      padding: '2px 4px',
                                      cursor: 'pointer',
                                    }}
                                  >
                                    🗑️
                                  </button>
                                </>
                              )}

                              {inv.status === 'pending_approval' && (
                                <button
                                  onClick={() => setApprovalModalInvoice(inv)}
                                  style={{
                                    padding: '4px 10px',
                                    borderRadius: '5px',
                                    border: 'none',
                                    backgroundColor: '#d97706',
                                    color: '#ffffff',
                                    fontSize: '11.5px',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                  }}
                                >
                                  Review
                                </button>
                              )}

                              {inv.status === 'approved' && (
                                <>
                                  <button
                                    onClick={() => setPreviewInvoice(inv)}
                                    style={{
                                      padding: '4px 8px',
                                      borderRadius: '5px',
                                      border: '1px solid #cbd5e1',
                                      backgroundColor: '#ffffff',
                                      color: '#334155',
                                      fontSize: '11.5px',
                                      fontWeight: 600,
                                      cursor: 'pointer',
                                    }}
                                  >
                                    View
                                  </button>
                                  <a
                                    href={api.getSalesInvoicePdfUrl(inv.id, true)}
                                    download={`sales_invoice_${inv.invoice_number ? inv.invoice_number.replace(/\//g, '_') : inv.id}.pdf`}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{
                                      padding: '4px 8px',
                                      borderRadius: '5px',
                                      border: '1px solid #cbd5e1',
                                      backgroundColor: '#ffffff',
                                      color: '#ef233c',
                                      fontSize: '11.5px',
                                      fontWeight: 600,
                                      textDecoration: 'none',
                                      display: 'inline-block',
                                    }}
                                  >
                                    Download
                                  </a>
                                  <button
                                    onClick={() => setCancelModalInvoice(inv)}
                                    style={{
                                      background: 'none',
                                      border: 'none',
                                      color: '#dc2626',
                                      fontSize: '11px',
                                      fontWeight: 600,
                                      cursor: 'pointer',
                                    }}
                                  >
                                    Cancel
                                  </button>
                                </>
                              )}

                              {inv.status === 'cancelled' && (
                                <>
                                  <button
                                    onClick={() => setPreviewInvoice(inv)}
                                    style={{
                                      padding: '4px 8px',
                                      borderRadius: '5px',
                                      border: '1px solid #cbd5e1',
                                      backgroundColor: '#ffffff',
                                      color: '#334155',
                                      fontSize: '11.5px',
                                      fontWeight: 600,
                                      cursor: 'pointer',
                                    }}
                                  >
                                    View
                                  </button>
                                  <span style={{ fontSize: '11px', color: '#dc2626', fontStyle: 'italic' }}>
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
