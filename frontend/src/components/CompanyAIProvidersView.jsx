import React, { useState, useEffect } from 'react';
import { api } from '../api';

export default function CompanyAIProvidersView({ showToast, branchesList = [] }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Settings & Budget
  const [settings, setSettings] = useState(null);
  const [allowedProviders, setAllowedProviders] = useState(['gemini', 'openai', 'anthropic']);
  const [defaultReadProvider, setDefaultReadProvider] = useState('gemini');
  const [defaultReadModel, setDefaultReadModel] = useState('gemini-2.0-flash');
  const [defaultGenProvider, setDefaultGenProvider] = useState('gemini');
  const [defaultGenModel, setDefaultGenModel] = useState('gemini-2.0-flash');
  const [savingSettings, setSavingSettings] = useState(false);

  // Consents & Credentials
  const [consents, setConsents] = useState([]);
  const [credentials, setCredentials] = useState([]);
  const [showConsentModal, setShowConsentModal] = useState(null); // provider_key
  const [consentTermsAccepted, setConsentTermsAccepted] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // Add / Edit Key Modal
  const [showKeyModal, setShowKeyModal] = useState(null); // provider_key
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [savingKey, setSavingKey] = useState(false);

  // Connection Test
  const [testingConn, setTestingConn] = useState({}); // { [provider_key]: { loading, result } }

  // Usage Logs
  const [usageLogs, setUsageLogs] = useState([]);
  const [usageAggregates, setUsageAggregates] = useState(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [usageFilterBranch, setUsageFilterBranch] = useState('');
  const [usageFilterProvider, setUsageFilterProvider] = useState('');
  const [usageFilterOperation, setUsageFilterOperation] = useState('');

  const providerModels = {
    gemini: ['gemini-3.6-flash', 'gemini-3.8-flash', 'gemini-3.5-flash-lite', 'gemini-3.7-flash', 'gemini-3.5-flash'],
    openai: ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo', 'o3-mini'],
    anthropic: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
  };

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setLoading(true);
    setError('');
    try {
      await Promise.all([loadSettings(), loadCredentials(), loadUsage()]);
    } catch (err) {
      setError(err.message || 'Failed to load AI settings.');
    } finally {
      setLoading(false);
    }
  };

  const loadSettings = async () => {
    const res = await api.getCompanyAISettings();
    setSettings(res);
    setAllowedProviders(res.allowed_providers || ['gemini', 'openai', 'anthropic']);
    setDefaultReadProvider(res.default_read_provider || 'gemini');
    setDefaultReadModel(res.default_read_model || 'gemini-2.0-flash');
    setDefaultGenProvider(res.default_generate_provider || 'gemini');
    setDefaultGenModel(res.default_generate_model || 'gemini-2.0-flash');
    setConsents(res.consents || []);
  };

  const loadCredentials = async () => {
    const res = await api.getCompanyAICredentials();
    setCredentials(res || []);
  };

  const loadUsage = async () => {
    setUsageLoading(true);
    try {
      const params = {};
      if (usageFilterBranch) params.branch_id = usageFilterBranch;
      if (usageFilterProvider) params.provider = usageFilterProvider;
      if (usageFilterOperation) params.operation = usageFilterOperation;
      const res = await api.getCompanyAIUsage(params);
      setUsageLogs(res.items || []);
      setUsageAggregates(res.aggregates || null);
    } catch (err) {
      console.error('Failed to load usage logs:', err);
    } finally {
      setUsageLoading(false);
    }
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    setSavingSettings(true);
    setError('');
    setSuccess('');
    try {
      await api.updateCompanyAISettings({
        allowed_providers: allowedProviders,
        default_read_provider: defaultReadProvider,
        default_read_model: defaultReadModel,
        default_generate_provider: defaultGenProvider,
        default_generate_model: defaultGenModel,
      });
      setSuccess('AI settings saved successfully.');
      if (showToast) showToast('AI settings saved successfully.', 'success');
      setTimeout(() => setSuccess(''), 4000);
      loadSettings();
    } catch (err) {
      setError(err.message || 'Failed to update AI settings.');
    } finally {
      setSavingSettings(false);
    }
  };

  const handleGrantConsent = async (providerKey) => {
    setActionLoading(true);
    setError('');
    try {
      await api.grantCompanyAIConsent(providerKey, 'v1.0');
      setShowConsentModal(null);
      setConsentTermsAccepted(false);
      if (showToast) showToast(`Consent granted for ${providerKey}.`, 'success');
      await loadSettings();
    } catch (err) {
      setError(err.message || 'Failed to grant consent.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRevokeConsent = async (providerKey) => {
    if (!window.confirm(`Revoke consent for ${providerKey}? All branches configured with this provider will be blocked from external AI processing immediately.`)) {
      return;
    }
    setActionLoading(true);
    setError('');
    try {
      await api.revokeCompanyAIConsent(providerKey);
      if (showToast) showToast(`Consent revoked for ${providerKey}.`, 'info');
      await loadSettings();
    } catch (err) {
      setError(err.message || 'Failed to revoke consent.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSaveKey = async (e) => {
    e.preventDefault();
    if (!apiKeyInput.trim()) return;
    setSavingKey(true);
    setError('');
    try {
      await api.saveCompanyAICredential(showKeyModal, apiKeyInput.trim());
      setShowKeyModal(null);
      setApiKeyInput('');
      if (showToast) showToast(`Credential saved for ${showKeyModal}. Key stored write-only.`, 'success');
      await loadCredentials();
    } catch (err) {
      setError(err.message || 'Failed to save credential.');
    } finally {
      setSavingKey(false);
    }
  };

  const handleDeleteKey = async (credentialId, providerKey) => {
    if (!window.confirm(`Delete company credential for ${providerKey}?`)) return;
    try {
      await api.deleteCompanyAICredential(credentialId);
      if (showToast) showToast(`Credential for ${providerKey} deleted.`, 'info');
      await loadCredentials();
    } catch (err) {
      setError(err.message || 'Failed to delete credential.');
    }
  };

  const handleTestConnection = async (providerKey) => {
    let model;
    if (providerKey === defaultReadProvider && defaultReadModel) {
      model = defaultReadModel;
    } else if (providerKey === defaultGenProvider && defaultGenModel) {
      model = defaultGenModel;
    } else {
      model = providerModels[providerKey]?.[0] || 'gemini-3.6-flash';
    }
    setTestingConn((prev) => ({ ...prev, [providerKey]: { loading: true, result: null } }));
    try {
      // test against first branch if available, or branch 0
      const branchId = branchesList[0]?.id || 1;
      const res = await api.testBranchAIConnection(branchId, providerKey, model);
      setTestingConn((prev) => ({ ...prev, [providerKey]: { loading: false, result: res } }));
    } catch (err) {
      setTestingConn((prev) => ({
        ...prev,
        [providerKey]: { loading: false, result: { success: false, message: err.message, latency_ms: 0 } },
      }));
    }
  };

  const getConsentStatus = (providerKey) => {
    const c = consents.find((x) => x.provider_key === providerKey && x.is_consented);
    return c || null;
  };

  const getCredential = (providerKey) => {
    return credentials.find((x) => x.provider_key === providerKey && x.status === 'active');
  };

  // Budget calculations (Dual Currency: INR + USD)
  const rate = settings?.budget?.exchange_rate || 85.0;
  const budgetLimitUSD = settings?.budget?.monthly_ai_budget_cents ? settings.budget.monthly_ai_budget_cents / 100 : 50;
  const budgetSpentUSD = settings?.budget?.ai_budget_spent_cents ? settings.budget.ai_budget_spent_cents / 100 : 0;
  const budgetLimitINR = settings?.budget?.monthly_ai_budget_inr || (budgetLimitUSD * rate);
  const budgetSpentINR = settings?.budget?.ai_budget_spent_inr !== undefined ? settings.budget.ai_budget_spent_inr : (budgetSpentUSD * rate);
  const budgetPct = Math.min(100, Math.round((budgetSpentUSD / budgetLimitUSD) * 100));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '22px', fontWeight: 700, margin: '0 0 6px 0', color: '#0f172a' }}>
            AI &amp; Automation Architecture
          </h2>
          <p style={{ margin: 0, color: '#64748b', fontSize: '13.5px' }}>
            Multi-provider governance (Google Gemini, OpenAI GPT, Anthropic Claude). Manage provider permissions, company data consents, encrypted API keys, and attempt-level audit logs.
          </p>
        </div>
      </div>

      {error && (
        <div style={{ padding: '14px 18px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', borderRadius: '10px', fontSize: '13.5px' }}>
          {error}
        </div>
      )}

      {success && (
        <div style={{ padding: '14px 18px', backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534', borderRadius: '10px', fontSize: '13.5px' }}>
          {success}
        </div>
      )}

      {/* CARD 1: BUDGET & SPENDING */}
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e2e8f0',
        padding: '20px 24px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Company Monthly AI Budget (Dual Currency ₹ / $)
            </span>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '26px', fontWeight: 800, color: '#0f172a' }}>
                ₹{Number(budgetSpentINR).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span style={{ fontSize: '15px', color: '#64748b' }}>
                / ₹{Number(budgetLimitINR).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} limit
              </span>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#0284c7', backgroundColor: '#e0f2fe', padding: '2px 8px', borderRadius: '4px' }}>
                ${budgetSpentUSD.toFixed(2)} / ${budgetLimitUSD.toFixed(2)} USD
              </span>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span style={{
              display: 'inline-block',
              padding: '4px 12px',
              borderRadius: '20px',
              fontSize: '12px',
              fontWeight: 700,
              backgroundColor: budgetPct >= 90 ? '#fef2f2' : budgetPct >= 75 ? '#fffbeb' : '#f0fdf4',
              color: budgetPct >= 90 ? '#b91c1c' : budgetPct >= 75 ? '#b45309' : '#15803d',
              border: `1px solid ${budgetPct >= 90 ? '#fecaca' : budgetPct >= 75 ? '#fde68a' : '#bbf7d0'}`,
            }}>
              {budgetPct}% Used &middot; ₹{(budgetLimitINR - budgetSpentINR).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${(budgetLimitUSD - budgetSpentUSD).toFixed(2)} USD) Remaining
            </span>
          </div>
        </div>

        {/* Visual Progress Bar */}
        <div style={{ width: '100%', height: '8px', backgroundColor: '#f1f5f9', borderRadius: '4px', overflow: 'hidden' }}>
          <div style={{
            width: `${budgetPct}%`,
            height: '100%',
            backgroundColor: budgetPct >= 90 ? '#ef4444' : budgetPct >= 75 ? '#f59e0b' : '#10b981',
            borderRadius: '4px',
            transition: 'width 0.4s ease',
          }} />
        </div>
      </div>

      {/* CARD 2: PROVIDER MATRIX & CONSENTS */}
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e2e8f0',
        overflow: 'hidden',
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}>
        <div style={{ padding: '18px 24px', borderBottom: '1px solid #f1f5f9', backgroundColor: '#f8fafc' }}>
          <h3 style={{ margin: '0 0 2px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
            External AI Providers &amp; Mandatory Data Consent
          </h3>
          <p style={{ margin: 0, fontSize: '12.5px', color: '#64748b' }}>
            Explicit consent is legally required before transmitting customer document scans to external LLM providers. Revocation immediately takes effect across all branches.
          </p>
        </div>

        <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {['gemini', 'openai', 'anthropic'].map((provKey) => {
            const displayName = provKey === 'gemini' ? 'Google Gemini' : provKey === 'openai' ? 'OpenAI GPT' : 'Anthropic Claude';
            const consent = getConsentStatus(provKey);
            const cred = getCredential(provKey);
            const testInfo = testingConn[provKey];

            return (
              <div
                key={provKey}
                style={{
                  padding: '18px',
                  borderRadius: '10px',
                  border: '1px solid #e2e8f0',
                  backgroundColor: '#ffffff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '16px',
                }}
              >
                <div style={{ flex: '1 1 240px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                    <span style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>{displayName}</span>
                    <span style={{
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '12px',
                      backgroundColor: consent ? '#dcfce7' : '#fee2e2',
                      color: consent ? '#166534' : '#b91c1c',
                      border: `1px solid ${consent ? '#bbf7d0' : '#fecaca'}`,
                    }}>
                      {consent ? 'CONSENT ACTIVE' : 'CONSENT REQUIRED'}
                    </span>
                  </div>
                  <div style={{ fontSize: '12.5px', color: '#64748b' }}>
                    {consent
                      ? `Consented on ${new Date(consent.consented_at).toLocaleDateString()} (v${consent.terms_version})`
                      : 'Data transfer blocked until explicit consent is granted.'}
                  </div>
                  <div style={{ fontSize: '12px', color: '#475569', marginTop: '6px' }}>
                    <strong>API Key:</strong>{' '}
                    {cred ? (
                      <span style={{ fontFamily: 'monospace', color: '#0f172a', backgroundColor: '#f1f5f9', padding: '2px 6px', borderRadius: '4px' }}>
                        {cred.masked_key}
                      </span>
                    ) : (
                      <span style={{ color: '#94a3b8' }}>None (Inherits platform/env fallback)</span>
                    )}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  {/* Test Connection Button */}
                  <button
                    onClick={() => handleTestConnection(provKey)}
                    disabled={testInfo?.loading}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: '#ffffff',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: '#334155',
                      cursor: testInfo?.loading ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {testInfo?.loading ? 'Testing...' : 'Test Connection'}
                  </button>

                  {/* Add / Update Key Button */}
                  <button
                    onClick={() => setShowKeyModal(provKey)}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: '#ffffff',
                      fontSize: '12px',
                      fontWeight: 600,
                      color: '#334155',
                      cursor: 'pointer',
                    }}
                  >
                    {cred ? 'Update Key' : 'Add Custom Key'}
                  </button>

                  {/* Delete Key if exists */}
                  {cred && (
                    <button
                      onClick={() => handleDeleteKey(cred.id, displayName)}
                      style={{
                        padding: '6px 10px',
                        borderRadius: '6px',
                        border: '1px solid #fecaca',
                        backgroundColor: '#fff5f5',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: '#b91c1c',
                        cursor: 'pointer',
                      }}
                    >
                      Remove Key
                    </button>
                  )}

                  {/* Consent Toggle Button */}
                  {consent ? (
                    <button
                      onClick={() => handleRevokeConsent(provKey)}
                      disabled={actionLoading}
                      style={{
                        padding: '6px 14px',
                        borderRadius: '6px',
                        border: '1px solid #fecaca',
                        backgroundColor: '#fef2f2',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: '#b91c1c',
                        cursor: 'pointer',
                      }}
                    >
                      Revoke Consent
                    </button>
                  ) : (
                    <button
                      onClick={() => setShowConsentModal(provKey)}
                      disabled={actionLoading}
                      style={{
                        padding: '6px 14px',
                        borderRadius: '6px',
                        border: '1px solid #86efac',
                        backgroundColor: '#f0fdf4',
                        fontSize: '12px',
                        fontWeight: 700,
                        color: '#15803d',
                        cursor: 'pointer',
                      }}
                    >
                      Grant Consent
                    </button>
                  )}
                </div>

                {/* Live Test Result Banner */}
                {testInfo?.result && (
                  <div style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    backgroundColor: testInfo.result.success ? '#f0fdf4' : '#fef2f2',
                    border: `1px solid ${testInfo.result.success ? '#bbf7d0' : '#fecaca'}`,
                    color: testInfo.result.success ? '#166534' : '#b91c1c',
                  }}>
                    {testInfo.result.success
                      ? `✓ Live connection verified (${testInfo.result.latency_ms}ms)`
                      : `✕ Connection test failed: ${testInfo.result.message}`}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* CARD 3: COMPANY DEFAULTS & PERMITTED PROVIDERS FORM */}
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e2e8f0',
        padding: '24px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}>
        <h3 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
          Company Defaults &amp; Permitted Providers
        </h3>
        <p style={{ margin: '0 0 18px 0', fontSize: '12.5px', color: '#64748b' }}>
          Branches inherit these defaults unless explicitly overridden in branch AI settings.
        </p>

        <form onSubmit={handleSaveSettings}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '20px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                Default Reading Provider
              </label>
              <select
                value={defaultReadProvider}
                onChange={(e) => {
                  setDefaultReadProvider(e.target.value);
                  setDefaultReadModel(providerModels[e.target.value]?.[0] || '');
                }}
                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
              >
                <option value="gemini">Google Gemini</option>
                <option value="openai">OpenAI GPT</option>
                <option value="anthropic">Anthropic Claude</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                Default Reading Model
              </label>
              <select
                value={defaultReadModel}
                onChange={(e) => setDefaultReadModel(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
              >
                {(providerModels[defaultReadProvider] || []).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                Default Generation Provider
              </label>
              <select
                value={defaultGenProvider}
                onChange={(e) => {
                  setDefaultGenProvider(e.target.value);
                  setDefaultGenModel(providerModels[e.target.value]?.[0] || '');
                }}
                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
              >
                <option value="gemini">Google Gemini</option>
                <option value="openai">OpenAI GPT</option>
                <option value="anthropic">Anthropic Claude</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                Default Generation Model
              </label>
              <select
                value={defaultGenModel}
                onChange={(e) => setDefaultGenModel(e.target.value)}
                style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
              >
                {(providerModels[defaultGenProvider] || []).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="submit"
              disabled={savingSettings}
              style={{
                padding: '9px 20px',
                borderRadius: '8px',
                backgroundColor: '#9333ea',
                color: '#ffffff',
                border: 'none',
                fontWeight: 600,
                fontSize: '13px',
                cursor: savingSettings ? 'not-allowed' : 'pointer',
              }}
            >
              {savingSettings ? 'Saving...' : 'Save Company Defaults'}
            </button>
          </div>
        </form>
      </div>

      {/* CARD 4: ATTEMPT-LEVEL USAGE LOGS */}
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e2e8f0',
        overflow: 'hidden',
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}>
        <div style={{ padding: '18px 24px', borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h3 style={{ margin: '0 0 2px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
              Execution &amp; Cost Audit Trail
            </h3>
            <p style={{ margin: 0, fontSize: '12.5px', color: '#64748b' }}>
              Live attempt-level execution logs including primary and fallback executions, token usage, latency, and costs.
            </p>
          </div>

          {/* Quick Filters */}
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <select
              value={usageFilterBranch}
              onChange={(e) => { setUsageFilterBranch(e.target.value); }}
              style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '12px' }}
            >
              <option value="">All Branches</option>
              {branchesList.map((b) => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>

            <select
              value={usageFilterProvider}
              onChange={(e) => setUsageFilterProvider(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '12px' }}
            >
              <option value="">All Providers</option>
              <option value="gemini">Gemini</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Claude</option>
            </select>

            <button
              onClick={loadUsage}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                backgroundColor: '#ffffff',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Refresh
            </button>
          </div>
        </div>

        {/* Aggregates Banner */}
        {usageAggregates && (
          <div style={{
            padding: '12px 24px',
            backgroundColor: '#f8fafc',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            gap: '24px',
            flexWrap: 'wrap',
            fontSize: '13px',
          }}>
            <div><span style={{ color: '#64748b' }}>Total Incurred:</span> <strong>${(usageAggregates.total_cost_cents / 100).toFixed(2)}</strong></div>
            <div><span style={{ color: '#64748b' }}>Total Tokens:</span> <strong>{(usageAggregates.total_tokens_in + usageAggregates.total_tokens_out).toLocaleString()}</strong></div>
            <div><span style={{ color: '#64748b' }}>Attempts:</span> <strong>{usageAggregates.total_attempts}</strong> ({usageAggregates.successful_attempts} successful, {usageAggregates.failed_attempts} failed)</div>
            <div><span style={{ color: '#64748b' }}>Avg Latency:</span> <strong>{usageAggregates.avg_latency_ms}ms</strong></div>
          </div>
        )}

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px', textAlign: 'left' }}>
            <thead>
              <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase' }}>
                <th style={{ padding: '10px 16px' }}>Timestamp</th>
                <th style={{ padding: '10px 16px' }}>Operation</th>
                <th style={{ padding: '10px 16px' }}>Provider / Model</th>
                <th style={{ padding: '10px 16px' }}>Execution</th>
                <th style={{ padding: '10px 16px' }}>Tokens (In / Out)</th>
                <th style={{ padding: '10px 16px' }}>Cost</th>
                <th style={{ padding: '10px 16px' }}>Latency</th>
                <th style={{ padding: '10px 16px' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {usageLoading ? (
                <tr>
                  <td colSpan={8} style={{ padding: '40px 0', textAlign: 'center', color: '#64748b' }}>
                    Loading execution logs...
                  </td>
                </tr>
              ) : usageLogs.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: '40px 0', textAlign: 'center', color: '#94a3b8' }}>
                    No AI processing attempts recorded yet.
                  </td>
                </tr>
              ) : (
                usageLogs.map((log) => (
                  <tr key={log.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '12px 16px', color: '#64748b', whiteSpace: 'nowrap' }}>
                      {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 600, color: '#0f172a' }}>
                      <span style={{
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontSize: '11px',
                        backgroundColor: log.operation === 'read' ? '#eff6ff' : '#faf5ff',
                        color: log.operation === 'read' ? '#1d4ed8' : '#7e22ce',
                      }}>
                        {log.operation.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ fontWeight: 600, color: '#0f172a' }}>{log.provider}</div>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>{log.model}</div>
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontSize: '11px',
                        fontWeight: 600,
                        backgroundColor: log.is_fallback ? '#fff7ed' : '#f1f5f9',
                        color: log.is_fallback ? '#c2410c' : '#475569',
                      }}>
                        {log.is_fallback ? `Fallback (Attempt #${log.attempt_number})` : 'Primary (Attempt #1)'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontSize: '11px', color: '#334155' }}>
                      {log.tokens_in} / {log.tokens_out}
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 600, color: '#0f172a' }}>
                      ${(log.cost_cents / 100).toFixed(2)}
                    </td>
                    <td style={{ padding: '12px 16px', color: '#64748b' }}>
                      {log.latency_ms}ms
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: '12px',
                        fontSize: '11px',
                        fontWeight: 700,
                        backgroundColor: log.success ? '#ecfdf5' : '#fef2f2',
                        color: log.success ? '#047857' : '#b91c1c',
                        border: `1px solid ${log.success ? '#a7f3d0' : '#fecaca'}`,
                      }}>
                        {log.success ? 'SUCCESS' : (log.error_code || 'FAILED')}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* MODAL 1: GRANT CONSENT MODAL */}
      {showConsentModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1100,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '14px',
            maxWidth: '520px',
            width: '100%',
            padding: '24px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
          }}>
            <h3 style={{ margin: '0 0 10px 0', fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
              External AI Processing Consent — {showConsentModal.toUpperCase()}
            </h3>
            <p style={{ fontSize: '13px', color: '#475569', lineHeight: 1.6, margin: '0 0 16px 0' }}>
              By granting consent, you authorize our platform to transmit receipt, invoice, and bill documents belonging to your company to <strong>{showConsentModal}</strong>'s external cloud API endpoints for optical character recognition and field parsing.
            </p>
            <div style={{ padding: '12px', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '18px', fontSize: '12px', color: '#64748b' }}>
              • Credentials are encrypted at rest with AES-256-GCM.<br/>
              • You may revoke this consent at any time to immediately block all calls.<br/>
              • Processing logs record audit timestamps and authorized user IDs.
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 600, color: '#1e293b', marginBottom: '20px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={consentTermsAccepted}
                onChange={(e) => setConsentTermsAccepted(e.target.checked)}
              />
              I accept the data processing terms for {showConsentModal}.
            </label>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                type="button"
                onClick={() => { setShowConsentModal(null); setConsentTermsAccepted(false); }}
                style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#fff', fontSize: '13px', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!consentTermsAccepted || actionLoading}
                onClick={() => handleGrantConsent(showConsentModal)}
                style={{
                  padding: '8px 18px',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: '#16a34a',
                  color: '#fff',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: !consentTermsAccepted || actionLoading ? 'not-allowed' : 'pointer',
                }}
              >
                {actionLoading ? 'Granting...' : 'Confirm & Grant Consent'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: CONFIGURE WRITE-ONLY API KEY MODAL */}
      {showKeyModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1100,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '14px',
            maxWidth: '500px',
            width: '100%',
            padding: '24px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
          }}>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
              Set {showKeyModal.toUpperCase()} API Key
            </h3>
            <p style={{ fontSize: '12.5px', color: '#64748b', margin: '0 0 16px 0' }}>
              Keys are stored write-only. Once submitted, the key is encrypted with AES-256-GCM. The plaintext will never be returned via API or logs.
            </p>

            <form onSubmit={handleSaveKey}>
              <div style={{ marginBottom: '18px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                  API Key *
                </label>
                <input
                  type="password"
                  required
                  placeholder={`Enter ${showKeyModal} secret API key...`}
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => { setShowKeyModal(null); setApiKeyInput(''); }}
                  style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#fff', fontSize: '13px', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingKey || !apiKeyInput.trim()}
                  style={{
                    padding: '8px 18px',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: '#9333ea',
                    color: '#fff',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: savingKey ? 'not-allowed' : 'pointer',
                  }}
                >
                  {savingKey ? 'Encrypting & Saving...' : 'Save Encrypted Key'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
