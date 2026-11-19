import React, { useState, useEffect } from 'react';
import { api } from '../api';

export default function MfaModal({
  mode, // 'challenge' | 'mandatory_enroll' | 'self_enroll'
  mfaPendingToken,
  mfaEnrollmentToken,
  portalConfig,
  onSuccess,
  onCancel,
}) {
  const [totpCode, setTotpCode] = useState('');
  const [useRecovery, setUseRecovery] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Enrollment states
  const [enrollStep, setEnrollStep] = useState(1); // 1: QR & Code, 2: Recovery Codes
  const [enrollData, setEnrollData] = useState(null);
  const [generatedCodes, setGeneratedCodes] = useState([]);
  const [codesConfirmed, setCodesConfirmed] = useState(false);
  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedCodes, setCopiedCodes] = useState(false);

  // Initialize enrollment if in enroll mode
  useEffect(() => {
    let ignore = false;
    if (mode === 'mandatory_enroll' || mode === 'self_enroll') {
      setError('');
      setLoading(true);
      api.mfaEnrollStart(mfaEnrollmentToken)
        .then((data) => {
          if (!ignore) {
            setEnrollData(data);
          }
        })
        .catch((err) => {
          if (!ignore) {
            setError(err.message || 'Failed to start MFA setup.');
          }
        })
        .finally(() => {
          if (!ignore) {
            setLoading(false);
          }
        });
    }
    return () => {
      ignore = true;
    };
  }, [mode]);

  // Handle Step 2 login challenge submission
  const handleChallengeSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      let result;
      if (useRecovery) {
        result = await api.mfaRecoveryVerify(mfaPendingToken, recoveryCode);
      } else {
        result = await api.mfaVerify(mfaPendingToken, totpCode);
      }
      onSuccess(result);
    } catch (err) {
      setError(err.message || 'Verification failed. Please check your code and try again.');
    } finally {
      setLoading(false);
    }
  };

  // Handle enrollment verify submission
  const handleEnrollVerify = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const cleanCode = totpCode.trim().replace(/\s+/g, '');
      const result = await api.mfaEnrollVerify(cleanCode, mfaEnrollmentToken);
      setGeneratedCodes(result.recovery_codes || []);
      setEnrollStep(2);
      window._pendingMfaResult = result;
    } catch (err) {
      setError(err.message || 'Invalid verification code. Please make sure the code matches your authenticator app.');
    } finally {
      setLoading(false);
    }
  };

  const handleFinishEnrollment = () => {
    const result = window._pendingMfaResult;
    window._pendingMfaResult = null;
    onSuccess(result || { recovery_codes: generatedCodes });
  };

  const copySecretKey = () => {
    if (!enrollData?.secret) return;
    navigator.clipboard.writeText(enrollData.secret);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2500);
  };

  const handleRegenerateKey = async () => {
    setError('');
    setLoading(true);
    try {
      const data = await api.mfaEnrollStart(mfaEnrollmentToken, true);
      setEnrollData(data);
      setTotpCode('');
    } catch (err) {
      setError(err.message || 'Failed to generate new key.');
    } finally {
      setLoading(false);
    }
  };

  const copyCodes = () => {
    navigator.clipboard.writeText(generatedCodes.join('\n'));
    setCopiedCodes(true);
    setTimeout(() => setCopiedCodes(false), 2500);
  };

  const downloadCodes = () => {
    const text = `DMS Security - Recovery Codes\nGenerated: ${new Date().toISOString()}\n\n` +
      generatedCodes.map((c, i) => `${i + 1}. ${c}`).join('\n') +
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
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.7)',
        backdropFilter: 'blur(4px)',
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        animation: 'fadeIn 0.15s ease-out',
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && onCancel && mode !== 'mandatory_enroll' && !loading) {
          onCancel();
        }
      }}
    >
      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '460px',
          maxHeight: '90vh',
          overflowY: 'auto',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          border: '1px solid #e2e8f0',
          padding: '28px',
          boxSizing: 'border-box',
          animation: 'slideUp 0.18s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >

        {/* ── 1. LOGIN CHALLENGE MODE ────────────────────────────────────────── */}
        {mode === 'challenge' && (
          <div>
            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <div
                style={{
                  width: '52px',
                  height: '52px',
                  borderRadius: '50%',
                  backgroundColor: '#fee2e2',
                  color: '#ef233c',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px auto',
                }}
              >
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
              </div>
              <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                {useRecovery ? 'Emergency Recovery Code' : 'Two-Factor Authentication'}
              </h2>
              <p style={{ fontSize: '13px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {useRecovery
                  ? 'Enter one of your 12-character single-use emergency recovery codes.'
                  : 'Enter the 6-digit code from Microsoft Authenticator, Google Authenticator, or 1Password.'}
              </p>
            </div>

            <form onSubmit={handleChallengeSubmit}>
              {!useRecovery ? (
                <div style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px', textAlign: 'center' }}>
                    Security Code
                  </label>
                  <input
                    type="text"
                    inputMode="numeric"
                    autoFocus
                    maxLength={6}
                    placeholder="123456"
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                    style={{
                      width: '100%',
                      padding: '12px 16px',
                      fontSize: '26px',
                      fontWeight: 700,
                      fontFamily: "'JetBrains Mono', monospace",
                      letterSpacing: '8px',
                      textAlign: 'center',
                      borderRadius: '10px',
                      border: '2px solid #cbd5e1',
                      outline: 'none',
                      boxSizing: 'border-box',
                      color: '#0f172a',
                    }}
                    required
                  />
                </div>
              ) : (
                <div style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px', textAlign: 'center' }}>
                    12-Character Recovery Code
                  </label>
                  <input
                    type="text"
                    autoFocus
                    placeholder="ABCD-EFGH-1234"
                    value={recoveryCode}
                    onChange={(e) => setRecoveryCode(e.target.value.toUpperCase())}
                    style={{
                      width: '100%',
                      padding: '12px 16px',
                      fontSize: '16px',
                      fontWeight: 700,
                      fontFamily: "'JetBrains Mono', monospace",
                      letterSpacing: '2px',
                      textAlign: 'center',
                      borderRadius: '10px',
                      border: '2px solid #cbd5e1',
                      outline: 'none',
                      boxSizing: 'border-box',
                      color: '#0f172a',
                    }}
                    required
                  />
                </div>
              )}

              {error && (
                <div style={{
                  backgroundColor: '#fef2f2',
                  border: '1px solid #fecaca',
                  color: '#b91c1c',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  fontSize: '12.5px',
                  marginBottom: '14px',
                  textAlign: 'center',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                }}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  <span>{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={loading || (!useRecovery && totpCode.length !== 6) || (useRecovery && !recoveryCode.trim())}
                style={{
                  width: '100%',
                  padding: '12px 20px',
                  backgroundColor: loading ? '#94a3b8' : '#ef233c',
                  color: '#ffffff',
                  fontWeight: 600,
                  fontSize: '14px',
                  borderRadius: '10px',
                  border: 'none',
                  cursor: loading ? 'default' : 'pointer',
                  transition: 'background 0.2s',
                  marginBottom: '10px',
                }}
              >
                {loading ? 'Verifying...' : 'Verify & Continue'}
              </button>

              <div style={{ display: 'flex', justifyContent: 'center', marginTop: '10px' }}>
                <button
                  type="button"
                  onClick={() => {
                    setUseRecovery(!useRecovery);
                    setError('');
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#64748b',
                    fontSize: '12px',
                    fontWeight: 500,
                    cursor: 'pointer',
                    textDecoration: 'underline',
                  }}
                >
                  {useRecovery ? '← Back to Authenticator App Code' : 'Having trouble? Use an emergency recovery code'}
                </button>
              </div>

              {onCancel && (
                <div style={{ textAlign: 'center', marginTop: '8px' }}>
                  <button
                    type="button"
                    onClick={onCancel}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#94a3b8',
                      fontSize: '12px',
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </form>
          </div>
        )}

        {/* ── 2. ENROLLMENT MODE - STEP 1: SCAN QR CODE ──────────────────────── */}
        {(mode === 'mandatory_enroll' || mode === 'self_enroll') && enrollStep === 1 && (
          <div>
            <div style={{ textAlign: 'center', marginBottom: '16px' }}>
              <span style={{
                display: 'inline-block',
                fontSize: '10px',
                fontWeight: 700,
                letterSpacing: '1px',
                textTransform: 'uppercase',
                padding: '3px 10px',
                borderRadius: '12px',
                backgroundColor: '#fee2e2',
                color: '#ef233c',
                marginBottom: '8px',
              }}>
                {mode === 'mandatory_enroll' ? 'Security Policy Requirement' : '2FA Configuration'}
              </span>
              <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                Set Up Authenticator App
              </h2>
              <p style={{ fontSize: '13px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                Open Microsoft Authenticator or Google Authenticator on your mobile device and scan the QR code below.
              </p>
            </div>

            {loading && !enrollData && (
              <div style={{ textAlign: 'center', padding: '40px 0', color: '#64748b', fontSize: '13px' }}>
                Generating security credentials...
              </div>
            )}

            {enrollData && (
              <div>
                {/* QR Code Container */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  padding: '16px',
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  borderRadius: '12px',
                  marginBottom: '16px',
                  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.05)',
                }}>
                  {enrollData.qr_code_data_url ? (
                    <img
                      src={enrollData.qr_code_data_url}
                      alt="Authenticator QR Code"
                      style={{
                        width: '220px',
                        height: '220px',
                        display: 'block',
                        imageRendering: 'pixelated',
                      }}
                    />
                  ) : (
                    <div
                      style={{
                        width: '210px',
                        height: '210px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                      dangerouslySetInnerHTML={{
                        __html: (enrollData.qr_code_svg || '').replace(/<svg /, '<svg style="width:100%;height:100%;display:block;" '),
                      }}
                    />
                  )}
                </div>

                {/* Manual Entry Key */}
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                      Manual Entry Key
                    </span>
                    <div style={{ display: 'flex', gap: '12px' }}>
                      <button
                        type="button"
                        onClick={handleRegenerateKey}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#64748b',
                          fontSize: '11px',
                          fontWeight: 600,
                          cursor: 'pointer',
                          textDecoration: 'underline',
                        }}
                        title="Generate a brand new QR code and secret key"
                      >
                        Reset / New Key
                      </button>
                      <button
                        type="button"
                        onClick={copySecretKey}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: copiedKey ? '#16a34a' : '#ef233c',
                          fontSize: '11px',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        {copiedKey ? '✓ Copied' : 'Copy Key'}
                      </button>
                    </div>
                  </div>
                  <div
                    style={{
                      padding: '10px 12px',
                      backgroundColor: '#f8fafc',
                      borderRadius: '8px',
                      fontSize: '13px',
                      fontFamily: "'JetBrains Mono', monospace",
                      fontWeight: 600,
                      letterSpacing: '1.5px',
                      color: '#0f172a',
                      textAlign: 'center',
                      lineHeight: '1.6',
                      border: '1px solid #cbd5e1',
                      userSelect: 'all',
                    }}
                  >
                    <div>{enrollData.secret.slice(0, 16).match(/.{1,4}/g)?.join(' ')}</div>
                    <div>{enrollData.secret.slice(16).match(/.{1,4}/g)?.join(' ')}</div>
                  </div>
                </div>

                {/* Verification Code Form */}
                <form onSubmit={handleEnrollVerify}>
                  <div style={{ marginBottom: '16px' }}>
                    <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
                      Enter 6-Digit Code From App
                    </label>
                    <input
                      type="text"
                      inputMode="numeric"
                      maxLength={6}
                      placeholder="123456"
                      value={totpCode}
                      onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        fontSize: '22px',
                        fontWeight: 700,
                        fontFamily: "'JetBrains Mono', monospace",
                        letterSpacing: '6px',
                        textAlign: 'center',
                        borderRadius: '10px',
                        border: '2px solid #cbd5e1',
                        outline: 'none',
                        boxSizing: 'border-box',
                        color: '#0f172a',
                      }}
                      required
                    />
                  </div>

                  {error && (
                    <div style={{
                      backgroundColor: '#fef2f2',
                      border: '1px solid #fecaca',
                      color: '#b91c1c',
                      padding: '10px 14px',
                      borderRadius: '8px',
                      fontSize: '12px',
                      marginBottom: '14px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                      </svg>
                      <span>{error}</span>
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading || totpCode.length !== 6}
                    style={{
                      width: '100%',
                      padding: '12px 20px',
                      backgroundColor: (loading || totpCode.length !== 6) ? '#94a3b8' : '#ef233c',
                      color: '#ffffff',
                      fontWeight: 600,
                      fontSize: '14px',
                      borderRadius: '10px',
                      border: 'none',
                      cursor: (loading || totpCode.length !== 6) ? 'default' : 'pointer',
                      transition: 'background 0.2s',
                    }}
                  >
                    {loading ? 'Activating...' : 'Verify & Enable 2FA'}
                  </button>

                  {onCancel && mode !== 'mandatory_enroll' && (
                    <button
                      type="button"
                      onClick={onCancel}
                      style={{
                        width: '100%',
                        marginTop: '10px',
                        padding: '8px',
                        background: 'none',
                        border: 'none',
                        color: '#64748b',
                        fontSize: '13px',
                        cursor: 'pointer',
                      }}
                    >
                      Cancel
                    </button>
                  )}
                </form>
              </div>
            )}
          </div>
        )}

        {/* ── 3. ENROLLMENT MODE - STEP 2: RECOVERY CODES ─────────────────────── */}
        {(mode === 'mandatory_enroll' || mode === 'self_enroll') && enrollStep === 2 && (
          <div>
            <div style={{ textAlign: 'center', marginBottom: '16px' }}>
              <div
                style={{
                  width: '50px',
                  height: '50px',
                  borderRadius: '50%',
                  backgroundColor: '#dcfce7',
                  color: '#16a34a',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px auto',
                }}
              >
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M20 6L9 17l-5-5"/>
                </svg>
              </div>
              <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                Save Your Recovery Codes
              </h2>
              <p style={{ fontSize: '13px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                If you ever lose access to your phone or authenticator app, these emergency codes will let you log in. Each code can be used once.
              </p>
            </div>

            {/* Codes Grid */}
            <div style={{
              backgroundColor: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '12px',
              padding: '14px',
              marginBottom: '14px',
            }}>
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '8px',
              }}>
                {generatedCodes.map((code, index) => (
                  <div
                    key={index}
                    style={{
                      backgroundColor: '#ffffff',
                      border: '1px solid #cbd5e1',
                      borderRadius: '6px',
                      padding: '6px 8px',
                      fontSize: '12px',
                      fontFamily: "'JetBrains Mono', monospace",
                      fontWeight: 700,
                      color: '#1e293b',
                      textAlign: 'center',
                      userSelect: 'all',
                    }}
                  >
                    {code}
                  </div>
                ))}
              </div>
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              <button
                type="button"
                onClick={copyCodes}
                style={{
                  flex: 1,
                  padding: '9px 12px',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  backgroundColor: '#f1f5f9',
                  border: '1px solid #cbd5e1',
                  color: '#334155',
                  borderRadius: '8px',
                  cursor: 'pointer',
                }}
              >
                {copiedCodes ? '✓ Copied All' : 'Copy Codes'}
              </button>
              <button
                type="button"
                onClick={downloadCodes}
                style={{
                  flex: 1,
                  padding: '9px 12px',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  backgroundColor: '#f1f5f9',
                  border: '1px solid #cbd5e1',
                  color: '#334155',
                  borderRadius: '8px',
                  cursor: 'pointer',
                }}
              >
                Download (.txt)
              </button>
            </div>

            {/* Confirmation Checkbox */}
            <label style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
              fontSize: '12.5px',
              color: '#334155',
              cursor: 'pointer',
              marginBottom: '18px',
              lineHeight: 1.4,
            }}>
              <input
                type="checkbox"
                checked={codesConfirmed}
                onChange={(e) => setCodesConfirmed(e.target.checked)}
                style={{ marginTop: '3px', width: '16px', height: '16px', accentColor: '#ef233c' }}
              />
              <span>I have saved these recovery codes in a secure location (e.g. password manager).</span>
            </label>

            {/* Complete Button */}
            <button
              type="button"
              disabled={!codesConfirmed}
              onClick={handleFinishEnrollment}
              style={{
                width: '100%',
                padding: '12px 20px',
                backgroundColor: !codesConfirmed ? '#94a3b8' : '#16a34a',
                color: '#ffffff',
                fontWeight: 600,
                fontSize: '14px',
                borderRadius: '10px',
                border: 'none',
                cursor: !codesConfirmed ? 'default' : 'pointer',
                transition: 'background 0.2s',
              }}
            >
              Continue to System
            </button>
          </div>
        )}

      </div>
    </div>
  );
}
