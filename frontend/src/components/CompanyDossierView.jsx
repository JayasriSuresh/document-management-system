import React, { useState, useEffect } from 'react';
import { api, getAuthToken } from '../api';

export default function CompanyDossierView({
  companyId,
  onBack,
  onEditQuotas,
  onToggleStatus,
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [company, setCompany] = useState(null);
  const [onboarding, setOnboarding] = useState(null);
  const [copiedField, setCopiedField] = useState('');

  useEffect(() => {
    if (!companyId) {
      setLoading(false);
      setError('No company specified.');
      return;
    }

    async function loadDossier() {
      setLoading(true);
      setError('');
      try {
        const [compData, onbData] = await Promise.all([
          api.getCompanyDetail(companyId),
          api.getCompanyOnboardingDossier(companyId).catch(() => null),
        ]);
        setCompany(compData);
        setOnboarding(onbData);
      } catch (err) {
        setError(err.message || 'Failed to load company dossier.');
      } finally {
        setLoading(false);
      }
    }

    loadDossier();
  }, [companyId]);

  const copyToClipboard = (text, fieldName) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedField(fieldName);
    setTimeout(() => setCopiedField(''), 2000);
  };

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  if (loading) {
    return (
      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '60px 20px', textAlign: 'center', color: '#64748b' }}>
        <div className="spinner" style={{ margin: '0 auto 16px auto' }} />
        <p style={{ fontSize: '14px', fontWeight: 500, margin: 0 }}>Loading company onboarding dossier...</p>
      </div>
    );
  }

  if (error || !company) {
    return (
      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', padding: '40px 24px', textAlign: 'center' }}>
        <div style={{ color: '#ef4444', fontSize: '18px', fontWeight: 700, marginBottom: '8px' }}>
          Failed to load company details
        </div>
        <p style={{ color: '#64748b', fontSize: '14px', marginBottom: '20px' }}>{error || 'Company not found.'}</p>
        <button
          onClick={onBack}
          style={{
            padding: '8px 18px',
            backgroundColor: '#0284c7',
            color: '#ffffff',
            borderRadius: '6px',
            border: 'none',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          ← Back to Live Companies
        </button>
      </div>
    );
  }

  const token = getAuthToken();
  const getDocDownloadUrl = (docType) => {
    if (!onboarding?.id) return '#';
    return api.getAdminDocumentUrl(onboarding.id, docType);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', animation: 'fadeIn 0.2s ease-out' }}>
      
      {/* ── Top Navigation & Back Button ──────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
        <button
          onClick={onBack}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            background: 'none',
            border: 'none',
            color: '#0284c7',
            fontSize: '14px',
            fontWeight: 600,
            cursor: 'pointer',
            padding: '6px 0',
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12" />
            <polyline points="12 19 5 12 12 5" />
          </svg>
          Back to Live Companies
        </button>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={() => onEditQuotas && onEditQuotas(company)}
            style={{
              padding: '8px 16px',
              backgroundColor: '#ffffff',
              color: '#0f172a',
              border: '1px solid #cbd5e1',
              borderRadius: '8px',
              fontWeight: 600,
              fontSize: '13px',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
            </svg>
            Edit Quotas
          </button>

          <button
            onClick={() => onToggleStatus && onToggleStatus(company)}
            style={{
              padding: '8px 16px',
              backgroundColor: company.status === 'active' ? '#ffffff' : '#f0fdf4',
              color: company.status === 'active' ? '#dc2626' : '#16a34a',
              border: `1px solid ${company.status === 'active' ? '#fca5a5' : '#bbf7d0'}`,
              borderRadius: '8px',
              fontWeight: 600,
              fontSize: '13px',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            {company.status === 'active' ? 'Suspend Company' : 'Activate Company'}
          </button>
        </div>
      </div>

      {/* ── Main Profile Header Card ──────────────────────────────────────── */}
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e2e8f0',
        padding: '24px 28px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '6px' }}>
              <h1 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#0f172a', letterSpacing: '-0.01em' }}>
                {company.name}
              </h1>
              <span style={{
                padding: '3px 10px',
                borderRadius: '12px',
                fontSize: '11px',
                fontWeight: 700,
                backgroundColor: company.status === 'active' ? '#dcfce7' : '#fee2e2',
                color: company.status === 'active' ? '#15803d' : '#b91c1c',
                border: `1px solid ${company.status === 'active' ? '#bbf7d0' : '#fca5a5'}`,
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
              }}>
                {company.status}
              </span>
              <span style={{
                padding: '3px 10px',
                borderRadius: '12px',
                fontSize: '11px',
                fontWeight: 600,
                backgroundColor: company.mfa_required_for_all ? '#e0f2fe' : '#f1f5f9',
                color: company.mfa_required_for_all ? '#0369a1' : '#64748b',
                border: `1px solid ${company.mfa_required_for_all ? '#bae6fd' : '#e2e8f0'}`,
              }}>
                {company.mfa_required_for_all ? 'MFA Mandated Platform-Wide' : 'MFA Optional'}
              </span>
            </div>

            <div style={{ fontSize: '13px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
              <div>
                Company Code: <strong style={{ color: '#0f172a', fontFamily: 'monospace' }}>{company.code}</strong>
              </div>
              <div>•</div>
              <div>
                GSTIN: <strong style={{ color: '#0f172a' }}>{company.gstin || onboarding?.gstin || '—'}</strong>
              </div>
              <div>•</div>
              <div>
                Onboarded: <strong>{new Date(company.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}</strong>
              </div>
            </div>
          </div>
        </div>

        {/* Live Quota & Resource Usage Grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '14px',
          marginTop: '24px',
          paddingTop: '20px',
          borderTop: '1px solid #f1f5f9',
        }}>
          <div style={{ backgroundColor: '#f8fafc', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Branches Provisioned
            </div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a', marginTop: '4px' }}>
              {company.branch_count} <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}>/ {company.max_branches ?? 5} max</span>
            </div>
          </div>

          <div style={{ backgroundColor: '#f8fafc', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Active User Accounts
            </div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a', marginTop: '4px' }}>
              {company.user_count} <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}>/ {company.max_users ?? 20} max</span>
            </div>
          </div>

          <div style={{ backgroundColor: '#f8fafc', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Encrypted Storage
            </div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a', marginTop: '4px' }}>
              {formatBytes(company.storage_used_bytes || 0)} <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}>/ {formatBytes(company.storage_limit_bytes || 5368709120)}</span>
            </div>
          </div>

          <div style={{ backgroundColor: '#f8fafc', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Monthly AI Budget (₹ / $)
              </span>
            </div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a', marginTop: '4px' }}>
              ₹{Number(company.ai_spent_inr !== undefined ? company.ai_spent_inr : (((company.ai_spent_cents || 0) / 100) * 85)).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}> / ₹{Number(company.monthly_ai_budget_inr || (((company.monthly_ai_budget_cents || 2500) / 100) * 85)).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px', fontWeight: 500 }}>
              ${((company.ai_spent_cents || 0) / 100).toFixed(2)} / ${((company.monthly_ai_budget_cents || 2500) / 100).toFixed(2)} USD
            </div>
          </div>
        </div>
      </div>

      {/* ── ONBOARDING DOSSIER DETAILS ────────────────────────────────────── */}
      {onboarding ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Banner: Verified Onboarding Submission */}
          <div style={{
            backgroundColor: '#f0fdf4',
            border: '1px solid #bbf7d0',
            borderRadius: '10px',
            padding: '16px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ backgroundColor: '#16a34a', color: '#ffffff', width: '24px', height: '24px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px', fontWeight: 700 }}>
                ✓
              </span>
              <div>
                <strong style={{ color: '#166534', fontSize: '14px' }}>Verified Enterprise Onboarding Application</strong>
                <div style={{ fontSize: '12px', color: '#15803d', marginTop: '2px' }}>
                  Submitted by {onboarding.contact_name} on {onboarding.submitted_at ? new Date(onboarding.submitted_at).toLocaleDateString() : '—'} and approved on {onboarding.reviewed_at ? new Date(onboarding.reviewed_at).toLocaleDateString() : '—'}
                </div>
              </div>
            </div>
            <div style={{ fontSize: '12px', color: '#166534', backgroundColor: '#dcfce7', padding: '4px 10px', borderRadius: '6px', fontWeight: 600 }}>
              Status: APPROVED &amp; ACTIVE
            </div>
          </div>

          {/* Grid Layout: 2 Columns for Sections A to G */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(440px, 1fr))', gap: '20px' }}>

            {/* SECTION A: Corporate Identity & Business Profile */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '22px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 16px 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ backgroundColor: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' }}>Section A</span>
                Corporate Identity &amp; Profile
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '13px' }}>
                <div>
                  <span style={{ color: '#64748b' }}>Legal Registered Name:</span>
                  <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.legal_company_name || onboarding.initial_company_name}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Trade Name (DBA):</span>
                  <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.trade_name || 'Same as Legal Name'}
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div>
                    <span style={{ color: '#64748b' }}>Business Entity Type:</span>
                    <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                      {onboarding.business_type || '—'}
                    </div>
                  </div>
                  <div>
                    <span style={{ color: '#64748b' }}>Year of Establishment:</span>
                    <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                      {onboarding.year_of_establishment || '—'}
                    </div>
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Official Website:</span>
                  <div style={{ marginTop: '2px' }}>
                    {onboarding.company_website ? (
                      <a href={onboarding.company_website.startsWith('http') ? onboarding.company_website : `https://${onboarding.company_website}`} target="_blank" rel="noopener noreferrer" style={{ color: '#0284c7', textDecoration: 'underline', fontWeight: 600 }}>
                        {onboarding.company_website} ↗
                      </a>
                    ) : '—'}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Business Description:</span>
                  <div style={{ backgroundColor: '#f8fafc', padding: '10px 12px', borderRadius: '6px', border: '1px solid #e2e8f0', marginTop: '4px', color: '#334155', lineHeight: '1.5', whiteSpace: 'pre-wrap' }}>
                    {onboarding.business_description || 'No description provided.'}
                  </div>
                </div>
              </div>
            </div>

            {/* SECTION B: Statutory Tax & Compliance Identifiers */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '22px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 16px 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ backgroundColor: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' }}>Section B</span>
                Tax &amp; Regulatory Identifiers (India)
              </h3>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '14px', fontSize: '13px' }}>
                <div>
                  <span style={{ color: '#64748b' }}>Permanent Account Number (PAN):</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '2px' }}>
                    <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '14px', color: '#0f172a' }}>
                      {onboarding.pan_number || '—'}
                    </span>
                    {onboarding.pan_number && (
                      <button
                        onClick={() => copyToClipboard(onboarding.pan_number, 'pan')}
                        style={{ background: 'none', border: 'none', color: copiedField === 'pan' ? '#16a34a' : '#0284c7', fontSize: '11px', cursor: 'pointer', fontWeight: 600 }}
                      >
                        {copiedField === 'pan' ? '✓ Copied' : 'Copy'}
                      </button>
                    )}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>GSTIN &amp; Registration Type:</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '2px' }}>
                    <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '14px', color: '#0f172a' }}>
                      {onboarding.gstin || '—'}
                    </span>
                    {onboarding.gstin && (
                      <button
                        onClick={() => copyToClipboard(onboarding.gstin, 'gstin')}
                        style={{ background: 'none', border: 'none', color: copiedField === 'gstin' ? '#16a34a' : '#0284c7', fontSize: '11px', cursor: 'pointer', fontWeight: 600 }}
                      >
                        {copiedField === 'gstin' ? '✓ Copied' : 'Copy'}
                      </button>
                    )}
                  </div>
                  {onboarding.gst_type && <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>Type: {onboarding.gst_type}</div>}
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Corporate Identification (CIN):</span>
                  <div style={{ fontFamily: 'monospace', fontWeight: 700, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.cin || '—'}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>LLPIN (if applicable):</span>
                  <div style={{ fontFamily: 'monospace', fontWeight: 700, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.llpin || '—'}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>MSME / Udyam Number:</span>
                  <div style={{ fontFamily: 'monospace', fontWeight: 700, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.udyam_number || '—'}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Tax Deduction Number (TAN):</span>
                  <div style={{ fontFamily: 'monospace', fontWeight: 700, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.tan || '—'}
                  </div>
                </div>
              </div>
            </div>

            {/* SECTION C: Registered Corporate Office Address */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '22px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 16px 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ backgroundColor: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' }}>Section C</span>
                Registered Corporate Office
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px' }}>
                <div>
                  <span style={{ color: '#64748b' }}>Street Address:</span>
                  <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                    {[onboarding.address_line1, onboarding.address_line2].filter(Boolean).join(', ') || '—'}
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginTop: '6px' }}>
                  <div>
                    <span style={{ color: '#64748b' }}>City:</span>
                    <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>{onboarding.city || '—'}</div>
                  </div>
                  <div>
                    <span style={{ color: '#64748b' }}>District:</span>
                    <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>{onboarding.district || '—'}</div>
                  </div>
                  <div>
                    <span style={{ color: '#64748b' }}>State:</span>
                    <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>{onboarding.state || '—'}</div>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', marginTop: '6px' }}>
                  <div>
                    <span style={{ color: '#64748b' }}>Postal PIN Code:</span>
                    <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px', fontFamily: 'monospace' }}>{onboarding.pincode || '—'}</div>
                  </div>
                  <div>
                    <span style={{ color: '#64748b' }}>Country:</span>
                    <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>{onboarding.country || 'India'}</div>
                  </div>
                </div>
              </div>
            </div>

            {/* SECTION D: Authorized Representative & Signatory */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '22px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 16px 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ backgroundColor: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' }}>Section D</span>
                Authorized Representative / Signatory
              </h3>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', fontSize: '13px' }}>
                <div>
                  <span style={{ color: '#64748b' }}>Representative Name:</span>
                  <div style={{ fontWeight: 700, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.auth_contact_name || onboarding.contact_name || '—'}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Designation:</span>
                  <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.auth_contact_designation || 'Signatory / Director'}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Corporate Email:</span>
                  <div style={{ marginTop: '2px' }}>
                    <a href={`mailto:${onboarding.auth_contact_email || onboarding.contact_email}`} style={{ color: '#0284c7', textDecoration: 'none', fontWeight: 600 }}>
                      {onboarding.auth_contact_email || onboarding.contact_email}
                    </a>
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Mobile Number:</span>
                  <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.auth_contact_mobile || '—'}
                  </div>
                </div>

                {onboarding.auth_contact_alternate_mobile && (
                  <div>
                    <span style={{ color: '#64748b' }}>Alternate Phone:</span>
                    <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                      {onboarding.auth_contact_alternate_mobile}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* SECTION E: Branch Hierarchy & Tenancy Structure */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '22px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 16px 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ backgroundColor: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' }}>Section E</span>
                Tenancy &amp; Corporate Branches
              </h3>

              <div style={{ fontSize: '13px' }}>
                <div style={{ marginBottom: '10px', color: '#64748b' }}>
                  Branch Multi-tenancy Mode: <strong style={{ color: '#0f172a' }}>{onboarding.has_multiple_branches ? 'Multi-Branch Enterprise' : 'Single Central Office'}</strong>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', backgroundColor: '#f0fdf4', borderRadius: '6px', border: '1px solid #bbf7d0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '16px' }}>🏢</span>
                      <strong>Headquarters</strong>
                      <span style={{ fontSize: '11px', color: '#16a34a', backgroundColor: '#dcfce7', padding: '1px 6px', borderRadius: '4px', fontWeight: 700 }}>PRIMARY</span>
                    </div>
                    <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#166534' }}>HQ</span>
                  </div>

                  {(onboarding.branch_details || []).map((b, idx) => {
                    const bName = typeof b === 'object' ? b.name : b;
                    if (!bName || bName.toLowerCase() === 'headquarters') return null;
                    return (
                      <div key={idx} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '16px' }}>🏬</span>
                          <span>{bName}</span>
                        </div>
                        <span style={{ fontFamily: 'monospace', fontSize: '11px', color: '#64748b' }}>REGIONAL BRANCH</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* SECTION F: First Company Administrator Account */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '22px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 16px 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ backgroundColor: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' }}>Section F</span>
                First Company Administrator (Root)
              </h3>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', fontSize: '13px' }}>
                <div>
                  <span style={{ color: '#64748b' }}>Administrator Name:</span>
                  <div style={{ fontWeight: 700, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.admin_name || onboarding.contact_name || '—'}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Corporate Login Email:</span>
                  <div style={{ marginTop: '2px' }}>
                    <strong style={{ color: '#0f172a' }}>{onboarding.admin_email || onboarding.contact_email}</strong>
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Designation:</span>
                  <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.admin_designation || 'Company Administrator'}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Mobile:</span>
                  <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '2px' }}>
                    {onboarding.admin_mobile || '—'}
                  </div>
                </div>

                <div style={{ gridColumn: '1 / -1' }}>
                  <div style={{ padding: '8px 12px', backgroundColor: '#f1f5f9', borderRadius: '6px', fontSize: '12px', color: '#475569' }}>
                    Provisioned System Role: <strong>GLOBAL_ADMIN</strong> (Full executive authority over company branches, users, and compliance).
                  </div>
                </div>
              </div>
            </div>

            {/* SECTION G: Operational Profile & System Settings */}
            <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '22px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)', gridColumn: '1 / -1' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 16px 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ backgroundColor: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' }}>Section G</span>
                Operational Profile &amp; Localization
              </h3>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', fontSize: '13px' }}>
                <div>
                  <span style={{ color: '#64748b' }}>Expected Monthly Volume:</span>
                  <div style={{ fontWeight: 700, color: '#0f172a', marginTop: '4px' }}>
                    {onboarding.expected_monthly_volume || 'Standard'}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Timezone &amp; Currency:</span>
                  <div style={{ fontWeight: 600, color: '#0f172a', marginTop: '4px' }}>
                    {onboarding.timezone || 'Asia/Kolkata'} ({onboarding.currency || 'INR'})
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Primary Document Types:</span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
                    {(onboarding.primary_document_types || ['Invoices']).map((t, idx) => (
                      <span key={idx} style={{ backgroundColor: '#f1f5f9', color: '#334155', padding: '3px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: 600 }}>
                        {t}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <span style={{ color: '#64748b' }}>Working Languages:</span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '6px' }}>
                    {(onboarding.languages || ['English']).map((l, idx) => (
                      <span key={idx} style={{ backgroundColor: '#f1f5f9', color: '#334155', padding: '3px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: 600 }}>
                        {l}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>

          </div>

          {/* ── SECTION H: Uploaded Compliance & Verification Documents ────── */}
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 6px 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ backgroundColor: '#eff6ff', color: '#2563eb', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' }}>Compliance Files</span>
              Verification Documents &amp; Certificates
            </h3>
            <p style={{ margin: '0 0 20px 0', color: '#64748b', fontSize: '13px' }}>
              Statutory documents submitted during registration and verified by platform administration.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '14px' }}>
              {[
                { type: 'pan_card', label: 'Company PAN Card', icon: '📄' },
                { type: 'gst_certificate', label: 'GST Registration Certificate', icon: '📜' },
                { type: 'incorporation_certificate', label: 'Certificate of Incorporation', icon: '🏛️' },
                { type: 'address_proof', label: 'Registered Office Address Proof', icon: '📍' },
              ].map(doc => {
                const meta = onboarding.uploaded_documents?.[doc.type];
                return (
                  <div
                    key={doc.type}
                    style={{
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      padding: '16px',
                      backgroundColor: meta ? '#ffffff' : '#f8fafc',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      gap: '12px',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                        <span style={{ fontSize: '18px' }}>{doc.icon}</span>
                        <strong style={{ fontSize: '13px', color: '#0f172a' }}>{doc.label}</strong>
                      </div>
                      {meta ? (
                        <div style={{ fontSize: '11px', color: '#64748b', wordBreak: 'break-all' }}>
                          <div>File: <strong>{meta.filename}</strong></div>
                          <div style={{ marginTop: '2px' }}>Size: {formatBytes(meta.file_size)} • Uploaded: {new Date(meta.uploaded_at).toLocaleDateString()}</div>
                        </div>
                      ) : (
                        <div style={{ fontSize: '12px', color: '#94a3b8', fontStyle: 'italic' }}>
                          No document uploaded
                        </div>
                      )}
                    </div>

                    {meta && (
                      <a
                        href={getDocDownloadUrl(doc.type)}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '6px',
                          padding: '7px 12px',
                          backgroundColor: '#f1f5f9',
                          color: '#0f172a',
                          borderRadius: '6px',
                          textDecoration: 'none',
                          fontSize: '12px',
                          fontWeight: 600,
                          border: '1px solid #cbd5e1',
                          transition: 'background 0.15s',
                        }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                        Download Document
                      </a>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── SECTION I: Review History & Approval Trail ──────────────────── */}
          {onboarding.review_history && onboarding.review_history.length > 0 && (
            <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
              <h3 style={{ fontSize: '15px', fontWeight: 700, margin: '0 0 14px 0', color: '#0f172a' }}>
                Onboarding Audit &amp; Approval History
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {onboarding.review_history.map((h, idx) => (
                  <div key={idx} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', fontSize: '13px', padding: '10px 14px', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <span style={{ fontSize: '16px', marginTop: '1px' }}>
                      {h.action === 'approved' ? '✅' : h.action === 'changes_requested' ? '⚠️' : 'ℹ️'}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <strong style={{ color: '#0f172a', textTransform: 'capitalize' }}>{h.action.replace('_', ' ')}</strong>
                        <span style={{ fontSize: '11px', color: '#64748b' }}>
                          {h.timestamp ? new Date(h.timestamp).toLocaleString() : ''}
                        </span>
                      </div>
                      {h.admin_name && <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>Reviewer: {h.admin_name}</div>}
                      {h.note && <div style={{ fontSize: '12px', color: '#334155', marginTop: '4px', whiteSpace: 'pre-wrap' }}>{h.note}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      ) : (
        <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '36px', textAlign: 'center', color: '#64748b' }}>
          <span style={{ fontSize: '32px', display: 'block', marginBottom: '8px' }}>📋</span>
          <h3 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 4px 0' }}>Direct Workspace Provisioning</h3>
          <p style={{ fontSize: '13px', margin: 0 }}>This company was provisioned directly by Platform Administration without an external onboarding registration link.</p>
        </div>
      )}

    </div>
  );
}
