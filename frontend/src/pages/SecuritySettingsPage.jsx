import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Navigate } from 'react-router-dom';
import { api } from '../api';
import MfaModal from '../components/MfaModal';

export default function SecuritySettingsPage() {
  const { user, portal } = useAuth();

  // If Master Admin, automatically redirect to the Settings & Security tab inside Master Admin portal
  if (portal === 'platform' || user?.role === 'MASTER_ADMIN' || user?.portal === 'platform') {
    return <Navigate to="/admin?tab=settings" replace />;
  }

  // Staff and Uploader accounts cannot manage security policies or self-enroll; redirect to documents
  if (user?.role === 'STAFF' || user?.role === 'UPLOADER') {
    return <Navigate to="/documents" replace />;
  }

  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Modal triggers
  const [showEnrollModal, setShowEnrollModal] = useState(false);

  // Disable MFA form
  const [showDisableForm, setShowDisableForm] = useState(false);
  const [disablePassword, setDisablePassword] = useState('');
  const [disableCode, setDisableCode] = useState('');
  const [disableLoading, setDisableLoading] = useState(false);

  // Regenerate codes modal / state
  const [showRegenModal, setShowRegenModal] = useState(false);
  const [regenCode, setRegenCode] = useState('');
  const [newCodes, setNewCodes] = useState([]);
  const [regenLoading, setRegenLoading] = useState(false);
  const [copiedCodes, setCopiedCodes] = useState(false);

  // Role identification
  const isCompanyAdmin = user?.role === 'GLOBAL_ADMIN';
  const isBranchAdmin = user?.role === 'ADMIN';
  const isStaffOrUploader = user?.role === 'STAFF' || user?.role === 'UPLOADER';
  const isAdminUser = isCompanyAdmin || isBranchAdmin || user?.role === 'MASTER_ADMIN';

  // Company MFA policy (if Company Admin)
  const [companyPolicy, setCompanyPolicy] = useState(null);
  const [policyLoading, setPolicyLoading] = useState(false);

  // Branch MFA policy (if Branch Admin)
  const [branchPolicy, setBranchPolicy] = useState(null);
  const [branchPolicyLoading, setBranchPolicyLoading] = useState(false);

  useEffect(() => {
    loadStatus();
    if (isCompanyAdmin) loadCompanyPolicy();
    if (isBranchAdmin && user?.branch_id) loadBranchPolicy();
  }, [user]);

  const loadStatus = async () => {
    try {
      const res = await api.mfaStatus();
      setStatus(res);
    } catch (err) {
      setError(err.message || 'Failed to load MFA security status.');
    } finally {
      setLoading(false);
    }
  };

  const loadCompanyPolicy = async () => {
    try {
      const res = await api.getCompanyMfaPolicy();
      setCompanyPolicy(res);
    } catch {
      // Ignore if not permitted
    }
  };

  const loadBranchPolicy = async () => {
    if (!user?.branch_id) return;
    try {
      const res = await api.getBranchMfaPolicy(user.branch_id);
      setBranchPolicy(res);
    } catch {
      // Ignore if not permitted
    }
  };

  const handleToggleCompanyPolicy = async (e) => {
    const val = e.target.checked;
    setPolicyLoading(true);
    try {
      const updated = await api.updateCompanyMfaPolicy({ mfa_required_for_all: val });
      setCompanyPolicy(updated);
      setSuccess(`Company policy updated: MFA is now ${val ? 'mandatory' : 'optional'} for all company users.`);
      setTimeout(() => setSuccess(''), 5000);
      loadStatus();
    } catch (err) {
      setError(err.message || 'Failed to update company policy.');
    } finally {
      setPolicyLoading(false);
    }
  };

  const handleToggleBranchDelegation = async (e) => {
    const val = e.target.checked;
    setPolicyLoading(true);
    try {
      const updated = await api.updateCompanyMfaPolicy({ allow_branch_mfa_control: val });
      setCompanyPolicy(updated);
      setSuccess(`Branch delegation updated: Branch Administrators ${val ? 'can now' : 'can no longer'} manage branch MFA policies.`);
      setTimeout(() => setSuccess(''), 5000);
    } catch (err) {
      setError(err.message || 'Failed to update branch delegation setting.');
    } finally {
      setPolicyLoading(false);
    }
  };

  const handleToggleBranchPolicy = async (e) => {
    const val = e.target.checked;
    setBranchPolicyLoading(true);
    try {
      const updated = await api.updateBranchMfaPolicy(user.branch_id, val);
      setBranchPolicy(updated);
      setSuccess(`Branch MFA policy updated: MFA is now ${val ? 'mandatory' : 'optional'} for this branch.`);
      setTimeout(() => setSuccess(''), 5000);
      loadStatus();
    } catch (err) {
      setError(err.message || 'Failed to update branch MFA policy.');
    } finally {
      setBranchPolicyLoading(false);
    }
  };

  const handleDisableSubmit = async (e) => {
    e.preventDefault();
    setDisableLoading(true);
    setError('');
    try {
      await api.mfaDisable(disablePassword, disableCode);
      setSuccess('MFA has been successfully disabled.');
      setShowDisableForm(false);
      setDisablePassword('');
      setDisableCode('');
      loadStatus();
    } catch (err) {
      setError(err.message || 'Failed to disable MFA.');
    } finally {
      setDisableLoading(false);
    }
  };

  const handleRegenerateSubmit = async (e) => {
    e.preventDefault();
    setRegenLoading(true);
    setError('');
    try {
      const res = await api.mfaRegenerateRecovery({ code: regenCode });
      setNewCodes(res.recovery_codes || []);
      setRegenCode('');
      loadStatus();
    } catch (err) {
      setError(err.message || 'Failed to regenerate recovery codes.');
    } finally {
      setRegenLoading(false);
    }
  };

  const copyCodesToClipboard = () => {
    if (!newCodes.length) return;
    navigator.clipboard.writeText(newCodes.join('\n'));
    setCopiedCodes(true);
    setTimeout(() => setCopiedCodes(false), 2500);
  };

  const downloadCodesAsFile = () => {
    const text = `DMS Security - Emergency Recovery Codes\nGenerated: ${new Date().toISOString()}\nAccount: ${user?.email || ''}\n\n` +
      newCodes.map((c, i) => `${i + 1}. ${c}`).join('\n') +
      `\n\nKeep these codes safe. Each code can be used only once.`;
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dms-recovery-codes-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', padding: '32px 24px', fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif" }}>
      {/* Header */}
      <div style={{ marginBottom: '28px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0', letterSpacing: '-0.3px' }}>
          Security &amp; Authentication
        </h1>
        <p style={{ fontSize: '14px', color: '#64748b', margin: 0 }}>
          Manage two-factor authentication (TOTP), emergency recovery keys, and organization-wide security policies.
        </p>
      </div>

      {/* Notifications */}
      {error && (
        <div style={{
          backgroundColor: '#fef2f2',
          border: '1px solid #fecaca',
          color: '#991b1b',
          padding: '14px 18px',
          borderRadius: '10px',
          fontSize: '13px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <span>{error}</span>
          <button
            onClick={() => setError('')}
            style={{ background: 'none', border: 'none', color: '#991b1b', fontSize: '18px', cursor: 'pointer', padding: '0 4px', lineHeight: 1 }}
          >
            &times;
          </button>
        </div>
      )}

      {success && (
        <div style={{
          backgroundColor: '#ecfdf5',
          border: '1px solid #a7f3d0',
          color: '#065f46',
          padding: '14px 18px',
          borderRadius: '10px',
          fontSize: '13px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <span>{success}</span>
          <button
            onClick={() => setSuccess('')}
            style={{ background: 'none', border: 'none', color: '#065f46', fontSize: '18px', cursor: 'pointer', padding: '0 4px', lineHeight: 1 }}
          >
            &times;
          </button>
        </div>
      )}

      {/* ── 1. USER 2FA CARD ──────────────────────────────────────────────── */}
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '14px',
        border: '1px solid #e2e8f0',
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        overflow: 'hidden',
        marginBottom: '24px',
      }}>
        <div style={{
          padding: '24px',
          borderBottom: '1px solid #f1f5f9',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: status?.enabled ? '#ecfdf5' : '#f1f5f9',
              color: status?.enabled ? '#059669' : '#64748b',
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
            </div>
            <div>
              <h2 style={{ fontSize: '17px', fontWeight: 600, color: '#0f172a', margin: '0 0 4px 0' }}>
                Two-Factor Authentication (TOTP)
              </h2>
              <p style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>
                Protect your account with an extra verification step using Google Authenticator or Microsoft Authenticator.
              </p>
            </div>
          </div>
          <div>
            {status?.enabled ? (
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 12px',
                borderRadius: '20px',
                fontSize: '12px',
                fontWeight: 600,
                backgroundColor: '#ecfdf5',
                color: '#065f46',
                border: '1px solid #a7f3d0',
              }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#059669' }} />
                Active
              </span>
            ) : (
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '4px 12px',
                borderRadius: '20px',
                fontSize: '12px',
                fontWeight: 600,
                backgroundColor: '#f1f5f9',
                color: '#475569',
                border: '1px solid #e2e8f0',
              }}>
                Disabled
              </span>
            )}
          </div>
        </div>

        <div style={{ padding: '24px' }}>
          {loading ? (
            <div style={{ fontSize: '13px', color: '#94a3b8', padding: '16px 0' }}>Checking MFA status...</div>
          ) : status?.enabled ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '16px 20px',
                backgroundColor: '#f8fafc',
                borderRadius: '12px',
                border: '1px solid #e2e8f0',
                flexWrap: 'wrap',
                gap: '12px',
              }}>
                <div>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Remaining Recovery Codes
                  </div>
                  <div style={{ fontSize: '24px', fontWeight: 800, color: '#0f172a', marginTop: '2px' }}>
                    {status.remaining_recovery_codes} <span style={{ fontSize: '13px', fontWeight: 400, color: '#64748b' }}>of 8 codes</span>
                  </div>
                </div>
                {isAdminUser ? (
                  <button
                    type="button"
                    onClick={() => {
                      setShowRegenModal(true);
                      setNewCodes([]);
                    }}
                    style={{
                      padding: '8px 16px',
                      fontSize: '13px',
                      fontWeight: 600,
                      backgroundColor: '#ffffff',
                      border: '1px solid #cbd5e1',
                      borderRadius: '8px',
                      color: '#334155',
                      cursor: 'pointer',
                      boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
                    }}
                  >
                    Regenerate Codes
                  </button>
                ) : (
                  <div style={{ fontSize: '12px', color: '#64748b', fontStyle: 'italic' }}>
                    Contact your administrator if recovery codes need to be reset.
                  </div>
                )}
              </div>

              {status.mandatory && (
                <div style={{
                  padding: '12px 16px',
                  backgroundColor: '#fffbeb',
                  border: '1px solid #fde68a',
                  color: '#92400e',
                  borderRadius: '10px',
                  fontSize: '13px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  <span>MFA is mandatory for your organization or role and cannot be disabled.</span>
                </div>
              )}

              {!status.mandatory && isAdminUser && (
                <div style={{ paddingTop: '8px' }}>
                  {!showDisableForm ? (
                    <button
                      type="button"
                      onClick={() => setShowDisableForm(true)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: '#dc2626',
                        fontSize: '13px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        padding: 0,
                        textDecoration: 'underline',
                      }}
                    >
                      Disable two-factor authentication
                    </button>
                  ) : (
                    <form onSubmit={handleDisableSubmit} style={{
                      padding: '18px',
                      backgroundColor: '#fef2f2',
                      border: '1px solid #fecaca',
                      borderRadius: '12px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '12px',
                      maxWidth: '520px',
                    }}>
                      <div style={{ fontSize: '13px', fontWeight: 700, color: '#991b1b' }}>Confirm Disabling 2FA</div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                        <div>
                          <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                            Your Password
                          </label>
                          <input
                            type="password"
                            value={disablePassword}
                            onChange={(e) => setDisablePassword(e.target.value)}
                            style={{
                              width: '100%',
                              padding: '8px 12px',
                              fontSize: '13px',
                              border: '1px solid #cbd5e1',
                              borderRadius: '8px',
                              boxSizing: 'border-box',
                            }}
                            required
                          />
                        </div>
                        <div>
                          <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                            Authenticator Code
                          </label>
                          <input
                            type="text"
                            maxLength={6}
                            placeholder="123456"
                            value={disableCode}
                            onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, ''))}
                            style={{
                              width: '100%',
                              padding: '8px 12px',
                              fontSize: '13px',
                              border: '1px solid #cbd5e1',
                              borderRadius: '8px',
                              boxSizing: 'border-box',
                              fontFamily: 'monospace',
                              letterSpacing: '2px',
                            }}
                            required
                          />
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', paddingTop: '4px' }}>
                        <button
                          type="button"
                          onClick={() => setShowDisableForm(false)}
                          style={{
                            padding: '6px 14px',
                            fontSize: '12px',
                            fontWeight: 600,
                            backgroundColor: '#ffffff',
                            border: '1px solid #cbd5e1',
                            borderRadius: '6px',
                            color: '#475569',
                            cursor: 'pointer',
                          }}
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          disabled={disableLoading || !disablePassword || disableCode.length !== 6}
                          style={{
                            padding: '6px 14px',
                            fontSize: '12px',
                            fontWeight: 600,
                            backgroundColor: '#dc2626',
                            border: 'none',
                            borderRadius: '6px',
                            color: '#ffffff',
                            cursor: 'pointer',
                            opacity: (disableLoading || !disablePassword || disableCode.length !== 6) ? 0.6 : 1,
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
          ) : isStaffOrUploader ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <p style={{ fontSize: '13px', color: '#475569', margin: 0, lineHeight: 1.5 }}>
                Two-Factor Authentication (TOTP) is centrally managed by your organization's administrators.
              </p>
              {status?.mandatory ? (
                <div style={{
                  padding: '12px 16px',
                  backgroundColor: '#eff6ff',
                  border: '1px solid #bfdbfe',
                  color: '#1d4ed8',
                  borderRadius: '10px',
                  fontSize: '13px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}>
                  <span>MFA is mandatory for your account. You will be prompted to complete setup upon your next sign in.</span>
                </div>
              ) : (
                <div style={{
                  padding: '12px 16px',
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  color: '#64748b',
                  borderRadius: '10px',
                  fontSize: '13px',
                }}>
                  Voluntary self-enrollment is not permitted for staff accounts. Contact your branch administrator if you require MFA.
                </div>
              )}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <p style={{ fontSize: '13px', color: '#475569', margin: 0, lineHeight: 1.5 }}>
                You have not enabled two-factor authentication on your account yet. When enabled, signing in will require your password and a temporary verification code from your mobile device.
              </p>
              <div>
                <button
                  type="button"
                  onClick={() => setShowEnrollModal(true)}
                  style={{
                    backgroundColor: '#2563eb',
                    color: '#ffffff',
                    border: 'none',
                    padding: '10px 20px',
                    fontSize: '13px',
                    fontWeight: 600,
                    borderRadius: '8px',
                    cursor: 'pointer',
                    boxShadow: '0 2px 8px rgba(37,99,235,0.25)',
                  }}
                >
                  Set Up Two-Factor Authentication
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── 2. COMPANY ADMIN POLICY CARD ──────────────────────────────────── */}
      {isCompanyAdmin && (
        <div style={{
          backgroundColor: '#ffffff',
          borderRadius: '14px',
          border: '1px solid #e2e8f0',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          padding: '24px',
          marginBottom: '24px',
        }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <h2 style={{ fontSize: '17px', fontWeight: 600, color: '#0f172a', margin: '0 0 4px 0' }}>
                  Company MFA Enforcement Policy
                </h2>
                <p style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>
                  Require all employees and staff members across all branches of your enterprise to configure and use 2FA.
                </p>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={Boolean(companyPolicy?.mfa_required_for_all)}
                  onChange={handleToggleCompanyPolicy}
                  disabled={policyLoading}
                  style={{ width: '20px', height: '20px', accentColor: '#2563eb', cursor: 'pointer' }}
                />
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>
                  {Boolean(companyPolicy?.mfa_required_for_all) ? 'Enforced' : 'Optional'}
                </span>
              </label>
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '16px',
              paddingTop: '16px',
              borderTop: '1px solid #f1f5f9',
            }}>
              <div>
                <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a', margin: '0 0 4px 0' }}>
                  Branch MFA Delegation
                </h3>
                <p style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>
                  Allow Branch Administrators to manage and mandate MFA policies for their assigned branches independently.
                </p>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={Boolean(companyPolicy?.allow_branch_mfa_control)}
                  onChange={handleToggleBranchDelegation}
                  disabled={policyLoading}
                  style={{ width: '20px', height: '20px', accentColor: '#2563eb', cursor: 'pointer' }}
                />
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>
                  {Boolean(companyPolicy?.allow_branch_mfa_control) ? 'Delegated' : 'Disabled'}
                </span>
              </label>
            </div>
          </div>
        </div>
      )}

      {/* ── 2B. BRANCH ADMIN POLICY CARD ──────────────────────────────────── */}
      {isBranchAdmin && user?.branch_id && (
        <div style={{
          backgroundColor: '#ffffff',
          borderRadius: '14px',
          border: '1px solid #e2e8f0',
          boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
          padding: '24px',
          marginBottom: '24px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
            <div>
              <h2 style={{ fontSize: '17px', fontWeight: 600, color: '#0f172a', margin: '0 0 4px 0' }}>
                Branch MFA Policy
              </h2>
              <p style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>
                Manage two-factor authentication requirement for all staff members assigned to your branch.
              </p>
              {branchPolicy?.is_locked_by_higher_policy && (
                <div style={{ marginTop: '8px', fontSize: '12px', color: '#b45309', fontWeight: 500 }}>
                  Locked: {branchPolicy.lock_reason}
                </div>
              )}
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: branchPolicy?.is_locked_by_higher_policy ? 'not-allowed' : 'pointer' }}>
              <input
                type="checkbox"
                checked={Boolean(branchPolicy?.mfa_required_for_all)}
                onChange={handleToggleBranchPolicy}
                disabled={branchPolicyLoading || branchPolicy?.is_locked_by_higher_policy}
                style={{ width: '20px', height: '20px', accentColor: '#2563eb', cursor: branchPolicy?.is_locked_by_higher_policy ? 'not-allowed' : 'pointer' }}
              />
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>
                {Boolean(branchPolicy?.mfa_required_for_all) ? 'Enforced' : 'Optional'}
              </span>
            </label>
          </div>
        </div>
      )}

      {/* ── 3. SELF-ENROLLMENT MODAL ──────────────────────────────────────── */}
      {showEnrollModal && (
        <MfaModal
          mode="self_enroll"
          onSuccess={() => {
            setShowEnrollModal(false);
            setSuccess('Two-factor authentication enabled successfully.');
            loadStatus();
          }}
          onCancel={() => setShowEnrollModal(false)}
        />
      )}

      {/* ── 4. REGENERATE RECOVERY CODES MODAL ─────────────────────────────── */}
      {showRegenModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(4px)',
          zIndex: 10000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '16px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            width: '100%',
            maxWidth: '460px',
            padding: '28px',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)',
            border: '1px solid #e2e8f0',
          }}>
            {newCodes.length === 0 ? (
              <form onSubmit={handleRegenerateSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                  Regenerate Recovery Codes
                </h3>
                <p style={{ fontSize: '13px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                  Regenerating recovery codes will immediately invalidate all of your existing recovery codes. Enter your 6-digit authenticator code to confirm.
                </p>
                <div>
                  <input
                    type="text"
                    maxLength={6}
                    placeholder="123456"
                    value={regenCode}
                    onChange={(e) => setRegenCode(e.target.value.replace(/\D/g, ''))}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      fontSize: '20px',
                      textAlign: 'center',
                      fontFamily: 'monospace',
                      letterSpacing: '4px',
                      border: '1px solid #cbd5e1',
                      borderRadius: '10px',
                      boxSizing: 'border-box',
                    }}
                    required
                  />
                </div>
                <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', paddingTop: '8px' }}>
                  <button
                    type="button"
                    onClick={() => setShowRegenModal(false)}
                    style={{
                      padding: '8px 16px',
                      fontSize: '13px',
                      fontWeight: 600,
                      backgroundColor: '#ffffff',
                      border: '1px solid #cbd5e1',
                      borderRadius: '8px',
                      color: '#475569',
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={regenLoading || regenCode.length !== 6}
                    style={{
                      padding: '8px 16px',
                      fontSize: '13px',
                      fontWeight: 600,
                      backgroundColor: '#2563eb',
                      border: 'none',
                      borderRadius: '8px',
                      color: '#ffffff',
                      cursor: 'pointer',
                      opacity: (regenLoading || regenCode.length !== 6) ? 0.6 : 1,
                    }}
                  >
                    {regenLoading ? 'Regenerating...' : 'Generate New Codes'}
                  </button>
                </div>
              </form>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                  Your New Recovery Codes
                </h3>
                <p style={{ fontSize: '13px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                  Store these new codes in a secure password manager. Your previous codes are now permanently invalid.
                </p>

                <div style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '8px',
                  backgroundColor: '#f8fafc',
                  padding: '16px',
                  borderRadius: '10px',
                  border: '1px solid #e2e8f0',
                }}>
                  {newCodes.map((c, i) => (
                    <div key={i} style={{
                      backgroundColor: '#ffffff',
                      padding: '8px',
                      borderRadius: '6px',
                      border: '1px solid #e2e8f0',
                      textAlign: 'center',
                      fontFamily: 'monospace',
                      fontSize: '13px',
                      fontWeight: 700,
                      color: '#0f172a',
                      userSelect: 'all',
                    }}>
                      {c}
                    </div>
                  ))}
                </div>

                <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                  <button
                    type="button"
                    onClick={copyCodesToClipboard}
                    style={{
                      padding: '8px 16px',
                      fontSize: '12px',
                      fontWeight: 600,
                      backgroundColor: '#f1f5f9',
                      border: '1px solid #cbd5e1',
                      borderRadius: '8px',
                      color: '#334155',
                      cursor: 'pointer',
                    }}
                  >
                    {copiedCodes ? '✓ Copied!' : 'Copy All'}
                  </button>
                  <button
                    type="button"
                    onClick={downloadCodesAsFile}
                    style={{
                      padding: '8px 16px',
                      fontSize: '12px',
                      fontWeight: 600,
                      backgroundColor: '#f1f5f9',
                      border: '1px solid #cbd5e1',
                      borderRadius: '8px',
                      color: '#334155',
                      cursor: 'pointer',
                    }}
                  >
                    Download (.txt)
                  </button>
                </div>

                <button
                  type="button"
                  onClick={() => setShowRegenModal(false)}
                  style={{
                    width: '100%',
                    padding: '10px',
                    fontSize: '13px',
                    fontWeight: 600,
                    backgroundColor: '#059669',
                    border: 'none',
                    borderRadius: '8px',
                    color: '#ffffff',
                    cursor: 'pointer',
                    marginTop: '8px',
                  }}
                >
                  Done
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
