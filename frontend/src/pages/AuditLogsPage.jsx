import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';

export default function AuditLogsPage() {
  const { user, hasPermission } = useAuth();
  const [logs, setLogs] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filters
  const [actionFilter, setActionFilter] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [branchFilter, setBranchFilter] = useState('');
  const [branches, setBranches] = useState([]);

  // Modal for metadata inspection
  const [selectedLog, setSelectedLog] = useState(null);

  // Load branches if user is company admin
  useEffect(() => {
    if (hasPermission('audit.view_company') || user?.role === 'GLOBAL_ADMIN') {
      api.listCompanyBranches()
        .then(res => setBranches(res || []))
        .catch(() => {});
    }
  }, [hasPermission, user]);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        page,
        page_size: pageSize,
      };
      if (actionFilter) params.action = actionFilter;
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      if (branchFilter) params.branch_id = branchFilter;

      const res = await api.getAuditLogs(params);
      setLogs(res.items || []);
      setTotalCount(res.total_count || 0);
      setTotalPages(res.total_pages || 1);
    } catch (err) {
      console.error('Failed to load audit logs:', err);
      setError(err.message || 'Failed to fetch audit logs.');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, actionFilter, fromDate, toDate, branchFilter]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const handleFilterSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchLogs();
  };

  const handleResetFilters = () => {
    setActionFilter('');
    setFromDate('');
    setToDate('');
    setBranchFilter('');
    setPage(1);
  };

  const formatTimestamp = (ts) => {
    if (!ts) return '—';
    try {
      const d = new Date(ts);
      return d.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return ts;
    }
  };

  const getActionBadgeClass = (action) => {
    if (!action) return 'badge-neutral';
    if (action.includes('delete') || action.includes('fail') || action.includes('suspend') || action.includes('reject')) {
      return 'badge-danger';
    }
    if (action.includes('create') || action.includes('upload') || action.includes('activate') || action.includes('approve')) {
      return 'badge-success';
    }
    if (action.includes('login') || action.includes('logout') || action.includes('view') || action.includes('download')) {
      return 'badge-info';
    }
    return 'badge-warning';
  };

  return (
    <div className="page-content" style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box', padding: '1.5rem 2rem' }}>
      {/* Header */}
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', margin: '0 0 3px 0', letterSpacing: '-0.01em' }}>
            Audit Logs
          </h1>
          <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
            Immutable, tamper-resistant trail of security transactions, document operations, and system events.
          </p>
        </div>
        <button
          onClick={fetchLogs}
          disabled={loading}
          className="btn btn-secondary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '6px 12px', borderRadius: '6px' }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
          {loading ? 'Refreshing...' : 'Refresh Logs'}
        </button>
      </div>

      {/* Filter Bar */}
      <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '10px 14px', marginBottom: '14px', boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
        <form onSubmit={handleFilterSubmit} style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'flex-end' }}>
          {/* Action Filter */}
          <div style={{ flex: '1 1 180px' }}>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: '600', color: '#475569', marginBottom: '3px' }}>
              Action
            </label>
            <input
              type="text"
              placeholder="e.g. document.upload, auth.login"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="input-field"
              style={{ width: '100%', fontSize: '12px', height: '34px', padding: '5px 10px', borderRadius: '6px', border: '1px solid #cbd5e1' }}
            />
          </div>

          {/* Branch filter (if multi-branch allowed) */}
          {branches.length > 0 && (
            <div style={{ flex: '1 1 160px' }}>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: '600', color: '#475569', marginBottom: '3px' }}>
                Branch
              </label>
              <select
                value={branchFilter}
                onChange={(e) => setBranchFilter(e.target.value)}
                className="input-field"
                style={{ width: '100%', fontSize: '12px', height: '34px', padding: '5px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff' }}
              >
                <option value="">All Branches</option>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name} ({b.code})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Date range from */}
          <div style={{ flex: '1 1 140px' }}>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: '600', color: '#475569', marginBottom: '3px' }}>
              From Date
            </label>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="input-field"
              style={{ width: '100%', fontSize: '12px', height: '34px', padding: '5px 10px', borderRadius: '6px', border: '1px solid #cbd5e1' }}
            />
          </div>

          {/* Date range to */}
          <div style={{ flex: '1 1 140px' }}>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: '600', color: '#475569', marginBottom: '3px' }}>
              To Date
            </label>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="input-field"
              style={{ width: '100%', fontSize: '12px', height: '34px', padding: '5px 10px', borderRadius: '6px', border: '1px solid #cbd5e1' }}
            />
          </div>

          {/* Buttons */}
          <div style={{ display: 'flex', gap: '6px' }}>
            <button type="submit" className="btn btn-primary" style={{ padding: '0 14px', height: '34px', fontSize: '12px', borderRadius: '6px' }}>
              Filter
            </button>
            <button
              type="button"
              onClick={handleResetFilters}
              className="btn btn-secondary"
              style={{ padding: '0 12px', height: '34px', fontSize: '12px', borderRadius: '6px' }}
            >
              Reset
            </button>
          </div>
        </form>
      </div>

      {/* Error Banner */}
      {error && (
        <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', padding: '12px 16px', borderRadius: '8px', marginBottom: '20px', fontSize: '14px' }}>
          {error}
        </div>
      )}

      {/* Audit Log Table */}
      <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
        <div style={{ overflowX: 'auto', width: '100%' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                <th style={{ padding: '8px 10px' }}>Timestamp (IST)</th>
                <th style={{ padding: '8px 10px' }}>Action</th>
                <th style={{ padding: '8px 10px' }}>Actor</th>
                <th style={{ padding: '8px 10px' }}>Target Object</th>
                <th style={{ padding: '8px 10px' }}>Branch</th>
                <th style={{ padding: '8px 10px' }}>IP / Request ID</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && logs.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '36px', color: '#64748b', fontSize: '13px' }}>
                    Loading audit trail...
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '36px', color: '#64748b', fontSize: '13px' }}>
                    No audit records found matching criteria.
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr
                    key={log.id}
                    style={{ borderBottom: '1px solid #f1f5f9', transition: 'background-color 0.15s' }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f8fafc')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <td style={{ padding: '7px 10px', whiteSpace: 'nowrap', color: '#1e293b' }}>
                      {formatTimestamp(log.occurred_at)}
                    </td>
                    <td style={{ padding: '7px 10px' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '2px 7px',
                          borderRadius: '4px',
                          fontSize: '10.5px',
                          fontWeight: '600',
                          fontFamily: 'monospace',
                          background: log.action?.includes('delete') || log.action?.includes('fail')
                            ? '#fee2e2'
                            : log.action?.includes('create') || log.action?.includes('upload')
                            ? '#dcfce7'
                            : '#e0f2fe',
                          color: log.action?.includes('delete') || log.action?.includes('fail')
                            ? '#991b1b'
                            : log.action?.includes('create') || log.action?.includes('upload')
                            ? '#166534'
                            : '#0369a1',
                        }}
                      >
                        {log.action}
                      </span>
                    </td>
                    <td style={{ padding: '7px 10px' }}>
                      <div style={{ fontWeight: '500', color: '#0f172a' }}>
                        {log.actor_type === 'USER' ? `User #${log.actor_id}` : log.actor_type}
                      </div>
                    </td>
                    <td style={{ padding: '7px 10px', color: '#475569' }}>
                      {log.object_type ? (
                        <span>
                          <strong style={{ color: '#334155' }}>{log.object_type}</strong>{' '}
                          {log.object_id ? `#${log.object_id}` : ''}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td style={{ padding: '7px 10px', color: '#475569' }}>
                      {log.branch_id ? `Branch #${log.branch_id}` : 'Company-wide'}
                    </td>
                    <td style={{ padding: '7px 10px', color: '#64748b', fontSize: '11px', fontFamily: 'monospace' }}>
                      <div>{log.ip || '—'}</div>
                      {log.request_id && (
                        <div style={{ color: '#94a3b8', fontSize: '10px' }} title={log.request_id}>
                          req: {log.request_id.slice(0, 12)}...
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                      <button
                        onClick={() => setSelectedLog(log)}
                        style={{
                          background: '#f1f5f9',
                          border: '1px solid #cbd5e1',
                          borderRadius: '4px',
                          padding: '3px 8px',
                          fontSize: '11px',
                          cursor: 'pointer',
                          color: '#334155',
                          fontWeight: '500',
                        }}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '12px 20px',
            borderTop: '1px solid #e2e8f0',
            background: '#f8fafc',
            fontSize: '13px',
            color: '#64748b',
          }}
        >
          <div>
            Showing <strong>{logs.length}</strong> of <strong>{totalCount}</strong> logs (Page {page} of {totalPages})
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setPage((p) => Math.max(p - 1, 1))}
              disabled={page <= 1 || loading}
              className="btn btn-secondary"
              style={{ padding: '6px 12px', fontSize: '12px' }}
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
              disabled={page >= totalPages || loading}
              className="btn btn-secondary"
              style={{ padding: '6px 12px', fontSize: '12px' }}
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Metadata Inspection Modal */}
      {selectedLog && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.65)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '16px',
          }}
        >
          <div
            style={{
              background: '#fff',
              borderRadius: '12px',
              maxWidth: '640px',
              width: '100%',
              maxHeight: '90vh',
              overflowY: 'auto',
              boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '16px 20px',
                borderBottom: '1px solid #e2e8f0',
              }}
            >
              <div>
                <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '700', color: '#0f172a' }}>
                  Audit Record #{selectedLog.id}
                </h3>
                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                  {formatTimestamp(selectedLog.occurred_at)} UTC: {selectedLog.occurred_at}
                </div>
              </div>
              <button
                onClick={() => setSelectedLog(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '20px',
                  cursor: 'pointer',
                  color: '#94a3b8',
                  padding: '4px 8px',
                }}
              >
                &times;
              </button>
            </div>

            <div style={{ padding: '20px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px', fontSize: '13px' }}>
                <div>
                  <span style={{ color: '#64748b', fontWeight: '600' }}>Action:</span>
                  <div style={{ marginTop: '2px', fontFamily: 'monospace', fontWeight: '600', color: '#0369a1' }}>
                    {selectedLog.action}
                  </div>
                </div>
                <div>
                  <span style={{ color: '#64748b', fontWeight: '600' }}>Actor:</span>
                  <div style={{ marginTop: '2px' }}>
                    {selectedLog.actor_type} {selectedLog.actor_id ? `(#${selectedLog.actor_id})` : ''}
                  </div>
                </div>
                <div>
                  <span style={{ color: '#64748b', fontWeight: '600' }}>Target:</span>
                  <div style={{ marginTop: '2px' }}>
                    {selectedLog.object_type || '—'} {selectedLog.object_id ? `(#${selectedLog.object_id})` : ''}
                  </div>
                </div>
                <div>
                  <span style={{ color: '#64748b', fontWeight: '600' }}>Company / Branch:</span>
                  <div style={{ marginTop: '2px' }}>
                    Company #{selectedLog.company_id || 'Platform'} {selectedLog.branch_id ? `· Branch #${selectedLog.branch_id}` : ''}
                  </div>
                </div>
                <div>
                  <span style={{ color: '#64748b', fontWeight: '600' }}>IP Address:</span>
                  <div style={{ marginTop: '2px', fontFamily: 'monospace' }}>
                    {selectedLog.ip || '—'}
                  </div>
                </div>
                <div>
                  <span style={{ color: '#64748b', fontWeight: '600' }}>Request ID:</span>
                  <div style={{ marginTop: '2px', fontFamily: 'monospace', fontSize: '11px', wordBreak: 'break-all' }}>
                    {selectedLog.request_id || '—'}
                  </div>
                </div>
              </div>

              {/* User Agent */}
              {selectedLog.user_agent && (
                <div style={{ marginBottom: '16px', fontSize: '12px' }}>
                  <span style={{ color: '#64748b', fontWeight: '600' }}>User Agent:</span>
                  <div style={{ background: '#f8fafc', padding: '6px 10px', borderRadius: '6px', marginTop: '4px', color: '#334155', wordBreak: 'break-all' }}>
                    {selectedLog.user_agent}
                  </div>
                </div>
              )}

              {/* Metadata JSON */}
              <div style={{ marginBottom: '16px' }}>
                <span style={{ color: '#64748b', fontWeight: '600', fontSize: '13px' }}>Event Metadata:</span>
                <pre
                  style={{
                    background: '#0f172a',
                    color: '#38bdf8',
                    padding: '12px',
                    borderRadius: '8px',
                    fontSize: '12px',
                    overflowX: 'auto',
                    marginTop: '6px',
                    maxHeight: '240px',
                  }}
                >
                  {JSON.stringify(selectedLog.metadata || selectedLog.event_metadata || {}, null, 2)}
                </pre>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  onClick={() => setSelectedLog(null)}
                  className="btn btn-secondary"
                  style={{ padding: '8px 16px' }}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

