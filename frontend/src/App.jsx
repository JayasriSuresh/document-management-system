import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import PlatformProtectedRoute from './components/PlatformProtectedRoute';
import CompanyProtectedRoute from './components/CompanyProtectedRoute';
import BranchProtectedRoute from './components/BranchProtectedRoute';
import RoleBasedIndexRedirect from './components/RoleBasedIndexRedirect';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import AcceptInvitePage from './pages/AcceptInvitePage';
import ChangePasswordPage from './pages/ChangePasswordPage';
import DocumentsPage from './pages/DocumentsPage';
import BranchDashboardPage from './pages/BranchDashboardPage';
import UploadPage from './pages/UploadPage';
import DocumentViewPage from './pages/DocumentViewPage';
import DocumentReviewPage from './pages/DocumentReviewPage';
import InvoicesPage from './pages/InvoicesPage';
import SalesInvoiceEditorPage from './pages/SalesInvoiceEditorPage';
import AdminCompaniesPage from './pages/AdminCompaniesPage';
import CompanyOnboardingPage from './pages/CompanyOnboardingPage';
import CompanyAdminPortalPage from './pages/CompanyAdminPortalPage';
import AuditLogsPage from './pages/AuditLogsPage';
import SecuritySettingsPage from './pages/SecuritySettingsPage';
import BranchUserManagementPage from './pages/BranchUserManagementPage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Three Distinct Portals */}
          <Route path="/login" element={<LoginPage portal="app" />} />
          <Route path="/company/login" element={<LoginPage portal="company" />} />
          <Route path="/admin/login" element={<LoginPage portal="platform" />} />

          {/* Master Admin Portal (Completely Segregated Platform Administration) */}
          <Route
            path="/admin"
            element={
              <PlatformProtectedRoute>
                <AdminCompaniesPage />
              </PlatformProtectedRoute>
            }
          />
          <Route
            path="/admin/companies"
            element={
              <PlatformProtectedRoute>
                <AdminCompaniesPage />
              </PlatformProtectedRoute>
            }
          />
          <Route
            path="/admin/security"
            element={<Navigate to="/admin?tab=security" replace />}
          />

          {/* Public Company Onboarding Registration */}
          <Route path="/company/onboard" element={<CompanyOnboardingPage />} />
          <Route path="/onboard" element={<CompanyOnboardingPage />} />

          {/* Identity Workflows */}
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/accept-invite" element={<AcceptInvitePage />} />
          <Route path="/change-password" element={<ChangePasswordPage />} />

          {/* Unified Application Shell (Role-Based Navigation) */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            {/* Intelligent Role-Aware Landing Dispatcher */}
            <Route index element={<RoleBasedIndexRedirect />} />

            {/* Operations Section */}
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="branch-dashboard" element={<BranchDashboardPage />} />
            <Route path="invoices" element={<InvoicesPage />} />
            <Route path="invoices/new" element={<SalesInvoiceEditorPage />} />
            <Route path="invoices/:id/edit" element={<SalesInvoiceEditorPage />} />
            <Route path="upload" element={<UploadPage />} />
            <Route path="documents/:id" element={<DocumentViewPage />} />
            <Route path="documents/:id/review" element={<DocumentReviewPage />} />
            <Route path="audit" element={<AuditLogsPage />} />
            <Route path="security" element={<SecuritySettingsPage />} />
            <Route
              path="branch/users"
              element={
                <BranchProtectedRoute>
                  <BranchUserManagementPage />
                </BranchProtectedRoute>
              }
            />

            {/* Company Management Section (Strictly Company Admin Only) */}
            <Route
              path="company"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="dashboard" />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/dashboard"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="dashboard" />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/profile"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="profile" />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/branches"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="branches" />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/users"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="users" />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/documents"
              element={
                <CompanyProtectedRoute>
                  <DocumentsPage isArchiveView={true} />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/templates"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="templates" />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/ai"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="ai" />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/ai-usage"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="ai-usage" />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/jobs"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="jobs" />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/security"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="security" />
                </CompanyProtectedRoute>
              }
            />
            <Route
              path="company/audit-logs"
              element={
                <CompanyProtectedRoute>
                  <CompanyAdminPortalPage defaultTab="audit" />
                </CompanyProtectedRoute>
              }
            />
          </Route>

          {/* Catch-all Wildcard Route */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
