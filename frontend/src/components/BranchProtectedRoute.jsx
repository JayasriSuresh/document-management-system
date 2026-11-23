import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function BranchProtectedRoute({ children }) {
  const { user, loading, mustChangePassword, hasPermission } = useAuth();

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

  // Staff and Uploaders are not authorized -> stay inside workspace, redirect to /documents
  const isBranchAdmin = user.role === 'ADMIN' || user.role === 'GLOBAL_ADMIN' || hasPermission('user.view_branch');
  if (!isBranchAdmin) {
    return <Navigate to="/documents" replace />;
  }

  if (mustChangePassword) {
    return <Navigate to="/change-password" replace />;
  }

  return children;
}
