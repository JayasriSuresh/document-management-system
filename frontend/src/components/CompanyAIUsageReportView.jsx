import { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

function formatNumber(num) {
  if (num === null || num === undefined) return '0';
  return Number(num).toLocaleString('en-IN');
}

function formatUSD(amount) {
  if (amount === null || amount === undefined) return '$0.00';
  return `$${Number(amount).toFixed(4)}`;
}

function formatINR(amount) {
  if (amount === null || amount === undefined) return '₹0.00';
  return `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
}

export default function CompanyAIUsageReportView({ branchesList = [], showToast }) {
  const [datePreset, setDatePreset] = useState('last30');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [selectedBranch, setSelectedBranch] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState(false);

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

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { from, to } = calculateDateRange();
      const res = await api.getDashboardAIUsage({
        date_from: from,
        date_to: to,
        branch_id: selectedBranch || null,
      });
      setData(res);
    } catch (err) {
      setError(err.message || 'Failed to load AI usage metrics.');
    } finally {
      setLoading(false);
    }
  }, [calculateDateRange, selectedBranch]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleExportCsv = async () => {
    setExporting(true);
    try {
      const { from, to } = calculateDateRange();
      await api.downloadDashboardCsv('ai-usage', {
        date_from: from,
        date_to: to,
        branch_id: selectedBranch || null,
      });
      showToast?.('AI usage report downloaded successfully.', 'success');
    } catch (err) {
      showToast?.(err.message || 'Failed to export AI usage CSV.', 'error');
    } finally {
      setExporting(false);
    }
  };

  const { summary, by_provider = [], by_model = [], by_branch = [], daily_trends = [] } = data || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* ── Section Header ────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 4px 0', color: '#0f172a' }}>
            AI Usage &amp; Cost Intelligence
          </h2>
          <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
            Estimated token consumption, model throughput, and cost attribution across external providers.
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
            {exporting ? 'Exporting...' : 'Export AI CSV'}
          </button>

          <button
            onClick={loadData}
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

      {/* ── Filters Bar ──────────────────────────────────────────────── */}
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
        {/* Date presets */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: '#475569', marginRight: '4px' }}>Range:</span>
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
                padding: '4px 10px',
                borderRadius: '5px',
                fontSize: '11.5px',
                fontWeight: 600,
                border: '1px solid',
                cursor: 'pointer',
                backgroundColor: datePreset === p.id ? '#ef233c' : '#ffffff',
                borderColor: datePreset === p.id ? '#ef233c' : '#cbd5e1',
                color: datePreset === p.id ? '#ffffff' : '#475569',
                transition: 'all 0.15s ease',
              }}
            >
              {p.label}
            </button>
          ))}

          {datePreset === 'custom' && (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', marginLeft: '6px' }}>
              <input
                type="date"
                value={customFrom}
                onChange={e => setCustomFrom(e.target.value)}
                style={{ padding: '4px 6px', borderRadius: '5px', border: '1px solid #cbd5e1', fontSize: '11.5px' }}
              />
              <span style={{ color: '#94a3b8' }}>&ndash;</span>
              <input
                type="date"
                value={customTo}
                onChange={e => setCustomTo(e.target.value)}
                style={{ padding: '4px 6px', borderRadius: '5px', border: '1px solid #cbd5e1', fontSize: '11.5px' }}
              />
            </div>
          )}
        </div>

        {/* Branch Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>Branch:</label>
          <select
            value={selectedBranch}
            onChange={e => setSelectedBranch(e.target.value)}
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

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 0' }}>
          <div style={{ textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
            <div className="spinner" style={{ margin: '0 auto 10px' }} />
            Loading AI usage intelligence...
          </div>
        </div>
      ) : (
        <>
          {/* ── KPI Cards Grid ───────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
            {/* Card 1: Estimated Usage Cost (Dual Currency: INR + USD) */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '12px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                  Estimated AI Cost
                </span>
                <span style={{ fontSize: '10px', fontWeight: 600, color: '#0369a1', backgroundColor: '#e0f2fe', padding: '1px 5px', borderRadius: '4px' }}>
                  ₹ / $ Dual
                </span>
              </div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                {formatINR(summary?.cost_inr !== undefined ? summary?.cost_inr : (summary?.estimated_cost_usd || 0) * (summary?.exchange_rate || 85))}
              </div>
              <div style={{ fontSize: '11.5px', fontWeight: 500, color: '#64748b', marginTop: '2px' }}>
                {formatUSD(summary?.estimated_cost_usd)} USD <span style={{ fontWeight: 400, color: '#94a3b8' }}>({formatNumber(summary?.cost_cents)} cents)</span>
              </div>
            </div>

            {/* Card 2: Total Tokens */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '12px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: '4px' }}>
                Token Consumption
              </div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                {formatNumber(summary?.total_tokens)}
              </div>
              <div style={{ fontSize: '11.5px', color: '#64748b', marginTop: '2px' }}>
                {formatNumber(summary?.tokens_in)} in &middot; {formatNumber(summary?.tokens_out)} out
              </div>
            </div>

            {/* Card 3: Provider Invocations */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '12px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: '4px' }}>
                Provider Invocations
              </div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                {formatNumber(summary?.total_calls)}
              </div>
              <div style={{ fontSize: '11.5px', color: '#16a34a', marginTop: '2px' }}>
                {formatNumber(summary?.successful_calls)} ok &middot; <span style={{ color: summary?.failed_calls > 0 ? '#dc2626' : '#64748b' }}>{formatNumber(summary?.failed_calls)} failed</span>
              </div>
            </div>

            {/* Card 4: Fallbacks & Latency */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '12px 14px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
              <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: '4px' }}>
                Failovers &amp; Latency
              </div>
              <div style={{ fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                {formatNumber(summary?.fallback_calls)} <span style={{ fontSize: '12px', fontWeight: 500, color: '#64748b' }}>failovers</span>
              </div>
              <div style={{ fontSize: '11.5px', color: '#64748b', marginTop: '2px' }}>
                Avg Latency: {summary?.avg_latency_ms || 0} ms
              </div>
            </div>
          </div>

          {/* ── Two-Column Breakdown: By Provider & By Model ─────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '14px' }}>
            {/* Table 1: Provider Breakdown */}
            <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '14px 16px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
              <h3 style={{ fontSize: '14px', fontWeight: 700, margin: '0 0 10px 0', color: '#0f172a' }}>
                Provider Distribution
              </h3>
              {by_provider.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '24px', color: '#94a3b8', fontSize: '12.5px' }}>
                  No provider logs recorded in this window.
                </div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase' }}>
                      <th style={{ padding: '6px 8px' }}>Provider</th>
                      <th style={{ padding: '6px 8px', textAlign: 'right' }}>Calls</th>
                      <th style={{ padding: '6px 8px', textAlign: 'right' }}>Tokens</th>
                      <th style={{ padding: '6px 8px', textAlign: 'right' }}>Cost (₹ / $)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {by_provider.map((p) => (
                      <tr key={p.provider} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '8px', fontWeight: 600, color: '#0f172a', textTransform: 'capitalize' }}>
                          {p.provider}
                        </td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                          {formatNumber(p.calls)}
                          {p.failed_calls > 0 && (
                            <span style={{ color: '#dc2626', fontSize: '10.5px', marginLeft: '4px' }}>
                              ({p.failed_calls} err)
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                          {formatNumber(p.total_tokens)}
                        </td>
                        <td style={{ padding: '8px', textAlign: 'right', fontWeight: 600, color: '#0f172a' }}>
                          <div>₹{Number(p.cost_inr !== undefined ? p.cost_inr : (p.estimated_cost_usd * 85)).toFixed(2)}</div>
                          <div style={{ fontSize: '10.5px', fontWeight: 400, color: '#64748b' }}>{formatUSD(p.estimated_cost_usd)} USD</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Table 2: Model Breakdown */}
            <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '14px 16px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
              <h3 style={{ fontSize: '14px', fontWeight: 700, margin: '0 0 10px 0', color: '#0f172a' }}>
                Model Breakdown
              </h3>
              {by_model.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '24px', color: '#94a3b8', fontSize: '12.5px' }}>
                  No model logs recorded in this window.
                </div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase' }}>
                      <th style={{ padding: '6px 8px' }}>Model</th>
                      <th style={{ padding: '6px 8px', textAlign: 'right' }}>Calls</th>
                      <th style={{ padding: '6px 8px', textAlign: 'right' }}>Tokens</th>
                      <th style={{ padding: '6px 8px', textAlign: 'right' }}>Cost (₹ / $)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {by_model.map((m) => (
                      <tr key={`${m.provider}-${m.model}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '8px' }}>
                          <span style={{ fontWeight: 600, color: '#0f172a' }}>{m.model}</span>
                          <span style={{ fontSize: '10.5px', color: '#64748b', display: 'block', textTransform: 'capitalize' }}>
                            {m.provider}
                          </span>
                        </td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                          {formatNumber(m.calls)}
                        </td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                          {formatNumber(m.total_tokens)}
                        </td>
                        <td style={{ padding: '8px', textAlign: 'right', fontWeight: 600, color: '#0f172a' }}>
                          <div>₹{Number(m.cost_inr !== undefined ? m.cost_inr : (m.estimated_cost_usd * 85)).toFixed(2)}</div>
                          <div style={{ fontSize: '10.5px', fontWeight: 400, color: '#64748b' }}>{formatUSD(m.estimated_cost_usd)} USD</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* ── Branch Attribution Table ─────────────────────────────── */}
          <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '14px 16px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 700, margin: '0 0 10px 0', color: '#0f172a' }}>
              Branch Spending Attribution
            </h3>
            {by_branch.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '24px', color: '#94a3b8', fontSize: '12.5px' }}>
                No branch attribution records found.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase' }}>
                    <th style={{ padding: '6px 8px' }}>Branch</th>
                    <th style={{ padding: '6px 8px' }}>Code</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Total Calls</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Input Tokens</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Output Tokens</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Total Tokens</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Cost (₹ / $)</th>
                  </tr>
                </thead>
                <tbody>
                  {by_branch.map((b) => (
                    <tr key={b.branch_id || 'company'} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '8px', fontWeight: 600, color: '#0f172a' }}>
                        {b.branch_name}
                      </td>
                      <td style={{ padding: '8px', color: '#64748b' }}>
                        {b.branch_code}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                        {formatNumber(b.calls)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                        {formatNumber(b.tokens_in)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                        {formatNumber(b.tokens_out)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                        {formatNumber(b.total_tokens)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', fontWeight: 600, color: '#0f172a' }}>
                        <div>₹{Number(b.cost_inr !== undefined ? b.cost_inr : (b.estimated_cost_usd * 85)).toFixed(2)}</div>
                        <div style={{ fontSize: '10.5px', fontWeight: 400, color: '#64748b' }}>{formatUSD(b.estimated_cost_usd)} USD</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* ── Daily Trends Table ────────────────────────────────────── */}
          <div style={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '14px 16px', boxShadow: '0 1px 2px rgba(0,0,0,0.02)' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 700, margin: '0 0 10px 0', color: '#0f172a' }}>
              Daily Usage &amp; Cost Trend
            </h3>
            {daily_trends.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '24px', color: '#94a3b8', fontSize: '12.5px' }}>
                No daily activity recorded in the selected date range.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '10.5px', textTransform: 'uppercase' }}>
                    <th style={{ padding: '6px 8px' }}>Date</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Total Calls</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Success / Failed</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Total Tokens</th>
                    <th style={{ padding: '6px 8px', textAlign: 'right' }}>Estimated Cost (₹ / $)</th>
                  </tr>
                </thead>
                <tbody>
                  {daily_trends.map((t) => (
                    <tr key={t.date} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '8px', fontWeight: 600, color: '#0f172a' }}>
                        {t.date}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                        {formatNumber(t.calls)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                        <span style={{ color: '#16a34a' }}>{t.successful_calls}</span> / <span style={{ color: t.failed_calls > 0 ? '#dc2626' : '#64748b' }}>{t.failed_calls}</span>
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', color: '#475569' }}>
                        {formatNumber(t.total_tokens)}
                      </td>
                      <td style={{ padding: '8px', textAlign: 'right', fontWeight: 600, color: '#0f172a' }}>
                        <div>₹{Number(t.cost_inr !== undefined ? t.cost_inr : (t.estimated_cost_usd * 85)).toFixed(2)}</div>
                        <div style={{ fontSize: '10.5px', fontWeight: 400, color: '#64748b' }}>{formatUSD(t.estimated_cost_usd)} USD</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
