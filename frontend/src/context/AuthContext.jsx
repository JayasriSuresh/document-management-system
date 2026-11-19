import { createContext, useContext, useState, useEffect } from 'react';
import { api, setAuthToken } from '../api';

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [portal, setPortal] = useState('app');
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function initAuth() {
      const savedUser = localStorage.getItem('dms_user');
      const savedPortal = localStorage.getItem('dms_portal') || 'app';
      if (savedUser) {
        try {
          const parsed = JSON.parse(savedUser);
          setUser(parsed);
          setPortal(savedPortal);
          // Verify session validity with backend
          const me = await api.me();
          setUser(me);
          localStorage.setItem('dms_user', JSON.stringify(me));
        } catch {
          // If token expired, single-flight refresh inside api.js will attempt rotation
        }
      }
      setLoading(false);
    }
    initAuth();
  }, []);

  const login = async (email, password, requestedPortal = 'app') => {
    const data = await api.login(email, password, requestedPortal);
    if (data.mfa_required || data.mfa_enrollment_required) {
      return data;
    }
    localStorage.setItem('dms_user', JSON.stringify(data.user));
    localStorage.setItem('dms_portal', data.portal || requestedPortal);
    setUser(data.user);
    setPortal(data.portal || requestedPortal);
    setMustChangePassword(Boolean(data.must_change_password));
    // Refresh user profile asynchronously to ensure full permissions and assignments are synced
    api.me().then((me) => {
      if (me) {
        setUser(me);
        localStorage.setItem('dms_user', JSON.stringify(me));
      }
    }).catch(() => {});
    return data;
  };

  const completeMfaLogin = (data, requestedPortal = 'app') => {
    localStorage.setItem('dms_user', JSON.stringify(data.user));
    localStorage.setItem('dms_portal', data.portal || requestedPortal);
    setUser(data.user);
    setPortal(data.portal || requestedPortal);
    setMustChangePassword(Boolean(data.must_change_password));
    // Refresh user profile asynchronously to ensure full permissions and assignments are synced
    api.me().then((me) => {
      if (me) {
        setUser(me);
        localStorage.setItem('dms_user', JSON.stringify(me));
      }
    }).catch(() => {});
    return data;
  };

  const hasPermission = (permission) => {
    if (!user) return false;
    // Admins and Global Admins implicitly have operational branch permissions
    if (user.role === 'GLOBAL_ADMIN') return true;
    if (user.role === 'ADMIN' && !permission.startsWith('company:')) return true;
    if (Array.isArray(user.permissions) && user.permissions.includes(permission)) return true;
    return false;
  };

  const refreshUser = async () => {
    try {
      const me = await api.me();
      setUser(me);
      localStorage.setItem('dms_user', JSON.stringify(me));
      return me;
    } catch {
      return null;
    }
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // Ignore network errors on logout
    } finally {
      localStorage.removeItem('dms_user');
      localStorage.removeItem('dms_portal');
      setAuthToken(null);
      setUser(null);
      setMustChangePassword(false);
    }
  };

  const logoutAll = async () => {
    try {
      await api.logoutAll();
    } catch {
      // Ignore network errors
    } finally {
      localStorage.removeItem('dms_user');
      localStorage.removeItem('dms_portal');
      setAuthToken(null);
      setUser(null);
      setMustChangePassword(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        portal,
        mustChangePassword,
        setMustChangePassword,
        hasPermission,
        refreshUser,
        login,
        completeMfaLogin,
        logout,
        logoutAll,
        loading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
