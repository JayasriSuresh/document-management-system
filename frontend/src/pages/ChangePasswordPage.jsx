import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { api } from '../api';

export default function ChangePasswordPage() {
  const { user, mustChangePassword, setMustChangePassword } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters long.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setMustChangePassword(false);
      setSuccess(true);
      setTimeout(() => {
        navigate('/');
      }, 1500);
    } catch (err) {
      setError(err.message || 'Failed to change password. Please check your current password.');
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
            <p className="insta-tagline" style={{ fontWeight: 600 }}>
              {mustChangePassword ? 'Security Notice: Password Change Required' : 'Change Your Password'}
            </p>
            <p style={{ color: '#737373', fontSize: '13px', margin: '4px 0 16px' }}>
              {mustChangePassword
                ? 'Your administrator requires you to set a new password before accessing the system.'
                : 'Update your corporate credentials below.'}
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
                Password successfully updated! Redirecting to workspace…
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="insta-form">
              <div className="insta-input-group">
                <input
                  type="password"
                  className="insta-input"
                  value={currentPassword}
                  onChange={e => setCurrentPassword(e.target.value)}
                  placeholder="Current password"
                  required
                  autoFocus
                />
              </div>

              <div className="insta-input-group">
                <input
                  type="password"
                  className="insta-input"
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  placeholder="New password (min 8 characters)"
                  required
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
                disabled={loading || !currentPassword || !newPassword || !confirmPassword}
              >
                {loading ? 'Saving…' : 'Update Password'}
              </button>
            </form>
          )}

          {!mustChangePassword && (
            <div className="insta-help" style={{ marginTop: '16px' }}>
              <button
                type="button"
                onClick={() => navigate('/')}
                style={{ background: 'none', border: 'none', color: '#0095f6', cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}
              >
                Cancel and return to workspace
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
