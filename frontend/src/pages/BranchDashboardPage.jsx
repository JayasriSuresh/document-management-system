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

  useEffect(() => {
    if (!loading && user) {
      if (!hasPermission('branch.view') && user.role !== 'ADMIN' && user.role !== 'GLOBAL_ADMIN') {
        navigate('/documents', { replace: true });
        return;
      }

      api.listCompanyBranches()
        .then(data => {
          if (Array.isArray(data)) setBranches(data);
          else if (data?.items) setBranches(data.items);
        })
        .catch(() => {});
    }
  }, [user, loading, hasPermission, navigate]);

  if (loading) {
    return (
      <div className="page-loader" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="branch-dashboard-page" style={{ maxWidth: '1280px', margin: '0 auto', padding: '24px 20px 48px' }}>
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
        branchesList={branches}
        showToast={showToast}
        onNavigateToDocs={() => navigate('/documents')}
      />
    </div>
  );
}
