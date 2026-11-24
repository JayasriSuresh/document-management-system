import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';

export default function CompanyAIProvidersView({ showToast, branchesList = [] }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // ── Company AI Info & Consents ──────────────────────────────────────────────
  const [aiInfo, setAiInfo] = useState(null);
  const [consents, setConsents] = useState([]);

  // Consent modal
  const [showConsentModal, setShowConsentModal] = useState(null); // provider_key
  const [consentTermsAccepted, setConsentTermsAccepted] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // Connection Test
  const [testingConn, setTestingConn] = useState({}); // { [provider_key]: { loading, result } }

  // ── Model Request Workflow ──────────────────────────────────────────────────
  const [companyRequests, setCompanyRequests] = useState([]);
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [submittingRequest, setSubmittingRequest] = useState(false);
  const [requestForm, setRequestForm] = useState({
    modelSelection: '',
    task_type: 'extraction',
    reason: '',
  });

  // ── Load Data ───────────────────────────────────────────────────────────────
  const loadAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [infoRes, settingsRes, reqsRes] = await Promise.all([
        api.getCompanyAIInfo().catch(() => null),
        api.getCompanyAISettings().catch(() => ({ consents: [] })),
        api.getCompanyAIRequests().catch(() => []),
      ]);
      setAiInfo(infoRes);
      setConsents(settingsRes?.consents || []);
      setCompanyRequests(reqsRes || []);

      if (infoRes?.available_catalogue_models?.length > 0 && !requestForm.modelSelection) {
        const first = infoRes.available_catalogue_models[0];
        setRequestForm((prev) => ({
          ...prev,
          modelSelection: `${first.provider_key}::${first.model_id}`,
        }));
      }
    } catch (err) {
      setError(err.message || 'Failed to load AI configuration.');
    } finally {
      setLoading(false);
    }
  }, [requestForm.modelSelection]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // ── Consent Handlers ────────────────────────────────────────────────────────
  const handleGrantConsent = async (providerKey) => {
    setActionLoading(true);
    try {
      await api.grantCompanyAIConsent(providerKey, 'v1.0');
      setShowConsentModal(null);
      setConsentTermsAccepted(false);
      showToast?.(`Consent recorded for ${providerKey.toUpperCase()}.`, 'success');
      const st = await api.getCompanyAISettings();
      setConsents(st.consents || []);
    } catch (err) {
      showToast?.(err.message || 'Failed to grant consent.', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRevokeConsent = async (providerKey) => {
    if (!window.confirm(`Revoke data consent for ${providerKey.toUpperCase()}? Automated processing with this provider will be blocked.`)) {
      return;
    }
    setActionLoading(true);
    try {
      await api.revokeCompanyAIConsent(providerKey);
      showToast?.(`Consent revoked for ${providerKey.toUpperCase()}.`, 'info');
      const st = await api.getCompanyAISettings();
      setConsents(st.consents || []);
    } catch (err) {
      showToast?.(err.message || 'Failed to revoke consent.', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleTestConnection = async (providerKey, assignedModel) => {
    const branchId = branchesList[0]?.id || 1;
    const model = assignedModel || 'gemini-2.0-flash';
    setTestingConn((prev) => ({ ...prev, [providerKey]: { loading: true, result: null } }));
    try {
      const res = await api.testBranchAIConnection(branchId, providerKey, model);
      setTestingConn((prev) => ({ ...prev, [providerKey]: { loading: false, result: res } }));
      if (res.success) {
        showToast?.(`${providerKey.toUpperCase()} connection verified (${res.latency_ms}ms).`, 'success');
      } else {
        showToast?.(`Connection failed: ${res.message}`, 'error');
      }
    } catch (err) {
      setTestingConn((prev) => ({
        ...prev,
        [providerKey]: { loading: false, result: { success: false, message: err.message, latency_ms: 0 } },
      }));
    }
  };

  // ── Request Handlers ────────────────────────────────────────────────────────
  const handleSubmitRequest = async (e) => {
    e.preventDefault();
    if (!requestForm.modelSelection || !requestForm.reason.trim()) {
      showToast?.('Please select a model and provide a reason.', 'error');
      return;
    }

    const [providerKey, modelId] = requestForm.modelSelection.split('::');
    setSubmittingRequest(true);
    try {
      await api.submitCompanyAIRequest({
        provider_key: providerKey,
        model_id: modelId,
        task_type: requestForm.task_type,
        reason: requestForm.reason.trim(),
      });
      setShowRequestModal(false);
      setRequestForm((prev) => ({ ...prev, reason: '' }));
      showToast?.('AI model access request submitted to Master Admin.', 'success');
      const reqs = await api.getCompanyAIRequests();
      setCompanyRequests(reqs || []);
    } catch (err) {
      showToast?.(err.message || 'Failed to submit request.', 'error');
    } finally {
      setSubmittingRequest(false);
    }
  };

  const handleCancelRequest = async (requestId) => {
    if (!window.confirm('Cancel this pending request?')) return;
    try {
      await api.cancelCompanyAIRequest(requestId);
      showToast?.(`Request #${requestId} cancelled.`, 'info');
      const reqs = await api.getCompanyAIRequests();
      setCompanyRequests(reqs || []);
    } catch (err) {
      showToast?.(err.message || 'Failed to cancel request.', 'error');
    }
  };

  const isAiGloballyEnabled = aiInfo?.is_ai_enabled !== false;

  const getConsentForProvider = (providerKey) => {
    return consents.find((c) => c.provider_key === providerKey && c.is_consented);
  };

  if (loading && !aiInfo) {
    return (
      <div style={{ padding: '48px', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
        <div className="spinner" style={{ margin: '0 auto 10px auto' }} />
        Loading AI configuration...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '0 0 4px 0', color: '#0f172a' }}>
            AI &amp; Providers
          </h2>
          <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
            Approved foundation models, data compliance consents, and model access requests.
          </p>
        </div>

        <button
          onClick={() => setShowRequestModal(true)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            backgroundColor: '#ef233c',
            color: '#ffffff',
            padding: '7px 14px',
            borderRadius: '6px',
            border: 'none',
            fontWeight: 600,
            fontSize: '12.5px',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(239, 35, 60, 0.25)',
            transition: 'background-color 0.15s ease',
          }}
          onMouseOver={(e) => (e.currentTarget.style.backgroundColor = '#d90429')}
          onMouseOut={(e) => (e.currentTarget.style.backgroundColor = '#ef233c')}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Request Model Access
        </button>
      </div>

      {error && (
        <div style={{ padding: '12px 16px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', borderRadius: '8px', fontSize: '13px' }}>
          {error}
        </div>
      )}

      {/* ── Status Strip ───────────────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          padding: '10px 16px',
          backgroundColor: '#ffffff',
          borderRadius: '8px',
          border: '1px solid #e2e8f0',
          fontSize: '13px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: isAiGloballyEnabled ? '#16a34a' : '#dc2626',
            }}
          />
          <span style={{ fontWeight: 600, color: '#1e293b' }}>
            AI Access: {isAiGloballyEnabled ? 'Active' : 'Disabled by Platform Admin'}
          </span>
          <span style={{ color: '#cbd5e1' }}>&bull;</span>
          <span style={{ color: '#64748b', fontSize: '12.5px' }}>
            Models and API credentials are centrally managed by Master Admin
          </span>
        </div>

        <Link
          to="/company/ai-usage"
          style={{
            color: '#ef233c',
            fontSize: '12.5px',
            fontWeight: 600,
            textDecoration: 'none',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          Usage &amp; Cost Telemetry &rarr;
        </Link>
      </div>

      {/* ── SECTION 1: APPROVED MODELS BY TASK ─────────────────────────────── */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '10px',
          border: '1px solid #e2e8f0',
          padding: '20px',
          boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
        }}
      >
        <div style={{ marginBottom: '14px' }}>
          <h3 style={{ margin: '0 0 2px 0', fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
            Approved Models
          </h3>
          <p style={{ margin: 0, fontSize: '12.5px', color: '#64748b' }}>
            Active AI models assigned to your company for automated processing tasks.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '14px' }}>
          {[
            { key: 'ocr', title: 'OCR & Document Text', desc: 'Scan and image parsing' },
            { key: 'extraction', title: 'Invoice Data Extraction', desc: 'Line items and tax fields' },
            { key: 'generation', title: 'Invoice Generation', desc: 'Drafts and item notes' },
          ].map((task) => {
            const assignment = (aiInfo?.assignments || []).find((a) => a.task_type === task.key);
            const providerKey = assignment?.provider_key || 'gemini';
            const modelName = assignment?.model_display_name || assignment?.model_id || 'Gemini 2.0 Flash';
            const modelId = assignment?.model_id || 'gemini-2.0-flash';
            const consent = getConsentForProvider(providerKey);

            return (
              <div
                key={task.key}
                style={{
                  padding: '14px 16px',
                  borderRadius: '8px',
                  border: '1px solid #f1f5f9',
                  backgroundColor: '#f8fafc',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '10px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: '#64748b' }}>
                      {task.title}
                    </span>
                    <span
                      style={{
                        fontSize: '10px',
                        fontWeight: 600,
                        padding: '1px 6px',
                        borderRadius: '4px',
                        backgroundColor: '#ffffff',
                        border: '1px solid #e2e8f0',
                        color: '#475569',
                      }}
                    >
                      {providerKey.toUpperCase()}
                    </span>
                  </div>

                  <div style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                    {modelName}
                  </div>
                  <div style={{ fontSize: '11.5px', fontFamily: 'monospace', color: '#64748b', marginTop: '2px' }}>
                    {modelId}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '8px', borderTop: '1px solid #e2e8f0', fontSize: '11.5px' }}>
                  <span style={{ color: consent ? '#166534' : '#b45309', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: consent ? '#16a34a' : '#f59e0b' }} />
                    {consent ? 'Consented' : 'Consent needed'}
                  </span>
                  <span style={{ color: '#166534', fontWeight: 600 }}>Active</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── SECTION 2: DATA TRANSFER CONSENTS ──────────────────────────────── */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '10px',
          border: '1px solid #e2e8f0',
          overflow: 'hidden',
          boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
        }}
      >
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #f1f5f9' }}>
          <h3 style={{ margin: '0 0 2px 0', fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
            Provider Data Transfer Consents
          </h3>
          <p style={{ margin: 0, fontSize: '12.5px', color: '#64748b' }}>
            Explicit consent required by compliance before routing document scans to external LLMs.
          </p>
        </div>

        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
          <thead>
            <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '12px', fontWeight: 600 }}>
              <th style={{ padding: '10px 20px' }}>Provider</th>
              <th style={{ padding: '10px 20px' }}>Status</th>
              <th style={{ padding: '10px 20px' }}>Consent Details</th>
              <th style={{ padding: '10px 20px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {[
              { key: 'gemini', name: 'Google Gemini' },
              { key: 'openai', name: 'OpenAI GPT' },
              { key: 'anthropic', name: 'Anthropic Claude' },
            ].map((prov) => {
              const consent = getConsentForProvider(prov.key);
              const testInfo = testingConn[prov.key];

              return (
                <tr key={prov.key} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '12px 20px', fontWeight: 600, color: '#1e293b' }}>
                    {prov.name}
                  </td>
                  <td style={{ padding: '12px 20px' }}>
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '2px 8px',
                        borderRadius: '12px',
                        backgroundColor: consent ? '#dcfce7' : '#fee2e2',
                        color: consent ? '#166534' : '#991b1b',
                      }}
                    >
                      {consent ? 'Consented' : 'Not Granted'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 20px', color: '#64748b', fontSize: '12px' }}>
                    {consent
                      ? `Approved on ${new Date(consent.consented_at).toLocaleDateString()} (v${consent.terms_version || '1.0'})`
                      : 'Data transfer blocked until consent is granted.'}
                  </td>
                  <td style={{ padding: '12px 20px', textAlign: 'right' }}>
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                      <button
                        onClick={() => handleTestConnection(prov.key)}
                        disabled={testInfo?.loading}
                        style={{
                          padding: '4px 10px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          backgroundColor: '#ffffff',
                          fontSize: '12px',
                          fontWeight: 500,
                          color: '#475569',
                          cursor: testInfo?.loading ? 'not-allowed' : 'pointer',
                        }}
                      >
                        {testInfo?.loading ? 'Testing...' : 'Test'}
                      </button>

                      {consent ? (
                        <button
                          onClick={() => handleRevokeConsent(prov.key)}
                          disabled={actionLoading}
                          style={{
                            padding: '4px 10px',
                            borderRadius: '6px',
                            border: '1px solid #fecaca',
                            backgroundColor: '#fff',
                            fontSize: '12px',
                            fontWeight: 600,
                            color: '#b91c1c',
                            cursor: 'pointer',
                          }}
                        >
                          Revoke
                        </button>
                      ) : (
                        <button
                          onClick={() => setShowConsentModal(prov.key)}
                          disabled={actionLoading}
                          style={{
                            padding: '4px 12px',
                            borderRadius: '6px',
                            border: '1px solid #86efac',
                            backgroundColor: '#f0fdf4',
                            fontSize: '12px',
                            fontWeight: 600,
                            color: '#15803d',
                            cursor: 'pointer',
                          }}
                        >
                          Grant Consent
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── SECTION 3: MODEL ACCESS REQUESTS ──────────────────────────────── */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '10px',
          border: '1px solid #e2e8f0',
          overflow: 'hidden',
          boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
        }}
      >
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ margin: '0 0 2px 0', fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
              Model Access Requests
            </h3>
            <p style={{ margin: 0, fontSize: '12.5px', color: '#64748b' }}>
              Requests submitted to Master Admin for access to additional foundation models.
            </p>
          </div>
        </div>

        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
          <thead>
            <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '12px', fontWeight: 600 }}>
              <th style={{ padding: '10px 20px' }}>ID / Date</th>
              <th style={{ padding: '10px 20px' }}>Model &amp; Task</th>
              <th style={{ padding: '10px 20px' }}>Justification</th>
              <th style={{ padding: '10px 20px' }}>Status</th>
              <th style={{ padding: '10px 20px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {companyRequests.map((r) => {
              const st =
                r.status === 'approved'
                  ? { bg: '#dcfce7', text: '#166534' }
                  : r.status === 'rejected'
                  ? { bg: '#fee2e2', text: '#991b1b' }
                  : r.status === 'cancelled'
                  ? { bg: '#f1f5f9', text: '#64748b' }
                  : { bg: '#fef3c7', text: '#92400e' };

              return (
                <tr key={r.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '12px 20px' }}>
                    <div style={{ fontWeight: 600, color: '#1e293b' }}>#{r.id}</div>
                    <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                      {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}
                    </div>
                  </td>
                  <td style={{ padding: '12px 20px' }}>
                    <div style={{ fontWeight: 600, color: '#0f172a' }}>{r.model_id}</div>
                    <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'capitalize' }}>
                      {r.provider_key} &bull; {r.task_type}
                    </div>
                  </td>
                  <td style={{ padding: '12px 20px', maxWidth: '320px', color: '#475569', fontSize: '12.5px' }}>
                    <div>{r.reason}</div>
                    {r.decision_reason && (
                      <div style={{ fontSize: '11px', color: '#b91c1c', marginTop: '2px', fontStyle: 'italic' }}>
                        Note: {r.decision_reason}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '12px 20px' }}>
                    <span
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '2px 8px',
                        borderRadius: '12px',
                        backgroundColor: st.bg,
                        color: st.text,
                      }}
                    >
                      {r.status.toUpperCase()}
                    </span>
                  </td>
                  <td style={{ padding: '12px 20px', textAlign: 'right' }}>
                    {r.status === 'pending' ? (
                      <button
                        onClick={() => handleCancelRequest(r.id)}
                        style={{
                          padding: '3px 8px',
                          borderRadius: '4px',
                          border: '1px solid #fecaca',
                          backgroundColor: '#fff',
                          color: '#b91c1c',
                          fontSize: '11px',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Cancel
                      </button>
                    ) : (
                      <span style={{ color: '#94a3b8' }}>&mdash;</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {companyRequests.length === 0 && (
              <tr>
                <td colSpan="5" style={{ padding: '24px', textAlign: 'center', color: '#94a3b8', fontSize: '12.5px' }}>
                  No model requests submitted. Click &quot;Request Model Access&quot; above if your company requires other models.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── MODAL: REQUEST ACCESS ─────────────────────────────────────────── */}
      {showRequestModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15,23,42,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '16px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', width: '100%', maxWidth: '440px', padding: '22px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
              Request AI Model Access
            </h3>
            <p style={{ margin: '0 0 16px 0', fontSize: '12.5px', color: '#64748b' }}>
              Submit a model access request for Master Admin approval.
            </p>

            <form onSubmit={handleSubmitRequest} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                  Foundation Model *
                </label>
                <select
                  required
                  value={requestForm.modelSelection}
                  onChange={(e) => setRequestForm({ ...requestForm, modelSelection: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', fontWeight: 500 }}
                >
                  {(aiInfo?.available_catalogue_models || []).map((m) => (
                    <option key={`${m.provider_key}::${m.model_id}`} value={`${m.provider_key}::${m.model_id}`}>
                      {m.display_name} ({m.provider_key.toUpperCase()})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                  Intended Task *
                </label>
                <select
                  required
                  value={requestForm.task_type}
                  onChange={(e) => setRequestForm({ ...requestForm, task_type: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
                >
                  <option value="ocr">OCR &amp; Document Text</option>
                  <option value="extraction">Structured Data Extraction</option>
                  <option value="generation">Outbound Invoice Generation</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                  Business Justification *
                </label>
                <textarea
                  rows="3"
                  required
                  placeholder="Explain why this model is needed (e.g., higher accuracy for complex tables)..."
                  value={requestForm.reason}
                  onChange={(e) => setRequestForm({ ...requestForm, reason: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '6px' }}>
                <button
                  type="button"
                  onClick={() => setShowRequestModal(false)}
                  style={{ padding: '7px 14px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#fff', fontSize: '13px', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingRequest}
                  style={{
                    padding: '7px 16px',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: '#ef233c',
                    color: '#fff',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {submittingRequest ? 'Submitting...' : 'Submit Request'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: CONSENT ─────────────────────────────────────────────────── */}
      {showConsentModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(15,23,42,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '16px' }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', width: '100%', maxWidth: '460px', padding: '22px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 6px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
              Data Transfer Consent &mdash; {showConsentModal.toUpperCase()}
            </h3>
            <div style={{ maxHeight: '160px', overflowY: 'auto', padding: '10px 12px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', fontSize: '12px', color: '#475569', marginBottom: '14px', lineHeight: 1.5 }}>
              <p style={{ marginTop: 0 }}><strong>DMS AI Policy v1.0</strong></p>
              <p style={{ margin: 0 }}>You authorize transient transmission of document scan buffers to the selected foundation provider for OCR and data extraction. Data is processed in-memory under enterprise non-training agreements.</p>
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '12.5px', color: '#1e293b', marginBottom: '16px' }}>
              <input
                type="checkbox"
                checked={consentTermsAccepted}
                onChange={(e) => setConsentTermsAccepted(e.target.checked)}
              />
              <span>I confirm authorization on behalf of this company.</span>
            </label>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => { setShowConsentModal(null); setConsentTermsAccepted(false); }}
                style={{ padding: '7px 14px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#fff', fontSize: '13px', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!consentTermsAccepted || actionLoading}
                onClick={() => handleGrantConsent(showConsentModal)}
                style={{
                  padding: '7px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: consentTermsAccepted ? '#ef233c' : '#cbd5e1',
                  color: '#fff',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: consentTermsAccepted ? 'pointer' : 'not-allowed',
                }}
              >
                {actionLoading ? 'Saving...' : 'Grant Consent'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
