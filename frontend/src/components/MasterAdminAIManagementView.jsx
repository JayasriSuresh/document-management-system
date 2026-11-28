import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api';

const INR_RATE = 85;

export default function MasterAdminAIManagementView({ showToast }) {
  const [activeSubTab, setActiveSubTab] = useState('providers'); // 'providers' | 'models' | 'assignments' | 'requests' | 'usage'
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // ── Data States ─────────────────────────────────────────────────────────────
  const [providers, setProviders] = useState([]);
  const [credentials, setCredentials] = useState([]);
  const [catalogueModels, setCatalogueModels] = useState([]);
  const [companiesSummary, setCompaniesSummary] = useState([]);
  const [aiRequests, setAiRequests] = useState([]);
  const [usageOverview, setUsageOverview] = useState(null);

  // Selected Company for Assignment Sub-tab
  const [selectedCompanyId, setSelectedCompanyId] = useState('');
  const [selectedCompanyDetail, setSelectedCompanyDetail] = useState(null);
  const [assignmentLoading, setAssignmentLoading] = useState(false);
  const [assignmentSaving, setAssignmentSaving] = useState(false);
  const [assignmentForm, setAssignmentForm] = useState({
    is_ai_enabled: true,
    monthly_budget_dollars: 25,
    assignments: {
      ocr: { provider_key: 'gemini', model_id: 'gemini-2.0-flash' },
      extraction: { provider_key: 'gemini', model_id: 'gemini-2.0-flash' },
      generation: { provider_key: 'gemini', model_id: 'gemini-2.0-flash' },
    },
  });

  // ── Modals State ────────────────────────────────────────────────────────────
  // Provider modal
  const [showAddProviderModal, setShowAddProviderModal] = useState(false);
  const [newProviderForm, setNewProviderForm] = useState({
    provider_key: '',
    display_name: '',
    description: '',
    supported_models: '',
  });

  // Credential Modal
  const [showCredModal, setShowCredModal] = useState(null); // provider_key
  const [credInput, setCredInput] = useState('');
  const [credSaving, setCredSaving] = useState(false);

  // Test Connection
  const [testingConn, setTestingConn] = useState({}); // { [provider_key]: { loading, result } }

  // Model Modal (Add/Edit)
  const [showModelModal, setShowModelModal] = useState(false);
  const [editingModel, setEditingModel] = useState(null);
  const [modelForm, setModelForm] = useState({
    provider_key: 'gemini',
    model_id: '',
    display_name: '',
    capabilities: ['ocr', 'extraction'],
    is_active: true,
    context_window: 1000000,
    cost_per_1k_input: 0.0001,
    cost_per_1k_output: 0.0004,
  });

  // Request Decision Modal
  const [decisionModal, setDecisionModal] = useState(null); // { request, type: 'approve' | 'reject' }
  const [decisionNote, setDecisionNote] = useState('');
  const [autoAssignOnApprove, setAutoAssignOnApprove] = useState(true);
  const [decisionSaving, setDecisionSaving] = useState(false);

  // Request status filter
  const [requestFilter, setRequestFilter] = useState('');

  // ── Initial Load ────────────────────────────────────────────────────────────
  const loadAllData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [provRes, credRes, modelRes, compRes, reqRes, usageRes] = await Promise.all([
        api.getPlatformAIProviders().catch(() => []),
        api.getPlatformAICredentials().catch(() => []),
        api.getAICatalogueModels().catch(() => []),
        api.getCompanyAssignmentsSummary().catch(() => []),
        api.getPlatformAIRequests().catch(() => []),
        api.getPlatformAIUsageOverview().catch(() => null),
      ]);
      setProviders(provRes || []);
      setCredentials(credRes || []);
      setCatalogueModels(modelRes || []);
      setCompaniesSummary(compRes || []);
      setAiRequests(reqRes || []);
      setUsageOverview(usageRes);

      if (compRes && compRes.length > 0 && !selectedCompanyId) {
        setSelectedCompanyId(String(compRes[0].company_id));
      }
    } catch (err) {
      setError(err.message || 'Failed to load Master Admin AI configuration.');
    } finally {
      setLoading(false);
    }
  }, [selectedCompanyId]);

  useEffect(() => {
    loadAllData();
  }, [loadAllData]);

  // Load detailed assignments when selected company changes
  useEffect(() => {
    if (!selectedCompanyId) return;
    const fetchCompanyDetail = async () => {
      setAssignmentLoading(true);
      try {
        const detail = await api.getCompanyAssignmentsDetail(selectedCompanyId);
        setSelectedCompanyDetail(detail);
        const map = {
          ocr: { provider_key: 'gemini', model_id: 'gemini-2.0-flash' },
          extraction: { provider_key: 'gemini', model_id: 'gemini-2.0-flash' },
          generation: { provider_key: 'gemini', model_id: 'gemini-2.0-flash' },
        };
        const rawAssignments = Array.isArray(detail?.assignments)
          ? detail.assignments
          : (detail?.assignments && typeof detail.assignments === 'object')
          ? Object.entries(detail.assignments).map(([task, val]) => ({ task_type: task, ...val }))
          : [];

        rawAssignments.forEach((a) => {
          if (a?.task_type) {
            map[a.task_type] = {
              provider_key: a.provider_key || 'gemini',
              model_id: a.model_id || 'gemini-2.0-flash',
            };
          }
        });
        const budgetDollars = detail?.monthly_ai_budget_dollars ?? detail?.budget?.monthly_ai_budget_usd ?? 25;
        setAssignmentForm({
          is_ai_enabled: detail?.is_ai_enabled !== false,
          monthly_budget_dollars: budgetDollars,
          assignments: map,
        });
      } catch (err) {
        console.error('Failed to load company assignments:', err);
      } finally {
        setAssignmentLoading(false);
      }
    };
    fetchCompanyDetail();
  }, [selectedCompanyId]);

  // ── Handlers: Providers ─────────────────────────────────────────────────────
  const handleToggleProvider = async (providerKey, currentStatus) => {
    try {
      await api.updatePlatformAIProvider(providerKey, { is_enabled: !currentStatus });
      setProviders((prev) =>
        prev.map((p) => (p.provider_key === providerKey ? { ...p, is_enabled: !currentStatus } : p))
      );
      if (showToast) showToast(`Provider ${providerKey} ${!currentStatus ? 'activated' : 'deactivated'}.`, 'success');
    } catch (err) {
      setError(err.message || 'Failed to update provider status.');
    }
  };

  const handleSaveCredential = async (providerKey) => {
    if (!credInput.trim()) return;
    setCredSaving(true);
    try {
      await api.savePlatformAICredential(providerKey, credInput.trim());
      setShowCredModal(null);
      setCredInput('');
      const updatedCreds = await api.getPlatformAICredentials();
      setCredentials(updatedCreds);
      if (showToast) showToast(`Credential saved for ${providerKey}.`, 'success');
    } catch (err) {
      setError(err.message || 'Failed to save credential.');
    } finally {
      setCredSaving(false);
    }
  };

  const handleDeleteCredential = async (credentialId, providerKey) => {
    if (!window.confirm(`Delete API credential for ${providerKey}? Platform fallback and requests relying on it will fail.`)) {
      return;
    }
    try {
      await api.deletePlatformAICredential(credentialId);
      setCredentials((prev) => prev.filter((c) => c.id !== credentialId));
      if (showToast) showToast(`Credential for ${providerKey} deleted.`, 'info');
    } catch (err) {
      setError(err.message || 'Failed to delete credential.');
    }
  };

  const handleTestConnection = async (providerKey, defaultModel) => {
    setTestingConn((prev) => ({ ...prev, [providerKey]: { loading: true, result: null } }));
    try {
      const targetModel = defaultModel || (providerKey === 'gemini' ? 'gemini-3.6-flash' : providerKey === 'openai' ? 'gpt-4o' : 'claude-3-5-sonnet-20241022');
      const res = await api.testPlatformAIConnection(providerKey, targetModel);
      const isSuccess = Boolean(res.success || res.connected);
      const latency = res.latency_ms || 0;
      const message = res.message || res.error_message || (isSuccess ? 'Live connection verified' : 'Handshake failed');

      setTestingConn((prev) => ({
        ...prev,
        [providerKey]: {
          loading: false,
          result: { connected: isSuccess, success: isSuccess, error_message: message, message, latency_ms: latency },
        },
      }));
      if (isSuccess && showToast) {
        showToast(`Connection to ${providerKey} verified successfully (${latency}ms).`, 'success');
      }
    } catch (err) {
      setTestingConn((prev) => ({
        ...prev,
        [providerKey]: {
          loading: false,
          result: { connected: false, success: false, error_message: err.message || 'Handshake failed', message: err.message || 'Handshake failed', latency_ms: 0 },
        },
      }));
    }
  };

  const handleCreateProvider = async (e) => {
    e.preventDefault();
    try {
      const modelsArr = newProviderForm.supported_models
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      await api.createPlatformAIProvider({
        provider_key: newProviderForm.provider_key.trim().toLowerCase(),
        display_name: newProviderForm.display_name.trim(),
        description: newProviderForm.description.trim(),
        supported_models: modelsArr,
        is_enabled: true,
      });
      setShowAddProviderModal(false);
      setNewProviderForm({ provider_key: '', display_name: '', description: '', supported_models: '' });
      const provs = await api.getPlatformAIProviders();
      setProviders(provs);
      if (showToast) showToast('New AI provider registered successfully.', 'success');
    } catch (err) {
      setError(err.message || 'Failed to create provider.');
    }
  };

  // ── Handlers: Models ────────────────────────────────────────────────────────
  const handleOpenAddModel = () => {
    setEditingModel(null);
    setModelForm({
      provider_key: providers[0]?.provider_key || 'gemini',
      model_id: '',
      display_name: '',
      capabilities: ['ocr', 'extraction'],
      is_active: true,
      context_window: 1000000,
      cost_per_1k_input: 0.0001,
      cost_per_1k_output: 0.0004,
    });
    setShowModelModal(true);
  };

  const handleOpenEditModel = (m) => {
    setEditingModel(m);
    setModelForm({
      provider_key: m.provider_key,
      model_id: m.model_id,
      display_name: m.display_name,
      capabilities: m.capabilities || [],
      is_active: m.is_active,
      context_window: m.context_window || 1000000,
      cost_per_1k_input: m.cost_per_1k_input || 0.0001,
      cost_per_1k_output: m.cost_per_1k_output || 0.0004,
    });
    setShowModelModal(true);
  };

  const handleSaveModel = async (e) => {
    e.preventDefault();
    try {
      if (editingModel) {
        await api.updateAICatalogueModel(editingModel.id, {
          display_name: modelForm.display_name,
          capabilities: modelForm.capabilities,
          is_active: modelForm.is_active,
          context_window: Number(modelForm.context_window),
          cost_per_1k_input: Number(modelForm.cost_per_1k_input),
          cost_per_1k_output: Number(modelForm.cost_per_1k_output),
        });
        if (showToast) showToast(`Model ${modelForm.display_name} updated.`, 'success');
      } else {
        await api.createAICatalogueModel({
          provider_key: modelForm.provider_key,
          model_id: modelForm.model_id.trim(),
          display_name: modelForm.display_name.trim(),
          capabilities: modelForm.capabilities,
          is_active: modelForm.is_active,
          context_window: Number(modelForm.context_window),
          cost_per_1k_input: Number(modelForm.cost_per_1k_input),
          cost_per_1k_output: Number(modelForm.cost_per_1k_output),
        });
        if (showToast) showToast(`Model ${modelForm.display_name} added to catalogue.`, 'success');
      }
      setShowModelModal(false);
      const updatedModels = await api.getAICatalogueModels();
      setCatalogueModels(updatedModels);
    } catch (err) {
      setError(err.message || 'Failed to save model.');
    }
  };

  const handleToggleModelActive = async (model) => {
    try {
      await api.updateAICatalogueModel(model.id, { is_active: !model.is_active });
      setCatalogueModels((prev) =>
        prev.map((m) => (m.id === model.id ? { ...m, is_active: !model.is_active } : m))
      );
      if (showToast) showToast(`Model ${model.display_name} ${!model.is_active ? 'enabled' : 'disabled'}.`, 'success');
    } catch (err) {
      setError(err.message || 'Failed to update model status.');
    }
  };

  const handleDeleteModel = async (model) => {
    if (!window.confirm(`Delete ${model.display_name} (${model.model_id}) from the catalogue? Active assignments using this model will require reassignment.`)) {
      return;
    }
    try {
      await api.deleteAICatalogueModel(model.id);
      setCatalogueModels((prev) => prev.filter((m) => m.id !== model.id));
      if (showToast) showToast(`Model deleted from catalogue.`, 'info');
    } catch (err) {
      setError(err.message || 'Failed to delete model.');
    }
  };

  // ── Handlers: Company Assignments ───────────────────────────────────────────
  const handleSaveAssignments = async (e) => {
    e.preventDefault();
    if (!selectedCompanyId) return;
    setAssignmentSaving(true);
    setError('');
    try {
      const assignmentsPayload = Object.entries(assignmentForm.assignments).map(([task, val]) => ({
        task_type: task,
        provider_key: val.provider_key,
        model_id: val.model_id,
      }));

      await api.updateCompanyAssignments(selectedCompanyId, {
        is_ai_enabled: assignmentForm.is_ai_enabled,
        monthly_ai_budget_dollars: Number(assignmentForm.monthly_budget_dollars),
        assignments: assignmentsPayload,
      });

      if (showToast) showToast('Company AI configuration saved successfully.', 'success');

      // Refresh summaries
      const [sumRes, detRes] = await Promise.all([
        api.getCompanyAssignmentsSummary(),
        api.getCompanyAssignmentsDetail(selectedCompanyId),
      ]);
      setCompaniesSummary(sumRes);
      setSelectedCompanyDetail(detRes);
    } catch (err) {
      setError(err.message || 'Failed to save assignments.');
      if (showToast) showToast(err.message || 'Failed to save assignments.', 'error');
    } finally {
      setAssignmentSaving(false);
    }
  };

  // ── Handlers: Company Requests ──────────────────────────────────────────────
  const handleOpenDecisionModal = (req, type) => {
    setDecisionModal({ request: req, type });
    setDecisionNote('');
    setAutoAssignOnApprove(true);
  };

  const handleSubmitDecision = async () => {
    if (!decisionModal) return;
    const { request, type } = decisionModal;
    setDecisionSaving(true);
    try {
      if (type === 'approve') {
        await api.approveCompanyAIRequest(request.id, {
          decision_notes: decisionNote.trim() || undefined,
          auto_assign: autoAssignOnApprove,
        });
        if (showToast) showToast(`Request #${request.id} approved.`, 'success');
      } else {
        if (!decisionNote.trim()) {
          alert('Please enter a reason for rejection.');
          setDecisionSaving(false);
          return;
        }
        await api.rejectCompanyAIRequest(request.id, {
          rejection_reason: decisionNote.trim(),
        });
        if (showToast) showToast(`Request #${request.id} rejected.`, 'info');
      }
      setDecisionModal(null);
      const [reqRes, sumRes] = await Promise.all([
        api.getPlatformAIRequests(),
        api.getCompanyAssignmentsSummary(),
      ]);
      setAiRequests(reqRes);
      setCompaniesSummary(sumRes);
    } catch (err) {
      setError(err.message || `Failed to ${type} request.`);
    } finally {
      setDecisionSaving(false);
    }
  };

  // Helper for capability badges
  const renderCapBadges = (caps = []) => (
    <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
      {caps.map((c) => (
        <span
          key={c}
          style={{
            fontSize: '11px',
            fontWeight: 600,
            textTransform: 'uppercase',
            padding: '2px 6px',
            borderRadius: '4px',
            backgroundColor: c === 'ocr' ? '#e0f2fe' : c === 'extraction' ? '#fef3c7' : '#f3e8ff',
            color: c === 'ocr' ? '#0369a1' : c === 'extraction' ? '#92400e' : '#6b21a8',
          }}
        >
          {c}
        </span>
      ))}
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* ── Sub-navigation Header ─────────────────────────────────────────── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          flexWrap: 'wrap',
          backgroundColor: '#ffffff',
          padding: '10px 14px',
          borderRadius: '12px',
          border: '1px solid #e2e8f0',
          boxShadow: '0 2px 6px rgba(0,0,0,0.03)',
        }}
      >
        {[
          {
            id: 'providers',
            label: 'AI Providers & Keys',
            icon: (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            ),
          },
          {
            id: 'models',
            label: 'Model Catalogue',
            icon: (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="4" y="4" width="16" height="16" rx="2" />
                <rect x="9" y="9" width="6" height="6" />
                <line x1="9" y1="1" x2="9" y2="4" />
                <line x1="15" y1="1" x2="15" y2="4" />
                <line x1="9" y1="20" x2="9" y2="23" />
                <line x1="15" y1="20" x2="15" y2="23" />
                <line x1="20" y1="9" x2="23" y2="9" />
                <line x1="20" y1="14" x2="23" y2="14" />
                <line x1="1" y1="9" x2="4" y2="9" />
                <line x1="1" y1="14" x2="4" y2="14" />
              </svg>
            ),
          },
          {
            id: 'assignments',
            label: 'Company Assignments',
            icon: (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 21h18" />
                <path d="M5 21V7l8-4v18" />
                <path d="M19 21V11l-6-4" />
                <path d="M9 9v.01" />
                <path d="M9 12v.01" />
                <path d="M9 15v.01" />
                <path d="M9 18v.01" />
              </svg>
            ),
          },
          {
            id: 'requests',
            label: 'Model Requests',
            badge: aiRequests.filter((r) => r.status === 'pending').length,
            icon: (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
            ),
          },
          {
            id: 'usage',
            label: 'Usage & Budgets',
            icon: (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
            ),
          },
        ].map((tab) => {
          const isActive = activeSubTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveSubTab(tab.id)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                padding: '9px 18px',
                borderRadius: '8px',
                border: isActive ? '1.5px solid #dc2626' : '1px solid #e2e8f0',
                backgroundColor: isActive ? '#fef2f2' : '#ffffff',
                color: isActive ? '#dc2626' : '#475569',
                fontWeight: isActive ? 700 : 600,
                fontSize: '13px',
                cursor: 'pointer',
                boxShadow: isActive ? '0 2px 4px rgba(220, 38, 38, 0.12)' : '0 1px 2px rgba(0, 0, 0, 0.02)',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = '#f8fafc';
                  e.currentTarget.style.color = '#0f172a';
                  e.currentTarget.style.borderColor = '#cbd5e1';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = '#ffffff';
                  e.currentTarget.style.color = '#475569';
                  e.currentTarget.style.borderColor = '#e2e8f0';
                }
              }}
            >
              <span style={{ color: isActive ? '#dc2626' : '#64748b', display: 'flex', alignItems: 'center' }}>
                {tab.icon}
              </span>
              <span>{tab.label}</span>
              {tab.badge > 0 && (
                <span
                  style={{
                    padding: '2px 7px',
                    borderRadius: '10px',
                    fontSize: '11px',
                    fontWeight: 700,
                    backgroundColor: isActive ? '#dc2626' : '#fee2e2',
                    color: isActive ? '#ffffff' : '#dc2626',
                  }}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Notifications */}
      {success && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#f0fdf4',
            border: '1px solid #bbf7d0',
            color: '#166534',
            borderRadius: '10px',
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>{success}</span>
          <button onClick={() => setSuccess('')} style={{ background: 'none', border: 'none', color: '#166534', cursor: 'pointer', fontWeight: 700 }}>&times;</button>
        </div>
      )}
      {error && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#b91c1c',
            borderRadius: '10px',
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>{error}</span>
          <button onClick={() => setError('')} style={{ background: 'none', border: 'none', color: '#b91c1c', cursor: 'pointer', fontWeight: 700 }}>&times;</button>
        </div>
      )}

      {/* ── SUB-TAB 1: PROVIDERS & CREDENTIALS ────────────────────────────── */}
      {activeSubTab === 'providers' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#1e293b' }}>
                Platform Foundation AI Providers
              </h3>
            </div>
            <button
              onClick={() => setShowAddProviderModal(true)}
              style={{
                padding: '7px 14px',
                borderRadius: '6px',
                backgroundColor: '#2563eb',
                color: '#fff',
                fontSize: '13px',
                fontWeight: 600,
                border: 'none',
                cursor: 'pointer',
              }}
            >
              + Add Provider
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '16px' }}>
            {providers.map((p) => {
              const cred = credentials.find((c) => c.provider_key === p.provider_key);
              const testState = testingConn[p.provider_key];
              return (
                <div
                  key={p.provider_key}
                  style={{
                    backgroundColor: '#ffffff',
                    borderRadius: '12px',
                    border: '1px solid #e2e8f0',
                    padding: '20px',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    gap: '16px',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>{p.display_name}</span>
                          <span
                            style={{
                              fontSize: '10px',
                              fontWeight: 700,
                              padding: '2px 8px',
                              borderRadius: '12px',
                              backgroundColor: p.is_enabled ? '#dcfce7' : '#f1f5f9',
                              color: p.is_enabled ? '#166534' : '#64748b',
                            }}
                          >
                            {p.is_enabled ? 'ACTIVE' : 'DISABLED'}
                          </span>
                        </div>
                        <span style={{ fontSize: '12px', color: '#64748b' }}>Key: <code>{p.provider_key}</code></span>
                      </div>

                      <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '12px', fontWeight: 600, color: '#334155' }}>
                        <input
                          type="checkbox"
                          checked={Boolean(p.is_enabled)}
                          onChange={() => handleToggleProvider(p.provider_key, p.is_enabled)}
                        />
                        Enabled
                      </label>
                    </div>

                    <p style={{ margin: '0 0 12px 0', fontSize: '12.5px', color: '#475569' }}>
                      {p.description || 'Enterprise multimodal AI integration for document OCR and extraction.'}
                    </p>

                    {/* Encrypted Key Status */}
                    <div
                      style={{
                        backgroundColor: '#f8fafc',
                        border: '1px solid #e2e8f0',
                        borderRadius: '8px',
                        padding: '10px 12px',
                        fontSize: '12px',
                        marginBottom: '12px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 600, color: '#475569' }}>API Key (Encrypted at rest):</span>
                        {cred ? (
                          <span style={{ color: '#166534', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', backgroundColor: '#dcfce7', padding: '2px 7px', borderRadius: '4px' }}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                            Encrypted &amp; Active
                          </span>
                        ) : (
                          <span style={{ color: '#64748b', fontWeight: 500, fontSize: '11px', backgroundColor: '#f1f5f9', padding: '2px 7px', borderRadius: '4px' }}>
                            Not Configured
                          </span>
                        )}
                      </div>
                      <div style={{ fontFamily: 'monospace', color: cred ? '#0f172a' : '#94a3b8', fontSize: '12px' }}>
                        {cred ? (
                          <span>{cred.masked_key} <span style={{ fontFamily: 'sans-serif', fontSize: '10.5px', color: '#64748b', fontWeight: 'normal' }}>(Stored in DB)</span></span>
                        ) : (
                          'No key stored. Click "Add API Key" below.'
                        )}
                      </div>
                    </div>

                    {/* Connection Test Result (Inline contextual feedback) */}
                    {testState && (
                      <div
                        style={{
                          fontSize: '12px',
                          padding: '7px 10px',
                          borderRadius: '6px',
                          marginBottom: '10px',
                          backgroundColor: testState.loading ? '#eff6ff' : (testState.result?.connected || testState.result?.success) ? '#f0fdf4' : '#fef2f2',
                          color: testState.loading ? '#1d4ed8' : (testState.result?.connected || testState.result?.success) ? '#15803d' : '#b91c1c',
                          border: `1px solid ${testState.loading ? '#bfdbfe' : (testState.result?.connected || testState.result?.success) ? '#bbf7d0' : '#fecaca'}`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '8px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          {testState.loading ? (
                            <span>Checking live handshake...</span>
                          ) : (testState.result?.connected || testState.result?.success) ? (
                            <>
                              <span style={{ fontWeight: 700 }}>✓</span>
                              <span>Live connection verified ({testState.result.latency_ms || 0}ms) — {testState.result.message || 'OK'}</span>
                            </>
                          ) : (
                            <>
                              <span style={{ fontWeight: 700 }}>✕</span>
                              <span>{testState.result?.message || testState.result?.error_message || 'Connection failed'}</span>
                            </>
                          )}
                        </div>
                        {!testState.loading && (
                          <button
                            type="button"
                            onClick={() => setTestingConn(prev => { const n = { ...prev }; delete n[p.provider_key]; return n; })}
                            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '14px', fontWeight: 700, padding: '0 4px', lineHeight: 1 }}
                            title="Dismiss alert"
                          >
                            ×
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button
                      onClick={() => handleTestConnection(p.provider_key, p.supported_models?.[0])}
                      disabled={testState?.loading}
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
                      {testState?.loading ? 'Testing...' : 'Test Connection'}
                    </button>
                    <button
                      onClick={() => {
                        setShowCredModal(p.provider_key);
                        setCredInput('');
                      }}
                      style={{
                        padding: '6px 12px',
                        borderRadius: '6px',
                        border: '1px solid #2563eb',
                        backgroundColor: '#eff6ff',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: '#1d4ed8',
                        cursor: 'pointer',
                      }}
                    >
                      {cred ? 'Rotate Key' : 'Add API Key'}
                    </button>
                    {cred && (
                      <button
                        onClick={() => handleDeleteCredential(cred.id, p.provider_key)}
                        style={{
                          padding: '6px 12px',
                          borderRadius: '6px',
                          border: '1px solid #fecaca',
                          backgroundColor: '#fef2f2',
                          fontSize: '12px',
                          fontWeight: 600,
                          color: '#b91c1c',
                          cursor: 'pointer',
                        }}
                      >
                        Remove Key
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── SUB-TAB 2: MODEL CATALOGUE ─────────────────────────────────────── */}
      {activeSubTab === 'models' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#1e293b' }}>
                Foundation AI Model Catalogue
              </h3>
            </div>
            <button
              onClick={handleOpenAddModel}
              style={{
                padding: '7px 14px',
                borderRadius: '6px',
                backgroundColor: '#2563eb',
                color: '#fff',
                fontSize: '13px',
                fontWeight: 600,
                border: 'none',
                cursor: 'pointer',
              }}
            >
              + Add Model to Catalogue
            </button>
          </div>

          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}
          >
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569', fontWeight: 600 }}>
                  <th style={{ padding: '12px 16px' }}>Provider</th>
                  <th style={{ padding: '12px 16px' }}>Model Identifier</th>
                  <th style={{ padding: '12px 16px' }}>Display Name</th>
                  <th style={{ padding: '12px 16px' }}>Supported Tasks</th>
                  <th style={{ padding: '12px 16px' }}>Pricing (per 1k tokens)</th>
                  <th style={{ padding: '12px 16px' }}>Status</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {catalogueModels.map((m) => (
                  <tr key={m.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 600, color: '#1e293b' }}>
                      <span style={{ textTransform: 'uppercase', fontSize: '11px', letterSpacing: '0.5px' }}>{m.provider_key}</span>
                    </td>
                    <td style={{ padding: '12px 16px', fontFamily: 'monospace', color: '#0f172a' }}>
                      {m.model_id}
                    </td>
                    <td style={{ padding: '12px 16px', fontWeight: 600, color: '#334155' }}>
                      {m.display_name}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {renderCapBadges(m.capabilities)}
                    </td>
                    <td style={{ padding: '12px 16px', color: '#64748b', fontSize: '12px' }}>
                      ${m.cost_per_1k_input || 0} in / ${m.cost_per_1k_output || 0} out
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 700,
                          padding: '2px 8px',
                          borderRadius: '12px',
                          backgroundColor: m.is_active ? '#dcfce7' : '#f1f5f9',
                          color: m.is_active ? '#166534' : '#64748b',
                        }}
                      >
                        {m.is_active ? 'AVAILABLE' : 'DISABLED'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '8px' }}>
                        <button
                          onClick={() => handleToggleModelActive(m)}
                          style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            border: '1px solid #cbd5e1',
                            backgroundColor: '#fff',
                            fontSize: '11px',
                            fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          {m.is_active ? 'Disable' : 'Enable'}
                        </button>
                        <button
                          onClick={() => handleOpenEditModel(m)}
                          style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            border: '1px solid #93c5fd',
                            backgroundColor: '#eff6ff',
                            color: '#1d4ed8',
                            fontSize: '11px',
                            fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeleteModel(m)}
                          style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            border: '1px solid #fecaca',
                            backgroundColor: '#fef2f2',
                            color: '#b91c1c',
                            fontSize: '11px',
                            fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── SUB-TAB 3: COMPANY MODEL ASSIGNMENTS ────────────────────────────── */}
      {activeSubTab === 'assignments' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Company Selector Card */}
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              padding: '20px 24px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '16px',
            }}
          >
            <div>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                Select Enterprise Company
              </h3>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <select
                value={selectedCompanyId}
                onChange={(e) => setSelectedCompanyId(e.target.value)}
                style={{
                  padding: '9px 14px',
                  borderRadius: '8px',
                  border: '1px solid #cbd5e1',
                  fontSize: '13px',
                  fontWeight: 600,
                  color: '#1e293b',
                  minWidth: '240px',
                }}
              >
                {companiesSummary.map((c) => (
                  <option key={c.company_id} value={c.company_id}>
                    {c.company_name} {!c.is_ai_enabled ? '(AI Disabled)' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Assignment Editor */}
          {assignmentLoading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>
              Loading company assignments...
            </div>
          ) : selectedCompanyDetail ? (
            <form onSubmit={handleSaveAssignments} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Controls Card */}
              <div
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: '12px',
                  border: '1px solid #e2e8f0',
                  padding: '20px 24px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                }}
              >
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px', marginBottom: '16px' }}>
                  {/* AI Enabled Toggle */}
                  <div
                    style={{
                      padding: '16px',
                      backgroundColor: assignmentForm.is_ai_enabled ? '#f0fdf4' : '#fef2f2',
                      border: `1px solid ${assignmentForm.is_ai_enabled ? '#bbf7d0' : '#fecaca'}`,
                      borderRadius: '10px',
                    }}
                  >
                    <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={assignmentForm.is_ai_enabled}
                        onChange={(e) => setAssignmentForm({ ...assignmentForm, is_ai_enabled: e.target.checked })}
                        style={{ width: '18px', height: '18px', accentColor: '#16a34a' }}
                      />
                      <div>
                        <div style={{ fontSize: '14px', fontWeight: 700, color: assignmentForm.is_ai_enabled ? '#166534' : '#991b1b' }}>
                          Company AI Access: {assignmentForm.is_ai_enabled ? 'ENABLED' : 'DISABLED'}
                        </div>
                        <div style={{ fontSize: '12px', color: '#64748b' }}>
                          When disabled, all branches of this company receive immediate 403 blocks on AI operations.
                        </div>
                      </div>
                    </label>
                  </div>

                  {/* Monthly Budget Input */}
                  <div style={{ padding: '16px', backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '10px' }}>
                    <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                      Monthly AI Budget ($ USD / ~₹ INR)
                    </label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <input
                        type="number"
                        min="0"
                        max="100000"
                        required
                        value={assignmentForm.monthly_budget_dollars}
                        onChange={(e) => setAssignmentForm({ ...assignmentForm, monthly_budget_dollars: e.target.value })}
                        style={{
                          width: '140px',
                          padding: '8px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          fontWeight: 600,
                        }}
                      />
                      <span style={{ fontSize: '13px', color: '#64748b' }}>
                        ~₹{(Number(assignmentForm.monthly_budget_dollars || 0) * INR_RATE).toLocaleString('en-IN', { minimumFractionDigits: 2 })} / mo
                      </span>
                    </div>
                  </div>
                </div>

                <div style={{ borderTop: '1px solid #f1f5f9', paddingTop: '20px' }}>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                    Exclusive Task-to-Model Mappings
                  </h4>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
                    {[
                      { key: 'ocr', title: 'OCR & Document Text Extraction', desc: 'Converts scanned invoices and PDFs into machine-readable text.' },
                      { key: 'extraction', title: 'Structured Invoice Data Extraction', desc: 'Extracts invoice lines, vendor details, tax amounts, and totals.' },
                      { key: 'generation', title: 'Invoice Generation & Line Drafting', desc: 'Drafts items, tax descriptions, and customer communications.' },
                    ].map((task) => {
                      const currentAssign = assignmentForm.assignments[task.key] || { provider_key: 'gemini', model_id: 'gemini-3.6-flash' };
                      const compatibleModels = catalogueModels.filter((m) => m.capabilities?.includes(task.key) && m.is_active);

                      return (
                        <div
                          key={task.key}
                          style={{
                            padding: '16px',
                            backgroundColor: '#f8fafc',
                            border: '1px solid #e2e8f0',
                            borderRadius: '10px',
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'space-between',
                            gap: '12px',
                          }}
                        >
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                              <span style={{ fontSize: '13.5px', fontWeight: 700, color: '#0f172a' }}>{task.title}</span>
                              <span style={{ fontSize: '10px', fontWeight: 700, padding: '2px 6px', borderRadius: '4px', backgroundColor: '#e2e8f0', color: '#475569' }}>
                                TASK: {task.key.toUpperCase()}
                              </span>
                            </div>
                            <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>{task.desc}</p>
                          </div>

                          <div>
                            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#64748b', marginBottom: '4px' }}>
                              Assigned Approved Model:
                            </label>
                            <select
                              value={`${currentAssign.provider_key}::${currentAssign.model_id}`}
                              onChange={(e) => {
                                const [pKey, mId] = e.target.value.split('::');
                                setAssignmentForm({
                                  ...assignmentForm,
                                  assignments: {
                                    ...assignmentForm.assignments,
                                    [task.key]: { provider_key: pKey, model_id: mId },
                                  },
                                });
                              }}
                              style={{
                                width: '100%',
                                padding: '8px 10px',
                                borderRadius: '6px',
                                border: '1px solid #cbd5e1',
                                fontSize: '12.5px',
                                fontWeight: 600,
                              }}
                            >
                              {compatibleModels.map((m) => (
                                <option key={`${m.provider_key}::${m.model_id}`} value={`${m.provider_key}::${m.model_id}`}>
                                  {m.display_name} ({m.provider_key.toUpperCase()})
                                </option>
                              ))}
                              {compatibleModels.length === 0 && (
                                <option value="gemini::gemini-3.6-flash">Gemini 3.6 Flash (Default)</option>
                              )}
                            </select>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '20px' }}>
                  <button
                    type="submit"
                    disabled={assignmentSaving}
                    style={{
                      padding: '10px 24px',
                      borderRadius: '8px',
                      backgroundColor: '#2563eb',
                      color: '#ffffff',
                      fontSize: '13px',
                      fontWeight: 600,
                      border: 'none',
                      cursor: assignmentSaving ? 'not-allowed' : 'pointer',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    {assignmentSaving ? (
                      <>
                        <div className="spinner" style={{ width: '14px', height: '14px', borderTopColor: '#ffffff' }} />
                        Saving Assignments...
                      </>
                    ) : (
                      'Save Company AI Configuration'
                    )}
                  </button>
                </div>
              </div>
            </form>
          ) : null}

          {/* Quick Summary Table */}
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}
          >
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #f1f5f9' }}>
              <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                All Companies AI Assignment Matrix
              </h4>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12.5px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569', fontWeight: 600 }}>
                  <th style={{ padding: '10px 16px' }}>Company</th>
                  <th style={{ padding: '10px 16px' }}>AI Access</th>
                  <th style={{ padding: '10px 16px' }}>OCR Engine</th>
                  <th style={{ padding: '10px 16px' }}>Extraction Model</th>
                  <th style={{ padding: '10px 16px' }}>Generation Model</th>
                  <th style={{ padding: '10px 16px' }}>Budget ($ / ₹)</th>
                </tr>
              </thead>
              <tbody>
                {companiesSummary.map((c) => {
                  const getModelFor = (task) => {
                    if (c?.assignments && typeof c.assignments === 'object' && !Array.isArray(c.assignments)) {
                      const item = c.assignments[task];
                      if (item) return `${item.provider_key} / ${item.model_id}`;
                    }
                    const arr = Array.isArray(c?.assignments) ? c.assignments : Array.isArray(c?.assignment_list) ? c.assignment_list : [];
                    const found = arr.find((a) => a.task_type === task);
                    return found ? `${found.provider_key} / ${found.model_id}` : 'gemini-2.0-flash';
                  };
                  const bUSD = c?.budget?.monthly_ai_budget_usd ?? c?.monthly_ai_budget_dollars ?? 25;
                  return (
                    <tr
                      key={c.company_id}
                      style={{
                        borderBottom: '1px solid #f1f5f9',
                        backgroundColor: String(c.company_id) === String(selectedCompanyId) ? '#f0fdf4' : 'transparent',
                        cursor: 'pointer',
                      }}
                      onClick={() => setSelectedCompanyId(String(c.company_id))}
                    >
                      <td style={{ padding: '10px 16px', fontWeight: 600, color: '#1e293b' }}>
                        {c.company_name}
                      </td>
                      <td style={{ padding: '10px 16px' }}>
                        <span
                          style={{
                            fontSize: '10px',
                            fontWeight: 700,
                            padding: '2px 6px',
                            borderRadius: '10px',
                            backgroundColor: c.is_ai_enabled ? '#dcfce7' : '#fee2e2',
                            color: c.is_ai_enabled ? '#166534' : '#991b1b',
                          }}
                        >
                          {c.is_ai_enabled ? 'ENABLED' : 'DISABLED'}
                        </span>
                      </td>
                      <td style={{ padding: '10px 16px', fontFamily: 'monospace', color: '#475569' }}>
                        {getModelFor('ocr')}
                      </td>
                      <td style={{ padding: '10px 16px', fontFamily: 'monospace', color: '#475569' }}>
                        {getModelFor('extraction')}
                      </td>
                      <td style={{ padding: '10px 16px', fontFamily: 'monospace', color: '#475569' }}>
                        {getModelFor('generation')}
                      </td>
                      <td style={{ padding: '10px 16px', color: '#334155', fontWeight: 600 }}>
                        ${bUSD} (~₹{(bUSD * INR_RATE).toLocaleString('en-IN')})
                      </td>
                    </tr>
                  );
                })}
                {companiesSummary.length === 0 && (
                  <tr>
                    <td colSpan="6" style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      No companies found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── SUB-TAB 4: COMPANY MODEL REQUESTS ──────────────────────────────── */}
      {activeSubTab === 'requests' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#1e293b' }}>
                Company AI Model Access Requests
              </h3>
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              {['', 'pending', 'approved', 'rejected'].map((st) => (
                <button
                  key={st}
                  onClick={() => setRequestFilter(st)}
                  style={{
                    padding: '5px 12px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: requestFilter === st ? '#1e293b' : '#fff',
                    color: requestFilter === st ? '#fff' : '#475569',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {st ? st.toUpperCase() : 'ALL'}
                </button>
              ))}
            </div>
          </div>

          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}
          >
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569', fontWeight: 600 }}>
                  <th style={{ padding: '12px 16px' }}>ID / Date</th>
                  <th style={{ padding: '12px 16px' }}>Company</th>
                  <th style={{ padding: '12px 16px' }}>Requested Model &amp; Task</th>
                  <th style={{ padding: '12px 16px' }}>Business Justification</th>
                  <th style={{ padding: '12px 16px' }}>Status</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {aiRequests
                  .filter((r) => !requestFilter || r.status === requestFilter)
                  .map((r) => {
                    const stColor =
                      r.status === 'approved'
                        ? { bg: '#dcfce7', text: '#166534' }
                        : r.status === 'rejected'
                        ? { bg: '#fee2e2', text: '#991b1b' }
                        : r.status === 'cancelled'
                        ? { bg: '#f1f5f9', text: '#64748b' }
                        : { bg: '#fef3c7', text: '#92400e' };

                    return (
                      <tr key={r.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '12px 16px' }}>
                          <div style={{ fontWeight: 600, color: '#1e293b' }}>#{r.id}</div>
                          <div style={{ fontSize: '11px', color: '#64748b' }}>
                            {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}
                          </div>
                        </td>
                        <td style={{ padding: '12px 16px', fontWeight: 600, color: '#334155' }}>
                          {r.company_name || `Company #${r.company_id}`}
                        </td>
                        <td style={{ padding: '12px 16px' }}>
                          <div style={{ fontWeight: 600, color: '#0f172a' }}>
                            {r.requested_provider?.toUpperCase()} &mdash; <code>{r.requested_model}</code>
                          </div>
                          <div style={{ fontSize: '11.5px', color: '#64748b', textTransform: 'uppercase' }}>
                            Task: {r.target_task_type}
                          </div>
                        </td>
                        <td style={{ padding: '12px 16px', maxWidth: '280px', color: '#475569' }}>
                          <div>{r.reason}</div>
                          {r.decision_notes && (
                            <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px', fontStyle: 'italic' }}>
                              Decision Note: {r.decision_notes}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: '12px 16px' }}>
                          <span
                            style={{
                              fontSize: '11px',
                              fontWeight: 700,
                              padding: '2px 8px',
                              borderRadius: '12px',
                              backgroundColor: stColor.bg,
                              color: stColor.text,
                            }}
                          >
                            {r.status.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                          {r.status === 'pending' ? (
                            <div style={{ display: 'inline-flex', gap: '8px' }}>
                              <button
                                onClick={() => handleOpenDecisionModal(r, 'approve')}
                                style={{
                                  padding: '5px 10px',
                                  borderRadius: '6px',
                                  border: 'none',
                                  backgroundColor: '#16a34a',
                                  color: '#fff',
                                  fontSize: '11px',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                              >
                                Approve
                              </button>
                              <button
                                onClick={() => handleOpenDecisionModal(r, 'reject')}
                                style={{
                                  padding: '5px 10px',
                                  borderRadius: '6px',
                                  border: 'none',
                                  backgroundColor: '#dc2626',
                                  color: '#fff',
                                  fontSize: '11px',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                              >
                                Reject
                              </button>
                            </div>
                          ) : (
                            <span style={{ fontSize: '12px', color: '#94a3b8' }}>&mdash;</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                {aiRequests.length === 0 && (
                  <tr>
                    <td colSpan="6" style={{ padding: '32px', textAlign: 'center', color: '#64748b' }}>
                      No AI model access requests recorded.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── SUB-TAB 5: USAGE & BUDGETS OVERVIEW ────────────────────────────── */}
      {/* ── SUB-TAB 5: USAGE & BUDGETS OVERVIEW ────────────────────────────── */}
      {activeSubTab === 'usage' && (() => {
        const totalRequests = usageOverview?.total_requests ?? usageOverview?.platform_totals?.total_attempts ?? 0;
        const totalCostUsd = usageOverview?.total_cost_usd ?? usageOverview?.platform_totals?.total_cost_usd ?? 0;
        const failedRequests = usageOverview?.failed_requests ?? usageOverview?.platform_totals?.failed_attempts ?? 0;
        const providerList = usageOverview?.provider_breakdown || usageOverview?.providers || [];
        const companyList = usageOverview?.company_breakdown || usageOverview?.companies || [];

        return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Top Metrics Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
            <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '12px 14px' }}>
              <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total AI Requests</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', marginTop: '2px' }}>
                {totalRequests.toLocaleString()}
              </div>
            </div>
            <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '12px 14px' }}>
              <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Platform AI Cost</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#16a34a', marginTop: '2px' }}>
                ${totalCostUsd.toFixed(4)}
              </div>
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                ~₹{(totalCostUsd * INR_RATE).toFixed(2)} INR
              </div>
            </div>
            <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '12px 14px' }}>
              <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Failed Requests</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: failedRequests > 0 ? '#dc2626' : '#0f172a', marginTop: '2px' }}>
                {failedRequests.toLocaleString()}
              </div>
            </div>
            <div style={{ backgroundColor: '#ffffff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '12px 14px' }}>
              <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Configured Models</div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#2563eb', marginTop: '2px' }}>
                {catalogueModels.length}
              </div>
            </div>
          </div>

          {/* Provider Breakdown */}
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}
          >
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #f1f5f9' }}>
              <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                AI Consumption by Foundation Provider
              </h4>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569', fontWeight: 600 }}>
                  <th style={{ padding: '10px 16px' }}>Provider</th>
                  <th style={{ padding: '10px 16px' }}>Total Requests</th>
                  <th style={{ padding: '10px 16px' }}>Success Rate</th>
                  <th style={{ padding: '10px 16px' }}>Total Cost ($ USD / ₹ INR)</th>
                </tr>
              </thead>
              <tbody>
                {providerList.length === 0 ? (
                  <tr>
                    <td colSpan="4" style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      No AI requests recorded yet across foundation providers.
                    </td>
                  </tr>
                ) : (
                  providerList.map((p) => {
                    const reqCount = p.total_requests ?? p.requests_count ?? 0;
                    const successCount = p.successful_requests ?? reqCount;
                    const rate = reqCount > 0 ? ((successCount / reqCount) * 100).toFixed(1) : '100.0';
                    const costVal = p.total_cost_usd ?? p.cost_usd ?? ((p.cost_cents || 0) / 100);
                    const providerLabel = p.provider === 'gemini' ? 'Google Gemini' : p.provider === 'openai' ? 'OpenAI GPT' : p.provider === 'anthropic' ? 'Anthropic Claude' : (p.provider || '').toUpperCase();

                    return (
                      <tr key={p.provider} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '10px 16px', fontWeight: 700, color: '#1e293b' }}>
                          {providerLabel} <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>({p.provider})</span>
                        </td>
                        <td style={{ padding: '10px 16px', color: '#0f172a' }}>
                          {reqCount}
                        </td>
                        <td style={{ padding: '10px 16px' }}>
                          <span style={{ fontWeight: 600, color: Number(rate) < 95 && reqCount > 0 ? '#dc2626' : '#16a34a' }}>
                            {rate}%
                          </span>
                        </td>
                        <td style={{ padding: '10px 16px', fontWeight: 600, color: '#334155' }}>
                          ${costVal.toFixed(4)} (~₹{(costVal * INR_RATE).toFixed(2)})
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Company Consumption vs Budget */}
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              overflow: 'hidden',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
            }}
          >
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #f1f5f9' }}>
              <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                Company-Wise Consumption Against Monthly Budgets
              </h4>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569', fontWeight: 600 }}>
                  <th style={{ padding: '10px 16px' }}>Company</th>
                  <th style={{ padding: '10px 16px' }}>Monthly Spend ($ USD / ₹ INR)</th>
                  <th style={{ padding: '10px 16px' }}>Configured Budget</th>
                  <th style={{ padding: '10px 16px' }}>Budget Consumption</th>
                  <th style={{ padding: '10px 16px' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {companyList.length === 0 ? (
                  <tr>
                    <td colSpan="5" style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
                      No enterprise companies recorded.
                    </td>
                  </tr>
                ) : (
                  companyList.map((c) => {
                    const budget = c.monthly_budget_dollars ?? c.budget_usd ?? ((c.budget_cents || 0) / 100) ?? 25;
                    const currentSpend = c.current_spend_usd ?? c.spent_usd ?? ((c.spent_cents || 0) / 100) ?? 0;
                    const pct = budget > 0 ? Math.min(100, Math.round((currentSpend / budget) * 100)) : 0;
                    const isOver = currentSpend >= budget;

                    return (
                      <tr key={c.company_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '10px 16px', fontWeight: 600, color: '#1e293b' }}>
                          {c.company_name}
                        </td>
                        <td style={{ padding: '10px 16px', fontWeight: 600, color: '#0f172a' }}>
                          ${currentSpend.toFixed(4)} (~₹{(currentSpend * INR_RATE).toFixed(2)})
                        </td>
                        <td style={{ padding: '10px 16px', color: '#475569' }}>
                          ${budget} (~₹{(budget * INR_RATE).toLocaleString('en-IN')})
                        </td>
                        <td style={{ padding: '10px 16px', minWidth: '160px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ flex: 1, height: '8px', backgroundColor: '#e2e8f0', borderRadius: '4px', overflow: 'hidden' }}>
                              <div
                                style={{
                                  width: `${pct}%`,
                                  height: '100%',
                                  backgroundColor: isOver ? '#dc2626' : pct > 80 ? '#f59e0b' : '#2563eb',
                                }}
                              />
                            </div>
                            <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', width: '32px' }}>{pct}%</span>
                          </div>
                        </td>
                        <td style={{ padding: '10px 16px' }}>
                          <span
                            style={{
                              fontSize: '10px',
                              fontWeight: 700,
                              padding: '2px 6px',
                              borderRadius: '10px',
                              backgroundColor: isOver ? '#fee2e2' : '#dcfce7',
                              color: isOver ? '#991b1b' : '#166534',
                            }}
                          >
                            {isOver ? 'BUDGET EXCEEDED' : 'NORMAL'}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
        );
      })()}

      {/* ── MODAL: ADD / EDIT CREDENTIAL ───────────────────────────────────── */}
      {showCredModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', width: '100%', maxWidth: '440px', padding: '24px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
              Configure API Key: {showCredModal.toUpperCase()}
            </h3>
            <p style={{ margin: '0 0 16px 0', fontSize: '12.5px', color: '#64748b' }}>
              The key will be encrypted at rest (AES-256-GCM) and used for platform model execution and company fallbacks. Plaintext keys are never returned to clients.
            </p>

            <form onSubmit={(e) => { e.preventDefault(); handleSaveCredential(showCredModal); }}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Secret API Key
                </label>
                <input
                  type="password"
                  required
                  placeholder="Enter secret API key..."
                  value={credInput}
                  onChange={(e) => setCredInput(e.target.value)}
                  style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => setShowCredModal(null)}
                  style={{ padding: '8px 14px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#fff', fontSize: '13px', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={credSaving}
                  style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', backgroundColor: '#2563eb', color: '#fff', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  {credSaving ? 'Encrypting & Saving...' : 'Save Encrypted Key'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: ADD PROVIDER ────────────────────────────────────────────── */}
      {showAddProviderModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', width: '100%', maxWidth: '480px', padding: '24px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
              Add New Foundation AI Provider
            </h3>
            <p style={{ margin: '0 0 16px 0', fontSize: '12.5px', color: '#64748b' }}>
              Register a new provider engine for document processing and model catalogue assignment.
            </p>

            <form onSubmit={handleCreateProvider} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Provider Key (e.g. mistral, bedrock)</label>
                <input
                  type="text"
                  required
                  placeholder="provider-key"
                  value={newProviderForm.provider_key}
                  onChange={(e) => setNewProviderForm({ ...newProviderForm, provider_key: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Display Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Mistral AI"
                  value={newProviderForm.display_name}
                  onChange={(e) => setNewProviderForm({ ...newProviderForm, display_name: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Description</label>
                <input
                  type="text"
                  placeholder="Brief description of capabilities..."
                  value={newProviderForm.description}
                  onChange={(e) => setNewProviderForm({ ...newProviderForm, description: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Supported Models (comma-separated)</label>
                <input
                  type="text"
                  placeholder="model-1, model-2"
                  value={newProviderForm.supported_models}
                  onChange={(e) => setNewProviderForm({ ...newProviderForm, supported_models: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '6px' }}>
                <button
                  type="button"
                  onClick={() => setShowAddProviderModal(false)}
                  style={{ padding: '8px 14px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#fff', fontSize: '13px', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', backgroundColor: '#2563eb', color: '#fff', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Register Provider
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: ADD / EDIT CATALOGUE MODEL ──────────────────────────────── */}
      {showModelModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', width: '100%', maxWidth: '500px', padding: '24px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
              {editingModel ? 'Edit Catalogue Model' : 'Add Model to Catalogue'}
            </h3>
            <p style={{ margin: '0 0 16px 0', fontSize: '12.5px', color: '#64748b' }}>
              Configure model identifiers, capabilities, and unit token economics.
            </p>

            <form onSubmit={handleSaveModel} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {!editingModel && (
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Provider</label>
                  <select
                    value={modelForm.provider_key}
                    onChange={(e) => setModelForm({ ...modelForm, provider_key: e.target.value })}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', fontWeight: 600 }}
                  >
                    {providers.map((p) => (
                      <option key={p.provider_key} value={p.provider_key}>{p.display_name}</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Model Identifier</label>
                <input
                  type="text"
                  required
                  disabled={Boolean(editingModel)}
                  placeholder="e.g. gemini-2.5-flash"
                  value={modelForm.model_id}
                  onChange={(e) => setModelForm({ ...modelForm, model_id: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Display Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Gemini 2.5 Flash"
                  value={modelForm.display_name}
                  onChange={(e) => setModelForm({ ...modelForm, display_name: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Supported Tasks / Capabilities</label>
                <div style={{ display: 'flex', gap: '16px' }}>
                  {['ocr', 'extraction', 'generation'].map((cap) => (
                    <label key={cap} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={modelForm.capabilities.includes(cap)}
                        onChange={(e) => {
                          const nextCaps = e.target.checked
                            ? [...modelForm.capabilities, cap]
                            : modelForm.capabilities.filter((c) => c !== cap);
                          setModelForm({ ...modelForm, capabilities: nextCaps });
                        }}
                      />
                      {cap.toUpperCase()}
                    </label>
                  ))}
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Cost / 1k Input ($)</label>
                  <input
                    type="number"
                    step="0.00001"
                    min="0"
                    value={modelForm.cost_per_1k_input}
                    onChange={(e) => setModelForm({ ...modelForm, cost_per_1k_input: e.target.value })}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>Cost / 1k Output ($)</label>
                  <input
                    type="number"
                    step="0.00001"
                    min="0"
                    value={modelForm.cost_per_1k_output}
                    onChange={(e) => setModelForm({ ...modelForm, cost_per_1k_output: e.target.value })}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
                <button
                  type="button"
                  onClick={() => setShowModelModal(false)}
                  style={{ padding: '8px 14px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#fff', fontSize: '13px', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', backgroundColor: '#2563eb', color: '#fff', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  {editingModel ? 'Update Model' : 'Add Model'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: APPROVE / REJECT REQUEST ───────────────────────────────── */}
      {decisionModal && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', width: '100%', maxWidth: '460px', padding: '24px', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', fontWeight: 700, color: decisionModal.type === 'approve' ? '#166534' : '#991b1b' }}>
              {decisionModal.type === 'approve' ? 'Approve AI Model Request' : 'Reject AI Model Request'}
            </h3>
            <p style={{ margin: '0 0 16px 0', fontSize: '12.5px', color: '#64748b' }}>
              Request #{decisionModal.request.id} for <strong>{decisionModal.request.requested_model}</strong> ({decisionModal.request.requested_provider}) by <strong>{decisionModal.request.company_name}</strong>.
            </p>

            <div style={{ marginBottom: '14px' }}>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                {decisionModal.type === 'approve' ? 'Decision Notes (Optional)' : 'Rejection Reason *'}
              </label>
              <textarea
                rows="3"
                required={decisionModal.type === 'reject'}
                placeholder={decisionModal.type === 'approve' ? 'Optional remarks...' : 'State the reason for rejection...'}
                value={decisionNote}
                onChange={(e) => setDecisionNote(e.target.value)}
                style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
              />
            </div>

            {decisionModal.type === 'approve' && (
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', color: '#1e293b', marginBottom: '16px' }}>
                <input
                  type="checkbox"
                  checked={autoAssignOnApprove}
                  onChange={(e) => setAutoAssignOnApprove(e.target.checked)}
                />
                Automatically assign this model to company for task: <strong>{decisionModal.request.target_task_type}</strong>
              </label>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setDecisionModal(null)}
                style={{ padding: '8px 14px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#fff', fontSize: '13px', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitDecision}
                disabled={decisionSaving}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: decisionModal.type === 'approve' ? '#16a34a' : '#dc2626',
                  color: '#fff',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {decisionSaving ? 'Processing...' : decisionModal.type === 'approve' ? 'Confirm Approval' : 'Confirm Rejection'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
