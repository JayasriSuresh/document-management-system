import { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { api } from '../api';

const INDIAN_STATES = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
  'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka',
  'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram',
  'Nagaland', 'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu',
  'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
  'Andaman and Nicobar Islands', 'Chandigarh', 'Dadra and Nagar Haveli and Daman and Diu',
  'Delhi', 'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry',
];

const BUSINESS_TYPES = [
  'Private Limited Company (Pvt Ltd)',
  'Limited Liability Partnership (LLP)',
  'Partnership Firm',
  'Sole Proprietorship',
  'Public Limited Company (Ltd)',
  'One Person Company (OPC)',
  'Trust / Society / Section 8',
  'Other',
];

const GST_REGISTRATION_TYPES = [
  'Regular',
  'Composition',
  'SEZ Unit / Developer',
  'Input Service Distributor (ISD)',
  'Consumer / Unregistered',
  'Not Applicable',
];

const MONTHLY_VOLUMES = [
  'Less than 100 documents',
  '100 - 500 documents',
  '500 - 2,000 documents',
  '2,000 - 10,000 documents',
  '10,000+ documents',
];

const COMMON_DOC_TYPES = [
  'Invoices',
  'Purchase Orders',
  'Contracts & Agreements',
  'Bills of Lading & Challans',
  'Receipts & Vouchers',
  'Tax & Compliance Filings',
  'Identity & Employee Documents',
];

const COMMON_LANGUAGES = [
  'English', 'Hindi', 'Tamil', 'Telugu', 'Kannada', 'Malayalam', 'Marathi', 'Bengali', 'Gujarati', 'Punjabi'
];

