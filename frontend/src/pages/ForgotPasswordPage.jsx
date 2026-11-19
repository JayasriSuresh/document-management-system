import { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { api } from '../api';

export default function ForgotPasswordPage() {
  const [searchParams] = useSearchParams();
  const portal = searchParams.get('portal') || 'app';
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.requestPasswordReset({ email, portal });
      setMessage(res.message || 'If the account is eligible, password reset instructions will be sent.');
      setSubmitted(true);
    } catch (err) {
      setError(err.message || 'Unable to process reset request.');
    } finally {
      setLoading(false);
    }
  };

  const getBackLoginUrl = () => {
    if (portal === 'platform') return '/admin/login';
    if (portal === 'company') return '/company/login';
    return '/login';
  };

  return (
    <div className="insta-login-page">
      <div className="insta-login-wrapper">
        <div className="insta-card">
          <div className="insta-header">
            <h1 className="insta-logo">DMS</h1>
            <p className="insta-tagline" style={{ fontWeight: 600 }}>Trouble Logging In?</p>
            <p style={{ color: '#737373', fontSize: '13px', margin: '4px 0 16px' }}>
              Enter your corporate email and we will send you a secure link to recover your account.
            </p>
          </div>

          {submitted ? (
            <div style={{ textAlign: 'center', padding: '10px 0' }}>
              <div style={{
                backgroundColor: '#f0fdf4',
                color: '#166534',
                padding: '12px',
                borderRadius: '6px',
                fontSize: '13px',
                marginBottom: '16px',
                lineHeight: 1.4,
              }}>
                {message}
              </div>
              <Link to={getBackLoginUrl()} className="insta-button" style={{ display: 'inline-block', textDecoration: 'none' }}>
                Return to Login
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="insta-form">
              <div className="insta-input-group">
                <input
                  type="email"
                  className="insta-input"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="Corporate email address"
                  required
                  autoFocus
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
                disabled={loading || !email.trim()}
              >
                {loading ? 'Sending link…' : 'Send Login Link'}
              </button>
            </form>
          )}

          <div className="insta-divider">
            <div className="insta-divider-line" />
            <div className="insta-divider-text">OR</div>
            <div className="insta-divider-line" />
          </div>

          <div className="insta-help">
            <Link to={getBackLoginUrl()} className="insta-help-link" style={{ fontWeight: 600 }}>
              Back to Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
