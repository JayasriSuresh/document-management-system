import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import ConfirmModal from '../components/ConfirmModal';
import MfaModal from '../components/MfaModal';
import CompanyDossierView from '../components/CompanyDossierView';
import MasterAdminAIManagementView from '../components/MasterAdminAIManagementView';

export default function AdminCompaniesPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Active view tab: 'dashboard' | 'companies' | 'onboarding' | 'audit' | 'ai' | 'settings' | 'security' | 'company_detail'
  const tabFromUrl = searchParams.get('tab');
  const validTabs = ['dashboard', 'companies', 'onboarding', 'audit', 'ai', 'settings', 'security', 'company_detail'];
  const [activeTab, setActiveTab] = useState(
    validTabs.includes(tabFromUrl) ? (tabFromUrl === 'security' ? 'settings' : tabFromUrl) : 'dashboard'
  );
  const [selectedCompanyIdForDossier, setSelectedCompanyIdForDossier] = useState(() => {
    const cid = searchParams.get('company_id');
    return cid ? parseInt(cid, 10) : null;
  });
  const [statusFilter, setStatusFilter] = useState('all');

  // Sidebar navigation panel state (consistent with Layout.jsx)
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= 1024);

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= 1024) {
        setSidebarOpen(true);
      } else {
        setSidebarOpen(false);
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    const t = searchParams.get('tab');
    const normalized = t === 'security' ? 'settings' : t;
    if (normalized && validTabs.includes(normalized) && normalized !== activeTab) {
      setActiveTab(normalized);
    }
    const cid = searchParams.get('company_id');
    if (cid) {
      const parsed = parseInt(cid, 10);
      if (parsed && parsed !== selectedCompanyIdForDossier) {
        setSelectedCompanyIdForDossier(parsed);
      }
    }
  }, [searchParams]);

  const switchTab = (tab, compId = null) => {
    const normalized = tab === 'security' ? 'settings' : tab;
    setActiveTab(normalized);
    if (normalized === 'company_detail' && compId) {
      setSelectedCompanyIdForDossier(compId);
      setSearchParams({ tab: 'company_detail', company_id: compId });
    } else if (normalized === 'company_detail' && selectedCompanyIdForDossier) {
      setSearchParams({ tab: 'company_detail', company_id: selectedCompanyIdForDossier });
    } else {
      setSearchParams({ tab: normalized });
    }
    if (window.innerWidth < 1024) {
      setSidebarOpen(false);
    }
  };

  const handleOpenCompanyDossier = (companyId) => {
    if (!companyId) return;
    setSelectedCompanyIdForDossier(companyId);
    setActiveTab('company_detail');
    setSearchParams({ tab: 'company_detail', company_id: companyId });
    if (window.innerWidth < 1024) {
      setSidebarOpen(false);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Data states
  const [onboardings, setOnboardings] = useState([]);
  const [allOnboardings, setAllOnboardings] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Add Company Modal state
  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState({ company_name: '', contact_name: '', contact_email: '' });
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState('');
  const [addSuccessData, setAddSuccessData] = useState(null);
  const [copiedLink, setCopiedLink] = useState(false);

  // Review Application Modal state
  const [selectedOnboarding, setSelectedOnboarding] = useState(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [actionError, setActionError] = useState('');
  const [actionSuccess, setActionSuccess] = useState('');

  // Action input states (for Request Changes / Reject)
  const [showChangeInput, setShowChangeInput] = useState(false);
  const [changeComment, setChangeComment] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [submittingAction, setSubmittingAction] = useState(false);

  // Styled Confirmation Dialog State (replaces window.confirm)
  const [confirmDialog, setConfirmDialog] = useState(null);

  // Platform Audit Logs (Module 5)
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditTotalCount, setAuditTotalCount] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [auditTotalPages, setAuditTotalPages] = useState(1);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditActionFilter, setAuditActionFilter] = useState('');
  const [auditCompanyFilter, setAuditCompanyFilter] = useState('');
  const [selectedAuditLog, setSelectedAuditLog] = useState(null);

  // ── Platform Dashboard State ────────────────────────────────────────────────
  const [dashboardData, setDashboardData] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);

  const loadDashboard = async () => {
    setDashboardLoading(true);
    try {
      const data = await api.getPlatformDashboard();
      setDashboardData(data);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      setError(err.message || 'Failed to refresh dashboard metrics.');
    } finally {
      setTimeout(() => {
        setDashboardLoading(false);
      }, 350);
    }
  };

  // ── Edit Company & Quotas Modal State ───────────────────────────────────────
  const [selectedCompanyForEdit, setSelectedCompanyForEdit] = useState(null);
  const [showEditCompanyModal, setShowEditCompanyModal] = useState(false);
  const [editCompanyForm, setEditCompanyForm] = useState({
    name: '',
    gstin: '',
    address: '',
    status: 'active',
    mfa_required_for_all: false,
    max_branches: 5,
    max_users: 20,
    storage_limit_gb: 5,
    monthly_ai_budget_dollars: 25,
  });
  const [editCompanyLoading, setEditCompanyLoading] = useState(false);
  const [editCompanyError, setEditCompanyError] = useState('');

  const handleOpenEditCompany = (c) => {
    setSelectedCompanyForEdit(c);
    setEditCompanyForm({
      name: c.name || '',
      gstin: c.gstin || '',
      address: c.address || '',
      status: c.status || 'active',
      mfa_required_for_all: Boolean(c.mfa_required_for_all),
      max_branches: c.max_branches || 5,
      max_users: c.max_users || 20,
      storage_limit_gb: Math.round((c.storage_limit_bytes || 5368709120) / (1024 * 1024 * 1024)),
      monthly_ai_budget_dollars: Math.round((c.monthly_ai_budget_cents || 2500) / 100),
    });
    setEditCompanyError('');
    setShowEditCompanyModal(true);
  };

  const handleSaveCompanyEdit = async (e) => {
    e.preventDefault();
    if (!selectedCompanyForEdit) return;
    setEditCompanyLoading(true);
    setEditCompanyError('');
    try {
      const payload = {
        name: editCompanyForm.name,
        gstin: editCompanyForm.gstin || null,
        address: editCompanyForm.address || null,
        status: editCompanyForm.status,
        mfa_required_for_all: editCompanyForm.mfa_required_for_all,
        max_branches: parseInt(editCompanyForm.max_branches, 10),
        max_users: parseInt(editCompanyForm.max_users, 10),
        storage_limit_bytes: parseInt(editCompanyForm.storage_limit_gb, 10) * 1024 * 1024 * 1024,
        monthly_ai_budget_cents: parseInt(editCompanyForm.monthly_ai_budget_dollars, 10) * 100,
      };
      await api.updateCompany(selectedCompanyForEdit.id, payload);
      setShowEditCompanyModal(false);
      setSelectedCompanyForEdit(null);
      loadData();
      if (activeTab === 'dashboard') loadDashboard();
    } catch (err) {
      setEditCompanyError(err.message || 'Failed to update company.');
    } finally {
      setEditCompanyLoading(false);
    }
  };

  // ── System Settings & AI Providers State ─────────────────────────────────────
  const [settingsDefaults, setSettingsDefaults] = useState({
    default_max_branches: 5,
    default_max_users: 20,
    default_storage_limit_gb: 5,
    default_monthly_ai_budget_dollars: 25,
  });
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [applyToExisting, setApplyToExisting] = useState(false);
  const [settingsSuccess, setSettingsSuccess] = useState('');
  const [settingsError, setSettingsError] = useState('');
  const [toastMessage, setToastMessage] = useState(null);

  const showToast = (message, type = 'success') => {
    setToastMessage({ message, type });
    setTimeout(() => setToastMessage(null), 4000);
  };

  const loadSystemSettings = async () => {
    setSettingsLoading(true);
    try {
      const res = await api.getSystemSettings();
      if (res.system_defaults) {
        setSettingsDefaults({
          default_max_branches: res.system_defaults.default_max_branches || 5,
          default_max_users: res.system_defaults.default_max_users || 20,
          default_storage_limit_gb: Math.round((res.system_defaults.default_storage_limit_bytes || 5368709120) / (1024 * 1024 * 1024)),
          default_monthly_ai_budget_dollars: Math.round((res.system_defaults.default_monthly_ai_budget_cents || 2500) / 100),
        });
      }
      if (res.mfa_policy) {
        setPlatformPolicy(res.mfa_policy);
      }
    } catch (err) {
      console.error('Failed to load system settings:', err);
    } finally {
      setSettingsLoading(false);
    }
  };

  const handleSaveDefaults = async (e) => {
    e.preventDefault();
    setSettingsSaving(true);
    setSettingsSuccess('');
    setSettingsError('');
    try {
      const payload = {
        system_defaults: {
          default_max_branches: parseInt(settingsDefaults.default_max_branches, 10),
          default_max_users: parseInt(settingsDefaults.default_max_users, 10),
          default_storage_limit_bytes: parseInt(settingsDefaults.default_storage_limit_gb, 10) * 1024 * 1024 * 1024,
          default_monthly_ai_budget_cents: parseInt(settingsDefaults.default_monthly_ai_budget_dollars, 10) * 100,
        },
        apply_to_existing_companies: applyToExisting,
      };
      await api.updateSystemSettings(payload);
      setSettingsSuccess(
        applyToExisting
          ? 'Platform default quotas saved and applied to all existing companies successfully.'
          : 'Platform default quotas saved successfully.'
      );
      setTimeout(() => setSettingsSuccess(''), 5000);
      if (applyToExisting) {
        fetchCompanies();
      }
    } catch (err) {
      setSettingsError(err.message || 'Failed to save default settings.');
    } finally {
      setSettingsSaving(false);
    }
  };

  const loadPlatformAuditLogs = async () => {
    setAuditLoading(true);
    try {
      const params = { page: auditPage, page_size: 20 };
      if (auditActionFilter) params.action = auditActionFilter;
      if (auditCompanyFilter) params.company_id = auditCompanyFilter;
      const res = await api.getPlatformAuditLogs(params);
      setAuditLogs(res.items || []);
      setAuditTotalCount(res.total_count || 0);
      setAuditTotalPages(res.total_pages || 1);
    } catch (err) {
      console.error('Failed to load platform audit logs:', err);
    } finally {
      setAuditLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'dashboard') {
      loadDashboard();
    } else if (activeTab === 'audit') {
      loadPlatformAuditLogs();
    } else if (activeTab === 'settings' || activeTab === 'security') {
      loadPlatformSecurity();
      loadSystemSettings();
    }
  }, [activeTab, auditPage, auditActionFilter, auditCompanyFilter]);

  // Platform Security & 2FA State (Module 6)
  const [platformPolicy, setPlatformPolicy] = useState({
    enforce_all: false,
    enforce_master_admin: false,
    enforce_company_admin: false,
  });
  const [mfaStatus, setMfaStatus] = useState(null);
  const [securityLoading, setSecurityLoading] = useState(false);
  const [securityError, setSecurityError] = useState('');
  const [securitySuccess, setSecuritySuccess] = useState('');
  const [showMfaEnrollModal, setShowMfaEnrollModal] = useState(false);
  const [showDisableForm, setShowDisableForm] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [disableLoading, setDisableLoading] = useState(false);
  const [showRegenModal, setShowRegenModal] = useState(false);
  const [regenPassword, setRegenPassword] = useState('');
  const [regenCode, setRegenCode] = useState('');
  const [newRegenCodes, setNewRegenCodes] = useState([]);
  const [regenLoading, setRegenLoading] = useState(false);

  const loadPlatformSecurity = async () => {
    setSecurityLoading(true);
    setSecurityError('');
    try {
      const [policyRes, statusRes] = await Promise.all([
        api.getPlatformMfaPolicy().catch(() => ({})),
        api.mfaStatus().catch(() => ({ enabled: false })),
      ]);
      setPlatformPolicy(policyRes || {});
      setMfaStatus(statusRes || {});
    } catch (err) {
      setSecurityError(err.message || 'Failed to load security policies.');
    } finally {
      setSecurityLoading(false);
    }
  };

  const handleTogglePlatformPolicy = async (key, value) => {
    setSecurityError('');
    setSecuritySuccess('');
    try {
      const updated = await api.updatePlatformMfaPolicy({ [key]: value });
      setPlatformPolicy(updated);
      setSecuritySuccess(`Platform policy updated: ${key.replace(/_/g, ' ')} is now ${value ? 'ENFORCED' : 'OPTIONAL'}.`);
      setTimeout(() => setSecuritySuccess(''), 5000);
      loadPlatformSecurity();
    } catch (err) {
      setSecurityError(err.message || 'Failed to update platform security policy.');
    }
  };

  const handleDisableMfa = async (e) => {
    e.preventDefault();
    setDisableLoading(true);
    setSecurityError('');
    try {
      await api.mfaDisable(disablePassword, disableCode);
      setSecuritySuccess('Two-factor authentication disabled successfully.');
      setShowDisableForm(false);
      setDisablePassword('');
      setDisableCode('');
      setTimeout(() => setSecuritySuccess(''), 5000);
      loadPlatformSecurity();
    } catch (err) {
      setSecurityError(err.message || 'Failed to disable 2FA.');
    } finally {
      setDisableLoading(false);
    }
  };

  const handleRegenCodes = async (e) => {
    e.preventDefault();
    setRegenLoading(true);
    setSecurityError('');
    try {
      const res = await api.mfaRegenerateRecovery({ password: regenPassword, code: regenCode });
      setNewRegenCodes(res.recovery_codes || []);
      setSecuritySuccess('New emergency recovery codes generated.');
      setRegenPassword('');
      setRegenCode('');
      loadPlatformSecurity();
    } catch (err) {
      setSecurityError(err.message || 'Failed to regenerate recovery codes.');
    } finally {
      setRegenLoading(false);
    }
  };

  const loadData = async () => {
    setLoading(true);
    setError('');
    try {
      const [allOnbData, filteredOnbData, companiesData] = await Promise.all([
        api.listOnboardings('all'),
        statusFilter === 'all' ? null : api.listOnboardings(statusFilter),
        api.listAdminCompanies(),
      ]);
      const fullList = Array.isArray(allOnbData) ? allOnbData : [];
      setAllOnboardings(fullList);
      setOnboardings(statusFilter === 'all' ? fullList : (Array.isArray(filteredOnbData) ? filteredOnbData : []));
      setCompanies(Array.isArray(companiesData) ? companiesData : []);
    } catch (err) {
      setError(err.message || 'Failed to load platform data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  const handleLogout = () => {
    logout();
    navigate('/admin/login');
  };

  // ── Handle Add Company ───────────────────────────────────────────────────────
  const handleAddSubmit = async (e) => {
    e.preventDefault();
    setAddError('');
    setAddLoading(true);
    try {
      const result = await api.initiateOnboarding(addForm);
      setAddSuccessData(result);
      loadData();
    } catch (err) {
      setAddError(err.message || 'Failed to initiate company onboarding.');
    } finally {
      setAddLoading(false);
    }
  };

  const handleCopyLink = (url) => {
    navigator.clipboard.writeText(url);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 3000);
  };

  const closeAddModal = () => {
    setShowAddModal(false);
    setAddForm({ company_name: '', contact_name: '', contact_email: '' });
    setAddSuccessData(null);
    setAddError('');
  };

  // ── Handle Review Detail ─────────────────────────────────────────────────────
  const openReviewModal = async (onboardingId) => {
    setReviewLoading(true);
    setActionError('');
    setActionSuccess('');
    setShowChangeInput(false);
    setShowRejectInput(false);
    setChangeComment('');
    setRejectReason('');
    try {
      const detail = await api.getOnboardingDetail(onboardingId);
      setSelectedOnboarding(detail);
    } catch (err) {
      setError(err.message || 'Failed to fetch application details.');
    } finally {
      setReviewLoading(false);
    }
  };

  const closeReviewModal = () => {
    setSelectedOnboarding(null);
    setActionError('');
    setActionSuccess('');
    setShowChangeInput(false);
    setShowRejectInput(false);
  };

  // ── Master Admin Review Actions ──────────────────────────────────────────────
  const handleApprove = () => {
    if (!selectedOnboarding) return;
    const companyName = selectedOnboarding.legal_company_name || selectedOnboarding.initial_company_name;
    setConfirmDialog({
      title: 'Approve Company Application',
      message: `Approve "${companyName}" and provision company account & administrator?`,
      details: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div><strong>Company Legal Name:</strong> {companyName}</div>
          <div><strong>Contact Person:</strong> {selectedOnboarding.contact_name} ({selectedOnboarding.contact_email})</div>
          <div><strong>Admin Email:</strong> {selectedOnboarding.admin_email}</div>
          <div style={{ marginTop: '6px', color: '#16a34a', fontWeight: 600 }}>
            ✓ This will activate the company tenant and send account credentials to the administrator.
          </div>
        </div>
      ),
      confirmText: 'Accept & Approve',
      variant: 'success',
      onConfirm: async () => {
        setSubmittingAction(true);
        setActionError('');
        try {
          const res = await api.approveOnboarding(selectedOnboarding.id);
          setActionSuccess(res.message);
          // Reload detail and list
          const updated = await api.getOnboardingDetail(selectedOnboarding.id);
          setSelectedOnboarding(updated);
          loadData();
        } catch (err) {
          setActionError(err.message || 'Approval failed.');
        } finally {
          setSubmittingAction(false);
          setConfirmDialog(null);
        }
      },
    });
  };

  const handleRequestChanges = async () => {
    if (!changeComment.trim()) {
      setActionError('Please enter review comments explaining what the applicant needs to change.');
      return;
    }
    setSubmittingAction(true);
    setActionError('');
    try {
      const res = await api.requestOnboardingChanges(selectedOnboarding.id, changeComment.trim());
      setActionSuccess(res.message);
      setShowChangeInput(false);
      setChangeComment('');
      const updated = await api.getOnboardingDetail(selectedOnboarding.id);
      setSelectedOnboarding(updated);
      loadData();
    } catch (err) {
      setActionError(err.message || 'Failed to request changes.');
    } finally {
      setSubmittingAction(false);
    }
  };

  const handleReject = () => {
    if (!selectedOnboarding) return;
    const companyName = selectedOnboarding.legal_company_name || selectedOnboarding.initial_company_name;
    setConfirmDialog({
      title: 'Reject Company Application',
      message: `Are you sure you want to reject the application for "${companyName}"?`,
      details: rejectReason.trim() ? (
        <div><strong>Rejection Reason:</strong> {rejectReason.trim()}</div>
      ) : (
        <div style={{ color: '#dc2626' }}>Note: This application will be marked as rejected and the applicant notified.</div>
      ),
      confirmText: 'Reject Application',
      variant: 'danger',
      onConfirm: async () => {
        setSubmittingAction(true);
        setActionError('');
        try {
          const res = await api.rejectOnboarding(selectedOnboarding.id, rejectReason.trim());
          setActionSuccess(res.message);
          setShowRejectInput(false);
          setRejectReason('');
          const updated = await api.getOnboardingDetail(selectedOnboarding.id);
          setSelectedOnboarding(updated);
          loadData();
        } catch (err) {
          setActionError(err.message || 'Failed to reject application.');
        } finally {
          setSubmittingAction(false);
          setConfirmDialog(null);
        }
      },
    });
  };

  const handleToggleCompany = (company) => {
    const isSuspending = company.status === 'active';
    const action = isSuspending ? 'suspend' : 'activate';
    setConfirmDialog({
      title: `${isSuspending ? 'Suspend' : 'Activate'} Company Account`,
      message: `Are you sure you want to ${action} company "${company.name}"?`,
      details: isSuspending ? (
        <div style={{ color: '#b45309' }}>
          <strong>Warning:</strong> Suspending will immediately prevent all users of this company from accessing their documents and workspace.
        </div>
      ) : (
        <div style={{ color: '#16a34a' }}>
          Activating will immediately restore full workspace access for this company and all its branches.
        </div>
      ),
      confirmText: isSuspending ? 'Suspend Company' : 'Activate Company',
      variant: isSuspending ? 'warning' : 'success',
      onConfirm: async () => {
        try {
          await api.toggleCompanyStatus(company.id);
          loadData();
        } catch (err) {
          setError(err.message || 'Failed to update company status.');
        } finally {
          setConfirmDialog(null);
        }
      },
    });
  };

  // ── Status Badge Formatter ───────────────────────────────────────────────────
  const getStatusBadge = (status) => {
    const map = {
      pending_submission: { label: 'Pending Submission', bg: '#f1f5f9', color: '#475569', border: '#cbd5e1' },
      submitted: { label: 'Under Review', bg: '#eff6ff', color: '#1d4ed8', border: '#93c5fd' },
      changes_requested: { label: 'Changes Requested', bg: '#fffbeb', color: '#b45309', border: '#fcd34d' },
      approved: { label: 'Approved & Live', bg: '#f0fdf4', color: '#15803d', border: '#86efac' },
      rejected: { label: 'Rejected', bg: '#fef2f2', color: '#b91c1c', border: '#fca5a5' },
    };
    const s = map[status] || { label: status, bg: '#f1f5f9', color: '#475569', border: '#cbd5e1' };
    return (
      <span style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '3px 10px',
        borderRadius: '12px',
        fontSize: '12px',
        fontWeight: 600,
        backgroundColor: s.bg,
        color: s.color,
        border: `1px solid ${s.border}`,
        whiteSpace: 'nowrap',
      }}>
        <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: s.color }} />
        {s.label}
      </span>
    );
  };

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  // Stats calculation
  const stats = {
    total: allOnboardings.length,
    underReview: allOnboardings.filter(o => o.status === 'submitted').length,
    changesRequested: allOnboardings.filter(o => o.status === 'changes_requested').length,
    pending: allOnboardings.filter(o => o.status === 'pending_submission').length,
    approved: allOnboardings.filter(o => o.status === 'approved').length,
    rejected: allOnboardings.filter(o => o.status === 'rejected').length,
    liveCompanies: companies.length,
  };

  // Close open modals on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (selectedOnboarding && !submittingAction) {
          closeReviewModal();
        } else if (showAddModal && !addLoading) {
          closeAddModal();
        } else if (selectedAuditLog) {
          setSelectedAuditLog(null);
        } else if (showEditCompanyModal && !editCompanyLoading) {
          setShowEditCompanyModal(false);
          setSelectedCompanyForEdit(null);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedOnboarding, submittingAction, showAddModal, addLoading, selectedAuditLog, showEditCompanyModal, editCompanyLoading]);

  return (
    <div className="app-shell">
      {/* Floating Toast Notification */}
      {toastMessage && (
        <div style={{
          position: 'fixed',
          top: '74px',
          right: '24px',
          zIndex: 9999,
          backgroundColor: toastMessage.type === 'error' ? '#fef2f2' : '#f0fdf4',
          color: toastMessage.type === 'error' ? '#991b1b' : '#166534',
          border: `1px solid ${toastMessage.type === 'error' ? '#f87171' : '#86efac'}`,
          padding: '12px 18px',
          borderRadius: '10px',
          boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
          fontSize: '13.5px',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
        }}>
          {toastMessage.type === 'error' ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
          )}
          <span>{toastMessage.message}</span>
          <button
            onClick={() => setToastMessage(null)}
            style={{
              background: 'none',
              border: 'none',
              marginLeft: '8px',
              color: toastMessage.type === 'error' ? '#991b1b' : '#166534',
              cursor: 'pointer',
              fontSize: '16px',
              fontWeight: 700,
              lineHeight: 1,
            }}
          >
            &times;
          </button>
        </div>
      )}
      
      {/* ── Top Navigation Bar ────────────────────────────────────────────── */}
      <header className="topnav" role="banner">
        <div className="topnav-left">
          <button
            className="topnav-toggle"
            onClick={() => setSidebarOpen(o => !o)}
            aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
            title={sidebarOpen ? 'Close menu' : 'Open menu'}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{
              backgroundColor: '#ef4444',
              color: '#ffffff',
              padding: '3px 8px',
              borderRadius: '6px',
              fontSize: '11px',
              fontWeight: 800,
              letterSpacing: '0.8px',
            }}>
              PLATFORM
            </span>
            <span style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
              DMS Administration
            </span>
          </div>
        </div>

        <div className="topnav-right">
          <div className="topnav-user">
            <div className="topnav-user-info">
              <div className="topnav-user-name">{user?.name || 'Platform Admin'}</div>
              <div className="topnav-user-role" style={{ color: '#ef4444' }}>
                Platform Root Administrator
              </div>
            </div>
            <div className="topnav-avatar" style={{ backgroundColor: '#fee2e2', color: '#b91c1c' }} title={user?.name}>
              {user?.name?.[0]?.toUpperCase() || 'A'}
            </div>
          </div>

          <div className="topnav-divider" />

          <button className="topnav-signout" onClick={handleLogout} title="Sign out">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Sign out
          </button>
        </div>
      </header>

      {/* ── Mobile Overlay ────────────────────────────────────────────────── */}
      {sidebarOpen && typeof window !== 'undefined' && window.innerWidth < 1024 && (
        <div
          className="sidebar-overlay visible"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── Left Side Navigation Panel ────────────────────────────────────── */}
      <aside
        className={`sidebar ${sidebarOpen ? 'sidebar-open' : 'sidebar-collapsed'}`}
        aria-label="Platform navigation"
      >
        <div className="sidebar-brand">
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '8px',
            backgroundColor: '#fee2e2',
            color: '#dc2626',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 800,
            fontSize: '11px',
            letterSpacing: '0.5px',
            flexShrink: 0,
            border: '1px solid #fecaca',
          }}>
            ROOT
          </div>
          <div>
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a', lineHeight: 1.2 }}>
              DMS Platform
            </div>
            <div style={{ fontSize: '11px', color: '#64748b' }}>
              Master Administration
            </div>
          </div>
        </div>

        <nav className="sidebar-nav" role="navigation">
          <span className="nav-section-label">Platform Control</span>

          <button
            type="button"
            onClick={() => switchTab('dashboard')}
            className={`nav-link ${activeTab === 'dashboard' ? 'active' : ''}`}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              textAlign: 'left',
              border: activeTab === 'dashboard' ? '1px solid #fca5a5' : '1px solid transparent',
              backgroundColor: activeTab === 'dashboard' ? '#fee2e2' : 'transparent',
              color: activeTab === 'dashboard' ? '#b91c1c' : '#475569',
              fontWeight: activeTab === 'dashboard' ? 600 : 500,
              cursor: 'pointer',
              marginBottom: '2px',
            }}
          >
            <span className="nav-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '18px', height: '18px' }}>
                <rect x="3" y="3" width="7" height="9" />
                <rect x="14" y="3" width="7" height="5" />
                <rect x="14" y="12" width="7" height="9" />
                <rect x="3" y="16" width="7" height="5" />
              </svg>
            </span>
            Dashboard
          </button>

          <button
            type="button"
            onClick={() => switchTab('companies')}
            className={`nav-link ${(activeTab === 'companies' || activeTab === 'company_detail') ? 'active' : ''}`}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              textAlign: 'left',
              border: (activeTab === 'companies' || activeTab === 'company_detail') ? '1px solid #fca5a5' : '1px solid transparent',
              backgroundColor: (activeTab === 'companies' || activeTab === 'company_detail') ? '#fee2e2' : 'transparent',
              color: (activeTab === 'companies' || activeTab === 'company_detail') ? '#b91c1c' : '#475569',
              fontWeight: (activeTab === 'companies' || activeTab === 'company_detail') ? 600 : 500,
              cursor: 'pointer',
              marginBottom: '2px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span className="nav-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '18px', height: '18px' }}>
                  <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                  <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
                </svg>
              </span>
              Live Companies
            </div>
            {stats.liveCompanies > 0 && (
              <span style={{
                backgroundColor: (activeTab === 'companies' || activeTab === 'company_detail') ? '#dc2626' : '#e2e8f0',
                color: (activeTab === 'companies' || activeTab === 'company_detail') ? '#ffffff' : '#475569',
                padding: '1px 7px',
                borderRadius: '10px',
                fontSize: '11px',
                fontWeight: 700,
              }}>
                {stats.liveCompanies}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => switchTab('onboarding')}
            className={`nav-link ${activeTab === 'onboarding' ? 'active' : ''}`}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              textAlign: 'left',
              border: activeTab === 'onboarding' ? '1px solid #fca5a5' : '1px solid transparent',
              backgroundColor: activeTab === 'onboarding' ? '#fee2e2' : 'transparent',
              color: activeTab === 'onboarding' ? '#b91c1c' : '#475569',
              fontWeight: activeTab === 'onboarding' ? 600 : 500,
              cursor: 'pointer',
              marginBottom: '2px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span className="nav-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '18px', height: '18px' }}>
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              </span>
              Company Onboarding
            </div>
            {stats.total > 0 && (
              <span style={{
                backgroundColor: activeTab === 'onboarding' ? '#dc2626' : '#e2e8f0',
                color: activeTab === 'onboarding' ? '#ffffff' : '#475569',
                padding: '1px 7px',
                borderRadius: '10px',
                fontSize: '11px',
                fontWeight: 700,
              }}>
                {stats.total}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => switchTab('audit')}
            className={`nav-link ${activeTab === 'audit' ? 'active' : ''}`}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              textAlign: 'left',
              border: activeTab === 'audit' ? '1px solid #fca5a5' : '1px solid transparent',
              backgroundColor: activeTab === 'audit' ? '#fee2e2' : 'transparent',
              color: activeTab === 'audit' ? '#b91c1c' : '#475569',
              fontWeight: activeTab === 'audit' ? 600 : 500,
              cursor: 'pointer',
              marginBottom: '2px',
            }}
          >
            <span className="nav-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '18px', height: '18px' }}>
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
            </span>
            Platform Audit Logs
          </button>

          <button
            type="button"
            onClick={() => switchTab('ai')}
            className={`nav-link ${activeTab === 'ai' ? 'active' : ''}`}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              textAlign: 'left',
              border: activeTab === 'ai' ? '1px solid #fca5a5' : '1px solid transparent',
              backgroundColor: activeTab === 'ai' ? '#fee2e2' : 'transparent',
              color: activeTab === 'ai' ? '#b91c1c' : '#475569',
              fontWeight: activeTab === 'ai' ? 600 : 500,
              cursor: 'pointer',
              marginBottom: '2px',
            }}
          >
            <span className="nav-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '18px', height: '18px' }}>
                <path d="M12 2a4 4 0 0 1 4 4v2a4 4 0 0 1-8 0V6a4 4 0 0 1 4-4z" />
                <path d="M18 14v4a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-4" />
                <line x1="12" y1="12" x2="12" y2="18" />
                <circle cx="12" cy="15" r="1" />
              </svg>
            </span>
            AI &amp; Model Governance
          </button>

          <button
            type="button"
            onClick={() => switchTab('settings')}
            className={`nav-link ${activeTab === 'settings' ? 'active' : ''}`}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              textAlign: 'left',
              border: activeTab === 'settings' ? '1px solid #fca5a5' : '1px solid transparent',
              backgroundColor: activeTab === 'settings' ? '#fee2e2' : 'transparent',
              color: activeTab === 'settings' ? '#b91c1c' : '#475569',
              fontWeight: activeTab === 'settings' ? 600 : 500,
              cursor: 'pointer',
              marginBottom: '2px',
            }}
          >
            <span className="nav-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '18px', height: '18px' }}>
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </span>
            System Settings &amp; Security
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-tenant">
            <span className="tenant-status-dot" style={{ backgroundColor: '#22c55e' }} />
            <span style={{ fontSize: '12px', fontWeight: 500, color: '#475569' }}>
              Platform Root &mdash; Active
            </span>
          </div>
        </div>
      </aside>

      {/* ── Main Content Area ─────────────────────────────────────────────── */}
      <main
        className={`main-content ${sidebarOpen && typeof window !== 'undefined' && window.innerWidth >= 1024 ? 'with-sidebar' : 'no-sidebar'}`}
        id="main-content"
      >
        <div style={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box', padding: '1.5rem 2rem' }}>

          {/* Dismissible Alert Message Banners */}
          {error && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 16px',
              backgroundColor: '#fef2f2',
              border: '1px solid #fca5a5',
              borderRadius: '8px',
              color: '#b91c1c',
              fontSize: '13px',
              marginBottom: '16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontWeight: 700 }}>✕</span>
                <span>{error}</span>
              </div>
              <button
                type="button"
                onClick={() => setError('')}
                style={{ background: 'none', border: 'none', color: '#b91c1c', cursor: 'pointer', fontSize: '16px', fontWeight: 700, padding: '0 4px' }}
                title="Dismiss"
              >
                ✕
              </button>
            </div>
          )}

          {settingsSuccess && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 16px',
              backgroundColor: '#f0fdf4',
              border: '1px solid #bbf7d0',
              borderRadius: '8px',
              color: '#15803d',
              fontSize: '13px',
              marginBottom: '16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontWeight: 700 }}>✓</span>
                <span>{settingsSuccess}</span>
              </div>
              <button
                type="button"
                onClick={() => setSettingsSuccess('')}
                style={{ background: 'none', border: 'none', color: '#15803d', cursor: 'pointer', fontSize: '16px', fontWeight: 700, padding: '0 4px' }}
                title="Dismiss"
              >
                ✕
              </button>
            </div>
          )}

          {/* Section Header: Platform Dashboard */}
          {activeTab === 'dashboard' && (
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: 700, margin: 0, color: '#0f172a', letterSpacing: '-0.01em' }}>
                  Platform Dashboard
                </h2>
              </div>
              <button
                onClick={loadDashboard}
                disabled={dashboardLoading}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  backgroundColor: '#ffffff',
                  color: dashboardLoading ? '#94a3b8' : '#475569',
                  padding: '9px 16px',
                  borderRadius: '8px',
                  border: '1px solid #cbd5e1',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: dashboardLoading ? 'not-allowed' : 'pointer',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                  transition: 'all 0.15s ease',
                }}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  style={{ animation: dashboardLoading ? 'spin 0.8s linear infinite' : 'none' }}
                >
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
                </svg>
                {dashboardLoading ? 'Refreshing...' : 'Refresh Metrics'}
              </button>
            </div>
          )}

          {/* Section Header: Company Onboarding */}
          {activeTab === 'onboarding' && (
            <>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                  <h2 style={{ fontSize: '20px', fontWeight: 700, margin: 0, color: '#0f172a', letterSpacing: '-0.01em' }}>
                    Company Onboarding
                  </h2>
                </div>

                <button
                  onClick={() => setShowAddModal(true)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    backgroundColor: '#ef233c',
                    color: '#ffffff',
                    padding: '6px 14px',
                    borderRadius: '6px',
                    border: 'none',
                    fontWeight: 600,
                    fontSize: '12px',
                    cursor: 'pointer',
                    boxShadow: '0 1px 3px rgba(239, 35, 60, 0.2)',
                    transition: 'background-color 0.2s',
                  }}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  Add Company
                </button>
              </div>

              {/* Stats Row */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '16px' }}>
                <div style={{ backgroundColor: '#ffffff', padding: '12px 14px', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                  <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Applications</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', marginTop: '2px' }}>{stats.total}</div>
                </div>
                <div style={{ backgroundColor: '#ffffff', padding: '12px 14px', borderRadius: '8px', border: '1px solid #93c5fd', boxShadow: '0 1px 3px rgba(59,130,246,0.05)' }}>
                  <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#1d4ed8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Under Review</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#1d4ed8', marginTop: '2px' }}>{stats.underReview}</div>
                </div>
                <div style={{ backgroundColor: '#ffffff', padding: '12px 14px', borderRadius: '8px', border: '1px solid #fcd34d', boxShadow: '0 1px 3px rgba(245,158,11,0.05)' }}>
                  <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#b45309', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Changes Requested</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#b45309', marginTop: '2px' }}>{stats.changesRequested}</div>
                </div>
                <div style={{ backgroundColor: '#ffffff', padding: '12px 14px', borderRadius: '8px', border: '1px solid #86efac', boxShadow: '0 1px 3px rgba(34,197,94,0.05)' }}>
                  <div style={{ fontSize: '10.5px', fontWeight: 700, color: '#15803d', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Approved Live Tenants</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#15803d', marginTop: '2px' }}>{stats.liveCompanies}</div>
                </div>
              </div>

              {/* Sub-filter row with live counts */}
              <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
                {[
                  { key: 'all', label: `All (${stats.total})` },
                  { key: 'submitted', label: `Under Review (${stats.underReview})` },
                  { key: 'approved', label: `Approved & Provisioned (${stats.approved})` },
                  { key: 'changes_requested', label: `Changes Requested (${stats.changesRequested})` },
                  { key: 'pending_submission', label: `Pending Submission (${stats.pending})` },
                  { key: 'rejected', label: `Rejected (${stats.rejected})` },
                ].map(f => (
                  <button
                    key={f.key}
                    onClick={() => setStatusFilter(f.key)}
                    style={{
                      padding: '4px 10px',
                      borderRadius: '16px',
                      border: '1px solid',
                      borderColor: statusFilter === f.key ? '#ef233c' : '#e2e8f0',
                      backgroundColor: statusFilter === f.key ? '#ffedef' : '#ffffff',
                      color: statusFilter === f.key ? '#d90429' : '#475569',
                      fontSize: '11.5px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'all 0.15s',
                    }}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              {/* Informational Banner for Approved Applications */}
              {statusFilter === 'submitted' && stats.approved > 0 && (
                <div style={{
                  backgroundColor: '#f0fdf4',
                  border: '1px solid #bbf7d0',
                  borderRadius: '8px',
                  padding: '10px 16px',
                  marginBottom: '18px',
                  fontSize: '13px',
                  color: '#166534',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '8px',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '15px' }}>✓</span>
                    <span>Looking for approved companies? <strong>{stats.approved} application(s)</strong> have been approved and their full form data is saved.</span>
                  </div>
                  <button
                    onClick={() => setStatusFilter('approved')}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#15803d',
                      fontWeight: 700,
                      cursor: 'pointer',
                      textDecoration: 'underline',
                      fontSize: '12px',
                    }}
                  >
                    View Approved Applications →
                  </button>
                </div>
              )}
            </>
          )}

          {/* Section Header: Live Companies */}
          {activeTab === 'companies' && (
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: 700, margin: 0, color: '#0f172a', letterSpacing: '-0.01em' }}>
                  Live Companies &amp; Workspaces
                </h2>
              </div>

              <button
                onClick={() => setShowAddModal(true)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: '#ef233c',
                  color: '#ffffff',
                  padding: '6px 14px',
                  borderRadius: '6px',
                  border: 'none',
                  fontWeight: 600,
                  fontSize: '12px',
                  cursor: 'pointer',
                  boxShadow: '0 1px 3px rgba(239, 35, 60, 0.2)',
                  transition: 'background-color 0.2s',
                }}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                Add Company
              </button>
            </div>
          )}

          {/* Section Header: Platform Audit Logs */}
          {activeTab === 'audit' && (
            <div style={{ marginBottom: '16px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 700, margin: 0, color: '#0f172a', letterSpacing: '-0.01em' }}>
                Platform Audit Logs
              </h2>
            </div>
          )}

          {/* Section Header: AI Infrastructure & Model Governance */}
          {activeTab === 'ai' && (
            <div style={{ marginBottom: '16px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 700, margin: 0, color: '#0f172a', letterSpacing: '-0.01em' }}>
                AI Infrastructure &amp; Model Governance
              </h2>
            </div>
          )}

          {/* Section Header: System Settings & Security */}
          {(activeTab === 'settings' || activeTab === 'security') && (
            <div style={{ marginBottom: '16px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: 700, margin: 0, color: '#0f172a', letterSpacing: '-0.01em' }}>
                System Settings &amp; Security
              </h2>
            </div>
          )}

        {/* ── Content View ──────────────────────────────────────────────────── */}
        {loading ? (
          <div style={{ padding: '60px', textAlign: 'center', color: '#64748b' }}>
            <div className="spinner" style={{ margin: '0 auto 12px auto' }} />
            Loading records...
          </div>
        ) : activeTab === 'dashboard' ? (
          /* ── PLATFORM DASHBOARD TAB ────────────────────────────────────────── */
          <div>
            {dashboardLoading && !dashboardData ? (
              <div style={{ padding: '60px', textAlign: 'center', color: '#64748b' }}>
                <div className="spinner" style={{ margin: '0 auto 12px auto' }} />
                Loading platform metrics...
              </div>
            ) : (
              <>
                {/* 6 Key Metric Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '28px' }}>
                  
                  {/* Card 1: Enterprise Companies */}
                  <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        Enterprise Companies
                      </span>
                      <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#eff6ff', color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
                      </div>
                    </div>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a' }}>
                      {dashboardData?.total_companies ?? companies.length}
                    </div>
                    <div style={{ fontSize: '12px', color: '#16a34a', marginTop: '4px', fontWeight: 500 }}>
                      {dashboardData?.active_companies ?? companies.filter(c => c.status === 'active').length} Active · {dashboardData?.suspended_companies ?? companies.filter(c => c.status === 'suspended').length} Suspended
                    </div>
                  </div>

                  {/* Card 2: Provisioned Branches */}
                  <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        Provisioned Branches
                      </span>
                      <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#f0fdf4', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                      </div>
                    </div>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a' }}>
                      {dashboardData?.total_branches ?? 0}
                    </div>
                    <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                      Across all company workspaces
                    </div>
                  </div>

                  {/* Card 3: Active Users */}
                  <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        Active Users
                      </span>
                      <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#faf5ff', color: '#9333ea', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                      </div>
                    </div>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a' }}>
                      {dashboardData?.total_users ?? 0}
                    </div>
                    <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                      Verified tenant staff &amp; admins
                    </div>
                  </div>

                  {/* Card 4: Platform Storage */}
                  <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        Total Storage Volume
                      </span>
                      <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#fff7ed', color: '#ea580c', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
                      </div>
                    </div>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a' }}>
                      {formatBytes(dashboardData?.total_storage_bytes ?? 0)}
                    </div>
                    <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                      {dashboardData?.total_documents ?? 0} active tenant files
                    </div>
                  </div>

                  {/* Card 5: Monthly AI Compute Spend (Dual Currency: INR + USD) */}
                  <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        Monthly AI Spend
                      </span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <span style={{ fontSize: '10px', fontWeight: 600, color: '#0284c7', backgroundColor: '#e0f2fe', padding: '1px 5px', borderRadius: '3px' }}>
                          ₹ / $
                        </span>
                        <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#fdf2f8', color: '#db2777', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '14px' }}>
                          ₹
                        </div>
                      </div>
                    </div>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>
                      ₹{Number(dashboardData?.total_ai_spent_inr !== undefined ? dashboardData?.total_ai_spent_inr : (((dashboardData?.total_ai_spent_cents ?? 0) / 100) * 85)).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div style={{ fontSize: '12px', color: '#475569', marginTop: '2px', fontWeight: 600 }}>
                      ${((dashboardData?.total_ai_spent_cents ?? 0) / 100).toFixed(2)} USD
                    </div>
                    <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                      OCR &amp; AI extraction ledger across all tenants
                    </div>
                  </div>

                  {/* Card 6: Pending Onboarding */}
                  <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        Pending Onboarding
                      </span>
                      <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: '#fef2f2', color: '#dc2626', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                      </div>
                    </div>
                    <div style={{ fontSize: '28px', fontWeight: 700, color: '#0f172a' }}>
                      {dashboardData?.pending_onboardings ?? stats.total}
                    </div>
                    <div style={{ fontSize: '12px', color: '#b45309', marginTop: '4px', cursor: 'pointer' }} onClick={() => switchTab('onboarding')}>
                      Review registrations &rarr;
                    </div>
                  </div>

                </div>

                {/* Recent Platform Operations */}
                <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
                  <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                      Recent Administrative Operations
                    </h3>
                    <button
                      onClick={() => switchTab('audit')}
                      style={{ fontSize: '12.5px', fontWeight: 600, color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}
                    >
                      View All Platform Logs &rarr;
                    </button>
                  </div>
                  {(!dashboardData?.recent_activity || dashboardData.recent_activity.length === 0) ? (
                    <div style={{ padding: '40px 20px', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
                      No recent platform audit records.
                    </div>
                  ) : (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px', tableLayout: 'fixed' }}>
                        <thead>
                          <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', textTransform: 'uppercase', fontSize: '10.5px', letterSpacing: '0.4px' }}>
                            <th style={{ padding: '8px 10px', width: '20%' }}>Timestamp</th>
                            <th style={{ padding: '8px 10px', width: '25%' }}>Action</th>
                            <th style={{ padding: '8px 10px', width: '20%' }}>Actor</th>
                            <th style={{ padding: '8px 10px', width: '20%' }}>Target</th>
                            <th style={{ padding: '8px 10px', width: '15%' }}>IP</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dashboardData.recent_activity.map((ev, i) => (
                            <tr key={ev.id || i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '7px 10px', color: '#64748b', whiteSpace: 'nowrap', fontSize: '11px', verticalAlign: 'middle' }}>
                                {ev.occurred_at ? new Date(ev.occurred_at).toLocaleString() : '—'}
                              </td>
                              <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                                <span style={{
                                  display: 'inline-block',
                                  padding: '1.5px 6px',
                                  borderRadius: '4px',
                                  fontSize: '10.5px',
                                  fontWeight: 600,
                                  fontFamily: 'monospace',
                                  backgroundColor: ev.action?.includes('fail') || ev.action?.includes('suspend') ? '#fee2e2' : '#f1f5f9',
                                  color: ev.action?.includes('fail') || ev.action?.includes('suspend') ? '#991b1b' : '#334155',
                                }}>
                                  {ev.action}
                                </span>
                              </td>
                              <td style={{ padding: '7px 10px', color: '#1e293b', fontSize: '11px', verticalAlign: 'middle' }}>
                                {ev.actor_type} {ev.actor_id ? `#${ev.actor_id}` : ''}
                              </td>
                              <td style={{ padding: '7px 10px', color: '#475569', fontSize: '11px', verticalAlign: 'middle' }}>
                                {ev.object_type ? `${ev.object_type} #${ev.object_id || ''}` : (ev.company_id ? `Company #${ev.company_id}` : 'Platform')}
                              </td>
                              <td style={{ padding: '7px 10px', color: '#64748b', fontFamily: 'monospace', fontSize: '10.5px', verticalAlign: 'middle' }}>
                                {ev.ip || '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        ) : activeTab === 'onboarding' ? (
          /* ── ONBOARDING APPLICATIONS TABLE ─────────────────────────────────── */
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            {onboardings.length === 0 ? (
              <div style={{ padding: '60px 20px', textAlign: 'center', color: '#64748b' }}>
                <p style={{ fontSize: '16px', fontWeight: 500, margin: '0 0 12px 0' }}>No onboarding applications found.</p>
                <button
                  onClick={() => setShowAddModal(true)}
                  style={{
                    padding: '8px 16px',
                    backgroundColor: '#ef233c',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: '6px',
                    fontWeight: 600,
                    fontSize: '13px',
                    cursor: 'pointer',
                  }}
                >
                  + Add Company
                </button>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px', tableLayout: 'fixed' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', textTransform: 'uppercase', fontSize: '10.5px', letterSpacing: '0.4px' }}>
                      <th style={{ padding: '8px 10px', width: '26%' }}>Company Name</th>
                      <th style={{ padding: '8px 10px', width: '22%' }}>Contact Person</th>
                      <th style={{ padding: '8px 10px', width: '16%' }}>Status</th>
                      <th style={{ padding: '8px 10px', width: '16%' }}>Initiated / Updated</th>
                      <th style={{ padding: '8px 10px', width: '20%', textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {onboardings.map((app) => (
                      <tr key={app.id} style={{ borderBottom: '1px solid #f1f5f9', transition: 'background-color 0.15s' }}>
                        <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                          <div style={{ fontWeight: 600, color: '#0f172a', fontSize: '12px' }}>
                            {app.legal_company_name || app.initial_company_name}
                          </div>
                          {app.legal_company_name && app.legal_company_name !== app.initial_company_name && (
                            <div style={{ fontSize: '11px', color: '#64748b' }}>Init: {app.initial_company_name}</div>
                          )}
                        </td>
                        <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                          <div style={{ fontWeight: 500, color: '#1e293b', fontSize: '12px' }}>{app.contact_name}</div>
                          <div style={{ fontSize: '11px', color: '#64748b' }}>{app.contact_email}</div>
                          {app.auth_contact_mobile && (
                            <div style={{ fontSize: '10.5px', color: '#94a3b8' }}>{app.auth_contact_mobile}</div>
                          )}
                        </td>
                        <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                          {getStatusBadge(app.status)}
                          {app.status === 'changes_requested' && app.review_comments && (
                            <div style={{ fontSize: '11px', color: '#b45309', marginTop: '3px', maxWidth: '240px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              Note: {app.review_comments}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: '7px 10px', color: '#64748b', fontSize: '11px', verticalAlign: 'middle' }}>
                          <div>{new Date(app.created_at).toLocaleDateString()}</div>
                          <div style={{ fontSize: '10.5px', color: '#94a3b8' }}>
                            {app.submitted_at ? `Submitted: ${new Date(app.submitted_at).toLocaleDateString()}` : 'Not submitted yet'}
                          </div>
                        </td>
                        <td style={{ padding: '7px 10px', textAlign: 'right', verticalAlign: 'middle' }}>
                          <div style={{ display: 'inline-flex', gap: '5px', justifyContent: 'flex-end', alignItems: 'center', flexWrap: 'nowrap' }}>
                            {app.status === 'approved' && app.company_id && (
                              <button
                                onClick={() => handleOpenCompanyDossier(app.company_id)}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: '5px',
                                  border: '1px solid #0284c7',
                                  backgroundColor: '#f0f9ff',
                                  color: '#0369a1',
                                  fontWeight: 600,
                                  fontSize: '11px',
                                  cursor: 'pointer',
                                  transition: 'all 0.15s',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '4px',
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                  <polyline points="14 2 14 8 20 8"/>
                                </svg>
                                <span>Dossier</span>
                              </button>
                            )}
                            <button
                              onClick={() => openReviewModal(app.id)}
                              style={{
                                padding: '4px 8px',
                                borderRadius: '5px',
                                border: '1px solid #cbd5e1',
                                backgroundColor: '#ffffff',
                                color: '#0f172a',
                                fontWeight: 600,
                                fontSize: '11px',
                                cursor: 'pointer',
                                transition: 'all 0.15s',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {app.status === 'submitted' ? 'Review Application' : 'Review Details'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : activeTab === 'companies' ? (
          /* ── LIVE COMPANIES TABLE ──────────────────────────────────────────── */
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            {companies.length === 0 ? (
              <div style={{ padding: '60px 20px', textAlign: 'center', color: '#64748b' }}>
                No active companies found.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px', tableLayout: 'fixed' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', textTransform: 'uppercase', fontSize: '10.5px', letterSpacing: '0.4px' }}>
                      <th style={{ padding: '8px 10px', width: '22%' }}>Company</th>
                      <th style={{ padding: '8px 10px', width: '13%' }}>Code / Tax</th>
                      <th style={{ padding: '8px 10px', width: '33%' }}>Quotas &amp; Live Capacity</th>
                      <th style={{ padding: '8px 10px', width: '12%' }}>Status &amp; MFA</th>
                      <th style={{ padding: '8px 10px', width: '20%', textAlign: 'right' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {companies.map((c) => (
                      <tr key={c.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                          <div style={{ fontWeight: 600, color: '#0f172a', fontSize: '12px' }}>{c.name}</div>
                          {c.address && (
                            <div style={{ fontSize: '11px', color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.address}>
                              {c.address}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                          <div style={{ fontFamily: 'monospace', fontWeight: 700, color: '#1e293b', fontSize: '11.5px' }}>{c.code}</div>
                          <div style={{ fontSize: '11px', color: '#64748b' }}>GSTIN: {c.gstin || '—'}</div>
                        </td>
                        <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', fontSize: '11px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                              <span style={{ color: '#64748b' }}>Branches: <strong style={{ color: '#0f172a', fontWeight: 600 }}>{c.branch_count}/{c.max_branches ?? 5}</strong></span>
                              <span style={{ color: '#cbd5e1' }}>•</span>
                              <span style={{ color: '#64748b' }}>Users: <strong style={{ color: '#0f172a', fontWeight: 600 }}>{c.user_count}/{c.max_users ?? 20}</strong></span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                              <span style={{ color: '#64748b' }}>Storage: <strong style={{ color: '#0f172a', fontWeight: 600 }}>{formatBytes(c.storage_used_bytes || 0)} / {formatBytes(c.storage_limit_bytes || 5368709120)}</strong></span>
                              <span style={{ color: '#cbd5e1' }}>•</span>
                              <span style={{ color: '#64748b' }}>
                                AI: <strong style={{ color: '#0f172a', fontWeight: 600 }}>₹{Number(c.ai_spent_inr !== undefined ? c.ai_spent_inr : (((c.ai_spent_cents || 0) / 100) * 85)).toFixed(2)} / ₹{Number(c.monthly_ai_budget_inr || (((c.monthly_ai_budget_cents || 2500) / 100) * 85)).toFixed(2)}</strong>
                                <span style={{ color: '#94a3b8', fontSize: '10px', marginLeft: '3px' }}>(${((c.ai_spent_cents || 0) / 100).toFixed(2)})</span>
                              </span>
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', alignItems: 'flex-start' }}>
                            <span style={{
                              padding: '1.5px 7px',
                              borderRadius: '10px',
                              fontSize: '10.5px',
                              fontWeight: 700,
                              backgroundColor: c.status === 'active' ? '#f0fdf4' : '#fef2f2',
                              color: c.status === 'active' ? '#15803d' : '#b91c1c',
                              border: `1px solid ${c.status === 'active' ? '#bbf7d0' : '#fecaca'}`,
                            }}>
                              {c.status.toUpperCase()}
                            </span>
                            <span style={{
                              fontSize: '10px',
                              fontWeight: 600,
                              color: c.mfa_required_for_all ? '#166534' : '#64748b',
                              backgroundColor: c.mfa_required_for_all ? '#dcfce7' : '#f1f5f9',
                              padding: '1px 5px',
                              borderRadius: '3px',
                            }}>
                              {c.mfa_required_for_all ? 'MFA Mandated' : 'MFA Optional'}
                            </span>
                          </div>
                        </td>
                        <td style={{ padding: '7px 10px', textAlign: 'right', verticalAlign: 'middle' }}>
                          <div style={{ display: 'inline-flex', gap: '5px', alignItems: 'center', justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
                            <button
                              onClick={() => handleOpenCompanyDossier(c.id)}
                              style={{
                                padding: '4px 8px',
                                borderRadius: '5px',
                                border: '1px solid #0284c7',
                                backgroundColor: '#f0f9ff',
                                color: '#0369a1',
                                fontWeight: 600,
                                fontSize: '11px',
                                cursor: 'pointer',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                                whiteSpace: 'nowrap',
                              }}
                              title="View full onboarding dossier & submitted details"
                            >
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                <polyline points="14 2 14 8 20 8"/>
                              </svg>
                              <span>Dossier</span>
                            </button>
                            <button
                              onClick={() => handleOpenEditCompany(c)}
                              style={{
                                padding: '4px 8px',
                                borderRadius: '5px',
                                border: '1px solid #cbd5e1',
                                backgroundColor: '#ffffff',
                                color: '#1e293b',
                                fontWeight: 600,
                                fontSize: '11px',
                                cursor: 'pointer',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              Quotas
                            </button>
                            <button
                              onClick={() => handleToggleCompany(c)}
                              style={{
                                padding: '4px 8px',
                                borderRadius: '5px',
                                border: '1px solid #cbd5e1',
                                backgroundColor: c.status === 'active' ? '#ffffff' : '#f0fdf4',
                                color: c.status === 'active' ? '#b91c1c' : '#15803d',
                                fontWeight: 600,
                                fontSize: '11px',
                                cursor: 'pointer',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {c.status === 'active' ? 'Suspend' : 'Activate'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : activeTab === 'audit' ? (
          /* ── PLATFORM AUDIT LOGS TABLE ─────────────────────────────────────── */
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            {/* Filter Bar */}
            <div style={{ padding: '14px 20px', borderBottom: '1px solid #e2e8f0', background: '#f8fafc', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
              <input
                type="text"
                placeholder="Filter action (e.g. auth, company)..."
                value={auditActionFilter}
                onChange={(e) => { setAuditActionFilter(e.target.value); setAuditPage(1); }}
                style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', width: '220px' }}
              />
              <select
                value={auditCompanyFilter}
                onChange={(e) => { setAuditCompanyFilter(e.target.value); setAuditPage(1); }}
                style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
              >
                <option value="">All Companies / Platform</option>
                {companies.map(c => (
                  <option key={c.id} value={c.id}>{c.name} ({c.code})</option>
                ))}
              </select>
              <button
                onClick={loadPlatformAuditLogs}
                style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', fontSize: '13px', cursor: 'pointer' }}
              >
                Refresh
              </button>
            </div>

            {auditLoading && auditLogs.length === 0 ? (
              <div style={{ padding: '60px 20px', textAlign: 'center', color: '#64748b' }}>Loading platform logs...</div>
            ) : auditLogs.length === 0 ? (
              <div style={{ padding: '60px 20px', textAlign: 'center', color: '#64748b' }}>No audit records found.</div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px', tableLayout: 'fixed' }}>
                  <thead>
                    <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', textTransform: 'uppercase', fontSize: '10.5px', letterSpacing: '0.4px' }}>
                      <th style={{ padding: '8px 10px', width: '18%' }}>Timestamp (UTC)</th>
                      <th style={{ padding: '8px 10px', width: '20%' }}>Action</th>
                      <th style={{ padding: '8px 10px', width: '16%' }}>Actor</th>
                      <th style={{ padding: '8px 10px', width: '16%' }}>Target</th>
                      <th style={{ padding: '8px 10px', width: '12%' }}>Company ID</th>
                      <th style={{ padding: '8px 10px', width: '10%' }}>IP / Request ID</th>
                      <th style={{ padding: '8px 10px', width: '8%', textAlign: 'right' }}>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.map(log => (
                      <tr key={log.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '7px 10px', whiteSpace: 'nowrap', color: '#1e293b', fontSize: '11px', verticalAlign: 'middle' }}>{log.occurred_at}</td>
                        <td style={{ padding: '7px 10px', verticalAlign: 'middle' }}>
                          <span style={{
                            display: 'inline-block',
                            padding: '1.5px 6px',
                            borderRadius: '4px',
                            fontSize: '10.5px',
                            fontWeight: '600',
                            fontFamily: 'monospace',
                            background: log.action?.includes('fail') || log.action?.includes('suspend') || log.action?.includes('reject') ? '#fee2e2' : '#e0f2fe',
                            color: log.action?.includes('fail') || log.action?.includes('suspend') || log.action?.includes('reject') ? '#991b1b' : '#0369a1',
                          }}>
                            {log.action}
                          </span>
                        </td>
                        <td style={{ padding: '7px 10px', fontSize: '11px', verticalAlign: 'middle' }}>{log.actor_type} {log.actor_id ? `#${log.actor_id}` : ''}</td>
                        <td style={{ padding: '7px 10px', fontSize: '11px', verticalAlign: 'middle' }}>{log.object_type ? `${log.object_type} #${log.object_id || ''}` : '—'}</td>
                        <td style={{ padding: '7px 10px', fontSize: '11px', verticalAlign: 'middle' }}>{log.company_id ? `Company #${log.company_id}` : 'Platform'}</td>
                        <td style={{ padding: '7px 10px', fontSize: '10.5px', fontFamily: 'monospace', color: '#64748b', verticalAlign: 'middle' }}>
                          <div>{log.ip || '—'}</div>
                        </td>
                        <td style={{ padding: '7px 10px', textAlign: 'right', verticalAlign: 'middle' }}>
                          <button
                            onClick={() => setSelectedAuditLog(log)}
                            style={{ padding: '3px 8px', fontSize: '11px', borderRadius: '4px', border: '1px solid #cbd5e1', background: '#f8fafc', cursor: 'pointer' }}
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 20px', borderTop: '1px solid #e2e8f0', background: '#f8fafc', fontSize: '13px', color: '#64748b' }}>
              <div>Showing {auditLogs.length} of {auditTotalCount} logs</div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  disabled={auditPage <= 1}
                  onClick={() => setAuditPage(p => Math.max(1, p - 1))}
                  style={{ padding: '4px 10px', fontSize: '12px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer' }}
                >
                  Prev
                </button>
                <button
                  disabled={auditPage >= auditTotalPages}
                  onClick={() => setAuditPage(p => Math.min(auditTotalPages, p + 1))}
                  style={{ padding: '4px 10px', fontSize: '12px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer' }}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        ) : activeTab === 'company_detail' ? (
          /* ── COMPANY DOSSIER VIEW (POST-APPROVAL ONBOARDING DETAILS) ────────── */
          <CompanyDossierView
            companyId={selectedCompanyIdForDossier}
            onBack={() => switchTab('companies')}
            onEditQuotas={(comp) => {
              handleOpenEditCompany(comp);
            }}
            onToggleStatus={(comp) => {
              handleToggleCompany(comp);
            }}
          />
        ) : activeTab === 'ai' ? (
          /* ── AI INFRASTRUCTURE & MODEL GOVERNANCE TAB ─────────────────────── */
          <MasterAdminAIManagementView showToast={showToast} />
        ) : (
          /* ── SYSTEM SETTINGS & SECURITY TAB ────────────────────────────────── */
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

            {/* System Settings Alerts */}
            {settingsSuccess && (
              <div style={{
                padding: '12px 16px',
                backgroundColor: '#f0fdf4',
                border: '1px solid #bbf7d0',
                color: '#166534',
                borderRadius: '10px',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                  <span>{settingsSuccess}</span>
                </div>
                <button
                  onClick={() => setSettingsSuccess('')}
                  style={{ background: 'none', border: 'none', color: '#166534', fontSize: '16px', cursor: 'pointer', fontWeight: 700 }}
                >
                  &times;
                </button>
              </div>
            )}

            {settingsError && (
              <div style={{
                padding: '12px 16px',
                backgroundColor: '#fef2f2',
                border: '1px solid #fecaca',
                color: '#b91c1c',
                borderRadius: '10px',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  <span>{settingsError}</span>
                </div>
                <button
                  onClick={() => setSettingsError('')}
                  style={{ background: 'none', border: 'none', color: '#b91c1c', fontSize: '16px', cursor: 'pointer', fontWeight: 700 }}
                >
                  &times;
                </button>
              </div>
            )}

            {/* CARD A: DEFAULT TENANT QUOTAS */}
            <div style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
              overflow: 'hidden',
            }}>
              <div style={{ padding: '20px 24px', borderBottom: '1px solid #f1f5f9' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '8px',
                    backgroundColor: '#eff6ff',
                    color: '#2563eb',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
                    </svg>
                  </div>
                  <div>
                    <h3 style={{ margin: '0 0 2px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                      Default Quotas for New Companies
                    </h3>
                    <p style={{ margin: 0, fontSize: '12.5px', color: '#64748b' }}>
                      Baseline limits automatically provisioned when an enterprise onboarding application is approved.
                    </p>
                  </div>
                </div>
              </div>

              <form onSubmit={handleSaveDefaults} style={{ padding: '20px 24px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '20px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                      Default Max Branches
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="1000"
                      required
                      value={settingsDefaults.default_max_branches}
                      onChange={(e) => setSettingsDefaults({ ...settingsDefaults, default_max_branches: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                      Default Max Users
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="10000"
                      required
                      value={settingsDefaults.default_max_users}
                      onChange={(e) => setSettingsDefaults({ ...settingsDefaults, default_max_users: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                      Default Storage Limit (GB)
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="10000"
                      required
                      value={settingsDefaults.default_storage_limit_gb}
                      onChange={(e) => setSettingsDefaults({ ...settingsDefaults, default_storage_limit_gb: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                      Default Monthly AI Budget ($ USD / ~₹ INR)
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="100000"
                      required
                      value={settingsDefaults.default_monthly_ai_budget_dollars}
                      onChange={(e) => setSettingsDefaults({ ...settingsDefaults, default_monthly_ai_budget_dollars: e.target.value })}
                      style={{ width: '100%', padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                    />
                    <span style={{ fontSize: '11px', color: '#64748b', marginTop: '4px', display: 'block' }}>
                      ~₹{(Number(settingsDefaults.default_monthly_ai_budget_dollars || 0) * 85).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} at ₹85/USD
                    </span>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', color: '#334155', fontWeight: 500 }}>
                    <input
                      type="checkbox"
                      checked={applyToExisting}
                      onChange={(e) => setApplyToExisting(e.target.checked)}
                      style={{ cursor: 'pointer', width: '16px', height: '16px', accentColor: '#2563eb' }}
                    />
                    <span>Also apply these quotas to all existing companies now</span>
                  </label>

                  <button
                    type="submit"
                    disabled={settingsSaving}
                    style={{
                      padding: '9px 20px',
                      borderRadius: '8px',
                      backgroundColor: '#2563eb',
                      color: '#ffffff',
                      fontSize: '13px',
                      fontWeight: 600,
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    {settingsSaving ? 'Saving Defaults...' : 'Save Default Quotas'}
                  </button>
                </div>
              </form>
            </div>

            {/* AI & Model Governance Hub Callout */}
            <div style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              padding: '16px 20px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '12px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '8px',
                  backgroundColor: '#f5f3ff',
                  color: '#7c3aed',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/>
                    <rect x="3" y="8" width="18" height="12" rx="2"/>
                    <circle cx="8" cy="14" r="1.5"/>
                    <circle cx="16" cy="14" r="1.5"/>
                  </svg>
                </div>
                <div>
                  <div style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                    AI Foundation Infrastructure &amp; Model Governance
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => switchTab('ai')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '7px 14px',
                  borderRadius: '6px',
                  backgroundColor: '#eff6ff',
                  border: '1px solid #93c5fd',
                  color: '#1d4ed8',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <span>Open AI &amp; Model Governance</span>
                <span>&rarr;</span>
              </button>
            </div>

            {/* Alerts */}
            {securitySuccess && (
              <div style={{
                padding: '12px 16px',
                backgroundColor: '#f0fdf4',
                border: '1px solid #bbf7d0',
                color: '#166534',
                borderRadius: '10px',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                  <span>{securitySuccess}</span>
                </div>
                <button
                  onClick={() => setSecuritySuccess('')}
                  style={{ background: 'none', border: 'none', color: '#166534', fontSize: '16px', cursor: 'pointer', fontWeight: 700 }}
                >
                  &times;
                </button>
              </div>
            )}

            {securityError && (
              <div style={{
                padding: '12px 16px',
                backgroundColor: '#fef2f2',
                border: '1px solid #fecaca',
                color: '#b91c1c',
                borderRadius: '10px',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  <span>{securityError}</span>
                </div>
                <button
                  onClick={() => setSecurityError('')}
                  style={{ background: 'none', border: 'none', color: '#b91c1c', fontSize: '16px', cursor: 'pointer', fontWeight: 700 }}
                >
                  &times;
                </button>
              </div>
            )}

            {/* CARD 1: PLATFORM-WIDE ENFORCEMENT POLICIES */}
            <div style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
              overflow: 'hidden',
            }}>
              <div style={{ padding: '20px 24px', borderBottom: '1px solid #f1f5f9' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '8px',
                    backgroundColor: '#fee2e2',
                    color: '#ef233c',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                    </svg>
                  </div>
                  <div>
                    <h3 style={{ margin: '0 0 2px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                      Platform-Wide Security Policies
                    </h3>
                    <p style={{ margin: 0, fontSize: '12.5px', color: '#64748b' }}>
                      Policies configured here strictly override individual company and branch preferences across the platform.
                    </p>
                  </div>
                </div>
              </div>

              <div style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                
                {/* Policy 1: Master Admin */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '16px',
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '10px',
                }}>
                  <div style={{ flex: 1, paddingRight: '20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <span style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                        Enforce MFA for Master Admins
                      </span>
                      <span style={{
                        fontSize: '10px',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '12px',
                        backgroundColor: platformPolicy.enforce_master_admin ? '#dcfce7' : '#f1f5f9',
                        color: platformPolicy.enforce_master_admin ? '#166534' : '#64748b',
                      }}>
                        {platformPolicy.enforce_master_admin ? 'MANDATORY' : 'OPTIONAL'}
                      </span>
                    </div>
                    <div style={{ fontSize: '12.5px', color: '#64748b', lineHeight: 1.4 }}>
                      Mandates time-based one-time passwords (TOTP) for all root platform administrators upon login.
                    </div>
                  </div>

                  <label style={{ position: 'relative', display: 'inline-block', width: '48px', height: '26px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={Boolean(platformPolicy.enforce_master_admin)}
                      onChange={(e) => handleTogglePlatformPolicy('enforce_master_admin', e.target.checked)}
                      style={{ opacity: 0, width: 0, height: 0 }}
                    />
                    <span style={{
                      position: 'absolute',
                      cursor: 'pointer',
                      top: 0, left: 0, right: 0, bottom: 0,
                      backgroundColor: platformPolicy.enforce_master_admin ? '#ef233c' : '#cbd5e1',
                      transition: '0.2s',
                      borderRadius: '34px',
                    }}>
                      <span style={{
                        position: 'absolute',
                        content: '""',
                        height: '20px',
                        width: '20px',
                        left: platformPolicy.enforce_master_admin ? '25px' : '3px',
                        bottom: '3px',
                        backgroundColor: 'white',
                        transition: '0.2s',
                        borderRadius: '50%',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                      }} />
                    </span>
                  </label>
                </div>

                {/* Policy 2: Company Admin */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '16px',
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '10px',
                }}>
                  <div style={{ flex: 1, paddingRight: '20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <span style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                        Enforce MFA for Company Administrators
                      </span>
                      <span style={{
                        fontSize: '10px',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '12px',
                        backgroundColor: platformPolicy.enforce_company_admin ? '#dcfce7' : '#f1f5f9',
                        color: platformPolicy.enforce_company_admin ? '#166534' : '#64748b',
                      }}>
                        {platformPolicy.enforce_company_admin ? 'MANDATORY' : 'OPTIONAL'}
                      </span>
                    </div>
                    <div style={{ fontSize: '12.5px', color: '#64748b', lineHeight: 1.4 }}>
                      Requires company executive accounts (<code>GLOBAL_ADMIN</code>) to verify with an authenticator app when accessing headquarters tools.
                    </div>
                  </div>

                  <label style={{ position: 'relative', display: 'inline-block', width: '48px', height: '26px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={Boolean(platformPolicy.enforce_company_admin)}
                      onChange={(e) => handleTogglePlatformPolicy('enforce_company_admin', e.target.checked)}
                      style={{ opacity: 0, width: 0, height: 0 }}
                    />
                    <span style={{
                      position: 'absolute',
                      cursor: 'pointer',
                      top: 0, left: 0, right: 0, bottom: 0,
                      backgroundColor: platformPolicy.enforce_company_admin ? '#ef233c' : '#cbd5e1',
                      transition: '0.2s',
                      borderRadius: '34px',
                    }}>
                      <span style={{
                        position: 'absolute',
                        content: '""',
                        height: '20px',
                        width: '20px',
                        left: platformPolicy.enforce_company_admin ? '25px' : '3px',
                        bottom: '3px',
                        backgroundColor: 'white',
                        transition: '0.2s',
                        borderRadius: '50%',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                      }} />
                    </span>
                  </label>
                </div>

                {/* Policy 3: Platform Wide All */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '16px',
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '10px',
                }}>
                  <div style={{ flex: 1, paddingRight: '20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <span style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                        Enforce MFA for All Users Platform-Wide
                      </span>
                      <span style={{
                        fontSize: '10px',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '12px',
                        backgroundColor: platformPolicy.enforce_all ? '#dcfce7' : '#f1f5f9',
                        color: platformPolicy.enforce_all ? '#166534' : '#64748b',
                      }}>
                        {platformPolicy.enforce_all ? 'MANDATORY' : 'OPTIONAL'}
                      </span>
                    </div>
                    <div style={{ fontSize: '12.5px', color: '#64748b', lineHeight: 1.4 }}>
                      Mandates two-factor authentication for every tenant, branch administrator, staff member, and uploader across the system.
                    </div>
                  </div>

                  <label style={{ position: 'relative', display: 'inline-block', width: '48px', height: '26px', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={Boolean(platformPolicy.enforce_all)}
                      onChange={(e) => handleTogglePlatformPolicy('enforce_all', e.target.checked)}
                      style={{ opacity: 0, width: 0, height: 0 }}
                    />
                    <span style={{
                      position: 'absolute',
                      cursor: 'pointer',
                      top: 0, left: 0, right: 0, bottom: 0,
                      backgroundColor: platformPolicy.enforce_all ? '#ef233c' : '#cbd5e1',
                      transition: '0.2s',
                      borderRadius: '34px',
                    }}>
                      <span style={{
                        position: 'absolute',
                        content: '""',
                        height: '20px',
                        width: '20px',
                        left: platformPolicy.enforce_all ? '25px' : '3px',
                        bottom: '3px',
                        backgroundColor: 'white',
                        transition: '0.2s',
                        borderRadius: '50%',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                      }} />
                    </span>
                  </label>
                </div>

              </div>
            </div>

            {/* CARD 2: MASTER ADMIN PERSONAL 2FA STATUS */}
            <div style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
              overflow: 'hidden',
            }}>
              <div style={{ padding: '20px 24px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <div style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '8px',
                    backgroundColor: mfaStatus?.enabled ? '#dcfce7' : '#f1f5f9',
                    color: mfaStatus?.enabled ? '#16a34a' : '#64748b',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                    </svg>
                  </div>
                  <div>
                    <h3 style={{ margin: '0 0 2px 0', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                      Master Admin Two-Factor Authentication (TOTP)
                    </h3>
                    <p style={{ margin: 0, fontSize: '12.5px', color: '#64748b' }}>
                      Secure your root administrator login with Microsoft Authenticator or Google Authenticator.
                    </p>
                  </div>
                </div>

                <div>
                  {mfaStatus?.enabled ? (
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '4px 12px',
                      borderRadius: '20px',
                      fontSize: '12px',
                      fontWeight: 700,
                      backgroundColor: '#dcfce7',
                      color: '#166534',
                    }}>
                      <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#16a34a' }} />
                      2FA Active
                    </span>
                  ) : (
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '4px 12px',
                      borderRadius: '20px',
                      fontSize: '12px',
                      fontWeight: 700,
                      backgroundColor: '#f1f5f9',
                      color: '#64748b',
                    }}>
                      Disabled
                    </span>
                  )}
                </div>
              </div>

              <div style={{ padding: '24px' }}>
                {securityLoading && !mfaStatus ? (
                  <div style={{ textAlign: 'center', padding: '30px 0', color: '#64748b', fontSize: '13px' }}>
                    Loading administrator MFA status...
                  </div>
                ) : mfaStatus?.enabled ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    {/* Recovery codes status card */}
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '16px 20px',
                      backgroundColor: '#f8fafc',
                      border: '1px solid #e2e8f0',
                      borderRadius: '10px',
                    }}>
                      <div>
                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          Remaining Emergency Recovery Codes
                        </div>
                        <div style={{ fontSize: '22px', fontWeight: 700, color: '#0f172a', marginTop: '2px' }}>
                          {mfaStatus.remaining_recovery_codes} <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}>of 8 remaining</span>
                        </div>
                      </div>
                      <button
                        onClick={() => {
                          setShowRegenModal(true);
                          setNewRegenCodes([]);
                        }}
                        style={{
                          padding: '8px 16px',
                          fontSize: '12.5px',
                          fontWeight: 600,
                          backgroundColor: '#ffffff',
                          border: '1px solid #cbd5e1',
                          color: '#334155',
                          borderRadius: '8px',
                          cursor: 'pointer',
                        }}
                      >
                        Regenerate Codes
                      </button>
                    </div>

                    {/* Mandatory notice or Disable button */}
                    {mfaStatus.mandatory ? (
                      <div style={{
                        padding: '12px 16px',
                        backgroundColor: '#fffbeb',
                        border: '1px solid #fef3c7',
                        color: '#92400e',
                        borderRadius: '8px',
                        fontSize: '12.5px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                      }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                        </svg>
                        <span>2FA is mandatory for Master Admins under current platform security policy and cannot be disabled.</span>
                      </div>
                    ) : (
                      <div style={{ paddingTop: '4px' }}>
                        {!showDisableForm ? (
                          <button
                            onClick={() => setShowDisableForm(true)}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: '#dc2626',
                              fontSize: '12.5px',
                              fontWeight: 600,
                              cursor: 'pointer',
                              padding: 0,
                              textDecoration: 'underline',
                            }}
                          >
                            Disable Two-Factor Authentication
                          </button>
                        ) : (
                          <form onSubmit={handleDisableMfa} style={{
                            padding: '16px',
                            backgroundColor: '#fef2f2',
                            border: '1px solid #fecaca',
                            borderRadius: '10px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '12px',
                          }}>
                            <div style={{ fontSize: '13px', fontWeight: 700, color: '#991b1b' }}>
                              Confirm Disabling 2FA
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                              <div>
                                <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
                                  Your Password
                                </label>
                                <input
                                  type="password"
                                  value={disablePassword}
                                  onChange={(e) => setDisablePassword(e.target.value)}
                                  placeholder="Enter password"
                                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                                  required
                                />
                              </div>
                              <div>
                                <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>
                                  Current Authenticator Code
                                </label>
                                <input
                                  type="text"
                                  maxLength={6}
                                  value={disableCode}
                                  onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, ''))}
                                  placeholder="6-digit code"
                                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                                  required
                                />
                              </div>
                            </div>
                            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '4px' }}>
                              <button
                                type="button"
                                onClick={() => { setShowDisableForm(false); setDisablePassword(''); setDisableCode(''); }}
                                style={{ padding: '6px 12px', fontSize: '12px', background: 'none', border: 'none', color: '#64748b', cursor: 'pointer' }}
                              >
                                Cancel
                              </button>
                              <button
                                type="submit"
                                disabled={disableLoading}
                                style={{
                                  padding: '6px 14px',
                                  fontSize: '12px',
                                  fontWeight: 600,
                                  backgroundColor: '#dc2626',
                                  color: '#ffffff',
                                  border: 'none',
                                  borderRadius: '6px',
                                  cursor: 'pointer',
                                }}
                              >
                                {disableLoading ? 'Disabling...' : 'Confirm Disable'}
                              </button>
                            </div>
                          </form>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <div>
                    <button
                      onClick={() => setShowMfaEnrollModal(true)}
                      style={{
                        padding: '10px 20px',
                        backgroundColor: '#ef233c',
                        color: '#ffffff',
                        fontSize: '13.5px',
                        fontWeight: 600,
                        borderRadius: '8px',
                        border: 'none',
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '8px',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                      }}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="12" y1="5" x2="12" y2="19"/>
                        <line x1="5" y1="12" x2="19" y2="12"/>
                      </svg>
                      Connect Authenticator App
                    </button>
                  </div>
                )}
              </div>
            </div>

          </div>
        )}
        </div>
      </main>

      {/* ── MODAL 1: ADD COMPANY (INITIATE ONBOARDING) ────────────────────────── */}
      {showAddModal && (
        <div 
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10000,
            padding: '24px',
            boxSizing: 'border-box',
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget && !addLoading) {
              closeAddModal();
            }
          }}
        >
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            maxWidth: '520px',
            width: '100%',
            padding: '28px',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
            border: '1px solid #e2e8f0',
          }}>
            {!addSuccessData ? (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                    Add New Company
                  </h3>
                  <button
                    onClick={closeAddModal}
                    style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#94a3b8' }}
                  >
                    &times;
                  </button>
                </div>

                <p style={{ margin: '0 0 20px 0', fontSize: '13px', color: '#64748b', lineHeight: '1.5' }}>
                  Fill out the preliminary details below. An automated email with a secure registration link will be sent to the contact person to complete the 7-section onboarding form.
                </p>

                {addError && (
                  <div style={{ padding: '10px 14px', backgroundColor: '#fef2f2', border: '1px solid #fca5a5', borderRadius: '6px', color: '#b91c1c', fontSize: '13px', marginBottom: '16px' }}>
                    {addError}
                  </div>
                )}

                <form onSubmit={handleAddSubmit}>
                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                      Company Name <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Acme Corporation Pvt Ltd"
                      value={addForm.company_name}
                      onChange={(e) => setAddForm({ ...addForm, company_name: e.target.value })}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        borderRadius: '6px',
                        border: '1px solid #cbd5e1',
                        fontSize: '14px',
                        outline: 'none',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>

                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                      Contact Person Name <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Rajesh Sharma"
                      value={addForm.contact_name}
                      onChange={(e) => setAddForm({ ...addForm, contact_name: e.target.value })}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        borderRadius: '6px',
                        border: '1px solid #cbd5e1',
                        fontSize: '14px',
                        outline: 'none',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>

                  <div style={{ marginBottom: '24px' }}>
                    <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                      Contact Person Email ID <span style={{ color: '#ef4444' }}>*</span>
                    </label>
                    <input
                      type="email"
                      required
                      placeholder="e.g. rajesh.sharma@acme.com"
                      value={addForm.contact_email}
                      onChange={(e) => setAddForm({ ...addForm, contact_email: e.target.value })}
                      style={{
                        width: '100%',
                        padding: '10px 12px',
                        borderRadius: '6px',
                        border: '1px solid #cbd5e1',
                        fontSize: '14px',
                        outline: 'none',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                    <button
                      type="button"
                      onClick={closeAddModal}
                      style={{
                        padding: '9px 16px',
                        borderRadius: '6px',
                        border: '1px solid #cbd5e1',
                        backgroundColor: '#ffffff',
                        color: '#475569',
                        fontWeight: 600,
                        fontSize: '13px',
                        cursor: 'pointer',
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={addLoading}
                      style={{
                        padding: '9px 20px',
                        borderRadius: '6px',
                        border: 'none',
                        backgroundColor: '#ef233c',
                        color: '#ffffff',
                        fontWeight: 600,
                        fontSize: '13px',
                        cursor: addLoading ? 'not-allowed' : 'pointer',
                        opacity: addLoading ? 0.7 : 1,
                      }}
                    >
                      {addLoading ? 'Dispatching Invitation...' : 'Send Onboarding Form'}
                    </button>
                  </div>
                </form>
              </>
            ) : (
              /* Success State with Onboarding Link */
              <div>
                <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                  <div style={{
                    width: '48px',
                    height: '48px',
                    backgroundColor: '#f0fdf4',
                    color: '#16a34a',
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto 12px auto',
                    fontSize: '24px',
                  }}>
                    ✓
                  </div>
                  <h3 style={{ margin: '0 0 6px 0', fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                    Onboarding Form Dispatched!
                  </h3>
                  <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
                    An email has been sent to <strong>{addSuccessData.contact_email}</strong> with instructions to fill out the onboarding application.
                  </p>
                </div>

                <div style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '16px', marginBottom: '20px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>
                    Direct Onboarding Link (Test / Preview):
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <input
                      type="text"
                      readOnly
                      value={addSuccessData.onboarding_url}
                      style={{
                        flex: 1,
                        padding: '8px 10px',
                        borderRadius: '6px',
                        border: '1px solid #cbd5e1',
                        fontSize: '12px',
                        fontFamily: 'monospace',
                        backgroundColor: '#ffffff',
                      }}
                    />
                    <button
                      onClick={() => handleCopyLink(addSuccessData.onboarding_url)}
                      style={{
                        padding: '8px 14px',
                        borderRadius: '6px',
                        border: '1px solid #cbd5e1',
                        backgroundColor: '#ffffff',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {copiedLink ? 'Copied!' : 'Copy Link'}
                    </button>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                  <a
                    href={addSuccessData.onboarding_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      padding: '9px 16px',
                      borderRadius: '6px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: '#ffffff',
                      color: '#0f172a',
                      fontWeight: 600,
                      fontSize: '13px',
                      textDecoration: 'none',
                      display: 'inline-flex',
                      alignItems: 'center',
                    }}
                  >
                    Open Form
                  </a>
                  <button
                    onClick={closeAddModal}
                    style={{
                      padding: '9px 20px',
                      borderRadius: '6px',
                      border: 'none',
                      backgroundColor: '#ef233c',
                      color: '#ffffff',
                      fontWeight: 600,
                      fontSize: '13px',
                      cursor: 'pointer',
                    }}
                  >
                    Done
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── MODAL 2: APPLICATION REVIEW DRAWER / MODAL ───────────────────────── */}
      {selectedOnboarding && (
        <div 
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10000,
            padding: '24px',
            boxSizing: 'border-box',
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget && !submittingAction) {
              closeReviewModal();
            }
          }}
        >
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            maxWidth: '920px',
            width: '100%',
            maxHeight: '90vh',
            margin: 'auto',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
            border: '1px solid #e2e8f0',
            overflow: 'hidden',
          }}>
            {/* Modal Header */}
            <div style={{
              padding: '20px 24px',
              borderBottom: '1px solid #e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: '#ffffff',
            }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                    {selectedOnboarding.legal_company_name || selectedOnboarding.initial_company_name}
                  </h3>
                  {getStatusBadge(selectedOnboarding.status)}
                </div>
                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                  Application #{selectedOnboarding.id} &middot; Contact: {selectedOnboarding.contact_name} ({selectedOnboarding.contact_email})
                </div>
              </div>
              <button
                onClick={closeReviewModal}
                style={{ background: 'none', border: 'none', fontSize: '22px', cursor: 'pointer', color: '#94a3b8' }}
              >
                &times;
              </button>
            </div>

            {/* Action Feedback alerts */}
            {actionSuccess && (
              <div style={{ margin: '16px 24px 0 24px', padding: '12px 16px', backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '6px', color: '#166534', fontSize: '13px', fontWeight: 500 }}>
                ✓ {actionSuccess}
              </div>
            )}
            {actionError && (
              <div style={{ margin: '16px 24px 0 24px', padding: '12px 16px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#b91c1c', fontSize: '13px', fontWeight: 500 }}>
                ✕ {actionError}
              </div>
            )}

            {/* Review Action Toolbar (Prominent for submitted applications) */}
            <div style={{
              padding: '16px 24px',
              backgroundColor: '#f8fafc',
              borderBottom: '1px solid #e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '12px',
            }}>
              <div style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>
                Master Admin Review Decision:
              </div>

              <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                {selectedOnboarding.status === 'submitted' ? (
                  <>
                    <button
                      onClick={handleApprove}
                      disabled={submittingAction}
                      style={{
                        padding: '8px 16px',
                        backgroundColor: '#16a34a',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '6px',
                        fontWeight: 600,
                        fontSize: '13px',
                        cursor: submittingAction ? 'not-allowed' : 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      ✓ Accept &amp; Approve Company
                    </button>

                    <button
                      onClick={() => {
                        setShowChangeInput(!showChangeInput);
                        setShowRejectInput(false);
                      }}
                      disabled={submittingAction}
                      style={{
                        padding: '8px 16px',
                        backgroundColor: '#d97706',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '6px',
                        fontWeight: 600,
                        fontSize: '13px',
                        cursor: submittingAction ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Request Changes
                    </button>

                    <button
                      onClick={() => {
                        setShowRejectInput(!showRejectInput);
                        setShowChangeInput(false);
                      }}
                      disabled={submittingAction}
                      style={{
                        padding: '8px 16px',
                        backgroundColor: '#dc2626',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '6px',
                        fontWeight: 600,
                        fontSize: '13px',
                        cursor: submittingAction ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Reject
                    </button>
                  </>
                ) : selectedOnboarding.status === 'changes_requested' ? (
                  <div style={{ fontSize: '13px', color: '#b45309', fontWeight: 600 }}>
                    Awaiting Applicant Updates &amp; Resubmission
                  </div>
                ) : selectedOnboarding.status === 'approved' ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{ fontSize: '13px', color: '#15803d', fontWeight: 600 }}>
                      Company Approved &amp; Workspace Active
                    </div>
                    {selectedOnboarding.company_id && (
                      <button
                        onClick={() => {
                          const compId = selectedOnboarding.company_id;
                          setSelectedOnboarding(null);
                          handleOpenCompanyDossier(compId);
                        }}
                        style={{
                          padding: '6px 14px',
                          borderRadius: '6px',
                          backgroundColor: '#0284c7',
                          color: '#ffffff',
                          border: 'none',
                          fontWeight: 600,
                          fontSize: '12px',
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                      >
                        <span>Open Company Dossier</span>
                        <span>&rarr;</span>
                      </button>
                    )}
                  </div>
                ) : (
                  <div style={{ fontSize: '13px', color: '#64748b' }}>
                    Application status: {selectedOnboarding.status}
                  </div>
                )}
              </div>
            </div>

            {/* Expandable Request Changes Textarea */}
            {showChangeInput && (
              <div style={{ padding: '16px 24px', backgroundColor: '#fffbeb', borderBottom: '1px solid #fde68a' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#92400e', marginBottom: '6px' }}>
                  Specify the changes or missing details required from the applicant:
                </div>
                <textarea
                  rows={3}
                  value={changeComment}
                  onChange={(e) => setChangeComment(e.target.value)}
                  placeholder="e.g. Please re-upload a clear copy of PAN Card and ensure GSTIN matches your legal company name."
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    border: '1px solid #fcd34d',
                    fontSize: '13px',
                    outline: 'none',
                    boxSizing: 'border-box',
                    marginBottom: '10px',
                  }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                  <button
                    onClick={() => setShowChangeInput(false)}
                    style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid #d97706', background: 'none', color: '#92400e', fontSize: '12px', cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleRequestChanges}
                    disabled={submittingAction}
                    style={{ padding: '6px 16px', borderRadius: '6px', border: 'none', backgroundColor: '#d97706', color: '#ffffff', fontWeight: 600, fontSize: '12px', cursor: 'pointer' }}
                  >
                    {submittingAction ? 'Sending...' : 'Send Review Feedback & Allow Edit'}
                  </button>
                </div>
              </div>
            )}

            {/* Expandable Reject Textarea */}
            {showRejectInput && (
              <div style={{ padding: '16px 24px', backgroundColor: '#fef2f2', borderBottom: '1px solid #fca5a5' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#991b1b', marginBottom: '6px' }}>
                  Rejection Reason:
                </div>
                <input
                  type="text"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Reason for rejection..."
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    border: '1px solid #fca5a5',
                    fontSize: '13px',
                    outline: 'none',
                    boxSizing: 'border-box',
                    marginBottom: '10px',
                  }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                  <button
                    onClick={() => setShowRejectInput(false)}
                    style={{ padding: '6px 12px', borderRadius: '6px', border: '1px solid #dc2626', background: 'none', color: '#991b1b', fontSize: '12px', cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleReject}
                    disabled={submittingAction}
                    style={{ padding: '6px 16px', borderRadius: '6px', border: 'none', backgroundColor: '#dc2626', color: '#ffffff', fontWeight: 600, fontSize: '12px', cursor: 'pointer' }}
                  >
                    Confirm Rejection
                  </button>
                </div>
              </div>
            )}

            {/* Scrollable Body: Sections A through G */}
            <div style={{ padding: '24px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '24px' }}>
              
              {/* Review History Banner if present */}
              {selectedOnboarding.review_comments && (
                <div style={{
                  padding: '14px 18px',
                  borderRadius: '8px',
                  backgroundColor: selectedOnboarding.status === 'changes_requested' ? '#fffbeb' : '#f8fafc',
                  border: `1px solid ${selectedOnboarding.status === 'changes_requested' ? '#fde68a' : '#e2e8f0'}`,
                }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#92400e', textTransform: 'uppercase', marginBottom: '4px' }}>
                    Latest Review Comments:
                  </div>
                  <div style={{ fontSize: '13px', color: '#78350f' }}>{selectedOnboarding.review_comments}</div>
                </div>
              )}

              {/* SECTION A – Company details */}
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '18px' }}>
                <h4 style={{ margin: '0 0 14px 0', fontSize: '14px', fontWeight: 700, color: '#0f172a', borderBottom: '1px solid #f1f5f9', paddingBottom: '8px' }}>
                  Section A – Company Details
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', fontSize: '13px' }}>
                  <div><span style={{ color: '#64748b' }}>Legal Company Name:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.legal_company_name || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Trade Name:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.trade_name || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Business Type:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.business_type || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Year Established:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.year_of_establishment || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Website:</span> <div>{selectedOnboarding.company_website ? <a href={selectedOnboarding.company_website} target="_blank" rel="noreferrer" style={{ color: '#ef233c' }}>{selectedOnboarding.company_website}</a> : '—'}</div></div>
                  <div style={{ gridColumn: '1 / -1' }}><span style={{ color: '#64748b' }}>Description:</span> <div>{selectedOnboarding.business_description || '—'}</div></div>
                </div>
              </div>

              {/* SECTION B – Indian business and tax details */}
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '18px' }}>
                <h4 style={{ margin: '0 0 14px 0', fontSize: '14px', fontWeight: 700, color: '#0f172a', borderBottom: '1px solid #f1f5f9', paddingBottom: '8px' }}>
                  Section B – Indian Business &amp; Tax Details
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', fontSize: '13px' }}>
                  <div><span style={{ color: '#64748b' }}>PAN Number:</span> <div style={{ fontWeight: 700, fontFamily: 'monospace' }}>{selectedOnboarding.pan_number || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>GSTIN:</span> <div style={{ fontWeight: 700, fontFamily: 'monospace' }}>{selectedOnboarding.gstin || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>GST Type:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.gst_type || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>CIN:</span> <div style={{ fontFamily: 'monospace' }}>{selectedOnboarding.cin || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>LLPIN:</span> <div style={{ fontFamily: 'monospace' }}>{selectedOnboarding.llpin || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Udyam MSME:</span> <div style={{ fontFamily: 'monospace' }}>{selectedOnboarding.udyam_number || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>TAN:</span> <div style={{ fontFamily: 'monospace' }}>{selectedOnboarding.tan || '—'}</div></div>
                </div>
              </div>

              {/* SECTION C – Registered office address */}
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '18px' }}>
                <h4 style={{ margin: '0 0 14px 0', fontSize: '14px', fontWeight: 700, color: '#0f172a', borderBottom: '1px solid #f1f5f9', paddingBottom: '8px' }}>
                  Section C – Registered Office &amp; Address
                </h4>
                <div style={{ fontSize: '13px', lineHeight: '1.6' }}>
                  <div><strong>Address:</strong> {selectedOnboarding.address_line1 || '—'} {selectedOnboarding.address_line2 ? `, ${selectedOnboarding.address_line2}` : ''}</div>
                  <div><strong>City / District:</strong> {selectedOnboarding.city || '—'}, {selectedOnboarding.district || '—'}</div>
                  <div><strong>State &amp; PIN:</strong> {selectedOnboarding.state || '—'} &mdash; {selectedOnboarding.pincode || '—'}</div>
                  <div><strong>Country:</strong> {selectedOnboarding.country || 'India'}</div>
                </div>
              </div>

              {/* SECTION D – Authorized contact person */}
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '18px' }}>
                <h4 style={{ margin: '0 0 14px 0', fontSize: '14px', fontWeight: 700, color: '#0f172a', borderBottom: '1px solid #f1f5f9', paddingBottom: '8px' }}>
                  Section D – Authorized Contact Person
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', fontSize: '13px' }}>
                  <div><span style={{ color: '#64748b' }}>Full Name:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.auth_contact_name || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Designation:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.auth_contact_designation || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Email:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.auth_contact_email || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Mobile:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.auth_contact_mobile || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Alternate Mobile:</span> <div>{selectedOnboarding.auth_contact_alternate_mobile || '—'}</div></div>
                </div>
              </div>

              {/* SECTION E – Company branches */}
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '18px' }}>
                <h4 style={{ margin: '0 0 14px 0', fontSize: '14px', fontWeight: 700, color: '#0f172a', borderBottom: '1px solid #f1f5f9', paddingBottom: '8px' }}>
                  Section E – Branches &amp; Locations
                </h4>
                <div style={{ fontSize: '13px' }}>
                  <div style={{ marginBottom: '8px' }}>
                    <span style={{ color: '#64748b' }}>Multiple Office Locations?</span>{' '}
                    <strong style={{ color: selectedOnboarding.has_multiple_branches ? '#16a34a' : '#475569' }}>
                      {selectedOnboarding.has_multiple_branches ? 'Yes' : 'No'}
                    </strong>
                  </div>
                  {selectedOnboarding.has_multiple_branches && selectedOnboarding.branch_details?.length > 0 && (
                    <div>
                      <span style={{ color: '#64748b' }}>Initial Branch Locations:</span>
                      <ul style={{ margin: '6px 0 0 20px', padding: 0 }}>
                        {selectedOnboarding.branch_details.map((b, i) => (
                          <li key={i} style={{ marginBottom: '2px' }}>
                            {typeof b === 'object' ? b.name : b}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>

              {/* SECTION F – First company administrator */}
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '18px' }}>
                <h4 style={{ margin: '0 0 14px 0', fontSize: '14px', fontWeight: 700, color: '#0f172a', borderBottom: '1px solid #f1f5f9', paddingBottom: '8px' }}>
                  Section F – First Company Administrator
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', fontSize: '13px' }}>
                  <div><span style={{ color: '#64748b' }}>Admin Name:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.admin_name || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Login Email:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.admin_email || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Designation:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.admin_designation || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Mobile:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.admin_mobile || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Password Configured?</span> <div style={{ color: selectedOnboarding.has_admin_password ? '#16a34a' : '#dc2626', fontWeight: 600 }}>{selectedOnboarding.has_admin_password ? '✓ Password Configured' : '✕ Missing Password'}</div></div>
                </div>
              </div>

              {/* SECTION G – Preferences */}
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '18px' }}>
                <h4 style={{ margin: '0 0 14px 0', fontSize: '14px', fontWeight: 700, color: '#0f172a', borderBottom: '1px solid #f1f5f9', paddingBottom: '8px' }}>
                  Section G – Document &amp; Business Preferences
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', fontSize: '13px' }}>
                  <div><span style={{ color: '#64748b' }}>Primary Document Types:</span> <div>{selectedOnboarding.primary_document_types?.join(', ') || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Expected Monthly Volume:</span> <div style={{ fontWeight: 600 }}>{selectedOnboarding.expected_monthly_volume || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Languages:</span> <div>{selectedOnboarding.languages?.join(', ') || '—'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Time Zone:</span> <div>{selectedOnboarding.timezone || 'Asia/Kolkata'}</div></div>
                  <div><span style={{ color: '#64748b' }}>Currency:</span> <div>{selectedOnboarding.currency || 'INR'}</div></div>
                </div>
              </div>

              {/* UPLOADED DOCUMENTS */}
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '18px', backgroundColor: '#fcfcfd' }}>
                <h4 style={{ margin: '0 0 14px 0', fontSize: '14px', fontWeight: 700, color: '#0f172a', borderBottom: '1px solid #f1f5f9', paddingBottom: '8px' }}>
                  Verification Documents Uploaded
                </h4>

                {Object.keys(selectedOnboarding.uploaded_documents || {}).length === 0 ? (
                  <div style={{ color: '#94a3b8', fontSize: '13px' }}>No documents uploaded yet.</div>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
                    {Object.entries(selectedOnboarding.uploaded_documents).map(([typeKey, meta]) => {
                      const docUrl = api.getAdminDocumentUrl(selectedOnboarding.id, typeKey);
                      return (
                        <div key={typeKey} style={{
                          backgroundColor: '#ffffff',
                          border: '1px solid #e2e8f0',
                          borderRadius: '6px',
                          padding: '12px 14px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                        }}>
                          <div style={{ overflow: 'hidden', marginRight: '8px' }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: '#334155' }}>
                              {meta.display_name || typeKey}
                            </div>
                            <div style={{ fontSize: '11px', color: '#64748b', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                              {meta.filename} ({(meta.file_size / 1024).toFixed(0)} KB)
                            </div>
                          </div>
                          <a
                            href={docUrl}
                            target="_blank"
                            rel="noreferrer"
                            style={{
                              padding: '5px 10px',
                              backgroundColor: '#f1f5f9',
                              border: '1px solid #cbd5e1',
                              borderRadius: '4px',
                              fontSize: '11px',
                              fontWeight: 600,
                              color: '#0f172a',
                              textDecoration: 'none',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            Inspect
                          </a>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

            </div>

            {/* Modal Footer */}
            <div style={{ padding: '16px 24px', borderTop: '1px solid #e2e8f0', display: 'flex', justifyContent: 'flex-end', backgroundColor: '#ffffff' }}>
              <button
                onClick={closeReviewModal}
                style={{ padding: '8px 20px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontWeight: 600, fontSize: '13px', cursor: 'pointer' }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal for Inspecting Platform Audit Log Metadata ── */}
      {selectedAuditLog && (
        <div 
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10000,
            padding: '24px',
            boxSizing: 'border-box',
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setSelectedAuditLog(null);
            }
          }}
        >
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            maxWidth: '600px',
            width: '100%',
            maxHeight: '90vh',
            overflowY: 'auto',
            padding: '24px',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
            border: '1px solid #e2e8f0',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                Platform Audit Log #{selectedAuditLog.id}
              </h3>
              <button
                onClick={() => setSelectedAuditLog(null)}
                style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#64748b' }}
              >
                &times;
              </button>
            </div>
            <div style={{ fontSize: '13px', color: '#475569', marginBottom: '12px' }}>
              <div><strong>Action:</strong> <span style={{ fontFamily: 'monospace' }}>{selectedAuditLog.action}</span></div>
              <div><strong>Actor:</strong> {selectedAuditLog.actor_type} {selectedAuditLog.actor_id ? `(#${selectedAuditLog.actor_id})` : ''}</div>
              <div><strong>Target:</strong> {selectedAuditLog.object_type} {selectedAuditLog.object_id ? `(#${selectedAuditLog.object_id})` : ''}</div>
              <div><strong>Company:</strong> {selectedAuditLog.company_id ? `Company #${selectedAuditLog.company_id}` : 'Platform-level'}</div>
              <div><strong>Timestamp:</strong> {selectedAuditLog.occurred_at}</div>
              <div><strong>IP / Agent:</strong> {selectedAuditLog.ip || '—'} &middot; {selectedAuditLog.user_agent || '—'}</div>
              <div><strong>Request ID:</strong> <span style={{ fontFamily: 'monospace', fontSize: '11px' }}>{selectedAuditLog.request_id || '—'}</span></div>
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: '12px', marginBottom: '4px' }}>Metadata:</div>
              <pre style={{
                background: '#0f172a',
                color: '#38bdf8',
                padding: '12px',
                borderRadius: '8px',
                fontSize: '12px',
                overflowX: 'auto',
                maxHeight: '220px',
              }}>
                {JSON.stringify(selectedAuditLog.metadata || selectedAuditLog.event_metadata || {}, null, 2)}
              </pre>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
              <button
                onClick={() => setSelectedAuditLog(null)}
                style={{ padding: '6px 16px', borderRadius: '6px', border: '1px solid #cbd5e1', background: '#f8fafc', cursor: 'pointer' }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── MFA ENROLLMENT MODAL ── */}
      {showMfaEnrollModal && (
        <MfaModal
          mode="self_enroll"
          onSuccess={() => {
            setShowMfaEnrollModal(false);
            setSecuritySuccess('Two-factor authentication successfully enabled!');
            loadPlatformSecurity();
          }}
          onCancel={() => setShowMfaEnrollModal(false)}
        />
      )}

      {/* ── REGENERATE RECOVERY CODES MODAL ── */}
      {showRegenModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.7)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10000,
          padding: '16px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            maxWidth: '460px',
            width: '100%',
            padding: '28px',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
            border: '1px solid #e2e8f0',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                Regenerate Recovery Codes
              </h3>
              <button
                onClick={() => { setShowRegenModal(false); setNewRegenCodes([]); }}
                style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#64748b' }}
              >
                &times;
              </button>
            </div>

            {newRegenCodes.length === 0 ? (
              <form onSubmit={handleRegenCodes}>
                <p style={{ margin: '0 0 16px 0', fontSize: '13px', color: '#64748b', lineHeight: 1.5 }}>
                  Regenerating recovery codes will invalidate all of your previous emergency recovery codes. Please authenticate to confirm.
                </p>

                <div style={{ marginBottom: '14px' }}>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                    Current Password
                  </label>
                  <input
                    type="password"
                    value={regenPassword}
                    onChange={(e) => setRegenPassword(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                    required
                  />
                </div>

                <div style={{ marginBottom: '18px' }}>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                    Authenticator App Code
                  </label>
                  <input
                    type="text"
                    maxLength={6}
                    value={regenCode}
                    onChange={(e) => setRegenCode(e.target.value.replace(/\D/g, ''))}
                    placeholder="6-digit code"
                    style={{ width: '100%', padding: '10px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                    required
                  />
                </div>

                <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    onClick={() => { setShowRegenModal(false); setNewRegenCodes([]); }}
                    style={{ padding: '8px 16px', fontSize: '13px', background: 'none', border: 'none', color: '#64748b', cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={regenLoading}
                    style={{
                      padding: '8px 18px',
                      fontSize: '13px',
                      fontWeight: 600,
                      backgroundColor: '#ef233c',
                      color: '#ffffff',
                      borderRadius: '8px',
                      border: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    {regenLoading ? 'Generating...' : 'Regenerate Codes'}
                  </button>
                </div>
              </form>
            ) : (
              <div>
                <p style={{ margin: '0 0 14px 0', fontSize: '13px', color: '#166534', fontWeight: 600 }}>
                  ✓ New recovery codes generated successfully. Store them in a safe place.
                </p>

                <div style={{
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '10px',
                  padding: '12px',
                  marginBottom: '16px',
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '8px',
                }}>
                  {newRegenCodes.map((c, i) => (
                    <div key={i} style={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      padding: '6px 8px',
                      fontSize: '12px',
                      fontFamily: "'JetBrains Mono', monospace",
                      fontWeight: 700,
                      textAlign: 'center',
                    }}>
                      {c}
                    </div>
                  ))}
                </div>

                <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(newRegenCodes.join('\n'));
                      alert('Recovery codes copied to clipboard.');
                    }}
                    style={{ flex: 1, padding: '8px 12px', fontSize: '12.5px', fontWeight: 600, backgroundColor: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '8px', cursor: 'pointer' }}
                  >
                    Copy Codes
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const text = `DMS Platform Recovery Codes\nGenerated: ${new Date().toISOString()}\n\n` + newRegenCodes.join('\n');
                      const blob = new Blob([text], { type: 'text/plain' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `dms-recovery-codes-${Date.now()}.txt`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                    style={{ flex: 1, padding: '8px 12px', fontSize: '12.5px', fontWeight: 600, backgroundColor: '#f1f5f9', border: '1px solid #cbd5e1', borderRadius: '8px', cursor: 'pointer' }}
                  >
                    Download (.txt)
                  </button>
                </div>

                <button
                  type="button"
                  onClick={() => { setShowRegenModal(false); setNewRegenCodes([]); }}
                  style={{
                    width: '100%',
                    padding: '10px 16px',
                    backgroundColor: '#16a34a',
                    color: '#ffffff',
                    fontWeight: 600,
                    borderRadius: '8px',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  Done
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── MODAL: EDIT COMPANY & QUOTAS ───────────────────────────────────────── */}
      {showEditCompanyModal && selectedCompanyForEdit && (
        <div 
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10000,
            padding: '24px',
            boxSizing: 'border-box',
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget && !editCompanyLoading) {
              setShowEditCompanyModal(false);
              setSelectedCompanyForEdit(null);
            }
          }}
        >
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            maxWidth: '620px',
            width: '100%',
            maxHeight: '90vh',
            overflowY: 'auto',
            padding: '28px',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
            border: '1px solid #e2e8f0',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                  Edit Enterprise Company &amp; Quotas
                </h3>
                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                  {selectedCompanyForEdit.name} ({selectedCompanyForEdit.code})
                </div>
              </div>
              <button
                onClick={() => { setShowEditCompanyModal(false); setSelectedCompanyForEdit(null); }}
                style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer', color: '#94a3b8' }}
              >
                &times;
              </button>
            </div>

            {editCompanyError && (
              <div style={{ padding: '10px 14px', backgroundColor: '#fef2f2', border: '1px solid #fca5a5', borderRadius: '6px', color: '#b91c1c', fontSize: '13px', marginBottom: '16px' }}>
                {editCompanyError}
              </div>
            )}

            <form onSubmit={handleSaveCompanyEdit}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                    Legal Company Name
                  </label>
                  <input
                    type="text"
                    required
                    value={editCompanyForm.name}
                    onChange={(e) => setEditCompanyForm({ ...editCompanyForm, name: e.target.value })}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                    GSTIN (Tax ID)
                  </label>
                  <input
                    type="text"
                    placeholder="33AABCA1234F1Z5"
                    value={editCompanyForm.gstin}
                    onChange={(e) => setEditCompanyForm({ ...editCompanyForm, gstin: e.target.value })}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                  Registered Business Address
                </label>
                <textarea
                  rows={2}
                  value={editCompanyForm.address}
                  onChange={(e) => setEditCompanyForm({ ...editCompanyForm, address: e.target.value })}
                  style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box', resize: 'vertical' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                    Account Status
                  </label>
                  <select
                    value={editCompanyForm.status}
                    onChange={(e) => setEditCompanyForm({ ...editCompanyForm, status: e.target.value })}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box', background: '#fff' }}
                  >
                    <option value="active">Active (Full Access)</option>
                    <option value="suspended">Suspended (Blocked Access)</option>
                  </select>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', paddingTop: '18px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: 600, color: '#1e293b' }}>
                    <input
                      type="checkbox"
                      checked={editCompanyForm.mfa_required_for_all}
                      onChange={(e) => setEditCompanyForm({ ...editCompanyForm, mfa_required_for_all: e.target.checked })}
                    />
                    Mandate MFA for all accounts
                  </label>
                </div>
              </div>

              <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '16px', marginBottom: '16px' }}>
                <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                  Resource Quotas &amp; Spending Limits
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                      Max Allowed Branches
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="1000"
                      required
                      value={editCompanyForm.max_branches}
                      onChange={(e) => setEditCompanyForm({ ...editCompanyForm, max_branches: e.target.value })}
                      style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                      Max Allowed Users
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="10000"
                      required
                      value={editCompanyForm.max_users}
                      onChange={(e) => setEditCompanyForm({ ...editCompanyForm, max_users: e.target.value })}
                      style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                      Storage Limit (Gigabytes)
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="10000"
                      required
                      value={editCompanyForm.storage_limit_gb}
                      onChange={(e) => setEditCompanyForm({ ...editCompanyForm, storage_limit_gb: e.target.value })}
                      style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                      Monthly AI Budget ($ USD / ~₹ INR)
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="100000"
                      required
                      value={editCompanyForm.monthly_ai_budget_dollars}
                      onChange={(e) => setEditCompanyForm({ ...editCompanyForm, monthly_ai_budget_dollars: e.target.value })}
                      style={{ width: '100%', padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px', boxSizing: 'border-box' }}
                    />
                    <span style={{ fontSize: '11px', color: '#64748b', marginTop: '4px', display: 'block' }}>
                      ~₹{(Number(editCompanyForm.monthly_ai_budget_dollars || 0) * 85).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (1 USD = ₹85)
                    </span>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '24px' }}>
                <button
                  type="button"
                  onClick={() => { setShowEditCompanyModal(false); setSelectedCompanyForEdit(null); }}
                  style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editCompanyLoading}
                  style={{ padding: '8px 20px', borderRadius: '6px', border: 'none', backgroundColor: '#ef233c', color: '#ffffff', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  {editCompanyLoading ? 'Saving Changes...' : 'Save Company Quotas'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Custom Styled Confirmation Modal (Replaces unstyled browser confirm) ── */}
      <ConfirmModal
        isOpen={!!confirmDialog}
        title={confirmDialog?.title}
        message={confirmDialog?.message}
        details={confirmDialog?.details}
        confirmText={confirmDialog?.confirmText || 'Confirm'}
        cancelText={confirmDialog?.cancelText || 'Cancel'}
        variant={confirmDialog?.variant || 'primary'}
        loading={submittingAction}
        onConfirm={confirmDialog?.onConfirm}
        onCancel={() => setConfirmDialog(null)}
      />

    </div>
  );
}

