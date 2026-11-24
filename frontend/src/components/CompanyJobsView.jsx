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
  const [selectedJobDetails, setSelectedJobDetails] = useState(null);

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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* ── Section Header ────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 4px 0', color: '#0f172a' }}>
            Background Processing Jobs
          </h2>
          <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
            Monitor asynchronous OCR extraction pipelines, dead-letter jobs, and retry failed executions safely.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={handleExportCsv}
            disabled={exporting || loading}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#ffffff',
              color: '#334155',
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontWeight: 600,
              fontSize: '12px',
              cursor: exporting || loading ? 'not-allowed' : 'pointer',
              boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            {exporting ? 'Exporting...' : 'Export Jobs CSV'}
          </button>

          <button
            onClick={loadJobs}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              color: '#334155',
              fontSize: '12px',
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
        borderRadius: '8px',
        padding: '10px 14px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '10px',
      }}>
        {/* Status Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: '#475569', marginRight: '4px' }}>Status:</span>
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
                padding: '4px 10px',
                borderRadius: '5px',
                fontSize: '11.5px',
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Branch:</label>
          <select
            value={selectedBranch}
            onChange={e => { setSelectedBranch(e.target.value); setPage(1); }}
            style={{
              padding: '5px 10px',
              borderRadius: '5px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              fontSize: '12px',
              color: '#1e293b',
              fontWeight: 500,
              minWidth: '150px',
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
        <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', padding: '10px 14px', borderRadius: '6px', color: '#991b1b', fontSize: '13px' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* ── Jobs Table ────────────────────────────────────────────────── */}
      <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '16px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '50px 0' }}>
            <div style={{ textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
              <div className="spinner" style={{ margin: '0 auto 10px' }} />
              Loading background jobs...
            </div>
          </div>
        ) : jobs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '50px 20px', color: '#64748b' }}>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5" style={{ margin: '0 auto 10px', display: 'block' }}>
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <div style={{ fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
              No {statusFilter !== 'all' ? statusFilter : ''} jobs found
            </div>
            <p style={{ margin: '4px 0 0 0', fontSize: '12px' }}>
              Background queue is clear for the selected filters.
            </p>
          </div>
        ) : (
          <>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                    <th style={{ padding: '8px 10px', width: '80px' }}>Job ID</th>
                    <th style={{ padding: '8px 10px', minWidth: '170px' }}>Document</th>
                    <th style={{ padding: '8px 10px', width: '130px' }}>Branch</th>
                    <th style={{ padding: '8px 10px', width: '85px' }}>Status</th>
                    <th style={{ padding: '8px 10px', width: '75px' }}>Attempts</th>
                    <th style={{ padding: '8px 10px', minWidth: '240px' }}>Diagnostic Summary</th>
                    <th style={{ padding: '8px 10px', width: '145px' }}>Updated</th>
                    <th style={{ padding: '8px 10px', width: '105px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => {
                    const badge = STATUS_BADGES[job.status] || { label: job.status, bg: '#f1f5f9', text: '#334155', border: '#e2e8f0' };
                    return (
                      <tr key={job.job_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '9px 10px', fontFamily: 'monospace', color: '#64748b', fontSize: '12px', verticalAlign: 'middle' }}>
                          #{job.job_id}
                        </td>
                        <td style={{ padding: '9px 10px', verticalAlign: 'middle' }}>
                          <span style={{ fontWeight: 600, color: '#0f172a', display: 'block', fontSize: '12.5px' }}>
                            {job.document_filename}
                          </span>
                          <span style={{ fontSize: '11px', color: '#94a3b8' }}>
                            Doc #{job.document_id} {job.document_deleted && '(Deleted)'}
                          </span>
                        </td>
                        <td style={{ padding: '9px 10px', color: '#475569', fontSize: '12px', verticalAlign: 'middle' }}>
                          {job.branch_name || '—'}
                        </td>
                        <td style={{ padding: '9px 10px', verticalAlign: 'middle' }}>
                          <span style={{
                            display: 'inline-block',
                            padding: '2px 7px',
                            borderRadius: '4px',
                            fontSize: '11px',
                            fontWeight: 600,
                            backgroundColor: badge.bg,
                            color: badge.text,
                            border: `1px solid ${badge.border}`,
                          }}>
                            {badge.label}
                          </span>
                        </td>
                        <td style={{ padding: '9px 10px', color: '#475569', fontSize: '12px', verticalAlign: 'middle' }}>
                          {job.attempts} / {job.max_attempts}
                        </td>
                        <td style={{ padding: '9px 10px', verticalAlign: 'middle' }}>
                          {job.error_summary ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                              {job.error_code && (
                                <span style={{
                                  fontSize: '10px',
                                  fontWeight: 600,
                                  color: '#991b1b',
                                  backgroundColor: '#fee2e2',
                                  padding: '1px 5px',
                                  borderRadius: '3px',
                                  border: '1px solid #fecaca',
                                  whiteSpace: 'nowrap',
                                  flexShrink: 0,
                                }}>
                                  {job.error_code}
                                </span>
                              )}
                              <span
                                title={job.error_summary}
                                style={{
                                  fontSize: '11.5px',
                                  color: '#475569',
                                  display: '-webkit-box',
                                  WebkitLineClamp: 1,
                                  WebkitBoxOrient: 'vertical',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  maxWidth: '240px',
                                }}
                              >
                                {job.error_summary}
                              </span>
                              <button
                                onClick={() => setSelectedJobDetails(job)}
                                style={{
                                  background: 'none',
                                  border: 'none',
                                  color: '#ef233c',
                                  fontSize: '11px',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                  padding: '0 2px',
                                  whiteSpace: 'nowrap',
                                  flexShrink: 0,
                                  textDecoration: 'underline',
                                }}
                              >
                                Details
                              </button>
                            </div>
                          ) : (
                            <span style={{ color: '#94a3b8' }}>&mdash;</span>
                          )}
                        </td>
                        <td style={{ padding: '9px 10px', color: '#64748b', fontSize: '11.5px', whiteSpace: 'nowrap', verticalAlign: 'middle' }}>
                          {job.updated_at ? new Date(job.updated_at).toLocaleString() : '—'}
                        </td>
                        <td style={{ padding: '9px 10px', textAlign: 'right', verticalAlign: 'middle' }}>
                          {job.can_reprocess ? (
                            <button
                              onClick={() => handleReprocess(job.document_id, job.job_id)}
                              disabled={reprocessingId === job.job_id}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                                padding: '4px 10px',
                                borderRadius: '5px',
                                border: '1px solid #cbd5e1',
                                backgroundColor: '#ffffff',
                                color: '#ef233c',
                                fontSize: '11.5px',
                                fontWeight: 600,
                                cursor: reprocessingId === job.job_id ? 'not-allowed' : 'pointer',
                                boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
                                transition: 'all 0.15s ease',
                              }}
                              onMouseOver={(e) => { e.currentTarget.style.backgroundColor = '#fef2f2'; e.currentTarget.style.borderColor = '#fca5a5'; }}
                              onMouseOut={(e) => { e.currentTarget.style.backgroundColor = '#ffffff'; e.currentTarget.style.borderColor = '#cbd5e1'; }}
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
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '14px', paddingTop: '12px', borderTop: '1px solid #f1f5f9' }}>
                <div style={{ fontSize: '12px', color: '#64748b' }}>
                  Showing Page {pagination.page} of {pagination.total_pages} ({pagination.total_items} total jobs)
                </div>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage(p => Math.max(p - 1, 1))}
                    style={{
                      padding: '4px 10px',
                      borderRadius: '5px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: page <= 1 ? '#f8fafc' : '#ffffff',
                      color: page <= 1 ? '#94a3b8' : '#334155',
                      fontSize: '11.5px',
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
                      padding: '4px 10px',
                      borderRadius: '5px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: page >= pagination.total_pages ? '#f8fafc' : '#ffffff',
                      color: page >= pagination.total_pages ? '#94a3b8' : '#334155',
                      fontSize: '11.5px',
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

      {/* ── MODAL: JOB DIAGNOSTIC DETAILS ─────────────────────────────────── */}
      {selectedJobDetails && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15,23,42,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '16px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', width: '100%', maxWidth: '560px', padding: '20px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', borderBottom: '1px solid #f1f5f9', paddingBottom: '10px' }}>
              <div>
                <h3 style={{ margin: '0 0 2px 0', fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                  Job Diagnostic Details #{selectedJobDetails.job_id}
                </h3>
                <span style={{ fontSize: '12px', color: '#64748b' }}>
                  {selectedJobDetails.document_filename} (Doc #{selectedJobDetails.document_id})
                </span>
              </div>
              <button
                onClick={() => setSelectedJobDetails(null)}
                style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#94a3b8' }}
              >
                &times;
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginBottom: '14px', fontSize: '12px' }}>
              <div>
                <span style={{ color: '#64748b' }}>Branch:</span>{' '}
                <strong style={{ color: '#0f172a' }}>{selectedJobDetails.branch_name || '—'}</strong>
              </div>
              <div>
                <span style={{ color: '#64748b' }}>Status:</span>{' '}
                <strong style={{ color: '#991b1b', textTransform: 'uppercase' }}>{selectedJobDetails.status}</strong>
              </div>
              <div>
                <span style={{ color: '#64748b' }}>Attempts:</span>{' '}
                <strong>{selectedJobDetails.attempts} / {selectedJobDetails.max_attempts}</strong>
              </div>
              <div>
                <span style={{ color: '#64748b' }}>Updated:</span>{' '}
                <span>{selectedJobDetails.updated_at ? new Date(selectedJobDetails.updated_at).toLocaleString() : '—'}</span>
              </div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, color: '#475569', textTransform: 'uppercase' }}>
                  Diagnostic Summary {selectedJobDetails.error_code && `[${selectedJobDetails.error_code}]`}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(selectedJobDetails.error_summary || '');
                    showToast?.('Diagnostic log copied to clipboard.', 'info');
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#ef233c',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Copy Log
                </button>
              </div>

              <div style={{
                backgroundColor: '#0f172a',
                color: '#f8fafc',
                padding: '12px',
                borderRadius: '6px',
                fontSize: '11.5px',
                fontFamily: 'monospace',
                maxHeight: '180px',
                overflowY: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                lineHeight: 1.4,
              }}>
                {selectedJobDetails.error_summary || 'No diagnostic output provided.'}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              {selectedJobDetails.can_reprocess && (
                <button
                  type="button"
                  onClick={() => {
                    handleReprocess(selectedJobDetails.document_id, selectedJobDetails.job_id);
                    setSelectedJobDetails(null);
                  }}
                  style={{
                    padding: '6px 14px',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: '#ef233c',
                    color: '#ffffff',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  ↻ Reprocess Job
                </button>
              )}
              <button
                type="button"
                onClick={() => setSelectedJobDetails(null)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  color: '#334155',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
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
