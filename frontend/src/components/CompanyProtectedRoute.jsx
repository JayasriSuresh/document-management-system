import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function CompanyProtectedRoute({ children }) {
  const { user, loading, mustChangePassword } = useAuth();

  if (loading) {
    return (
      <div className="page-loader" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="spinner" />
      </div>
    );
  }

  // Not logged in -> go to login
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Authenticated non-Company Admin -> stay inside workspace, don't kick out to login
  if (user.role !== 'GLOBAL_ADMIN') {
    return <Navigate to="/documents" replace />;
  }

  if (mustChangePassword) {
    return <Navigate to="/change-password" replace />;
  }

  return children;
}
