import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ProtectedRoute({ children }) {
  const { user, portal, loading, mustChangePassword } = useAuth();
  if (loading) return <div className="page-loader"><div className="spinner" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  if (mustChangePassword) return <Navigate to="/change-password" replace />;
  if (user.role === 'MASTER_ADMIN' || portal === 'platform') {
    return <Navigate to="/admin" replace />;
  }
  return children;
}
