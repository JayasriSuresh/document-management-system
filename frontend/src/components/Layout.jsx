import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, NavLink, Outlet, useLocation } from 'react-router-dom';
import { api } from '../api';

// Professional SVG Icons
const IconDashboard = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
  </svg>
);

const IconDocuments = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
  </svg>
);

const IconInvoices = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2" ry="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" />
  </svg>
);

const IconUpload = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16 16 12 12 8 16" /><line x1="12" y1="12" x2="12" y2="21" /><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
  </svg>
);

const IconCompanyProfile = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 21h18M3 7v14M21 7v14M6 11h4M6 15h4M14 11h4M14 15h4M9 3h6v4H9z" />
  </svg>
);

const IconBranchManagement = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="6" y1="3" x2="6" y2="15" /><circle cx="18" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><path d="M18 9a9 9 0 0 1-9 9" />
  </svg>
);

const IconUserManagement = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);

const IconArchive = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" /><line x1="12" y1="11" x2="12" y2="17" /><line x1="9" y1="14" x2="15" y2="14" />
  </svg>
);

const IconTemplates = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 3v18" /><path d="M14 9h4" /><path d="M14 15h4" />
  </svg>
);

const IconAI = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

const IconCost = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
  </svg>
);

const IconJobs = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </svg>
);

const IconCompanySecurity = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);

const IconAudit = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
  </svg>
);

const IconPersonalSecurity = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);

const IconMenu = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
  </svg>
);

const IconSignOut = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

