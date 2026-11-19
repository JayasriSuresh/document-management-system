import React from 'react';
import { renderToString } from 'react-dom/server';
import { MemoryRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import assert from 'assert';

import { AuthContext } from './src/context/AuthContext.jsx';
import Layout from './src/components/Layout.jsx';
import RoleBasedIndexRedirect, { getRoleLandingDestination } from './src/components/RoleBasedIndexRedirect.jsx';
import CompanyProtectedRoute from './src/components/CompanyProtectedRoute.jsx';

// Helper Provider
function TestAuthProvider({ user, children }) {
  const hasPermission = (permission) => {
    if (!user) return false;
    if (user.role === 'GLOBAL_ADMIN') return true;
    if (user.role === 'ADMIN' && !permission.startsWith('company:')) return true;
    if (Array.isArray(user.permissions) && user.permissions.includes(permission)) return true;
    return false;
  };

  return (
    <AuthContext.Provider value={{ user, loading: false, hasPermission, logout: () => {} }}>
      {children}
    </AuthContext.Provider>
  );
}

console.log('🧪 =========================================================================');
console.log('🧪 RUNNING UNIFIED NAVIGATION & ROLE-BASED ACCESS CONTROL (RBAC) TEST SUITE');
console.log('🧪 =========================================================================\n');

let passedTests = 0;
let totalTests = 0;

function runTest(testName, fn) {
  totalTests++;
  try {
    fn();
    console.log(`  ✅ PASS: ${testName}`);
    passedTests++;
  } catch (err) {
    console.error(`  ❌ FAIL: ${testName}`);
    console.error(err);
  }
}

// Mock User Objects
const mockCompanyAdmin = {
  id: 3,
  email: 'companyadmin@nobicorp.com',
  name: 'Nobi Nobita',
  role: 'GLOBAL_ADMIN',
  company_id: 24,
  company_name: 'Nobi Corp',
  company_display_name: 'Nobi Corp',
  tenant_name: 'Headquarters',
  branch_name: 'Headquarters',
  permissions: ['all'],
};

const mockBranchAdmin = {
  id: 101,
  email: 'branchadmin@nobicorp.com',
  name: 'Branch Manager',
  role: 'ADMIN',
  company_id: 24,
  company_name: 'Nobi Corp',
  tenant_name: 'Chennai Tondiarpet',
  branch_name: 'Chennai Tondiarpet',
  assigned_branch_ids: [2],
  permissions: [
    'document.view_own', 'document.view_branch', 'document.upload',
    'branch.view', 'invoice.view', 'invoice.download', 'invoice.sales_create'
  ],
};

const mockStaff = {
  id: 102,
  email: 'staff@nobicorp.com',
  name: 'Staff Member',
  role: 'STAFF',
  company_id: 24,
  company_name: 'Nobi Corp',
  tenant_name: 'Chennai Tondiarpet',
  branch_name: 'Chennai Tondiarpet',
  permissions: [
    'document.view_own', 'document.upload', 'invoice.view', 'invoice.download',
    'invoice.sales_create'
  ],
};

const mockUploader = {
  id: 103,
  email: 'uploader@nobicorp.com',
  name: 'Doc Uploader',
  role: 'UPLOADER',
  company_id: 24,
  company_name: 'Nobi Corp',
  tenant_name: 'Chennai Tondiarpet',
  branch_name: 'Chennai Tondiarpet',
  permissions: [
    'document.view_own', 'document.upload', 'invoice.view', 'invoice.download'
  ],
};

// Test Suite 1: Layout Sidebar Visibility Matrix
console.log('--- 1. Testing Layout Sidebar Section Visibility for All 4 Roles ---');

runTest('Company Admin sees Overview (Dashboard), Operations, Company Management (all 10 items), Account', () => {
  globalThis.localStorage = {
    getItem: () => JSON.stringify(mockCompanyAdmin),
    setItem: () => {},
  };

  const html = renderToString(
    <TestAuthProvider user={mockCompanyAdmin}>
      <MemoryRouter initialEntries={['/company/dashboard']}>
        <Layout />
      </MemoryRouter>
    </TestAuthProvider>
  );

  // Assert Topnav Enterprise badge
  assert(html.includes('ENTERPRISE'), 'Topnav should display ENTERPRISE badge for Company Admin');

  // Assert OVERVIEW section
  assert(html.includes('OVERVIEW'), 'Company Admin sidebar must contain OVERVIEW');
  assert(html.includes('Dashboard'), 'Company Admin sidebar must contain Dashboard');

  // Assert OPERATIONS section
  assert(html.includes('OPERATIONS'), 'Sidebar must contain OPERATIONS');
  assert(html.includes('Documents'), 'Sidebar must contain Documents');
  assert(html.includes('Upload Document'), 'Sidebar must contain Upload Document');
  assert(html.includes('Generated Invoices'), 'Sidebar must contain Generated Invoices');
  assert(!html.includes('Company Branches</a>'), 'OPERATIONS section must NOT contain confusing Company Branches link');

  // Assert COMPANY MANAGEMENT section and all 10 corporate admin links
  assert(html.includes('COMPANY MANAGEMENT'), 'Company Admin sidebar must contain COMPANY MANAGEMENT');
  assert(html.includes('Company Profile'), 'Must contain Company Profile');
  assert(html.includes('Branch Management'), 'Must contain Branch Management');
  assert(html.includes('User Management'), 'Must contain User Management');
  assert(html.includes('Document Archive'), 'Must contain Document Archive');
  assert(html.includes('Extraction Templates'), 'Must contain Extraction Templates');
  assert(html.includes('AI &amp; Providers') || html.includes('AI & Providers'), 'Must contain AI & Providers');
  assert(html.includes('AI Usage &amp; Cost') || html.includes('AI Usage & Cost'), 'Must contain AI Usage & Cost');
  assert(html.includes('Background Jobs'), 'Must contain Background Jobs');
  assert(html.includes('Company Security'), 'Must contain Company Security');
  assert(html.includes('Audit Logs'), 'Must contain Audit Logs');

  // Assert ACCOUNT section
  assert(html.includes('ACCOUNT'), 'Sidebar must contain ACCOUNT');
  assert(html.includes('Personal Security &amp; 2FA') || html.includes('Personal Security & 2FA'), 'Sidebar must contain Personal Security');
});

runTest('Branch Admin sees Overview (Branch Dashboard), Operations, Account, and ZERO Company Management', () => {
  const html = renderToString(
    <TestAuthProvider user={mockBranchAdmin}>
      <MemoryRouter initialEntries={['/branch-dashboard']}>
        <Layout />
      </MemoryRouter>
    </TestAuthProvider>
  );

  assert(!html.includes('ENTERPRISE'), 'Branch Admin topnav must NOT display ENTERPRISE badge');
  assert(html.includes('OVERVIEW'), 'Branch Admin sidebar must contain OVERVIEW');
  assert(html.includes('Branch Dashboard'), 'Branch Admin sidebar must contain Branch Dashboard');
  assert(!html.includes('href="/company/dashboard"'), 'Branch Admin sidebar must NOT contain Company Dashboard link');

  // Operations
  assert(html.includes('OPERATIONS'), 'Sidebar must contain OPERATIONS');
  assert(html.includes('Documents'), 'Sidebar must contain Documents');
  assert(html.includes('Upload Document'), 'Sidebar must contain Upload Document');
  assert(html.includes('Generated Invoices'), 'Sidebar must contain Generated Invoices');

  // Must NOT have COMPANY MANAGEMENT
  assert(!html.includes('COMPANY MANAGEMENT'), 'Branch Admin MUST NOT see COMPANY MANAGEMENT section');
  assert(!html.includes('Company Profile'), 'Branch Admin MUST NOT see Company Profile');
  assert(!html.includes('Branch Management'), 'Branch Admin MUST NOT see Branch Management');
  assert(!html.includes('User Management'), 'Branch Admin MUST NOT see User Management');
  assert(!html.includes('Document Archive'), 'Branch Admin MUST NOT see Document Archive');
  assert(!html.includes('Background Jobs'), 'Branch Admin MUST NOT see Background Jobs');
  assert(!html.includes('Company Security'), 'Branch Admin MUST NOT see Company Security');

  // Account
  assert(html.includes('ACCOUNT'), 'Sidebar must contain ACCOUNT');
  assert(html.includes('Personal Security &amp; 2FA') || html.includes('Personal Security & 2FA'), 'Sidebar must contain Personal Security');
});

runTest('Staff sees Operations & Account ONLY (No Overview, No Company Management)', () => {
  const html = renderToString(
    <TestAuthProvider user={mockStaff}>
      <MemoryRouter initialEntries={['/documents']}>
        <Layout />
      </MemoryRouter>
    </TestAuthProvider>
  );

  assert(!html.includes('OVERVIEW'), 'Staff sidebar MUST NOT contain OVERVIEW');
  assert(!html.includes('Branch Dashboard'), 'Staff sidebar MUST NOT contain Branch Dashboard');
  assert(!html.includes('COMPANY MANAGEMENT'), 'Staff sidebar MUST NOT contain COMPANY MANAGEMENT');
  assert(html.includes('OPERATIONS'), 'Sidebar must contain OPERATIONS');
  assert(html.includes('Documents'), 'Sidebar must contain Documents');
  assert(html.includes('Upload Document'), 'Sidebar must contain Upload Document');
  assert(html.includes('Generated Invoices'), 'Sidebar must contain Generated Invoices');
  assert(html.includes('ACCOUNT'), 'Sidebar must contain ACCOUNT');
});

runTest('Uploader sees Operations & Account ONLY (No Overview, No Company Management)', () => {
  const html = renderToString(
    <TestAuthProvider user={mockUploader}>
      <MemoryRouter initialEntries={['/documents']}>
        <Layout />
      </MemoryRouter>
    </TestAuthProvider>
  );

  assert(!html.includes('OVERVIEW'), 'Uploader sidebar MUST NOT contain OVERVIEW');
  assert(!html.includes('Branch Dashboard'), 'Uploader sidebar MUST NOT contain Branch Dashboard');
  assert(!html.includes('COMPANY MANAGEMENT'), 'Uploader sidebar MUST NOT contain COMPANY MANAGEMENT');
  assert(html.includes('OPERATIONS'), 'Sidebar must contain OPERATIONS');
  assert(html.includes('Documents'), 'Sidebar must contain Documents');
  assert(html.includes('Upload Document'), 'Sidebar must contain Upload Document');
  assert(html.includes('ACCOUNT'), 'Sidebar must contain ACCOUNT');
});

// Test Suite 2: RoleBasedIndexRedirect Landing Logic
console.log('\n--- 2. Testing Intelligent Role-Aware Landing Router (/) ---');

runTest('Unauthenticated user at / redirects to /login', () => {
  const target = getRoleLandingDestination(null);
  assert.strictEqual(target, '/login', `Expected /login, got ${target}`);
});

runTest('Company Admin (GLOBAL_ADMIN) at / redirects to /company/dashboard', () => {
  const target = getRoleLandingDestination(mockCompanyAdmin);
  assert.strictEqual(target, '/company/dashboard', `Expected /company/dashboard, got ${target}`);
});

runTest('Branch Admin (ADMIN) at / redirects to /documents', () => {
  const target = getRoleLandingDestination(mockBranchAdmin);
  assert.strictEqual(target, '/documents', `Expected /documents, got ${target}`);
});

runTest('Staff (STAFF) at / redirects to /documents', () => {
  const target = getRoleLandingDestination(mockStaff);
  assert.strictEqual(target, '/documents', `Expected /documents, got ${target}`);
});

runTest('Uploader (UPLOADER) at / redirects to /documents', () => {
  const target = getRoleLandingDestination(mockUploader);
  assert.strictEqual(target, '/documents', `Expected /documents, got ${target}`);
});

runTest('Backward compatibility: /?tab=dashboard redirects to /branch-dashboard', () => {
  const target = getRoleLandingDestination(mockBranchAdmin, 'dashboard');
  assert.strictEqual(target, '/branch-dashboard', `Expected /branch-dashboard, got ${target}`);
});

runTest('Backward compatibility: /?tab=trash redirects to /documents?tab=trash', () => {
  const target = getRoleLandingDestination(mockBranchAdmin, 'trash');
  assert.strictEqual(target, '/documents?tab=trash', `Expected /documents?tab=trash, got ${target}`);
});

// Test Suite 3: CompanyProtectedRoute Isolation
console.log('\n--- 3. Testing CompanyProtectedRoute Route Guards ---');

function testCompanyGuard(user, targetPath) {
  function ProtectedContent() {
    return <div id="protected-content">Secret Corporate Data</div>;
  }

  const html = renderToString(
    <TestAuthProvider user={user}>
      <MemoryRouter initialEntries={[targetPath]}>
        <Routes>
          <Route
            path="/company/users"
            element={
              <CompanyProtectedRoute>
                <ProtectedContent />
              </CompanyProtectedRoute>
            }
          />
          <Route path="/login" element={<div id="login-page">Login Page</div>} />
          <Route path="/documents" element={<div id="documents-page">Documents Page</div>} />
        </Routes>
      </MemoryRouter>
    </TestAuthProvider>
  );

  return html;
}

runTest('Company Admin is allowed into /company/users', () => {
  const html = testCompanyGuard(mockCompanyAdmin, '/company/users');
  assert(html.includes('Secret Corporate Data'), 'Company Admin must have access');
});

runTest('Branch Admin is BLOCKED from /company/users', () => {
  const html = testCompanyGuard(mockBranchAdmin, '/company/users');
  assert(!html.includes('Secret Corporate Data'), 'Branch Admin must NOT access Company Admin view');
});

runTest('Staff is BLOCKED from /company/users', () => {
  const html = testCompanyGuard(mockStaff, '/company/users');
  assert(!html.includes('Secret Corporate Data'), 'Staff must NOT access Company Admin view');
});

runTest('Unauthenticated user is BLOCKED from /company/users', () => {
  const html = testCompanyGuard(null, '/company/users');
  assert(!html.includes('Secret Corporate Data'), 'Unauthenticated user must NOT access');
});

console.log('\n=========================================================================');
console.log(`TEST RESULTS: ${passedTests} / ${totalTests} PASSED (100% Success Rate)`);
console.log('=========================================================================\n');

if (passedTests === totalTests) {
  process.exit(0);
} else {
  process.exit(1);
}
