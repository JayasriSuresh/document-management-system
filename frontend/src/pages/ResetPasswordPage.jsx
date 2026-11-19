import { useState } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { api } from '../api';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') || '';
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await api.resetPassword({ token, new_password: newPassword });
      setSuccess(true);
    } catch (err) {
      setError(err.message || 'Failed to reset password. The token may be expired or invalid.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="insta-login-page">
      <div className="insta-login-wrapper">
        <div className="insta-card">
          <div className="insta-header">
            <h1 className="insta-logo">DMS</h1>
            <p className="insta-tagline" style={{ fontWeight: 600 }}>Create New Password</p>
            <p style={{ color: '#737373', fontSize: '13px', margin: '4px 0 16px' }}>
              Your new password must be at least 8 characters.
            </p>
          </div>

          {success ? (
            <div style={{ textAlign: 'center', padding: '10px 0' }}>
              <div style={{
                backgroundColor: '#f0fdf4',
                color: '#166534',
                padding: '12px',
                borderRadius: '6px',
                fontSize: '13px',
                marginBottom: '16px',
              }}>
                Password successfully updated! All prior sessions have been revoked.
              </div>
              <button
                type="button"
                onClick={() => navigate('/login')}
                className="insta-button"
              >
                Sign In With New Password
              </button>
            </div>
          ) : !token ? (
            <div style={{ textAlign: 'center', color: '#dc2626', fontSize: '13px', padding: '16px 0' }}>
              Missing or invalid reset token. Please request a new password reset link.
              <div style={{ marginTop: '16px' }}>
                <Link to="/login" className="insta-help-link" style={{ fontWeight: 600 }}>
                  Back to Login
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="insta-form">
              <div className="insta-input-group">
                <input
                  type="password"
                  className="insta-input"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  placeholder="New password (min 8 characters)"
                  required
                  autoFocus
                />
              </div>

              <div className="insta-input-group">
                <input
                  type="password"
                  className="insta-input"
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                  required
                />
              </div>

              {error && (
                <div className="insta-error">
                  <span>{error}</span>
                </div>
              )}

              <button
                type="submit"
                className="insta-button"
                disabled={loading || !newPassword || !confirmPassword}
              >
                {loading ? 'Updating…' : 'Reset Password'}
              </button>
            </form>
          )}

          <div className="insta-divider">
            <div className="insta-divider-line" />
            <div className="insta-divider-text">OR</div>
            <div className="insta-divider-line" />
          </div>

          <div className="insta-help">
            <Link to="/login" className="insta-help-link" style={{ fontWeight: 600 }}>
              Return to Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