export default function Layout() {
  const { user, logout, hasPermission } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Sidebar responsive state
  const [sidebarOpen, setSidebarOpen] = useState(() => (typeof window !== 'undefined' ? window.innerWidth >= 1024 : true));

  // Real-time metadata badges for Company Admin
  const [branchesCount, setBranchesCount] = useState(0);
  const [failedJobsCount, setFailedJobsCount] = useState(0);

  // Resize listener
  useEffect(() => {
    if (typeof window === 'undefined') return;
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

  // Auto-close sidebar on mobile navigation
  useEffect(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      setSidebarOpen(false);
    }
  }, [location.pathname]);

  // Load badge counts for Company Admin
  useEffect(() => {
    if (user?.role === 'GLOBAL_ADMIN') {
      api.listCompanyBranches()
        .then(b => {
          if (Array.isArray(b)) setBranchesCount(b.length);
        })
        .catch(() => {});

      api.getDashboardJobs({ status: 'failed', page_size: 1 })
        .then(j => {
          if (j?.total !== undefined) setFailedJobsCount(j.total);
        })
        .catch(() => {});
    }
  }, [user]);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isCompanyAdmin = user?.role === 'GLOBAL_ADMIN';
  const isBranchAdmin = user?.role === 'ADMIN';

  return (
    <div className="app-shell">
      {/* ── TOP NAVIGATION BAR ──────────────────────────── */}
      <header className="topnav" role="banner">
        <div className="topnav-left">
          {/* Hamburger toggle */}
          <button
            className="topnav-toggle"
            onClick={() => setSidebarOpen(o => !o)}
            aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
            title={sidebarOpen ? 'Close menu' : 'Open menu'}
          >
            <IconMenu />
          </button>

          {/* Unified Brand Wordmark */}
          <div className="topnav-brand">
            <span className="topnav-brand-name">DMS</span>
          </div>
        </div>

        {/* User profile & Sign Out */}
        <div className="topnav-right">
          <div className="topnav-user">
            <div className="topnav-user-info">
              <div className="topnav-user-name">{user?.name}</div>
              <div
                className="topnav-user-role"
                style={{ color: isCompanyAdmin ? '#ef4444' : 'var(--text-muted)' }}
              >
                {isCompanyAdmin ? 'Company Administrator' : `${user?.role?.replace('_', ' ')} · ${user?.tenant_name || user?.branch_name || 'Branch'}`}
              </div>
            </div>
            <div
              className="topnav-avatar"
              style={{
                backgroundColor: isCompanyAdmin ? '#fee2e2' : 'var(--red-primary)',
                color: isCompanyAdmin ? '#b91c1c' : '#fff',
              }}
              title={user?.name}
            >
              {user?.name?.[0]?.toUpperCase()}
            </div>
          </div>

          <div className="topnav-divider" />

          <button className="topnav-signout" onClick={handleLogout} title="Sign out">
            <IconSignOut />
            Sign out
          </button>
        </div>
      </header>

      {/* ── MOBILE OVERLAY ───────────────────────────────── */}
      {sidebarOpen && typeof window !== 'undefined' && window.innerWidth < 1024 && (
        <div
          className="sidebar-overlay visible"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── UNIFIED APPLICATION SIDEBAR ─────────────────── */}
      <aside
        className={`sidebar ${sidebarOpen ? 'sidebar-open' : 'sidebar-collapsed'}`}
        aria-label="Main navigation"
      >
        {/* Company Identity Header */}
        <div className="sidebar-brand">
          {user?.company_logo_url ? (
            <div className="sidebar-company-logo-wrapper">
              <img
                src={user.company_logo_url}
                alt={user?.company_display_name || user?.company_name || 'Company'}
                className="sidebar-company-logo-img"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                  const fallback = e.currentTarget.parentElement?.querySelector('.sidebar-company-logo-fallback');
                  if (fallback) fallback.style.display = 'flex';
                }}
              />
              <div className="sidebar-company-logo sidebar-company-logo-fallback" style={{ display: 'none' }}>
                {(user?.company_name || user?.company_display_name || 'CO')
                  .split(' ')
                  .filter(Boolean)
                  .slice(0, 2)
                  .map(w => w[0])
                  .join('')
                  .toUpperCase() || 'CO'}
              </div>
            </div>
          ) : (
            <div className="sidebar-company-logo">
              {(user?.company_name || user?.company_display_name || 'CO')
                .split(' ')
                .filter(Boolean)
                .slice(0, 2)
                .map(w => w[0])
                .join('')
                .toUpperCase() || 'CO'}
            </div>
          )}
          <div style={{ overflow: 'hidden' }}>
            <div
              className="sidebar-company-name"
              title={user?.company_display_name || user?.company_name || 'Your Company'}
            >
              {user?.company_display_name || user?.company_name || 'Your Company'}
            </div>
            <div
              className="sidebar-company-hint"
              title={isCompanyAdmin ? 'Headquarters' : (user?.tenant_name || user?.branch_name || 'Branch')}
            >
              {isCompanyAdmin ? 'Headquarters' : (user?.tenant_name || user?.branch_name || 'Branch')}
            </div>
          </div>
        </div>

        {/* Navigation items by section */}
        <nav className="sidebar-nav" role="navigation">
          {/* 1. OVERVIEW SECTION (Company Admin & Branch Admin) */}
          {(isCompanyAdmin || isBranchAdmin) && (
            <>
              <span className="nav-section-label">OVERVIEW</span>
              {isCompanyAdmin && (
                <NavLink
                  to="/company/dashboard"
                  className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                >
                  <span className="nav-icon"><IconDashboard /></span>
                  Dashboard
                </NavLink>
              )}
              {isBranchAdmin && (
                <NavLink
                  to="/branch-dashboard"
                  className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                >
                  <span className="nav-icon"><IconDashboard /></span>
                  Branch Dashboard
                </NavLink>
              )}
            </>
          )}

          {/* 2. OPERATIONS SECTION (All Roles based on verified permissions) */}
          <span className="nav-section-label" style={{ marginTop: (isCompanyAdmin || isBranchAdmin) ? '6px' : '0' }}>
            OPERATIONS
          </span>

          <NavLink
            to="/documents"
            className={() => `nav-link${(location.pathname === '/documents' || location.pathname === '/') ? ' active' : ''}`}
          >
            <span className="nav-icon"><IconDocuments /></span>
            Documents
          </NavLink>

          {hasPermission('document.upload') && (
            <NavLink
              to="/upload"
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              <span className="nav-icon"><IconUpload /></span>
              Upload Document
            </NavLink>
          )}

          {hasPermission('invoice.view') && (
            <NavLink
              to="/invoices"
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              <span className="nav-icon"><IconInvoices /></span>
              Generated Invoices
            </NavLink>
          )}

          {/* 3. COMPANY MANAGEMENT SECTION (Company Admin Only) */}
          {isCompanyAdmin && (
            <>
              <span className="nav-section-label" style={{ marginTop: '8px' }}>COMPANY MANAGEMENT</span>

              <NavLink
                to="/company/profile"
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span className="nav-icon"><IconCompanyProfile /></span>
                Company Profile
              </NavLink>

              <NavLink
                to="/company/branches"
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                style={{ justifyContent: 'space-between' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                  <span className="nav-icon"><IconBranchManagement /></span>
                  Branch Management
                </div>
                {branchesCount > 0 && (
                  <span
                    style={{
                      backgroundColor: location.pathname === '/company/branches' ? '#fecaca' : '#e2e8f0',
                      color: location.pathname === '/company/branches' ? '#b91c1c' : '#64748b',
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '2px 7px',
                      borderRadius: '10px',
                    }}
                  >
                    {branchesCount}
                  </span>
                )}
              </NavLink>

              <NavLink
                to="/company/users"
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span className="nav-icon"><IconUserManagement /></span>
                User Management
              </NavLink>

              <NavLink
                to="/company/documents"
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span className="nav-icon"><IconArchive /></span>
                Document Archive
              </NavLink>

              <NavLink
                to="/company/templates"
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span className="nav-icon"><IconTemplates /></span>
                Extraction Templates
              </NavLink>

              <NavLink
                to="/company/ai"
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span className="nav-icon"><IconAI /></span>
                AI & Providers
              </NavLink>

              <NavLink
                to="/company/ai-usage"
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span className="nav-icon"><IconCost /></span>
                AI Usage & Cost
              </NavLink>

              <NavLink
                to="/company/jobs"
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                style={{ justifyContent: 'space-between' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
                  <span className="nav-icon"><IconJobs /></span>
                  Background Jobs
                </div>
                {failedJobsCount > 0 && (
                  <span
                    style={{
                      backgroundColor: '#ef4444',
                      color: '#ffffff',
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '2px 7px',
                      borderRadius: '10px',
                    }}
                  >
                    {failedJobsCount}
                  </span>
                )}
              </NavLink>

              <NavLink
                to="/company/security"
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span className="nav-icon"><IconCompanySecurity /></span>
                Company Security
              </NavLink>

              <NavLink
                to="/company/audit-logs"
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span className="nav-icon"><IconAudit /></span>
                Audit Logs
              </NavLink>
            </>
          )}

          {/* 4. ACCOUNT SECTION (All Authenticated Users) */}
          <span className="nav-section-label" style={{ marginTop: '8px' }}>ACCOUNT</span>

          <NavLink
            to="/security"
            className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          >
            <span className="nav-icon"><IconPersonalSecurity /></span>
            Personal Security & 2FA
          </NavLink>
        </nav>

        {/* Footer — tenant info */}
        <div className="sidebar-footer">
          <div className="sidebar-tenant">
            <span className="tenant-status-dot" style={{ backgroundColor: '#22c55e' }} />
            {isCompanyAdmin ? `${user?.tenant_name || 'Company'} — Active` : `${user?.tenant_name || user?.branch_name || 'Branch'} — Active`}
          </div>
        </div>
      </aside>

      {/* ── MAIN CONTENT ────────────────────────────────── */}
      <main
        className={`main-content ${sidebarOpen && (typeof window === 'undefined' || window.innerWidth >= 1024) ? 'with-sidebar' : 'no-sidebar'}`}
        id="main-content"
      >
        <Outlet />
      </main>
    </div>
  );
}
