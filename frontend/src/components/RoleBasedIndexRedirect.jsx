import React from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Deterministic role landing destination resolver.
 */
export function getRoleLandingDestination(user, tab = null) {
  if (!user) return '/login';
  if (tab === 'dashboard') return '/branch-dashboard';
  if (tab === 'trash') return '/documents?tab=trash';
  if (user.role === 'MASTER_ADMIN') return '/admin/companies';
  if (user.role === 'GLOBAL_ADMIN') return '/company/dashboard';
  return '/documents';
}

/**
 * Intelligent role-aware landing router at root ('/').
 * Dispatches users to their designated canonical landing view
 * based on authenticated role and query parameters.
 */
export default function RoleBasedIndexRedirect() {
  const { user, loading } = useAuth();
  const [searchParams] = useSearchParams();

  if (loading) {
    return (
      <div className="page-loader" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <div className="spinner" />
      </div>
    );
  }

  const destination = getRoleLandingDestination(user, searchParams.get('tab'));
  return <Navigate to={destination} replace />;
}
