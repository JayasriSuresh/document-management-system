import React, { useState, useEffect } from 'react';
import { api } from '../api';

export default function BranchAIConfigModal({ branch, onClose, showToast }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [companyDefaults, setCompanyDefaults] = useState(null);

  // Read config state
  const [readConfig, setReadConfig] = useState({
    operation: 'read',
    primary_provider: 'gemini',
    primary_model: 'gemini-2.0-flash',
    fallback_provider: '',
    fallback_model: '',
    max_retries: 2,
    timeout_seconds: 30,
  });

  // Generate config state
  const [generateConfig, setGenerateConfig] = useState({
    operation: 'generate',
    primary_provider: 'gemini',
    primary_model: 'gemini-2.0-flash',
    fallback_provider: '',
    fallback_model: '',
    max_retries: 2,
    timeout_seconds: 30,
  });

  // Test connection state
  const [testingRead, setTestingRead] = useState(false);
  const [readTestResult, setReadTestResult] = useState(null);
  const [testingGen, setTestingGen] = useState(false);
  const [genTestResult, setGenTestResult] = useState(null);

  const providerModels = {
    gemini: ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.5-flash', 'gemini-3.6-flash'],
    openai: ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo', 'o3-mini'],
    anthropic: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
  };

  useEffect(() => {
    loadBranchConfig();
  }, [branch.id]);

  const loadBranchConfig = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.getBranchAIConfig(branch.id);
      setCompanyDefaults(res.company_defaults || {});

      if (res.configs?.read) {
        setReadConfig({
          operation: 'read',
          primary_provider: res.configs.read.primary_provider,
          primary_model: res.configs.read.primary_model,
          fallback_provider: res.configs.read.fallback_provider || '',
          fallback_model: res.configs.read.fallback_model || '',
          max_retries: res.configs.read.max_retries,
          timeout_seconds: res.configs.read.timeout_seconds,
        });
      } else if (res.company_defaults?.read) {
        setReadConfig((prev) => ({
          ...prev,
          primary_provider: res.company_defaults.read.provider || 'gemini',
          primary_model: res.company_defaults.read.model || 'gemini-2.0-flash',
        }));
      }

      if (res.configs?.generate) {
        setGenerateConfig({
          operation: 'generate',
          primary_provider: res.configs.generate.primary_provider,
          primary_model: res.configs.generate.primary_model,
          fallback_provider: res.configs.generate.fallback_provider || '',
          fallback_model: res.configs.generate.fallback_model || '',
          max_retries: res.configs.generate.max_retries,
          timeout_seconds: res.configs.generate.timeout_seconds,
        });
      } else if (res.company_defaults?.generate) {
        setGenerateConfig((prev) => ({
          ...prev,
          primary_provider: res.company_defaults.generate.provider || 'gemini',
          primary_model: res.company_defaults.generate.model || 'gemini-2.0-flash',
        }));
      }
    } catch (err) {
      setError(err.message || 'Failed to load branch AI configuration.');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');

    try {
      // 1. Save Read operation config
      const readPayload = {
        operation: 'read',
        primary_provider: readConfig.primary_provider,
        primary_model: readConfig.primary_model,
        fallback_provider: readConfig.fallback_provider || null,
        fallback_model: readConfig.fallback_model || null,
        max_retries: parseInt(readConfig.max_retries, 10),
        timeout_seconds: parseInt(readConfig.timeout_seconds, 10),
      };
      await api.updateBranchAIConfig(branch.id, readPayload);

      // 2. Save Generate operation config
      const genPayload = {
        operation: 'generate',
        primary_provider: generateConfig.primary_provider,
        primary_model: generateConfig.primary_model,
        fallback_provider: generateConfig.fallback_provider || null,
        fallback_model: generateConfig.fallback_model || null,
        max_retries: parseInt(generateConfig.max_retries, 10),
        timeout_seconds: parseInt(generateConfig.timeout_seconds, 10),
      };
      await api.updateBranchAIConfig(branch.id, genPayload);

      if (showToast) showToast(`AI configuration saved for branch ${branch.name}.`, 'success');
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to save branch AI config.');
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async (operation) => {
    if (operation === 'read') {
      setTestingRead(true);
      setReadTestResult(null);
      try {
        const res = await api.testBranchAIConnection(branch.id, readConfig.primary_provider, readConfig.primary_model);
        setReadTestResult(res);
      } catch (err) {
        setReadTestResult({ success: false, message: err.message, latency_ms: 0 });
      } finally {
        setTestingRead(false);
      }
    } else {
      setTestingGen(true);
      setGenTestResult(null);
      try {
        const res = await api.testBranchAIConnection(branch.id, generateConfig.primary_provider, generateConfig.primary_model);
        setGenTestResult(res);
      } catch (err) {
        setGenTestResult({ success: false, message: err.message, latency_ms: 0 });
      } finally {
        setTestingGen(false);
      }
    }
  };

  const allowedProviders = companyDefaults?.allowed_providers || ['gemini', 'openai', 'anthropic'];

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(15, 23, 42, 0.65)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '20px',
    }}>
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '16px',
        width: '100%',
        maxWidth: '720px',
        maxHeight: '90vh',
        overflowY: 'auto',
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
        border: '1px solid #e2e8f0',
      }}>
        {/* Header */}
        <div style={{
          padding: '20px 24px',
          borderBottom: '1px solid #f1f5f9',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                Branch AI Configuration
              </h3>
              <span style={{
                fontSize: '11px',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: '6px',
                backgroundColor: '#fee2e2',
                color: '#b91c1c',
                fontFamily: 'monospace',
              }}>
                {branch.code}
              </span>
            </div>
            <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#64748b' }}>
              {branch.name} &middot; Configure independent primary &amp; fallback AI models per operation.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '22px',
              cursor: 'pointer',
              color: '#94a3b8',
              lineHeight: 1,
            }}
          >
            &times;
          </button>
        </div>

        {error && (
          <div style={{ margin: '16px 24px 0', padding: '12px 16px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', borderRadius: '8px', fontSize: '13px' }}>
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ padding: '60px 0', textAlign: 'center', color: '#64748b' }}>
            <div className="spinner" style={{ margin: '0 auto 12px' }} />
            Loading branch AI configuration...
          </div>
        ) : (
          <form onSubmit={handleSave} style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>

            {/* OPERATION 1: INVOICE OCR & READING */}
            <div style={{
              border: '1px solid #e2e8f0',
              borderRadius: '12px',
              padding: '18px',
              backgroundColor: '#f8fafc',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <div>
                  <h4 style={{ margin: '0 0 2px 0', fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                    1. Invoice OCR &amp; Data Extraction (Read)
                  </h4>
                  <span style={{ fontSize: '12px', color: '#64748b' }}>
                    Used when processing uploaded scans, receipts, bills, and purchase orders.
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => testConnection('read')}
                  disabled={testingRead}
                  style={{
                    padding: '6px 12px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: '#ffffff',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: testingRead ? 'not-allowed' : 'pointer',
                    color: '#334155',
                  }}
                >
                  {testingRead ? 'Testing...' : 'Test Primary'}
                </button>
              </div>

              {readTestResult && (
                <div style={{
                  marginBottom: '14px',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  backgroundColor: readTestResult.success ? '#f0fdf4' : '#fef2f2',
                  border: `1px solid ${readTestResult.success ? '#bbf7d0' : '#fecaca'}`,
                  color: readTestResult.success ? '#166534' : '#b91c1c',
                }}>
                  {readTestResult.success ? `✓ Connection successful (${readTestResult.latency_ms}ms)` : `✕ Test failed: ${readTestResult.message}`}
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
                    Primary Provider *
                  </label>
                  <select
                    value={readConfig.primary_provider}
                    onChange={(e) => {
                      const prov = e.target.value;
                      setReadConfig({
                        ...readConfig,
                        primary_provider: prov,
                        primary_model: providerModels[prov]?.[0] || '',
                      });
                    }}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#fff' }}
                  >
                    {allowedProviders.map((p) => (
                      <option key={p} value={p}>
                        {p === 'gemini' ? 'Google Gemini' : p === 'openai' ? 'OpenAI GPT' : 'Anthropic Claude'}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
                    Primary Model *
                  </label>
                  <select
                    value={readConfig.primary_model}
                    onChange={(e) => setReadConfig({ ...readConfig, primary_model: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#fff' }}
                  >
                    {(providerModels[readConfig.primary_provider] || []).map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
                    Fallback Provider (Optional)
                  </label>
                  <select
                    value={readConfig.fallback_provider}
                    onChange={(e) => {
                      const prov = e.target.value;
                      setReadConfig({
                        ...readConfig,
                        fallback_provider: prov,
                        fallback_model: prov ? providerModels[prov]?.[0] || '' : '',
                      });
                    }}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#fff' }}
                  >
                    <option value="">None (No Fallback)</option>
                    {allowedProviders.filter((p) => p !== readConfig.primary_provider).map((p) => (
                      <option key={p} value={p}>
                        {p === 'gemini' ? 'Google Gemini' : p === 'openai' ? 'OpenAI GPT' : 'Anthropic Claude'}
                      </option>
                    ))}
                  </select>
                </div>

                {readConfig.fallback_provider && (
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
                      Fallback Model
                    </label>
                    <select
                      value={readConfig.fallback_model}
                      onChange={(e) => setReadConfig({ ...readConfig, fallback_model: e.target.value })}
                      style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#fff' }}
                    >
                      {(providerModels[readConfig.fallback_provider] || []).map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            </div>

            {/* OPERATION 2: INVOICE GENERATION */}
            <div style={{
              border: '1px solid #e2e8f0',
              borderRadius: '12px',
              padding: '18px',
              backgroundColor: '#f8fafc',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <div>
                  <h4 style={{ margin: '0 0 2px 0', fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                    2. Invoice Generation (Generate)
                  </h4>
                  <span style={{ fontSize: '12px', color: '#64748b' }}>
                    Used when synthesizing structured Indian GST invoices and generating document templates.
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => testConnection('generate')}
                  disabled={testingGen}
                  style={{
                    padding: '6px 12px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: '#ffffff',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: testingGen ? 'not-allowed' : 'pointer',
                    color: '#334155',
                  }}
                >
                  {testingGen ? 'Testing...' : 'Test Primary'}
                </button>
              </div>

              {genTestResult && (
                <div style={{
                  marginBottom: '14px',
                  padding: '8px 12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  backgroundColor: genTestResult.success ? '#f0fdf4' : '#fef2f2',
                  border: `1px solid ${genTestResult.success ? '#bbf7d0' : '#fecaca'}`,
                  color: genTestResult.success ? '#166534' : '#b91c1c',
                }}>
                  {genTestResult.success ? `✓ Connection successful (${genTestResult.latency_ms}ms)` : `✕ Test failed: ${genTestResult.message}`}
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
                    Primary Provider *
                  </label>
                  <select
                    value={generateConfig.primary_provider}
                    onChange={(e) => {
                      const prov = e.target.value;
                      setGenerateConfig({
                        ...generateConfig,
                        primary_provider: prov,
                        primary_model: providerModels[prov]?.[0] || '',
                      });
                    }}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#fff' }}
                  >
                    {allowedProviders.map((p) => (
                      <option key={p} value={p}>
                        {p === 'gemini' ? 'Google Gemini' : p === 'openai' ? 'OpenAI GPT' : 'Anthropic Claude'}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
                    Primary Model *
                  </label>
                  <select
                    value={generateConfig.primary_model}
                    onChange={(e) => setGenerateConfig({ ...generateConfig, primary_model: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#fff' }}
                  >
                    {(providerModels[generateConfig.primary_provider] || []).map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
                    Fallback Provider (Optional)
                  </label>
                  <select
                    value={generateConfig.fallback_provider}
                    onChange={(e) => {
                      const prov = e.target.value;
                      setGenerateConfig({
                        ...generateConfig,
                        fallback_provider: prov,
                        fallback_model: prov ? providerModels[prov]?.[0] || '' : '',
                      });
                    }}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#fff' }}
                  >
                    <option value="">None (No Fallback)</option>
                    {allowedProviders.filter((p) => p !== generateConfig.primary_provider).map((p) => (
                      <option key={p} value={p}>
                        {p === 'gemini' ? 'Google Gemini' : p === 'openai' ? 'OpenAI GPT' : 'Anthropic Claude'}
                      </option>
                    ))}
                  </select>
                </div>

                {generateConfig.fallback_provider && (
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
                      Fallback Model
                    </label>
                    <select
                      value={generateConfig.fallback_model}
                      onChange={(e) => setGenerateConfig({ ...generateConfig, fallback_model: e.target.value })}
                      style={{ width: '100%', padding: '8px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#fff' }}
                    >
                      {(providerModels[generateConfig.fallback_provider] || []).map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            </div>

            {/* Footer buttons */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
              <button
                type="button"
                onClick={onClose}
                style={{
                  padding: '9px 16px',
                  borderRadius: '8px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  color: '#475569',
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                style={{
                  padding: '9px 20px',
                  borderRadius: '8px',
                  border: 'none',
                  backgroundColor: '#9333ea',
                  color: '#ffffff',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: saving ? 'not-allowed' : 'pointer',
                }}
              >
                {saving ? 'Saving...' : 'Save AI Configuration'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
