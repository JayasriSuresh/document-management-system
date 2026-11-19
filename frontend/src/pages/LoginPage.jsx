import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import MfaModal from '../components/MfaModal';

export default function LoginPage({ portal = 'app' }) {
  const { login, completeMfaLogin } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // MFA Challenge / Enrollment state
  const [showMfaModal, setShowMfaModal] = useState(false);
  const [mfaModalMode, setMfaModalMode] = useState('challenge');
  const [mfaPendingToken, setMfaPendingToken] = useState(null);
  const [mfaEnrollmentToken, setMfaEnrollmentToken] = useState(null);

  const portalConfig = {
    platform: {
      badge: 'PLATFORM ROOT',
      title: 'DMS Platform',
      tagline: 'Master Platform Administration',
      subcard: 'System Administration · Hardware & Tenant Control',
      emailPlaceholder: 'Administrator email',
      redirect: '/admin',
    },
    company: {
      badge: 'COMPANY ADMIN',
      title: 'DMS',
      tagline: 'Company Headquarters Admin Portal',
      subcard: 'Corporate Management · Headquarters Portal',
      emailPlaceholder: 'Corporate executive email',
      redirect: '/company/dashboard',
    },
    app: {
      badge: 'BRANCH WORKSPACE',
      title: 'DMS',
      tagline: 'Sign in to your corporate workspace',
      subcard: 'Protected System · Branch Workspace',
      emailPlaceholder: 'Corporate email',
      redirect: '/',
    },
  }[portal] || {
    badge: 'WORKSPACE',
    title: 'DMS',
    tagline: 'Sign in to your workspace',
    subcard: 'Protected System',
    emailPlaceholder: 'Email address',
    redirect: '/',
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await login(email, password, portal);
      if (data.mfa_required) {
        setMfaPendingToken(data.mfa_pending_token);
        setMfaModalMode('challenge');
        setShowMfaModal(true);
      } else if (data.mfa_enrollment_required) {
        setMfaEnrollmentToken(data.mfa_enrollment_token);
        setMfaModalMode('mandatory_enroll');
        setShowMfaModal(true);
      } else if (data.must_change_password) {
        navigate('/change-password');
      } else {
        navigate(portalConfig.redirect);
      }
    } catch (err) {
      setError(err.message || 'Invalid credentials. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleMfaSuccess = (result) => {
    completeMfaLogin(result, portal);
    setShowMfaModal(false);
    if (result.must_change_password) {
      navigate('/change-password');
    } else {
      navigate(portalConfig.redirect);
    }
  };

  const isFormValid = email.trim().length > 0 && password.length > 0;

  return (
    <div className="insta-login-page">
      <div className="insta-login-wrapper">

        {/* Primary Instagram-Style Card */}
        <div className="insta-card">
          {/* Logo / Brand Header */}
          <div className="insta-header">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '8px' }}>
              <h1 className="insta-logo">{portalConfig.title}</h1>
            </div>
            <div style={{
              display: 'inline-block',
              fontSize: '10px',
              fontWeight: 700,
              letterSpacing: '1px',
              padding: '2px 8px',
              borderRadius: '12px',
              backgroundColor: portal === 'platform' ? '#ef444422' : portal === 'company' ? '#8b5cf622' : '#0ea5e922',
              color: portal === 'platform' ? '#ef4444' : portal === 'company' ? '#8b5cf6' : '#0ea5e9',
              marginBottom: '10px',
            }}>
              {portalConfig.badge}
            </div>
            <p className="insta-tagline">{portalConfig.tagline}</p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="insta-form">
            <div className="insta-input-group">
              <input
                id="email"
                type="text"
                className="insta-input"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder={portalConfig.emailPlaceholder}
                required
                autoFocus
                autoComplete="username"
              />
            </div>

            <div className="insta-input-group insta-password-group">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                className="insta-input"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Password"
                required
                autoComplete="current-password"
              />
              {password.length > 0 && (
                <button
                  type="button"
                  className="insta-show-password"
                  onClick={() => setShowPassword(s => !s)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              )}
            </div>

            {error && (
              <div className="insta-error">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              className="insta-button"
              disabled={loading || !isFormValid}
            >
              {loading ? 'Signing in…' : 'Log in'}
            </button>
          </form>

          {/* Divider */}
          <div className="insta-divider">
            <div className="insta-divider-line" />
            <div className="insta-divider-text">OR</div>
            <div className="insta-divider-line" />
          </div>

          {/* Password recovery link */}
          <div className="insta-help">
            <Link
              to={`/forgot-password?portal=${portal}`}
              className="insta-help-link"
              style={{ color: '#0095f6', textDecoration: 'none', fontWeight: 600, fontSize: '12px' }}
            >
              Forgot password?
            </Link>
          </div>
        </div>

        {/* Secondary Box */}
        <div className="insta-subcard">
          <p className="insta-subcard-text">
            {portalConfig.subcard}
          </p>
        </div>

        {/* Footer */}
        <footer className="insta-footer">
          <div className="insta-footer-links">
            <Link to="/login" style={{ color: 'inherit', textDecoration: 'none' }}>App Portal</Link>
            <Link to="/company/login" style={{ color: 'inherit', textDecoration: 'none' }}>Company Admin</Link>
            <Link to="/admin/login" style={{ color: 'inherit', textDecoration: 'none' }}>Platform Admin</Link>
          </div>
          <div className="insta-copyright">
            &copy; 2026 DMS Inc. All rights reserved.
          </div>
        </footer>

      </div>

      {showMfaModal && (
        <MfaModal
          mode={mfaModalMode}
          mfaPendingToken={mfaPendingToken}
          mfaEnrollmentToken={mfaEnrollmentToken}
          portalConfig={portalConfig}
          onSuccess={handleMfaSuccess}
          onCancel={() => {
            setShowMfaModal(false);
            setMfaPendingToken(null);
            setMfaEnrollmentToken(null);
          }}
        />
      )}
    </div>
  );
}
