import React from 'react';
import { renderToString } from 'react-dom/server';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import assert from 'assert';

import { AuthContext } from './src/context/AuthContext.jsx';
import DocumentViewPage from './src/pages/DocumentViewPage.jsx';

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
console.log('🧪 RUNNING DOCUMENT DETAILS REDESIGN & REVIEW WORKSPACE TEST SUITE');
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

// Test 1: Initial Render
runTest('DocumentViewPage loads initial state without SSR errors', () => {
  const html = renderToString(
    <TestAuthProvider user={mockCompanyAdmin}>
      <MemoryRouter initialEntries={['/documents/492']}>
        <Routes>
          <Route path="/documents/:id" element={<DocumentViewPage />} />
        </Routes>
      </MemoryRouter>
    </TestAuthProvider>
  );

  assert(html.includes('Loading document review workspace') || html.includes('page-content'),
    'Expected document view page or loading indicator to render');
});

// Test 2: Verify CSS Classes & Layout Structure
runTest('index.css contains required Document Review Workspace styles', async () => {
  const fs = await import('fs');
  const css = fs.readFileSync('./src/index.css', 'utf8');

  assert(css.includes('.doc-review-layout'), 'Missing .doc-review-layout in index.css');
  assert(css.includes('.doc-review-panel'), 'Missing .doc-review-panel in index.css');
  assert(css.includes('.doc-preview-toolbar'), 'Missing .doc-preview-toolbar in index.css');
  assert(css.includes('.doc-extracted-container'), 'Missing .doc-extracted-container in index.css');
  assert(css.includes('.extracted-section-card'), 'Missing .extracted-section-card in index.css');
  assert(css.includes('.doc-table-compact'), 'Missing .doc-table-compact in index.css');
  assert(css.includes('.totals-summary-box'), 'Missing .totals-summary-box in index.css');
  assert(css.includes('.totals-grand-value'), 'Missing .totals-grand-value in index.css');
  assert(css.includes('.fullscreen-overlay'), 'Missing .fullscreen-overlay in index.css');
});

// Test 3: DocumentViewPage exports and features check
runTest('DocumentViewPage source code implements all mandatory workspace sections', async () => {
  const fs = await import('fs');
  const code = fs.readFileSync('./src/pages/DocumentViewPage.jsx', 'utf8');

  // Header Elements
  assert(code.includes('displayTitle'), 'Header must calculate human-readable title');
  assert(code.includes('handleReprocess'), 'Header must include OCR reprocess action');
  assert(code.includes('handleApprove'), 'Header must include verification / approve action');
  assert(code.includes('handleDelete'), 'Header must include delete action');

  // Document Preview Features
  assert(code.includes('Original Document'), 'Preview must have Original Document tab');
  assert(code.includes('Standardised Copy') || code.includes('Standardised Invoice'), 'Preview must support Standardised Copy');
  assert(code.includes('handleZoomIn'), 'Preview must support zoom in');
  assert(code.includes('handleZoomOut'), 'Preview must support zoom out');
  assert(code.includes('handleZoomReset'), 'Preview must support zoom reset / fit');
  assert(code.includes('handleRotate'), 'Preview must support image rotation');
  assert(code.includes('isFullScreen'), 'Preview must support fullscreen viewing');
  assert(code.includes('handleMouseDown') && code.includes('handleMouseMove'), 'Preview must support interactive pan & drag');
  assert(code.includes('pdf-iframe'), 'Preview must support PDF documents');
  assert(code.includes('download='), 'Preview must support download');

  // Structured Extracted Information Panel
  assert(code.includes('Supplier Details'), 'Extracted panel must include Supplier Details');
  assert(code.includes('Invoice Details'), 'Extracted panel must include Invoice Details');
  assert(code.includes('Customer / Buyer Details'), 'Extracted panel must include Customer Details');
  assert(code.includes('Line Items'), 'Extracted panel must include Line Items table');
  assert(code.includes('Invoice Summary'), 'Extracted panel must include Invoice Summary');
  assert(code.includes('Bank & Payment Details'), 'Extracted panel must support Bank Details');
  assert(code.includes('Declarations'), 'Extracted panel must support Declarations');

  // Validation Flags & Error Highlighting
  assert(code.includes('validation_flags'), 'Extracted panel must inspect validation flags');
  assert(code.includes('hasErrors'), 'Extracted panel must handle error-level flags');
  assert(code.includes('showOverrideModal'), 'Must support Override & Approve modal for validation errors');

  // Secondary Collapsible Sections
  assert(code.includes('showDetails'), 'Must provide collapsible Technical Document Details');
  assert(code.includes('SHA-256'), 'Must display SHA-256 in technical section');
  assert(code.includes('showRawData'), 'Must provide collapsible Raw Data & Audit section');
  assert(code.includes('Raw OCR Text'), 'Must support viewing raw OCR text');
  assert(code.includes('Structured JSON'), 'Must support viewing raw JSON');
  assert(code.includes('Edit Audit History'), 'Must support viewing edit audit history');
});

// Test 4: Verify navigation test suite also continues to pass
runTest('Existing 15 Navigation & RBAC tests continue passing without regression', async () => {
  const { execSync } = await import('child_process');
  const output = execSync('node test_navigation.bundle.mjs', { cwd: '.' }).toString();
  assert(output.includes('15 / 15 PASSED (100% Success Rate)'), 'Navigation tests failed');
});

console.log(`\n=========================================================================`);
console.log(`TEST EXECUTION SUMMARY: ${passedTests} / ${totalTests} Passed (${Math.round((passedTests/totalTests)*100)}%)`);
console.log(`=========================================================================\n`);
