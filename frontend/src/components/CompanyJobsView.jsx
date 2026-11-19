import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

const STATUS_BADGES = {
  failed: { label: 'Failed', bg: '#fee2e2', text: '#991b1b', border: '#fecaca' },
  pending: { label: 'Pending', bg: '#fef3c7', text: '#92400e', border: '#fde68a' },
  running: { label: 'Running', bg: '#e0f2fe', text: '#075985', border: '#bae6fd' },
  completed: { label: 'Completed', bg: '#dcfce7', text: '#166534', border: '#bbf7d0' },
};

export default function CompanyJobsView({ branchesList = [], showToast }) {
  const [statusFilter, setStatusFilter] = useState('failed');
  const [selectedBranch, setSelectedBranch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reprocessingId, setReprocessingId] = useState(null);
  const [exporting, setExporting] = useState(false);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.getDashboardJobs({
        status: statusFilter,
        branch_id: selectedBranch || null,
        page,
        page_size: pageSize,
      });
      setData(res);
    } catch (err) {
      setError(err.message || 'Failed to load background processing jobs.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, selectedBranch, page, pageSize]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const handleReprocess = async (docId, jobId) => {
    setReprocessingId(jobId);
    try {
      await api.reprocessDocument(docId);
      showToast?.(`Reprocessing job queued for document #${docId}.`, 'success');
      loadJobs();
    } catch (err) {
      showToast?.(err.message || 'Failed to reprocess document.', 'error');
    } finally {
      setReprocessingId(null);
    }
  };

  const handleExportCsv = async () => {
    setExporting(true);
    try {
      await api.downloadDashboardCsv('failed-jobs', {
        branch_id: selectedBranch || null,
      });
      showToast?.('Jobs report downloaded successfully.', 'success');
    } catch (err) {
      showToast?.(err.message || 'Failed to export jobs CSV.', 'error');
    } finally {
      setExporting(false);
    }
  };

  const { jobs = [], pagination = {} } = data || {};

  return (
    <div>
      {/* ── Section Header ────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '24px', fontWeight: 700, margin: '0 0 6px 0', color: '#0f172a' }}>
            Background Processing Jobs
          </h2>
          <p style={{ margin: 0, color: '#64748b', fontSize: '14px' }}>
            Monitor asynchronous OCR extraction pipelines, dead-letter jobs, and retry failed executions safely.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={handleExportCsv}
            disabled={exporting || loading}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: '#ffffff',
              color: '#334155',
              padding: '9px 16px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontWeight: 600,
              fontSize: '13px',
              cursor: exporting || loading ? 'not-allowed' : 'pointer',
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
            }}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {exporting ? 'Exporting...' : 'Export Jobs CSV'}
          </button>

          <button
            onClick={loadJobs}
            style={{
              padding: '9px 14px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              color: '#334155',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
            title="Refresh"
          >
            &#x21bb; Refresh
          </button>
        </div>
      </div>

      {/* ── Filter Controls Bar ───────────────────────────────────────── */}
      <div style={{
        backgroundColor: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: '10px',
        padding: '16px 20px',
        marginBottom: '24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '14px',
      }}>
        {/* Status Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#475569', marginRight: '6px' }}>Status:</span>
          {[
            { id: 'failed', label: 'Failed' },
            { id: 'pending', label: 'Pending' },
            { id: 'running', label: 'Running' },
            { id: 'completed', label: 'Completed' },
            { id: 'all', label: 'All Jobs' },
          ].map(st => (
            <button
              key={st.id}
              onClick={() => { setStatusFilter(st.id); setPage(1); }}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                border: '1px solid',
                cursor: 'pointer',
                backgroundColor: statusFilter === st.id ? '#ef233c' : '#ffffff',
                borderColor: statusFilter === st.id ? '#ef233c' : '#cbd5e1',
                color: statusFilter === st.id ? '#ffffff' : '#475569',
                transition: 'all 0.15s ease',
              }}
            >
              {st.label}
            </button>
          ))}
        </div>

        {/* Branch Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <label style={{ fontSize: '13px', fontWeight: 600, color: '#475569' }}>Branch:</label>
          <select
            value={selectedBranch}
            onChange={e => { setSelectedBranch(e.target.value); setPage(1); }}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              fontSize: '13px',
              color: '#1e293b',
              fontWeight: 500,
              minWidth: '180px',
            }}
          >
            <option value="">All Branches</option>
            {branchesList.map(b => (
              <option key={b.id} value={b.id}>
                {b.name} ({b.code})
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '14px 18px', borderRadius: '8px', color: '#991b1b', marginBottom: '20px', fontSize: '14px' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* ── Jobs Table ────────────────────────────────────────────────── */}
      <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}>
            <div style={{ textAlign: 'center', color: '#64748b' }}>
              <div className="spinner" style={{ margin: '0 auto 12px' }} />
              Loading background jobs...
            </div>
          </div>
        ) : jobs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: '#64748b' }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5" style={{ margin: '0 auto 12px', display: 'block' }}>
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <div style={{ fontSize: '16px', fontWeight: 600, color: '#1e293b' }}>
              No {statusFilter !== 'all' ? statusFilter : ''} jobs found
            </div>
            <p style={{ margin: '4px 0 0 0', fontSize: '13px' }}>
              Background queue is clear for the selected filters.
            </p>
          </div>
        ) : (
          <>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase' }}>
                    <th style={{ padding: '10px 12px' }}>Job ID</th>
                    <th style={{ padding: '10px 12px' }}>Document</th>
                    <th style={{ padding: '10px 12px' }}>Branch</th>
                    <th style={{ padding: '10px 12px' }}>Status</th>
                    <th style={{ padding: '10px 12px' }}>Attempts</th>
                    <th style={{ padding: '10px 12px' }}>Diagnostic Summary</th>
                    <th style={{ padding: '10px 12px' }}>Updated</th>
                    <th style={{ padding: '10px 12px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => {
                    const badge = STATUS_BADGES[job.status] || { label: job.status, bg: '#f1f5f9', text: '#334155', border: '#e2e8f0' };
                    return (
                      <tr key={job.job_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '12px', fontFamily: 'monospace', color: '#64748b', fontSize: '12px' }}>
                          #{job.job_id}
                        </td>
                        <td style={{ padding: '12px' }}>
                          <span style={{ fontWeight: 600, color: '#0f172a', display: 'block' }}>
                            {job.document_filename}
                          </span>
                          <span style={{ fontSize: '11px', color: '#64748b' }}>
                            Doc #{job.document_id} {job.document_deleted && '(Deleted)'}
                          </span>
                        </td>
                        <td style={{ padding: '12px', color: '#475569' }}>
                          {job.branch_name}
                        </td>
                        <td style={{ padding: '12px' }}>
                          <span style={{
                            display: 'inline-block',
                            padding: '3px 9px',
                            borderRadius: '12px',
                            fontSize: '11px',
                            fontWeight: 700,
                            backgroundColor: badge.bg,
                            color: badge.text,
                            border: `1px solid ${badge.border}`,
                          }}>
                            {badge.label}
                          </span>
                        </td>
                        <td style={{ padding: '12px', color: '#475569', fontSize: '12px' }}>
                          {job.attempts} / {job.max_attempts}
                        </td>
                        <td style={{ padding: '12px', maxWidth: '320px' }}>
                          {job.error_summary ? (
                            <div style={{
                              fontSize: '12px',
                              color: '#991b1b',
                              backgroundColor: '#fef2f2',
                              padding: '6px 8px',
                              borderRadius: '4px',
                              fontFamily: 'monospace',
                              wordBreak: 'break-word',
                              lineHeight: 1.3,
                            }}>
                              {job.error_code && <strong style={{ display: 'block', marginBottom: '2px' }}>[{job.error_code}]</strong>}
                              {job.error_summary}
                            </div>
                          ) : (
                            <span style={{ color: '#94a3b8' }}>&mdash;</span>
                          )}
                        </td>
                        <td style={{ padding: '12px', color: '#64748b', fontSize: '12px', whiteSpace: 'nowrap' }}>
                          {job.updated_at ? new Date(job.updated_at).toLocaleString() : '—'}
                        </td>
                        <td style={{ padding: '12px', textAlign: 'right' }}>
                          {job.can_reprocess ? (
                            <button
                              onClick={() => handleReprocess(job.document_id, job.job_id)}
                              disabled={reprocessingId === job.job_id}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '6px',
                                padding: '6px 12px',
                                borderRadius: '6px',
                                border: '1px solid #ef233c',
                                backgroundColor: '#fff1f2',
                                color: '#ef233c',
                                fontSize: '12px',
                                fontWeight: 600,
                                cursor: reprocessingId === job.job_id ? 'not-allowed' : 'pointer',
                              }}
                            >
                              {reprocessingId === job.job_id ? 'Retrying...' : '↻ Reprocess'}
                            </button>
                          ) : (
                            <span style={{ color: '#cbd5e1', fontSize: '12px' }}>&mdash;</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {pagination.total_pages > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '20px', paddingTop: '16px', borderTop: '1px solid #f1f5f9' }}>
                <div style={{ fontSize: '13px', color: '#64748b' }}>
                  Showing Page {pagination.page} of {pagination.total_pages} ({pagination.total_items} total jobs)
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage(p => Math.max(p - 1, 1))}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: page <= 1 ? '#f8fafc' : '#ffffff',
                      color: page <= 1 ? '#94a3b8' : '#334155',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: page <= 1 ? 'not-allowed' : 'pointer',
                    }}
                  >
                    &larr; Previous
                  </button>
                  <button
                    disabled={page >= pagination.total_pages}
                    onClick={() => setPage(p => Math.min(p + 1, pagination.total_pages))}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: page >= pagination.total_pages ? '#f8fafc' : '#ffffff',
                      color: page >= pagination.total_pages ? '#94a3b8' : '#334155',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: page >= pagination.total_pages ? 'not-allowed' : 'pointer',
                    }}
                  >
                    Next &rarr;
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
