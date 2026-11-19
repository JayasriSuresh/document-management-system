import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function PlatformProtectedRoute({ children }) {
  const { user, loading, mustChangePassword } = useAuth();
  if (loading) return <div className="page-loader"><div className="spinner" /></div>;
  if (!user || user.role !== 'MASTER_ADMIN') return <Navigate to="/admin/login" replace />;
  if (mustChangePassword) return <Navigate to="/change-password" replace />;
  return children;
}
