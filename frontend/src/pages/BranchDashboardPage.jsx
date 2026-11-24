import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';
import BranchDashboardView from '../components/BranchDashboardView';

export default function BranchDashboardPage() {
  const { user, hasPermission, loading } = useAuth();
  const navigate = useNavigate();
  const [branches, setBranches] = useState([]);
  const [toastMessage, setToastMessage] = useState(null);

  const showToast = (message, type = 'success') => {
    setToastMessage({ message, type });
    setTimeout(() => setToastMessage(null), 5000);
  };

  const isCompanyAdmin =
    user?.role === 'GLOBAL_ADMIN' ||
    hasPermission('company.view') ||
    hasPermission('document.view_company');
  const isBranchAdmin = user?.role === 'ADMIN' || hasPermission('branch.view');

  useEffect(() => {
    if (!loading && user) {
      if (!isCompanyAdmin && !isBranchAdmin) {
        navigate('/documents', { replace: true });
        return;
      }

      api.listCompanyBranches()
        .then(data => {
          const list = Array.isArray(data) ? data : (data?.items || []);
          if (isCompanyAdmin) {
            setBranches(list);
          } else {
            const authorizedIds = new Set();
            if (user.branch_id) authorizedIds.add(Number(user.branch_id));
            if (user.tenant_id) authorizedIds.add(Number(user.tenant_id));
            if (Array.isArray(user.assigned_branch_ids)) {
              user.assigned_branch_ids.forEach(id => authorizedIds.add(Number(id)));
            }
            if (Array.isArray(user.assignments)) {
              user.assignments.forEach(a => {
                if (a.scope_type === 'branch' && a.scope_id) {
                  authorizedIds.add(Number(a.scope_id));
                }
              });
            }
            const filtered = list.filter(b => authorizedIds.has(Number(b.id)));
            if (filtered.length === 0 && user.branch_id) {
              filtered.push({
                id: user.branch_id,
                name: user.branch_name || user.tenant_name || 'Assigned Branch',
                code: user.branch_code || 'BR',
              });
            }
            setBranches(filtered);
          }
        })
        .catch(() => {});
    }
  }, [user, loading, isCompanyAdmin, isBranchAdmin, navigate]);

  if (loading) {
    return (
      <div className="page-loader" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="spinner" />
      </div>
    );
  }

  // Non-authorized roles should never see the dashboard page
  if (!isCompanyAdmin && !isBranchAdmin) {
    return null;
  }

  return (
    <div className="page-content" style={{ width: '100%', maxWidth: '100%', padding: '1.5rem 2rem' }}>
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
          borderRadius: '8px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
          fontSize: '14px',
          fontWeight: 500,
        }}>
          {toastMessage.message}
        </div>
      )}

      <BranchDashboardView
        branchId={user?.branch_id}
        branchesList={branches}
        showToast={showToast}
        onNavigateToDocs={() => navigate('/documents')}
      />
    </div>
  );
}