export default function CompanyOnboardingPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [loading, setLoading] = useState(true);
  const [initError, setInitError] = useState('');
  const [onboarding, setOnboarding] = useState(null);

  // Form State
  const [form, setForm] = useState({
    // Section A
    legal_company_name: '',
    trade_name: '',
    business_type: 'Private Limited Company (Pvt Ltd)',
    business_description: '',
    year_of_establishment: '',
    company_website: '',
    // Section B
    pan_number: '',
    gstin: '',
    gst_type: 'Regular',
    cin: '',
    llpin: '',
    udyam_number: '',
    tan: '',
    // Section C
    address_line1: '',
    address_line2: '',
    city: '',
    state: 'Tamil Nadu',
    district: '',
    pincode: '',
    country: 'India',
    // Section D
    auth_contact_name: '',
    auth_contact_designation: '',
    auth_contact_email: '',
    auth_contact_mobile: '',
    auth_contact_alternate_mobile: '',
    // Section E
    has_multiple_branches: false,
    branch_input: '',
    branches_list: [],
    // Section F
    admin_name: '',
    admin_email: '',
    admin_password: '',
    confirm_password: '',
    admin_mobile: '',
    admin_designation: 'Company Administrator',
    // Section G
    primary_document_types: ['Invoices', 'Purchase Orders'],
    expected_monthly_volume: '500 - 2,000 documents',
    languages: ['English'],
    timezone: 'Asia/Kolkata',
    currency: 'INR',
  });

  // Upload state
  const [uploadingDoc, setUploadingDoc] = useState(null);
  const [uploadError, setUploadError] = useState('');
  const [uploadedDocs, setUploadedDocs] = useState({});

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [submitSuccess, setSubmitSuccess] = useState(false);

  // Active step / section for navigation
  const [activeStep, setActiveStep] = useState('all');

  useEffect(() => {
    if (!token) {
      setInitError('No onboarding token provided in URL. Please check the invitation email link.');
      setLoading(false);
      return;
    }

    async function fetchForm() {
      try {
        const data = await api.getOnboarding(token);
        setOnboarding(data);
        setUploadedDocs(data.uploaded_documents || {});

        // Pre-fill form from data
        const branches = (data.branch_details || []).map(b => (typeof b === 'object' ? b.name : b));
        setForm({
          legal_company_name: data.legal_company_name || data.initial_company_name || '',
          trade_name: data.trade_name || '',
          business_type: data.business_type || 'Private Limited Company (Pvt Ltd)',
          business_description: data.business_description || '',
          year_of_establishment: data.year_of_establishment || '',
          company_website: data.company_website || '',
          pan_number: data.pan_number || '',
          gstin: data.gstin || '',
          gst_type: data.gst_type || 'Regular',
          cin: data.cin || '',
          llpin: data.llpin || '',
          udyam_number: data.udyam_number || '',
          tan: data.tan || '',
          address_line1: data.address_line1 || '',
          address_line2: data.address_line2 || '',
          city: data.city || '',
          state: data.state || 'Tamil Nadu',
          district: data.district || '',
          pincode: data.pincode || '',
          country: data.country || 'India',
          auth_contact_name: data.auth_contact_name || data.contact_name || '',
          auth_contact_designation: data.auth_contact_designation || '',
          auth_contact_email: data.auth_contact_email || data.contact_email || '',
          auth_contact_mobile: data.auth_contact_mobile || '',
          auth_contact_alternate_mobile: data.auth_contact_alternate_mobile || '',
          has_multiple_branches: Boolean(data.has_multiple_branches),
          branch_input: '',
          branches_list: branches,
          admin_name: data.admin_name || data.contact_name || '',
          admin_email: data.admin_email || data.contact_email || '',
          admin_password: '',
          confirm_password: '',
          admin_mobile: data.admin_mobile || '',
          admin_designation: data.admin_designation || 'Company Administrator',
          primary_document_types: data.primary_document_types?.length ? data.primary_document_types : ['Invoices', 'Purchase Orders'],
          expected_monthly_volume: data.expected_monthly_volume || '500 - 2,000 documents',
          languages: data.languages?.length ? data.languages : ['English'],
          timezone: data.timezone || 'Asia/Kolkata',
          currency: data.currency || 'INR',
        });
      } catch (err) {
        setInitError(err.message || 'Failed to load onboarding application. The link may be expired.');
      } finally {
        setLoading(false);
      }
    }

    fetchForm();
  }, [token]);

  // Handle Document Upload
  const handleFileUpload = async (documentType, file) => {
    if (!file) return;
    setUploadingDoc(documentType);
    setUploadError('');
    try {
      const res = await api.uploadOnboardingDocument(token, documentType, file);
      setUploadedDocs(res.uploaded_documents);
    } catch (err) {
      setUploadError(`Failed to upload ${documentType}: ${err.message}`);
    } finally {
      setUploadingDoc(null);
    }
  };

  // Add Branch
  const handleAddBranch = () => {
    if (!form.branch_input.trim()) return;
    setForm(prev => ({
      ...prev,
      branches_list: [...prev.branches_list, prev.branch_input.trim()],
      branch_input: '',
    }));
  };

  const handleRemoveBranch = (index) => {
    setForm(prev => ({
      ...prev,
      branches_list: prev.branches_list.filter((_, i) => i !== index),
    }));
  };

  // Toggle multi-select tags (doc types, languages)
  const toggleArrayItem = (fieldName, item) => {
    setForm(prev => {
      const list = prev[fieldName] || [];
      if (list.includes(item)) {
        return { ...prev, [fieldName]: list.filter(x => x !== item) };
      } else {
        return { ...prev, [fieldName]: [...list, item] };
      }
    });
  };

  // Submit complete onboarding
  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitError('');

    // Check required documents
    if (!uploadedDocs.pan_document) {
      setSubmitError('PAN Card / Document upload is required before submitting.');
      window.scrollTo({ top: 800, behavior: 'smooth' });
      return;
    }

    // Check password if required
    if (!onboarding.has_admin_password && !form.admin_password) {
      setSubmitError('First company administrator password is required.');
      return;
    }
    if (form.admin_password && form.admin_password.length < 8) {
      setSubmitError('Administrator password must be at least 8 characters long.');
      return;
    }
    if (form.admin_password && form.admin_password !== form.confirm_password) {
      setSubmitError('Admin password and confirmation password do not match.');
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        legal_company_name: form.legal_company_name.trim(),
        trade_name: form.trade_name.trim() || null,
        business_type: form.business_type,
        business_description: form.business_description.trim() || null,
        year_of_establishment: form.year_of_establishment.trim() || null,
        company_website: form.company_website.trim() || null,
        pan_number: form.pan_number.trim(),
        gstin: form.gstin.trim() || null,
        gst_type: form.gst_type || null,
        cin: form.cin.trim() || null,
        llpin: form.llpin.trim() || null,
        udyam_number: form.udyam_number.trim() || null,
        tan: form.tan.trim() || null,
        address_line1: form.address_line1.trim(),
        address_line2: form.address_line2.trim() || null,
        city: form.city.trim(),
        state: form.state,
        district: form.district.trim(),
        pincode: form.pincode.trim(),
        country: form.country || 'India',
        auth_contact_name: form.auth_contact_name.trim(),
        auth_contact_designation: form.auth_contact_designation.trim(),
        auth_contact_email: form.auth_contact_email.trim(),
        auth_contact_mobile: form.auth_contact_mobile.trim(),
        auth_contact_alternate_mobile: form.auth_contact_alternate_mobile.trim() || null,
        has_multiple_branches: form.has_multiple_branches,
        branch_details: form.has_multiple_branches ? form.branches_list.map(b => ({ name: b })) : [],
        admin_name: form.admin_name.trim(),
        admin_email: form.admin_email.trim(),
        admin_password: form.admin_password || null,
        confirm_password: form.confirm_password || null,
        admin_mobile: form.admin_mobile.trim(),
        admin_designation: form.admin_designation.trim(),
        primary_document_types: form.primary_document_types,
        expected_monthly_volume: form.expected_monthly_volume,
        languages: form.languages,
        timezone: form.timezone,
        currency: form.currency,
      };

      await api.submitOnboarding(token, payload);
      setSubmitSuccess(true);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      setSubmitError(err.message || 'Submission failed. Please check the fields and try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // ── Loading & Errors ────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8fafc' }}>
        <div style={{ textAlign: 'center', color: '#64748b' }}>
          <div className="spinner" style={{ margin: '0 auto 16px auto' }} />
          <p style={{ fontSize: '14px', fontWeight: 500 }}>Loading company onboarding application...</p>
        </div>
      </div>
    );
  }

  if (initError) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8fafc', padding: '20px' }}>
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '36px', maxWidth: '480px', width: '100%', textAlign: 'center', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
          <div style={{ width: '50px', height: '50px', borderRadius: '50%', backgroundColor: '#fef2f2', color: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px auto', fontSize: '24px' }}>
            !
          </div>
          <h2 style={{ fontSize: '18px', fontWeight: 700, margin: '0 0 8px 0', color: '#0f172a' }}>Application Not Found</h2>
          <p style={{ fontSize: '13px', color: '#64748b', margin: '0 0 24px 0' }}>{initError}</p>
          <Link to="/login" style={{ padding: '10px 20px', backgroundColor: '#0284c7', color: '#ffffff', borderRadius: '6px', textDecoration: 'none', fontSize: '13px', fontWeight: 600 }}>
            Go to DMS Login
          </Link>
        </div>
      </div>
    );
  }

  // ── Case: Application Approved ──────────────────────────────────────────────
  if (onboarding?.status === 'approved') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8fafc', padding: '20px' }}>
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '40px', maxWidth: '520px', width: '100%', textAlign: 'center', border: '1px solid #bbf7d0', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.05)' }}>
          <div style={{ width: '60px', height: '60px', borderRadius: '50%', backgroundColor: '#f0fdf4', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px auto', fontSize: '32px' }}>
            ✓
          </div>
          <h2 style={{ fontSize: '22px', fontWeight: 700, margin: '0 0 8px 0', color: '#0f172a' }}>Company Approved &amp; Live!</h2>
          <p style={{ fontSize: '14px', color: '#64748b', margin: '0 0 20px 0', lineHeight: '1.6' }}>
            The onboarding application for <strong>{onboarding.legal_company_name || onboarding.initial_company_name}</strong> has been officially approved by the Master Administrator.
          </p>
          <div style={{ backgroundColor: '#f8fafc', padding: '14px', borderRadius: '8px', border: '1px solid #e2e8f0', marginBottom: '24px', fontSize: '13px', textAlign: 'left' }}>
            <div><strong>Administrator Email:</strong> {onboarding.admin_email}</div>
            <div style={{ marginTop: '4px', color: '#16a34a', fontWeight: 600 }}>Role: Global Company Administrator</div>
          </div>
          <Link
            to="/company/login"
            style={{
              display: 'inline-block',
              padding: '12px 28px',
              backgroundColor: '#16a34a',
              color: '#ffffff',
              borderRadius: '8px',
              textDecoration: 'none',
              fontSize: '14px',
              fontWeight: 600,
              boxShadow: '0 2px 8px rgba(22, 163, 74, 0.3)',
            }}
          >
            Sign In to Company Portal
          </Link>
        </div>
      </div>
    );
  }

  // ── Case: Application Submitted (Under Review) ──────────────────────────────
  if (submitSuccess || onboarding?.status === 'submitted') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8fafc', padding: '20px' }}>
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '40px', maxWidth: '540px', width: '100%', textAlign: 'center', border: '1px solid #93c5fd', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.05)' }}>
          <div style={{ width: '60px', height: '60px', borderRadius: '50%', backgroundColor: '#eff6ff', color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px auto', fontSize: '28px' }}>
            ⏳
          </div>
          <h2 style={{ fontSize: '22px', fontWeight: 700, margin: '0 0 8px 0', color: '#0f172a' }}>Application Under Review</h2>
          <p style={{ fontSize: '14px', color: '#64748b', margin: '0 0 20px 0', lineHeight: '1.6' }}>
            Thank you! Your company onboarding form and compliance documents for <strong>{onboarding.legal_company_name || onboarding.initial_company_name}</strong> have been submitted successfully.
          </p>
          <div style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '16px', fontSize: '13px', color: '#334155', textAlign: 'left', marginBottom: '24px' }}>
            <div style={{ fontWeight: 600, marginBottom: '6px' }}>What happens next?</div>
            <ul style={{ margin: 0, paddingLeft: '18px', lineHeight: '1.6' }}>
              <li>Our Master Administration team will inspect your legal details, GST/PAN information, and uploaded documents.</li>
              <li>If any corrections are needed, you will receive an email with instructions to update the form.</li>
              <li>Once verified and approved, your company workspace and administrator account will be provisioned immediately.</li>
            </ul>
          </div>
          <p style={{ fontSize: '12px', color: '#94a3b8' }}>
            You may bookmark this page to check your application status at any time.
          </p>
        </div>
      </div>
    );
  }

  // ── Case: Application Rejected ──────────────────────────────────────────────
  if (onboarding?.status === 'rejected') {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8fafc', padding: '20px' }}>
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '40px', maxWidth: '520px', width: '100%', textAlign: 'center', border: '1px solid #fca5a5', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.05)' }}>
          <div style={{ width: '60px', height: '60px', borderRadius: '50%', backgroundColor: '#fef2f2', color: '#dc2626', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px auto', fontSize: '28px' }}>
            ✕
          </div>
          <h2 style={{ fontSize: '22px', fontWeight: 700, margin: '0 0 8px 0', color: '#0f172a' }}>Application Rejected</h2>
          <p style={{ fontSize: '14px', color: '#64748b', margin: '0 0 16px 0' }}>
            The onboarding application for <strong>{onboarding.legal_company_name || onboarding.initial_company_name}</strong> was rejected by the Master Administrator.
          </p>
          {onboarding.review_comments && (
            <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', padding: '14px', textAlign: 'left', fontSize: '13px', color: '#991b1b', marginBottom: '24px' }}>
              <strong>Reason:</strong> {onboarding.review_comments}
            </div>
          )}
          <p style={{ fontSize: '12px', color: '#94a3b8' }}>
            Please contact the administrator who initiated your invitation for further information.
          </p>
        </div>
      </div>
    );
  }

  // ── ACTIVE EDIT/RESUBMIT FORM (Pending Submission OR Changes Requested) ──────
  const isChangesRequested = onboarding?.status === 'changes_requested';

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f1f5f9', color: '#0f172a', fontFamily: 'Inter, sans-serif', paddingBottom: '60px' }}>
      
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header style={{ backgroundColor: '#ffffff', borderBottom: '1px solid #e2e8f0', padding: '18px 24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
        <div style={{ maxWidth: '960px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ backgroundColor: '#ef233c', color: '#ffffff', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 800 }}>DMS</span>
            <span style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>Company Onboarding Registration</span>
          </div>
          <div style={{ fontSize: '12px', color: '#64748b' }}>
            Initiated for: <strong>{onboarding.initial_company_name}</strong>
          </div>
        </div>
      </header>

      {/* ── Main Container ────────────────────────────────────────────────── */}
      <main style={{ maxWidth: '960px', margin: '32px auto 0 auto', padding: '0 20px' }}>
        
        {/* Review Feedback Alert if changes were requested */}
        {isChangesRequested && (
          <div style={{
            backgroundColor: '#fffbeb',
            border: '2px solid #f59e0b',
            borderRadius: '10px',
            padding: '20px 24px',
            marginBottom: '28px',
            boxShadow: '0 4px 6px -1px rgba(245, 158, 11, 0.1)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#92400e', fontWeight: 800, fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '8px' }}>
              <span style={{ fontSize: '18px' }}>⚠️</span> Changes Requested by Master Administrator
            </div>
            <p style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#78350f', lineHeight: '1.5' }}>
              The reviewer has evaluated your previous submission and requested the following modifications:
            </p>
            <div style={{ backgroundColor: '#ffffff', border: '1px solid #fcd34d', borderRadius: '6px', padding: '14px 18px', color: '#92400e', fontSize: '14px', fontWeight: 600, whiteSpace: 'pre-wrap', marginBottom: '12px' }}>
              "{onboarding.review_comments}"
            </div>
            <p style={{ margin: 0, fontSize: '13px', color: '#b45309' }}>
              ✓ All previously submitted details and uploaded documents are retained below. Please edit the required items and click <strong>Resubmit Application</strong> at the bottom.
            </p>
          </div>
        )}

        {/* Global Error Banner */}
        {submitError && (
          <div style={{ backgroundColor: '#fef2f2', border: '1px solid #fca5a5', borderRadius: '8px', padding: '14px 18px', color: '#b91c1c', fontSize: '14px', fontWeight: 500, marginBottom: '24px' }}>
            ✕ {submitError}
          </div>
        )}

        <form onSubmit={handleSubmit}>

          {/* ═════════════════════════════════════════════════════════════════
              SECTION A: Company Details
             ═════════════════════════════════════════════════════════════════ */}
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '28px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <h3 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
              Section A – Company Details
            </h3>
            <p style={{ margin: '0 0 20px 0', color: '#64748b', fontSize: '13px' }}>
              Official registered details of the corporate entity.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '18px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Legal Company Name <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="Official registered name"
                  value={form.legal_company_name}
                  onChange={(e) => setForm({ ...form, legal_company_name: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Trade Name (if different)
                </label>
                <input
                  type="text"
                  placeholder="Name used for business / brand"
                  value={form.trade_name}
                  onChange={(e) => setForm({ ...form, trade_name: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Business Type <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <select
                  value={form.business_type}
                  onChange={(e) => setForm({ ...form, business_type: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                >
                  {BUSINESS_TYPES.map(bt => <option key={bt} value={bt}>{bt}</option>)}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Year of Establishment
                </label>
                <input
                  type="text"
                  placeholder="e.g. 2018"
                  value={form.year_of_establishment}
                  onChange={(e) => setForm({ ...form, year_of_establishment: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Company Website
                </label>
                <input
                  type="url"
                  placeholder="https://example.com"
                  value={form.company_website}
                  onChange={(e) => setForm({ ...form, company_website: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Business Description
                </label>
                <textarea
                  rows={2}
                  placeholder="Brief description of the company's activities..."
                  value={form.business_description}
                  onChange={(e) => setForm({ ...form, business_description: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>
            </div>
          </div>

          {/* ═════════════════════════════════════════════════════════════════
              SECTION B: Indian business and tax details
             ═════════════════════════════════════════════════════════════════ */}
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '28px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <h3 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
              Section B – Indian Business &amp; Tax Details
            </h3>
            <p style={{ margin: '0 0 20px 0', color: '#64748b', fontSize: '13px' }}>
              Statutory tax identifiers and registration certificates.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '18px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  PAN Number <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  maxLength={10}
                  placeholder="e.g. AABCA1234F"
                  value={form.pan_number}
                  onChange={(e) => setForm({ ...form, pan_number: e.target.value.toUpperCase() })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', fontFamily: 'monospace', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  GSTIN (If GST Registered)
                </label>
                <input
                  type="text"
                  maxLength={15}
                  placeholder="e.g. 33AABCA1234F1Z5"
                  value={form.gstin}
                  onChange={(e) => setForm({ ...form, gstin: e.target.value.toUpperCase() })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', fontFamily: 'monospace', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  GST Registration Type
                </label>
                <select
                  value={form.gst_type}
                  onChange={(e) => setForm({ ...form, gst_type: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                >
                  {GST_REGISTRATION_TYPES.map(gt => <option key={gt} value={gt}>{gt}</option>)}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  CIN (Corporate Identification Number)
                </label>
                <input
                  type="text"
                  maxLength={21}
                  placeholder="e.g. U72900TN2021PTC123456"
                  value={form.cin}
                  onChange={(e) => setForm({ ...form, cin: e.target.value.toUpperCase() })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', fontFamily: 'monospace', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  LLPIN (If applicable)
                </label>
                <input
                  type="text"
                  placeholder="e.g. AAA-1234"
                  value={form.llpin}
                  onChange={(e) => setForm({ ...form, llpin: e.target.value.toUpperCase() })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', fontFamily: 'monospace', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Udyam Registration (MSME - Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. UDYAM-TN-01-0012345"
                  value={form.udyam_number}
                  onChange={(e) => setForm({ ...form, udyam_number: e.target.value.toUpperCase() })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', fontFamily: 'monospace', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  TAN (Tax Deduction Number - If applicable)
                </label>
                <input
                  type="text"
                  maxLength={10}
                  placeholder="e.g. CHNA12345F"
                  value={form.tan}
                  onChange={(e) => setForm({ ...form, tan: e.target.value.toUpperCase() })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', fontFamily: 'monospace', boxSizing: 'border-box' }}
                />
              </div>
            </div>
          </div>

          {/* ═════════════════════════════════════════════════════════════════
              SECTION C: Registered office and business address
             ═════════════════════════════════════════════════════════════════ */}
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '28px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <h3 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
              Section C – Registered Office &amp; Business Address
            </h3>
            <p style={{ margin: '0 0 20px 0', color: '#64748b', fontSize: '13px' }}>
              Physical address of the principal place of business.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '18px' }}>
              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Address Line 1 <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="Building, flat/office number, street"
                  value={form.address_line1}
                  onChange={(e) => setForm({ ...form, address_line1: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div style={{ gridColumn: '1 / -1' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Address Line 2
                </label>
                <input
                  type="text"
                  placeholder="Area, locality, landmark"
                  value={form.address_line2}
                  onChange={(e) => setForm({ ...form, address_line2: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  City <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="City"
                  value={form.city}
                  onChange={(e) => setForm({ ...form, city: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  State <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <select
                  value={form.state}
                  onChange={(e) => setForm({ ...form, state: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                >
                  {INDIAN_STATES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  District <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="District"
                  value={form.district}
                  onChange={(e) => setForm({ ...form, district: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  PIN Code <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  maxLength={6}
                  placeholder="6-digit postal PIN"
                  value={form.pincode}
                  onChange={(e) => setForm({ ...form, pincode: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', fontFamily: 'monospace', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Country
                </label>
                <input
                  type="text"
                  disabled
                  value="India"
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '14px', backgroundColor: '#f8fafc', color: '#64748b', boxSizing: 'border-box' }}
                />
              </div>
            </div>
          </div>

          {/* ═════════════════════════════════════════════════════════════════
              SECTION D: Authorized contact person
             ═════════════════════════════════════════════════════════════════ */}
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '28px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <h3 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
              Section D – Authorized Contact Person
            </h3>
            <p style={{ margin: '0 0 20px 0', color: '#64748b', fontSize: '13px' }}>
              Designated contact for corporate inquiries and system authorization.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '18px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Full Name <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="Authorized person name"
                  value={form.auth_contact_name}
                  onChange={(e) => setForm({ ...form, auth_contact_name: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Designation <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Director, Owner, Managing Partner"
                  value={form.auth_contact_designation}
                  onChange={(e) => setForm({ ...form, auth_contact_designation: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Official Email <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="email"
                  required
                  placeholder="primary@company.com"
                  value={form.auth_contact_email}
                  onChange={(e) => setForm({ ...form, auth_contact_email: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Mobile Number (+91) <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="+91 9876543210"
                  value={form.auth_contact_mobile}
                  onChange={(e) => setForm({ ...form, auth_contact_mobile: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Alternate Mobile (Optional)
                </label>
                <input
                  type="text"
                  placeholder="+91 9876500000"
                  value={form.auth_contact_alternate_mobile}
                  onChange={(e) => setForm({ ...form, auth_contact_alternate_mobile: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>
            </div>
          </div>

          {/* ═════════════════════════════════════════════════════════════════
              SECTION E: Company branches
             ═════════════════════════════════════════════════════════════════ */}
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '28px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <h3 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
              Section E – Company Branches
            </h3>
            <p style={{ margin: '0 0 20px 0', color: '#64748b', fontSize: '13px' }}>
              Does your company have multiple office locations or branches?
            </p>

            <div style={{ display: 'flex', gap: '20px', marginBottom: '18px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                <input
                  type="radio"
                  name="has_branches"
                  checked={form.has_multiple_branches === true}
                  onChange={() => setForm({ ...form, has_multiple_branches: true })}
                />
                Yes &mdash; We have multiple branches
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: 600 }}>
                <input
                  type="radio"
                  name="has_branches"
                  checked={form.has_multiple_branches === false}
                  onChange={() => setForm({ ...form, has_multiple_branches: false })}
                />
                No &mdash; Single primary location
              </label>
            </div>

            {form.has_multiple_branches && (
              <div style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '18px', marginTop: '12px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '8px' }}>
                  Add Branch Locations / Names:
                </label>
                <div style={{ display: 'flex', gap: '10px', marginBottom: '12px' }}>
                  <input
                    type="text"
                    placeholder="e.g. Bengaluru Tech Hub, Mumbai Sales Office"
                    value={form.branch_input}
                    onChange={(e) => setForm({ ...form, branch_input: e.target.value })}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddBranch(); } }}
                    style={{ flex: 1, padding: '9px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
                  />
                  <button
                    type="button"
                    onClick={handleAddBranch}
                    style={{ padding: '9px 16px', borderRadius: '6px', backgroundColor: '#0f172a', color: '#ffffff', border: 'none', fontWeight: 600, fontSize: '13px', cursor: 'pointer' }}
                  >
                    + Add Branch
                  </button>
                </div>

                {form.branches_list.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {form.branches_list.map((branch, i) => (
                      <span
                        key={i}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          backgroundColor: '#ffffff',
                          border: '1px solid #cbd5e1',
                          padding: '4px 10px',
                          borderRadius: '16px',
                          fontSize: '12px',
                          fontWeight: 500,
                        }}
                      >
                        📍 {branch}
                        <button
                          type="button"
                          onClick={() => handleRemoveBranch(i)}
                          style={{ border: 'none', background: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '14px', lineHeight: 1 }}
                        >
                          &times;
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ═════════════════════════════════════════════════════════════════
              SECTION F: First company administrator
             ═════════════════════════════════════════════════════════════════ */}
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '28px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <h3 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
              Section F – First Company Administrator
            </h3>
            <p style={{ margin: '0 0 20px 0', color: '#64748b', fontSize: '13px' }}>
              This individual will hold the initial Global Admin account for your company on the DMS portal.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '18px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Admin Full Name <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="First Administrator Name"
                  value={form.admin_name}
                  onChange={(e) => setForm({ ...form, admin_name: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Admin Login Email <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="email"
                  required
                  placeholder="admin@company.com"
                  value={form.admin_email}
                  onChange={(e) => setForm({ ...form, admin_email: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Admin Mobile Number <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="+91 9876543210"
                  value={form.admin_mobile}
                  onChange={(e) => setForm({ ...form, admin_mobile: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Designation <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. IT Director, Managing Director"
                  value={form.admin_designation}
                  onChange={(e) => setForm({ ...form, admin_designation: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              {/* Password inputs */}
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Admin Password {!onboarding.has_admin_password && <span style={{ color: '#ef4444' }}>*</span>}
                  {onboarding.has_admin_password && <span style={{ color: '#16a34a', fontSize: '11px', marginLeft: '6px' }}>(Password already set; leave empty to keep)</span>}
                </label>
                <input
                  type="password"
                  required={!onboarding.has_admin_password}
                  placeholder={onboarding.has_admin_password ? 'Leave empty to retain existing password' : 'Min 8 characters'}
                  value={form.admin_password}
                  onChange={(e) => setForm({ ...form, admin_password: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Confirm Password {!onboarding.has_admin_password && <span style={{ color: '#ef4444' }}>*</span>}
                </label>
                <input
                  type="password"
                  required={Boolean(form.admin_password)}
                  placeholder="Re-type password"
                  value={form.confirm_password}
                  onChange={(e) => setForm({ ...form, confirm_password: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>
            </div>
          </div>

          {/* ═════════════════════════════════════════════════════════════════
              SECTION G: Document and business preferences
             ═════════════════════════════════════════════════════════════════ */}
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '28px', marginBottom: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <h3 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
              Section G – Document &amp; Business Preferences
            </h3>
            <p style={{ margin: '0 0 20px 0', color: '#64748b', fontSize: '13px' }}>
              Configure your expected document volumes, workflow preferences, and language needs.
            </p>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '8px' }}>
                Primary Document Types:
              </label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {COMMON_DOC_TYPES.map(docType => {
                  const selected = form.primary_document_types.includes(docType);
                  return (
                    <button
                      key={docType}
                      type="button"
                      onClick={() => toggleArrayItem('primary_document_types', docType)}
                      style={{
                        padding: '6px 12px',
                        borderRadius: '16px',
                        border: '1px solid',
                        borderColor: selected ? '#ef233c' : '#cbd5e1',
                        backgroundColor: selected ? '#ffedef' : '#ffffff',
                        color: selected ? '#d90429' : '#475569',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      {selected ? '✓ ' : '+ '} {docType}
                    </button>
                  );
                })}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '18px', marginBottom: '20px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Expected Monthly Document Volume
                </label>
                <select
                  value={form.expected_monthly_volume}
                  onChange={(e) => setForm({ ...form, expected_monthly_volume: e.target.value })}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '14px', backgroundColor: '#ffffff', boxSizing: 'border-box' }}
                >
                  {MONTHLY_VOLUMES.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Time Zone
                </label>
                <input
                  type="text"
                  disabled
                  value={form.timezone}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '14px', backgroundColor: '#f8fafc', color: '#64748b', boxSizing: 'border-box' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Currency
                </label>
                <input
                  type="text"
                  disabled
                  value={form.currency}
                  style={{ width: '100%', padding: '10px 12px', borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '14px', backgroundColor: '#f8fafc', color: '#64748b', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '8px' }}>
                Languages (Multiple selection supported):
              </label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {COMMON_LANGUAGES.map(lang => {
                  const selected = form.languages.includes(lang);
                  return (
                    <button
                      key={lang}
                      type="button"
                      onClick={() => toggleArrayItem('languages', lang)}
                      style={{
                        padding: '6px 12px',
                        borderRadius: '16px',
                        border: '1px solid',
                        borderColor: selected ? '#ef233c' : '#cbd5e1',
                        backgroundColor: selected ? '#ffedef' : '#ffffff',
                        color: selected ? '#d90429' : '#475569',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      {selected ? '✓ ' : '+ '} {lang}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* ═════════════════════════════════════════════════════════════════
              DOCUMENTS TO REQUEST AS UPLOADS
             ═════════════════════════════════════════════════════════════════ */}
          <div style={{ backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0', padding: '28px', marginBottom: '32px', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <h3 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 700, color: '#0f172a' }}>
              Verification Documents Upload
            </h3>
            <p style={{ margin: '0 0 20px 0', color: '#64748b', fontSize: '13px' }}>
              Please upload clear PDF, JPEG, or PNG scans. Max file size: 10 MB per document.
            </p>

            {uploadError && (
              <div style={{ padding: '10px 14px', backgroundColor: '#fef2f2', border: '1px solid #fca5a5', borderRadius: '6px', color: '#b91c1c', fontSize: '13px', marginBottom: '16px' }}>
                {uploadError}
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
              {[
                { key: 'pan_document', label: 'PAN Card / PAN Document', required: true, hint: 'Official PAN card of the company / proprietor' },
                { key: 'gst_certificate', label: 'GST Registration Certificate', required: false, hint: 'Mandatory if GST registered' },
                { key: 'incorporation_certificate', label: 'Certificate of Incorporation', required: false, hint: 'Applicable for Pvt Ltd, Ltd, or LLP' },
                { key: 'udyam_certificate', label: 'Udyam MSME Certificate', required: false, hint: 'Optional MSME registration proof' },
                { key: 'address_proof', label: 'Company Address Proof', required: true, hint: 'Electricity bill, lease agreement, bank statement' },
              ].map(docItem => {
                const uploaded = uploadedDocs[docItem.key];
                const isUploading = uploadingDoc === docItem.key;
                return (
                  <div
                    key={docItem.key}
                    style={{
                      border: uploaded ? '1px solid #86efac' : '1px solid #e2e8f0',
                      backgroundColor: uploaded ? '#f0fdf4' : '#fafafa',
                      borderRadius: '8px',
                      padding: '16px',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
                        <span style={{ fontSize: '13px', fontWeight: 700, color: '#1e293b' }}>
                          {docItem.label} {docItem.required && <span style={{ color: '#ef4444' }}>*</span>}
                        </span>
                        {uploaded && (
                          <span style={{ fontSize: '11px', fontWeight: 700, color: '#16a34a', backgroundColor: '#dcfce7', padding: '2px 8px', borderRadius: '10px' }}>
                            ✓ Uploaded
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '12px' }}>
                        {docItem.hint}
                      </div>

                      {uploaded && (
                        <div style={{ fontSize: '12px', color: '#15803d', marginBottom: '10px', wordBreak: 'break-all' }}>
                          📄 {uploaded.filename} ({(uploaded.file_size / 1024).toFixed(0)} KB)
                        </div>
                      )}
                    </div>

                    <div>
                      <label
                        style={{
                          display: 'inline-block',
                          padding: '7px 14px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          backgroundColor: '#ffffff',
                          color: '#0f172a',
                          fontSize: '12px',
                          fontWeight: 600,
                          cursor: isUploading ? 'not-allowed' : 'pointer',
                          textAlign: 'center',
                          width: '100%',
                          boxSizing: 'border-box',
                        }}
                      >
                        {isUploading ? 'Uploading...' : uploaded ? 'Replace Document' : 'Choose File to Upload'}
                        <input
                          type="file"
                          accept=".pdf,image/jpeg,image/png,image/webp"
                          disabled={isUploading}
                          onChange={(e) => {
                            if (e.target.files?.[0]) {
                              handleFileUpload(docItem.key, e.target.files[0]);
                            }
                          }}
                          style={{ display: 'none' }}
                        />
                      </label>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ═════════════════════════════════════════════════════════════════
              FORM ACTIONS: SUBMIT / RESUBMIT
             ═════════════════════════════════════════════════════════════════ */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#ffffff',
            borderRadius: '10px',
            border: '1px solid #e2e8f0',
            padding: '20px 28px',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)',
            flexWrap: 'wrap',
            gap: '16px',
          }}>
            <div>
              <div style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                {isChangesRequested ? 'Ready to Resubmit Application?' : 'Ready to Submit for Review?'}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b' }}>
                {isChangesRequested
                  ? 'Your updated application will be placed back into the Master Admin review queue.'
                  : 'Please review all entered details and documents before final submission.'}
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              style={{
                padding: '12px 32px',
                borderRadius: '8px',
                border: 'none',
                backgroundColor: isChangesRequested ? '#d97706' : '#ef233c',
                color: '#ffffff',
                fontWeight: 700,
                fontSize: '14px',
                cursor: submitting ? 'not-allowed' : 'pointer',
                boxShadow: isChangesRequested ? '0 2px 8px rgba(217, 119, 6, 0.3)' : '0 2px 8px rgba(239, 35, 60, 0.3)',
                opacity: submitting ? 0.7 : 1,
              }}
            >
              {submitting ? 'Submitting Application...' : isChangesRequested ? 'Resubmit Application' : 'Submit Application'}
            </button>
          </div>

        </form>

      </main>

    </div>
  );
}

