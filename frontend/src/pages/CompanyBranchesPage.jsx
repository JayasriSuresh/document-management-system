import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import { api } from '../api';
import ConfirmModal from '../components/ConfirmModal';

const INDIAN_STATES = [
  'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chandigarh',
  'Chhattisgarh', 'Dadra and Nagar Haveli and Daman and Diu', 'Delhi', 'Goa',
  'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jammu and Kashmir', 'Jharkhand',
  'Karnataka', 'Kerala', 'Ladakh', 'Lakshadweep', 'Madhya Pradesh',
  'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha',
  'Puducherry', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana',
  'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal', 'Andaman and Nicobar Islands'
];

const BRANCH_TYPES = [
  'Head Office',
  'Regional Office',
  'Branch',
  'Warehouse',
  'Sales Office',
  'Service Center',
  'Distribution Center',
  'Factory',
  'Retail Outlet',
];

const GST_REGISTRATION_TYPES = [
  'Regular',
  'Composition',
  'Casual Taxable Person',
  'Input Service Distributor (ISD)',
  'Non-Resident Taxable Person',
  'Special Economic Zone (SEZ)',
  'Government Entity',
];

export default function CompanyBranchesPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  // Company profile & branches state
  const [companyProfile, setCompanyProfile] = useState(null);
  const [branches, setBranches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Filtering & search
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');

  // Add Branch Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  // Add Branch Form State
  const initialFormState = {
    // Section 1: Branch Details
    branch_name: '',
    branch_code: '',
    branch_type: 'Branch',
    branch_email: '',
    branch_contact_number: '',
    address_line1: '',
    address_line2: '',
    city: '',
    district: '',
    state: 'Tamil Nadu',
    pincode: '',
    country: 'India',
    // Section 1.1: Branch GST Details
    gst_registered: false,
    gstin: '',
    gst_type: 'Regular',
    // Section 2: Primary Admin User
    admin_name: '',
    admin_email: '',
    admin_mobile: '',
  };

  const [form, setForm] = useState(initialFormState);

  // Success Confirmation Modal State
  const [createdBranchData, setCreatedBranchData] = useState(null);
  const [copiedLink, setCopiedLink] = useState(false);

  // Selected Branch for Details Modal
  const [selectedBranch, setSelectedBranch] = useState(null);

  // Action status (toggle active/inactive)
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [confirmDialog, setConfirmDialog] = useState(null);

  // ── Load Data ─────────────────────────────────────────────────────────────
  const loadData = async () => {
    setLoading(true);
    setError('');
    try {
      const [profileRes, branchesRes] = await Promise.all([
        api.getCompanyProfile().catch(() => null),
        api.listCompanyBranches(),
      ]);
      if (profileRes) setCompanyProfile(profileRes);
      setBranches(branchesRes || []);
    } catch (err) {
      setError(err.message || 'Failed to load company branches.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/company/login');
  };

  // ── Form Input Handler ───────────────────────────────────────────────────
  const handleInputChange = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  // ── Handle Add Branch Submit ─────────────────────────────────────────────
  const handleAddBranchSubmit = async (e) => {
    e.preventDefault();
    setFormError('');

    // Client-side validations
    if (!form.branch_name.trim()) {
      setFormError('Branch Name is required.');
      return;
    }
    if (!form.branch_code.trim()) {
      setFormError('Branch Code is required.');
      return;
    }
    if (!form.branch_contact_number.trim()) {
      setFormError('Branch Contact Number is required.');
      return;
    }
    if (!form.address_line1.trim()) {
      setFormError('Address Line 1 is required.');
      return;
    }
    if (!form.city.trim()) {
      setFormError('City is required.');
      return;
    }
    if (!form.district.trim()) {
      setFormError('District is required.');
      return;
    }
    if (!form.state.trim()) {
      setFormError('State is required.');
      return;
    }
    if (!form.pincode.trim() || !/^\d{6}$/.test(form.pincode.trim())) {
      setFormError('PIN Code must be a 6-digit numeric postal code.');
      return;
    }
    if (form.gst_registered) {
      const cleanGstin = form.gstin.trim().toUpperCase();
      if (!cleanGstin) {
        setFormError('GSTIN is required when branch is marked as GST registered.');
        return;
      }
      if (cleanGstin.length !== 15) {
        setFormError('Indian GSTIN must be exactly 15 characters (e.g. 33AABCA1234F1Z5).');
        return;
      }
    }
    if (!form.admin_name.trim()) {
      setFormError('Primary Admin Name is required.');
      return;
    }
    if (!form.admin_email.trim() || !form.admin_email.includes('@')) {
      setFormError('A valid Primary Admin Email is required.');
      return;
    }
    if (!form.admin_mobile.trim()) {
      setFormError('Primary Admin Mobile Number is required.');
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        branch_name: form.branch_name.trim(),
        branch_code: form.branch_code.trim().toUpperCase(),
        branch_type: form.branch_type,
        branch_email: form.branch_email.trim() || null,
        branch_contact_number: form.branch_contact_number.trim(),
        address_line1: form.address_line1.trim(),
        address_line2: form.address_line2.trim() || null,
        city: form.city.trim(),
        district: form.district.trim(),
        state: form.state.trim(),
        pincode: form.pincode.trim(),
        country: form.country.trim() || 'India',
        gst_registered: Boolean(form.gst_registered),
        gstin: form.gst_registered ? form.gstin.trim().toUpperCase() : null,
        gst_type: form.gst_registered ? form.gst_type : null,
        admin_name: form.admin_name.trim(),
        admin_email: form.admin_email.trim().toLowerCase(),
        admin_mobile: form.admin_mobile.trim(),
      };

      const result = await api.createCompanyBranch(payload);
      setCreatedBranchData(result);
      setShowAddModal(false);
      setForm(initialFormState);
      loadData();
    } catch (err) {
      setFormError(err.message || 'Failed to create branch.');
    } finally {
      setSubmitting(false);
    }
  };

  // ── Handle Toggle Status ─────────────────────────────────────────────────
  const handleToggleStatus = (branch) => {
    const isDeactivating = branch.status === 'active';
    const action = isDeactivating ? 'deactivate' : 'activate';
    setConfirmDialog({
      title: `${isDeactivating ? 'Deactivate' : 'Activate'} Branch`,
      message: `Are you sure you want to ${action} branch "${branch.name}" (${branch.code})?`,
      details: isDeactivating ? (
        <div style={{ color: '#b45309' }}>
          <strong>Notice:</strong> Deactivating will prevent new document uploads and staff actions within this branch.
        </div>
      ) : (
        <div style={{ color: '#16a34a' }}>
          Activating will restore full operations for this branch.
        </div>
      ),
      confirmText: isDeactivating ? 'Deactivate Branch' : 'Activate Branch',
      variant: isDeactivating ? 'warning' : 'success',
      onConfirm: async () => {
        setActionLoadingId(branch.id);
        try {
          await api.toggleBranchStatus(branch.id);
          await loadData();
        } catch (err) {
          setError(err.message || `Failed to ${action} branch.`);
        } finally {
          setActionLoadingId(null);
          setConfirmDialog(null);
        }
      },
    });
  };

  const handleCopyLink = (url) => {
    if (!url) return;
    navigator.clipboard.writeText(url);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 3000);
  };

  // ── Filtered Branches ────────────────────────────────────────────────────
  const filteredBranches = useMemo(() => {
    return branches.filter((b) => {
      const q = searchQuery.toLowerCase().trim();
      const matchSearch =
        !q ||
        b.name?.toLowerCase().includes(q) ||
        b.code?.toLowerCase().includes(q) ||
        b.city?.toLowerCase().includes(q) ||
        b.gstin?.toLowerCase().includes(q) ||
        b.primary_admin?.name?.toLowerCase().includes(q) ||
        b.primary_admin?.email?.toLowerCase().includes(q);

      const matchStatus =
        statusFilter === 'all' ||
        (statusFilter === 'active' && b.status === 'active') ||
        (statusFilter === 'inactive' && b.status === 'inactive');

      const matchType =
        typeFilter === 'all' || b.branch_type === typeFilter;

      return matchSearch && matchStatus && matchType;
    });
  }, [branches, searchQuery, statusFilter, typeFilter]);

  // ── Statistics ───────────────────────────────────────────────────────────
  const stats = useMemo(() => {
    const total = branches.length;
    const active = branches.filter((b) => b.status === 'active').length;
    const inactive = total - active;
    const gstCount = branches.filter((b) => b.gst_registered).length;
    const totalUsers = branches.reduce((sum, b) => sum + (b.user_count || 0), 0);
    return { total, active, inactive, gstCount, totalUsers };
  }, [branches]);

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#f8fafc', color: '#1e293b', fontFamily: 'Inter, system-ui, -apple-system, sans-serif' }}>
      
      {/* ── TOP NAV BAR ───────────────────────────────────────────────────── */}
      <header style={{
        height: '64px',
        backgroundColor: '#ffffff',
        borderBottom: '1px solid #e2e8f0',
        padding: '0 28px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'sticky',
        top: 0,
        zIndex: 40,
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            backgroundColor: '#8b5cf6',
            color: '#ffffff',
            padding: '4px 10px',
            borderRadius: '6px',
            fontSize: '11px',
            fontWeight: 800,
            letterSpacing: '1px',
          }}>
            COMPANY ADMIN
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>{companyProfile?.name || user?.tenant_name || 'DMS'}</span>
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#6366f1', backgroundColor: '#eef2ff', padding: '2px 8px', borderRadius: '4px' }}>
                {companyProfile?.code || 'HQ'}
              </span>
            </h1>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
          <Link
            to="/"
            style={{
              fontSize: '13px',
              fontWeight: 600,
              color: '#4f46e5',
              textDecoration: 'none',
              padding: '6px 12px',
              borderRadius: '6px',
              backgroundColor: '#eef2ff',
              transition: 'background 0.2s',
            }}
          >
            &larr; Workspace Documents
          </Link>

          <div style={{ height: '24px', width: '1px', backgroundColor: '#e2e8f0' }} />

          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '13px', fontWeight: 600 }}>{user?.name || 'Company Administrator'}</div>
            <div style={{ fontSize: '11px', color: '#64748b' }}>{user?.email || 'admin@company.com'}</div>
          </div>

          <button
            onClick={handleLogout}
            style={{
              padding: '7px 15px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              color: '#334155',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      {/* ── MAIN CONTENT CONTAINER ────────────────────────────────────────── */}
      <main style={{ maxWidth: '1320px', margin: '0 auto', padding: '32px 24px' }}>

        {/* ── Page Header & Add Branch Button ─────────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '28px', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
              <h2 style={{ fontSize: '26px', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                Company Branches &amp; Locations
              </h2>
              <span style={{
                backgroundColor: companyProfile?.status === 'active' ? '#ecfdf5' : '#fef2f2',
                color: companyProfile?.status === 'active' ? '#047857' : '#b91c1c',
                fontSize: '12px',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: '12px',
                border: companyProfile?.status === 'active' ? '1px solid #a7f3d0' : '1px solid #fecaca',
              }}>
                {(companyProfile?.status || 'active').toUpperCase()}
              </span>
            </div>
            <p style={{ margin: 0, color: '#64748b', fontSize: '14px' }}>
              Provision and oversee regional offices, warehouses, and branch workspaces under <strong>{companyProfile?.name || 'your enterprise'}</strong>.
            </p>
          </div>

          <button
            onClick={() => setShowAddModal(true)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: '#7c3aed',
              color: '#ffffff',
              padding: '11px 22px',
              borderRadius: '8px',
              border: 'none',
              fontWeight: 600,
              fontSize: '14px',
              cursor: 'pointer',
              boxShadow: '0 2px 10px rgba(124, 58, 237, 0.25)',
              transition: 'background-color 0.2s',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add Branch
          </button>
        </div>

        {/* ── Key Metrics Cards ────────────────────────────────────────────── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '16px', marginBottom: '28px' }}>
          <div style={{ backgroundColor: '#ffffff', padding: '18px 22px', borderRadius: '10px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Total Branches</div>
            <div style={{ fontSize: '28px', fontWeight: 800, color: '#0f172a', marginTop: '6px' }}>{stats.total}</div>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '18px 22px', borderRadius: '10px', border: '1px solid #86efac', boxShadow: '0 1px 3px rgba(34,197,94,0.05)' }}>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#15803d', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Active Branches</div>
            <div style={{ fontSize: '28px', fontWeight: 800, color: '#15803d', marginTop: '6px' }}>{stats.active}</div>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '18px 22px', borderRadius: '10px', border: '1px solid #fecaca', boxShadow: '0 1px 3px rgba(239,68,68,0.05)' }}>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#b91c1c', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Inactive Branches</div>
            <div style={{ fontSize: '28px', fontWeight: 800, color: '#b91c1c', marginTop: '6px' }}>{stats.inactive}</div>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '18px 22px', borderRadius: '10px', border: '1px solid #93c5fd', boxShadow: '0 1px 3px rgba(59,130,246,0.05)' }}>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#1d4ed8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>GST Registered</div>
            <div style={{ fontSize: '28px', fontWeight: 800, color: '#1d4ed8', marginTop: '6px' }}>{stats.gstCount}</div>
          </div>
          <div style={{ backgroundColor: '#ffffff', padding: '18px 22px', borderRadius: '10px', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.02)' }}>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Branch Staff &amp; Admins</div>
            <div style={{ fontSize: '28px', fontWeight: 800, color: '#6366f1', marginTop: '6px' }}>{stats.totalUsers}</div>
          </div>
        </div>

        {/* ── Search & Filter Controls ─────────────────────────────────────── */}
        <div style={{
          backgroundColor: '#ffffff',
          borderRadius: '10px',
          border: '1px solid #e2e8f0',
          padding: '16px 20px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '14px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
        }}>
          {/* Search Box */}
          <div style={{ position: 'relative', flex: '1', minWidth: '260px' }}>
            <svg
              style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }}
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              placeholder="Search branches by name, code, city, GSTIN, or admin..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                padding: '9px 12px 9px 36px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '13px',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>

          {/* Filters */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b' }}>Status:</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                style={{
                  padding: '8px 12px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  fontSize: '13px',
                  color: '#334155',
                  outline: 'none',
                }}
              >
                <option value="all">All Statuses</option>
                <option value="active">Active Only</option>
                <option value="inactive">Inactive Only</option>
              </select>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748b' }}>Type:</span>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                style={{
                  padding: '8px 12px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  fontSize: '13px',
                  color: '#334155',
                  outline: 'none',
                }}
              >
                <option value="all">All Types</option>
                {BRANCH_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* ── Error Banner ─────────────────────────────────────────────────── */}
        {error && (
          <div style={{
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            color: '#b91c1c',
            padding: '14px 18px',
            borderRadius: '8px',
            marginBottom: '24px',
            fontSize: '14px',
          }}>
            {error}
          </div>
        )}

        {/* ── Branches Table / Card List ───────────────────────────────────── */}
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', backgroundColor: '#ffffff', borderRadius: '10px', border: '1px solid #e2e8f0' }}>
            <div className="spinner" style={{ margin: '0 auto 12px auto' }} />
            <div style={{ color: '#64748b', fontSize: '14px' }}>Loading company branches...</div>
          </div>
        ) : filteredBranches.length === 0 ? (
          <div style={{
            textAlign: 'center',
            padding: '60px 24px',
            backgroundColor: '#ffffff',
            borderRadius: '10px',
            border: '1px solid #e2e8f0',
          }}>
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              backgroundColor: '#f1f5f9',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px auto',
              color: '#64748b',
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
              </svg>
            </div>
            <h3 style={{ margin: '0 0 6px 0', fontSize: '17px', fontWeight: 600, color: '#0f172a' }}>
              No branches found
            </h3>
            <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: '#64748b' }}>
              {searchQuery || statusFilter !== 'all' || typeFilter !== 'all'
                ? 'No branches match your active filter criteria.'
                : 'No branches added yet under this company.'}
            </p>
            <button
              onClick={() => setShowAddModal(true)}
              style={{
                backgroundColor: '#7c3aed',
                color: '#ffffff',
                padding: '9px 18px',
                borderRadius: '6px',
                border: 'none',
                fontWeight: 600,
                fontSize: '13px',
                cursor: 'pointer',
              }}
            >
              + Add First Branch
            </button>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))', gap: '20px' }}>
            {filteredBranches.map((branch) => {
              const isActive = branch.status === 'active';
              const admin = branch.primary_admin;

              return (
                <div
                  key={branch.id}
                  style={{
                    backgroundColor: '#ffffff',
                    borderRadius: '12px',
                    border: '1px solid #e2e8f0',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
                    padding: '24px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    transition: 'box-shadow 0.2s',
                  }}
                >
                  {/* Card Header */}
                  <div>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px', marginBottom: '12px' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                            {branch.name}
                          </h3>
                          <span style={{
                            backgroundColor: '#eef2ff',
                            color: '#4338ca',
                            fontSize: '11px',
                            fontWeight: 700,
                            padding: '2px 7px',
                            borderRadius: '4px',
                            letterSpacing: '0.5px',
                          }}>
                            {branch.code}
                          </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                          <span style={{
                            fontSize: '11px',
                            fontWeight: 600,
                            color: '#475569',
                            backgroundColor: '#f1f5f9',
                            padding: '1px 8px',
                            borderRadius: '10px',
                          }}>
                            {branch.branch_type || 'Branch'}
                          </span>
                          {branch.city && (
                            <span style={{ fontSize: '12px', color: '#64748b' }}>
                              &bull; {branch.city}{branch.state ? `, ${branch.state}` : ''}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Status Badge */}
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '5px',
                        padding: '3px 10px',
                        borderRadius: '12px',
                        fontSize: '11px',
                        fontWeight: 700,
                        backgroundColor: isActive ? '#ecfdf5' : '#f8fafc',
                        color: isActive ? '#059669' : '#64748b',
                        border: `1px solid ${isActive ? '#a7f3d0' : '#cbd5e1'}`,
                      }}>
                        <span style={{
                          width: '6px',
                          height: '6px',
                          borderRadius: '50%',
                          backgroundColor: isActive ? '#10b981' : '#94a3b8',
                        }} />
                        {isActive ? 'ACTIVE' : 'INACTIVE'}
                      </span>
                    </div>

                    {/* Address Block */}
                    <div style={{
                      backgroundColor: '#f8fafc',
                      borderRadius: '8px',
                      padding: '10px 14px',
                      marginBottom: '14px',
                      fontSize: '12px',
                      color: '#475569',
                      lineHeight: '1.5',
                    }}>
                      <div style={{ fontWeight: 600, color: '#334155', marginBottom: '2px' }}>
                        Address &amp; Location:
                      </div>
                      <div>
                        {branch.address_line1 || branch.address || 'No street address recorded'}
                        {branch.address_line2 ? `, ${branch.address_line2}` : ''}
                      </div>
                      <div>
                        {[branch.city, branch.district, branch.state, branch.pincode].filter(Boolean).join(', ') || 'India'}
                      </div>
                      {(branch.branch_contact_number || branch.contact_phone || branch.branch_email || branch.contact_email) && (
                        <div style={{ marginTop: '6px', paddingTop: '6px', borderTop: '1px dashed #e2e8f0', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                          {(branch.branch_contact_number || branch.contact_phone) && (
                            <span><strong>Tel:</strong> {branch.branch_contact_number || branch.contact_phone}</span>
                          )}
                          {(branch.branch_email || branch.contact_email) && (
                            <span><strong>Email:</strong> {branch.branch_email || branch.contact_email}</span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Tax / GST Details Section */}
                    <div style={{
                      backgroundColor: branch.gst_registered ? '#eff6ff' : '#f8fafc',
                      border: `1px solid ${branch.gst_registered ? '#bfdbfe' : '#e2e8f0'}`,
                      borderRadius: '8px',
                      padding: '10px 14px',
                      marginBottom: '14px',
                      fontSize: '12px',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 600, color: branch.gst_registered ? '#1e40af' : '#64748b' }}>
                          Branch Tax Status:
                        </span>
                        <span style={{
                          fontSize: '10px',
                          fontWeight: 700,
                          padding: '1px 6px',
                          borderRadius: '4px',
                          backgroundColor: branch.gst_registered ? '#dbeafe' : '#e2e8f0',
                          color: branch.gst_registered ? '#1d4ed8' : '#475569',
                        }}>
                          {branch.gst_registered ? 'GST REGISTERED' : 'NOT REGISTERED'}
                        </span>
                      </div>
                      {branch.gst_registered ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '4px' }}>
                          <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '13px', color: '#1e3a8a' }}>
                            {branch.gstin || 'GSTIN Pending'}
                          </span>
                          <span style={{ color: '#3b82f6', fontSize: '11px', fontWeight: 600 }}>
                            {branch.gst_type || 'Regular'}
                          </span>
                        </div>
                      ) : (
                        <div style={{ color: '#94a3b8', fontSize: '11px' }}>
                          No state-specific GSTIN assigned for this branch.
                        </div>
                      )}
                    </div>

                    {/* Primary Admin User Section */}
                    <div style={{
                      backgroundColor: '#faf5ff',
                      border: '1px solid #f3e8ff',
                      borderRadius: '8px',
                      padding: '10px 14px',
                      marginBottom: '16px',
                      fontSize: '12px',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 600, color: '#6b21a8' }}>
                          Primary Admin User:
                        </span>
                        {admin ? (
                          <span style={{
                            fontSize: '10px',
                            fontWeight: 700,
                            padding: '1px 6px',
                            borderRadius: '4px',
                            backgroundColor: admin.is_activated ? '#dcfce7' : '#fef3c7',
                            color: admin.is_activated ? '#15803d' : '#b45309',
                          }}>
                            {admin.is_activated ? 'ACTIVE ADMIN' : 'INVITED / PENDING'}
                          </span>
                        ) : (
                          <span style={{ fontSize: '10px', color: '#94a3b8' }}>Unassigned</span>
                        )}
                      </div>
                      {admin ? (
                        <div>
                          <div style={{ fontWeight: 600, color: '#1e293b' }}>{admin.name}</div>
                          <div style={{ color: '#64748b', fontSize: '11px' }}>{admin.email}</div>
                          {admin.mobile && (
                            <div style={{ color: '#64748b', fontSize: '11px' }}>Tel: {admin.mobile}</div>
                          )}
                        </div>
                      ) : (
                        <div style={{ color: '#94a3b8', fontSize: '11px' }}>
                          No primary branch administrator currently linked.
                        </div>
                      )}
                    </div>

                    {/* Stats Strip */}
                    <div style={{ display: 'flex', gap: '16px', fontSize: '12px', color: '#64748b', marginBottom: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <strong style={{ color: '#0f172a' }}>{branch.active_user_count ?? branch.user_count ?? 0}</strong> Users
                      </div>
                      <div>&bull;</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <strong style={{ color: '#0f172a' }}>{branch.document_count || 0}</strong> Documents
                      </div>
                    </div>
                  </div>

                  {/* Card Actions Footer */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: '14px', borderTop: '1px solid #f1f5f9' }}>
                    <button
                      onClick={() => setSelectedBranch(branch)}
                      style={{
                        padding: '6px 14px',
                        borderRadius: '6px',
                        border: '1px solid #cbd5e1',
                        backgroundColor: '#ffffff',
                        color: '#334155',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      View Details
                    </button>

                    <button
                      onClick={() => handleToggleStatus(branch)}
                      disabled={actionLoadingId === branch.id}
                      style={{
                        padding: '6px 14px',
                        borderRadius: '6px',
                        border: 'none',
                        backgroundColor: isActive ? '#fee2e2' : '#dcfce7',
                        color: isActive ? '#dc2626' : '#16a34a',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: actionLoadingId === branch.id ? 'not-allowed' : 'pointer',
                        opacity: actionLoadingId === branch.id ? 0.6 : 1,
                      }}
                    >
                      {actionLoadingId === branch.id
                        ? 'Updating...'
                        : isActive
                        ? 'Deactivate'
                        : 'Activate'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>

      {/* ── 1. ADD BRANCH ONBOARDING MODAL ─────────────────────────────────── */}
      {showAddModal && (
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
          zIndex: 100,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            maxWidth: '780px',
            width: '100%',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.2)',
            overflow: 'hidden',
          }}>
            {/* Modal Header */}
            <div style={{
              padding: '20px 28px',
              borderBottom: '1px solid #e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: '#faf5ff',
            }}>
              <div>
                <div style={{ display: 'inline-block', fontSize: '10px', fontWeight: 800, color: '#7c3aed', letterSpacing: '1px', textTransform: 'uppercase' }}>
                  Branch Provisioning
                </div>
                <h3 style={{ margin: '2px 0 0 0', fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>
                  Add Company Branch
                </h3>
              </div>
              <button
                onClick={() => {
                  setShowAddModal(false);
                  setFormError('');
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '22px',
                  color: '#64748b',
                  cursor: 'pointer',
                  padding: '4px',
                }}
              >
                &times;
              </button>
            </div>

            {/* Modal Form Scrollable Body */}
            <form onSubmit={handleAddBranchSubmit} style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
              <div style={{ padding: '24px 28px', overflowY: 'auto', flex: 1 }}>

                {formError && (
                  <div style={{
                    backgroundColor: '#fef2f2',
                    border: '1px solid #fecaca',
                    color: '#b91c1c',
                    padding: '12px 16px',
                    borderRadius: '8px',
                    marginBottom: '20px',
                    fontSize: '13px',
                  }}>
                    {formError}
                  </div>
                )}

                {/* ── SECTION 1: BRANCH DETAILS ────────────────────────────── */}
                <div style={{ marginBottom: '28px' }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    paddingBottom: '8px',
                    borderBottom: '2px solid #8b5cf6',
                    marginBottom: '16px',
                  }}>
                    <span style={{
                      backgroundColor: '#8b5cf6',
                      color: '#ffffff',
                      borderRadius: '50%',
                      width: '24px',
                      height: '24px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '12px',
                      fontWeight: 700,
                    }}>
                      1
                    </span>
                    <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                      Branch Details
                    </h4>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', marginBottom: '14px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Branch Name <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. Chennai Central Branch"
                        value={form.branch_name}
                        onChange={(e) => handleInputChange('branch_name', e.target.value)}
                        required
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Branch Code <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. CHN001 (Unique within company)"
                        value={form.branch_code}
                        onChange={(e) => handleInputChange('branch_code', e.target.value.toUpperCase())}
                        required
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          textTransform: 'uppercase',
                          fontWeight: 600,
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Branch Type <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <select
                        value={form.branch_type}
                        onChange={(e) => handleInputChange('branch_type', e.target.value)}
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          backgroundColor: '#ffffff',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      >
                        {BRANCH_TYPES.map((t) => (
                          <option key={t} value={t}>{t}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', marginBottom: '14px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Branch Contact Number <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. +91 9876543210"
                        value={form.branch_contact_number}
                        onChange={(e) => handleInputChange('branch_contact_number', e.target.value)}
                        required
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Branch Email <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 400 }}>(Optional)</span>
                      </label>
                      <input
                        type="email"
                        placeholder="e.g. chennai@company.com"
                        value={form.branch_email}
                        onChange={(e) => handleInputChange('branch_email', e.target.value)}
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>
                  </div>

                  {/* Address Fields */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Address Line 1 <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        placeholder="Building, street, door number"
                        value={form.address_line1}
                        onChange={(e) => handleInputChange('address_line1', e.target.value)}
                        required
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Address Line 2 <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 400 }}>(Optional)</span>
                      </label>
                      <input
                        type="text"
                        placeholder="Area, locality, landmark"
                        value={form.address_line2}
                        onChange={(e) => handleInputChange('address_line2', e.target.value)}
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '14px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        City <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. Chennai"
                        value={form.city}
                        onChange={(e) => handleInputChange('city', e.target.value)}
                        required
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        District <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. Chennai"
                        value={form.district}
                        onChange={(e) => handleInputChange('district', e.target.value)}
                        required
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        State <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <select
                        value={form.state}
                        onChange={(e) => handleInputChange('state', e.target.value)}
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          backgroundColor: '#ffffff',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      >
                        {INDIAN_STATES.map((st) => (
                          <option key={st} value={st}>{st}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        PIN Code <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        placeholder="6-digit PIN"
                        maxLength="6"
                        value={form.pincode}
                        onChange={(e) => handleInputChange('pincode', e.target.value.replace(/\D/g, ''))}
                        required
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Country
                      </label>
                      <input
                        type="text"
                        value={form.country}
                        disabled
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #e2e8f0',
                          backgroundColor: '#f1f5f9',
                          color: '#64748b',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>
                  </div>
                </div>

                {/* ── SECTION 1.1: BRANCH-SPECIFIC GST DETAILS ─────────────── */}
                <div style={{
                  backgroundColor: '#f0f9ff',
                  border: '1px solid #bae6fd',
                  borderRadius: '10px',
                  padding: '16px 20px',
                  marginBottom: '28px',
                }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px', marginBottom: '12px' }}>
                    <div>
                      <h5 style={{ margin: '0 0 2px 0', fontSize: '14px', fontWeight: 700, color: '#0369a1' }}>
                        Branch-specific GST Details
                      </h5>
                      <p style={{ margin: 0, fontSize: '12px', color: '#0284c7' }}>
                        A company may have separate GST registrations across different states. GSTIN is tracked against this specific branch location.
                      </p>
                    </div>

                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 600, fontSize: '13px', color: '#0369a1' }}>
                      <input
                        type="checkbox"
                        checked={form.gst_registered}
                        onChange={(e) => handleInputChange('gst_registered', e.target.checked)}
                        style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                      />
                      GST Registered?
                    </label>
                  </div>

                  {form.gst_registered && (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #e0f2fe' }}>
                      <div>
                        <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#0369a1', marginBottom: '4px' }}>
                          Branch GSTIN <span style={{ color: '#ef4444' }}>*</span>
                        </label>
                        <input
                          type="text"
                          placeholder="e.g. 33AABCA1234F1Z5 (15 chars)"
                          maxLength="15"
                          value={form.gstin}
                          onChange={(e) => handleInputChange('gstin', e.target.value.toUpperCase())}
                          required={form.gst_registered}
                          style={{
                            width: '100%',
                            padding: '8px 12px',
                            borderRadius: '6px',
                            border: '1px solid #7dd3fc',
                            backgroundColor: '#ffffff',
                            fontSize: '13px',
                            textTransform: 'uppercase',
                            fontWeight: 600,
                            fontFamily: 'monospace',
                            boxSizing: 'border-box',
                          }}
                        />
                      </div>

                      <div>
                        <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#0369a1', marginBottom: '4px' }}>
                          GST Registration Type <span style={{ color: '#ef4444' }}>*</span>
                        </label>
                        <select
                          value={form.gst_type}
                          onChange={(e) => handleInputChange('gst_type', e.target.value)}
                          style={{
                            width: '100%',
                            padding: '8px 12px',
                            borderRadius: '6px',
                            border: '1px solid #7dd3fc',
                            backgroundColor: '#ffffff',
                            fontSize: '13px',
                            boxSizing: 'border-box',
                          }}
                        >
                          {GST_REGISTRATION_TYPES.map((gt) => (
                            <option key={gt} value={gt}>{gt}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  )}
                </div>

                {/* ── SECTION 2: PRIMARY ADMIN USER ────────────────────────── */}
                <div>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    paddingBottom: '8px',
                    borderBottom: '2px solid #8b5cf6',
                    marginBottom: '16px',
                  }}>
                    <span style={{
                      backgroundColor: '#8b5cf6',
                      color: '#ffffff',
                      borderRadius: '50%',
                      width: '24px',
                      height: '24px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '12px',
                      fontWeight: 700,
                    }}>
                      2
                    </span>
                    <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                      Primary Admin User
                    </h4>
                  </div>

                  {/* Security Notice explaining no password is required */}
                  <div style={{
                    backgroundColor: '#faf5ff',
                    border: '1px solid #e9d5ff',
                    borderRadius: '8px',
                    padding: '12px 16px',
                    marginBottom: '16px',
                    fontSize: '12px',
                    color: '#6b21a8',
                    lineHeight: '1.5',
                  }}>
                    <div style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                      </svg>
                      Secure Invitation Flow (No Password Entry)
                    </div>
                    The Primary Admin account will be created in an invited/pending state. A secure activation email will be automatically sent to the administrator to set their password.
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '14px' }}>
                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Admin Full Name <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. Ramesh Kumar"
                        value={form.admin_name}
                        onChange={(e) => handleInputChange('admin_name', e.target.value)}
                        required
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Admin Email (Login ID) <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="email"
                        placeholder="e.g. ramesh@company.com"
                        value={form.admin_email}
                        onChange={(e) => handleInputChange('admin_email', e.target.value)}
                        required
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                        Admin Mobile Number <span style={{ color: '#ef4444' }}>*</span>
                      </label>
                      <input
                        type="text"
                        placeholder="e.g. +91 9876543210"
                        value={form.admin_mobile}
                        onChange={(e) => handleInputChange('admin_mobile', e.target.value)}
                        required
                        style={{
                          width: '100%',
                          padding: '9px 12px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '13px',
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>
                  </div>
                </div>

              </div>

              {/* Modal Footer */}
              <div style={{
                padding: '16px 28px',
                borderTop: '1px solid #e2e8f0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end',
                gap: '12px',
                backgroundColor: '#f8fafc',
              }}>
                <button
                  type="button"
                  onClick={() => {
                    setShowAddModal(false);
                    setFormError('');
                  }}
                  style={{
                    padding: '9px 18px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: '#ffffff',
                    color: '#475569',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={submitting}
                  style={{
                    padding: '9px 24px',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: '#7c3aed',
                    color: '#ffffff',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: submitting ? 'not-allowed' : 'pointer',
                    opacity: submitting ? 0.7 : 1,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  {submitting && <div className="spinner" style={{ width: '14px', height: '14px', borderWidth: '2px' }} />}
                  {submitting ? 'Creating Branch...' : 'Create Branch & Send Activation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── 2. SUCCESS CONFIRMATION MODAL ─────────────────────────────────── */}
      {createdBranchData && (
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
          zIndex: 110,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            maxWidth: '560px',
            width: '100%',
            padding: '28px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.2)',
            textAlign: 'center',
          }}>
            <div style={{
              width: '60px',
              height: '60px',
              borderRadius: '50%',
              backgroundColor: '#dcfce7',
              color: '#16a34a',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px auto',
            }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>

            <h3 style={{ margin: '0 0 8px 0', fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>
              Branch Created Successfully!
            </h3>
            <p style={{ margin: '0 0 20px 0', color: '#475569', fontSize: '14px' }}>
              {createdBranchData.message}
            </p>

            {/* Branch Summary Box */}
            <div style={{
              backgroundColor: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '8px',
              padding: '14px 18px',
              textAlign: 'left',
              fontSize: '13px',
              marginBottom: '20px',
              lineHeight: '1.6',
            }}>
              <div><strong>Branch Name:</strong> {createdBranchData.branch?.name}</div>
              <div><strong>Branch Code:</strong> {createdBranchData.branch?.code}</div>
              <div><strong>Location:</strong> {createdBranchData.branch?.city}, {createdBranchData.branch?.state}</div>
              <div><strong>Assigned Admin:</strong> {createdBranchData.branch?.primary_admin?.email}</div>
            </div>

            {/* Direct Activation URL link box */}
            {createdBranchData.activation_url && (
              <div style={{
                backgroundColor: '#faf5ff',
                border: '1px solid #e9d5ff',
                borderRadius: '8px',
                padding: '12px 16px',
                marginBottom: '24px',
                textAlign: 'left',
              }}>
                <div style={{ fontSize: '11px', fontWeight: 700, color: '#7c3aed', marginBottom: '6px', textTransform: 'uppercase' }}>
                  Direct Activation Link (Also Sent via Email)
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <input
                    type="text"
                    readOnly
                    value={createdBranchData.activation_url}
                    style={{
                      flex: 1,
                      padding: '7px 10px',
                      borderRadius: '4px',
                      border: '1px solid #d8b4fe',
                      backgroundColor: '#ffffff',
                      fontSize: '11px',
                      color: '#475569',
                      outline: 'none',
                    }}
                  />
                  <button
                    onClick={() => handleCopyLink(createdBranchData.activation_url)}
                    style={{
                      padding: '7px 14px',
                      borderRadius: '4px',
                      border: 'none',
                      backgroundColor: copiedLink ? '#16a34a' : '#7c3aed',
                      color: '#ffffff',
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
            )}

            <button
              onClick={() => setCreatedBranchData(null)}
              style={{
                width: '100%',
                padding: '11px',
                borderRadius: '8px',
                border: 'none',
                backgroundColor: '#0f172a',
                color: '#ffffff',
                fontSize: '14px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Done &amp; Return to Branches
            </button>
          </div>
        </div>
      )}

      {/* ── 3. VIEW BRANCH DETAILS MODAL ──────────────────────────────────── */}
      {selectedBranch && (
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
          zIndex: 100,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '16px',
            maxWidth: '650px',
            width: '100%',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.2)',
            overflow: 'hidden',
          }}>
            <div style={{
              padding: '20px 24px',
              borderBottom: '1px solid #e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <div>
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#6366f1' }}>
                  {selectedBranch.code} &bull; {selectedBranch.branch_type || 'Branch'}
                </span>
                <h3 style={{ margin: '2px 0 0 0', fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>
                  {selectedBranch.name}
                </h3>
              </div>
              <button
                onClick={() => setSelectedBranch(null)}
                style={{ background: 'none', border: 'none', fontSize: '22px', color: '#64748b', cursor: 'pointer' }}
              >
                &times;
              </button>
            </div>

            <div style={{ padding: '24px', overflowY: 'auto', flex: 1, fontSize: '13px', lineHeight: '1.6' }}>
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '13px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                  Location &amp; Address
                </h4>
                <div style={{ backgroundColor: '#f8fafc', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div><strong>Address 1:</strong> {selectedBranch.address_line1 || selectedBranch.address || 'Not specified'}</div>
                  {selectedBranch.address_line2 && <div><strong>Address 2:</strong> {selectedBranch.address_line2}</div>}
                  <div><strong>City / District:</strong> {selectedBranch.city || '—'} / {selectedBranch.district || '—'}</div>
                  <div><strong>State &amp; PIN:</strong> {selectedBranch.state || '—'} - {selectedBranch.pincode || '—'}</div>
                  <div><strong>Country:</strong> {selectedBranch.country || 'India'}</div>
                  {selectedBranch.contact_person && <div><strong>Contact Person:</strong> {selectedBranch.contact_person}</div>}
                  {(selectedBranch.branch_contact_number || selectedBranch.contact_phone) && <div><strong>Contact:</strong> {selectedBranch.branch_contact_number || selectedBranch.contact_phone}</div>}
                  {(selectedBranch.branch_email || selectedBranch.contact_email) && <div><strong>Branch Email:</strong> {selectedBranch.branch_email || selectedBranch.contact_email}</div>}
                </div>
              </div>

              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '13px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                  Branch Tax Information
                </h4>
                <div style={{ backgroundColor: '#f8fafc', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div><strong>GST Registered:</strong> {selectedBranch.gst_registered ? 'Yes' : 'No'}</div>
                  {selectedBranch.gst_registered && (
                    <>
                      <div><strong>GSTIN:</strong> <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>{selectedBranch.gstin}</span></div>
                      <div><strong>GST Registration Type:</strong> {selectedBranch.gst_type || 'Regular'}</div>
                    </>
                  )}
                </div>
              </div>

              <div>
                <h4 style={{ margin: '0 0 6px 0', fontSize: '13px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                  Primary Administrator
                </h4>
                <div style={{ backgroundColor: '#faf5ff', padding: '12px 16px', borderRadius: '8px', border: '1px solid #e9d5ff' }}>
                  {selectedBranch.primary_admin ? (
                    <>
                      <div><strong>Name:</strong> {selectedBranch.primary_admin.name}</div>
                      <div><strong>Email:</strong> {selectedBranch.primary_admin.email}</div>
                      {selectedBranch.primary_admin.mobile && <div><strong>Mobile:</strong> {selectedBranch.primary_admin.mobile}</div>}
                      <div><strong>Activation Status:</strong> {selectedBranch.primary_admin.is_activated ? 'Active' : 'Pending Activation'}</div>
                    </>
                  ) : (
                    <div style={{ color: '#94a3b8' }}>No primary admin assigned yet.</div>
                  )}
                </div>
              </div>
            </div>

            <div style={{ padding: '14px 24px', borderTop: '1px solid #e2e8f0', backgroundColor: '#f8fafc', textAlign: 'right' }}>
              <button
                onClick={() => setSelectedBranch(null)}
                style={{
                  padding: '8px 18px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  color: '#475569',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Custom Styled Confirmation Modal ─────────────────────────────── */}
      <ConfirmModal
        isOpen={!!confirmDialog}
        title={confirmDialog?.title}
        message={confirmDialog?.message}
        details={confirmDialog?.details}
        confirmText={confirmDialog?.confirmText || 'Confirm'}
        cancelText={confirmDialog?.cancelText || 'Cancel'}
        variant={confirmDialog?.variant || 'primary'}
        loading={!!actionLoadingId}
        onConfirm={confirmDialog?.onConfirm}
        onCancel={() => setConfirmDialog(null)}
      />

    </div>
  );
}

