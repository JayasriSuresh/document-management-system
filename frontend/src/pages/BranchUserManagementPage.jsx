import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';

export default function BranchUserManagementPage() {
  const { user } = useAuth();

  // State: Branches & scope
  const [authorizedBranches, setAuthorizedBranches] = useState([]);
  const [loadingBranches, setLoadingBranches] = useState(true);

  // State: Active tab ('users' | 'invitations')
  const [activeTab, setActiveTab] = useState('users');

  // State: Filters
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [branchFilter, setBranchFilter] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // State: Users data
  const [users, setUsers] = useState([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [userError, setUserError] = useState('');

  // State: Invitations data
  const [invitations, setInvitations] = useState([]);
  const [loadingInvitations, setLoadingInvitations] = useState(false);
  const [invitationError, setInvitationError] = useState('');

  // State: Invite Modal
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({
    name: '',
    email: '',
    mobile: '',
    role: 'STAFF',
    branch_id: '',
  });
  const [submittingInvite, setSubmittingInvite] = useState(false);
  const [inviteError, setInviteError] = useState('');
  const [inviteSuccessMsg, setInviteSuccessMsg] = useState('');

  // State: Edit Modal
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [editForm, setEditForm] = useState({ name: '', email: '', mobile: '' });
  const [submittingEdit, setSubmittingEdit] = useState(false);
  const [editError, setEditError] = useState('');

  // State: Deactivate/Reactivate Confirmation Modal
  const [confirmModal, setConfirmModal] = useState({
    isOpen: false,
    type: 'deactivate', // 'deactivate' | 'activate'
    user: null,
    loading: false,
    error: '',
  });

  // State: Global notification toast/banner
  const [feedback, setFeedback] = useState({ message: '', type: 'success' });

  const showFeedback = (message, type = 'success') => {
    setFeedback({ message, type });
    setTimeout(() => {
      setFeedback({ message: '', type: 'success' });
    }, 5000);
  };

  // 1. Fetch authorized branches
  useEffect(() => {
    let mounted = true;
    async function loadBranches() {
      try {
        setLoadingBranches(true);
        const data = await api.getBranchAuthorizedBranches();
        if (mounted) {
          const branches = Array.isArray(data) ? data : [];
          setAuthorizedBranches(branches);
          if (branches.length === 1) {
            setBranchFilter(String(branches[0].id));
          }
        }
      } catch (err) {
        // Silently handled: authorized branches will fallback to user branch context
      } finally {
        if (mounted) setLoadingBranches(false);
      }
    }
    loadBranches();
    return () => { mounted = false; };
  }, []);

  // 2. Fetch Users
  const loadUsers = useCallback(async () => {
    try {
      setLoadingUsers(true);
      setUserError('');
      const res = await api.getBranchUsers({
        page,
        pageSize,
        branchId: branchFilter ? parseInt(branchFilter, 10) : null,
        role: roleFilter || null,
        status: statusFilter || null,
        search: search.trim() || null,
      });
      setUsers(res.items || []);
      setTotalUsers(res.total || 0);
      setTotalPages(res.total_pages || 1);
    } catch (err) {
      setUserError(err.message || 'Failed to load branch users.');
      setUsers([]);
    } finally {
      setLoadingUsers(false);
    }
  }, [page, branchFilter, roleFilter, statusFilter, search]);

  useEffect(() => {
    if (activeTab === 'users') {
      loadUsers();
    }
  }, [loadUsers, activeTab]);

  // 3. Fetch Invitations
  const loadInvitations = useCallback(async () => {
    try {
      setLoadingInvitations(true);
      setInvitationError('');
      const res = await api.getBranchInvitations({
        branchId: branchFilter ? parseInt(branchFilter, 10) : null,
      });
      setInvitations(Array.isArray(res) ? res : []);
    } catch (err) {
      setInvitationError(err.message || 'Failed to load invitations.');
      setInvitations([]);
    } finally {
      setLoadingInvitations(false);
    }
  }, [branchFilter]);

  useEffect(() => {
    if (activeTab === 'invitations') {
      loadInvitations();
    }
  }, [loadInvitations, activeTab]);

  // 4. Handle Invite Modal Open
  const handleOpenInviteModal = () => {
    const defaultBranchId = authorizedBranches.length > 0 ? String(authorizedBranches[0].id) : (user?.branch_id ? String(user.branch_id) : '');
    setInviteForm({
      name: '',
      email: '',
      mobile: '',
      role: 'STAFF',
      branch_id: branchFilter || defaultBranchId,
    });
    setInviteError('');
    setInviteSuccessMsg('');
    setIsInviteModalOpen(true);
  };

  // Handle Invite Submit
  const handleInviteSubmit = async (e) => {
    e.preventDefault();
    if (!inviteForm.name.trim() || !inviteForm.email.trim()) {
      setInviteError('Name and email are required.');
      return;
    }
    const resolvedBranchId =
      inviteForm.branch_id ||
      (authorizedBranches.length > 0 ? authorizedBranches[0].id : null) ||
      user?.branch_id ||
      user?.tenant_id;
    if (!resolvedBranchId) {
      setInviteError('Please select a branch.');
      return;
    }

    try {
      setSubmittingInvite(true);
      setInviteError('');
      const payload = {
        name: inviteForm.name.trim(),
        email: inviteForm.email.trim().toLowerCase(),
        mobile: inviteForm.mobile.trim() || null,
        role: inviteForm.role,
        branch_id: parseInt(resolvedBranchId, 10),
      };

      const res = await api.inviteBranchUser(payload);
      const successMessage = res.message || `Invitation successfully sent to ${payload.email}.`;
      setInviteSuccessMsg(successMessage);
      showFeedback(successMessage);

      // Refresh list
      loadUsers();
      if (activeTab === 'invitations') loadInvitations();
    } catch (err) {
      setInviteError(err.message || 'Failed to send invitation.');
    } finally {
      setSubmittingInvite(false);
    }
  };

  // 5. Handle Edit Modal Open
  const handleOpenEditModal = (targetUser) => {
    setEditingUser(targetUser);
    setEditForm({
      name: targetUser.name || '',
      email: targetUser.email || '',
      mobile: targetUser.mobile || '',
    });
    setEditError('');
    setIsEditModalOpen(true);
  };

  // Handle Edit Submit
  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editForm.name.trim() || !editForm.email.trim()) {
      setEditError('Name and email are required.');
      return;
    }

    try {
      setSubmittingEdit(true);
      setEditError('');
      await api.updateBranchUser(editingUser.id, {
        name: editForm.name.trim(),
        email: editForm.email.trim().toLowerCase(),
        mobile: editForm.mobile.trim() || null,
      });
      setIsEditModalOpen(false);
      showFeedback(`User ${editForm.email} updated successfully.`);
      loadUsers();
    } catch (err) {
      setEditError(err.message || 'Failed to update user.');
    } finally {
      setSubmittingEdit(false);
    }
  };

  // 6. Handle Deactivate/Reactivate
  const handleOpenConfirmModal = (targetUser, type) => {
    setConfirmModal({
      isOpen: true,
      type,
      user: targetUser,
      loading: false,
      error: '',
    });
  };

  const handleConfirmAction = async () => {
    const { type, user: targetUser } = confirmModal;
    if (!targetUser) return;

    try {
      setConfirmModal((prev) => ({ ...prev, loading: true, error: '' }));
      if (type === 'deactivate') {
        await api.deactivateBranchUser(targetUser.id);
        showFeedback(`User ${targetUser.email} has been deactivated and logged out.`, 'success');
      } else {
        await api.activateBranchUser(targetUser.id);
        showFeedback(`User ${targetUser.email} has been reactivated.`, 'success');
      }
      setConfirmModal({ isOpen: false, type: 'deactivate', user: null, loading: false, error: '' });
      loadUsers();
    } catch (err) {
      setConfirmModal((prev) => ({ ...prev, loading: false, error: err.message || 'Action failed.' }));
    }
  };

  // 7. Resend / Revoke Invitation
  const handleResendInvitation = async (inv) => {
    try {
      const res = await api.resendBranchInvitation(inv.id);
      showFeedback(res.message || `Invitation resent to ${inv.email}.`, 'success');
      loadInvitations();
    } catch (err) {
      showFeedback(err.message || 'Failed to resend invitation.', 'error');
    }
  };

  const handleRevokeInvitation = async (inv) => {
    if (!window.confirm(`Are you sure you want to revoke the invitation for ${inv.email}?`)) {
      return;
    }
    try {
      const res = await api.revokeBranchInvitation(inv.id);
      showFeedback(res.message || `Invitation for ${inv.email} revoked.`, 'success');
      loadInvitations();
    } catch (err) {
      showFeedback(err.message || 'Failed to revoke invitation.', 'error');
    }
  };

  const isTargetAdmin = (targetUser) => {
    if (targetUser.role === 'ADMIN' || targetUser.role === 'GLOBAL_ADMIN') return true;
    if (Array.isArray(targetUser.assigned_branches)) {
      return targetUser.assigned_branches.some(a => a.role === 'ADMIN' || a.role === 'GLOBAL_ADMIN');
    }
    return false;
  };

  return (
    <div className="branch-user-management" style={{ maxWidth: '1280px', margin: '0 auto', padding: '24px 20px' }}>
      {/* ── Toast Feedback ─────────────────────────────────────────────── */}
      {feedback.message && (
        <div style={{
          position: 'fixed',
          top: '20px',
          right: '24px',
          zIndex: 9999,
          padding: '12px 20px',
          borderRadius: '8px',
          fontSize: '13px',
          fontWeight: 600,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          backgroundColor: feedback.type === 'error' ? '#ef4444' : '#10b981',
          color: '#ffffff',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}>
          <span>{feedback.type === 'error' ? '⚠️' : '✓'}</span>
          <span>{feedback.message}</span>
        </div>
      )}

      {/* ── Page Header ───────────────────────────────────────────────── */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        gap: '16px',
        marginBottom: '24px',
        borderBottom: '1px solid #e2e8f0',
        paddingBottom: '20px',
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 700, color: '#0f172a', letterSpacing: '-0.02em' }}>
            User Management
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: '14px', color: '#64748b' }}>
            Manage staff and uploaders in your authorized branches.
          </p>
        </div>

        <button
          onClick={handleOpenInviteModal}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: '#2563eb',
            color: '#ffffff',
            padding: '10px 18px',
            borderRadius: '8px',
            border: 'none',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
            boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
            transition: 'background-color 0.15s ease',
          }}
          onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#1d4ed8'}
          onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#2563eb'}
        >
          <span style={{ fontSize: '16px', lineHeight: 1 }}>+</span>
          Invite User
        </button>
      </div>

      {/* ── Tab Switcher ───────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <button
          onClick={() => { setActiveTab('users'); setPage(1); }}
          style={{
            padding: '8px 18px',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: 600,
            border: activeTab === 'users' ? '1px solid #2563eb' : '1px solid #cbd5e1',
            backgroundColor: activeTab === 'users' ? '#eff6ff' : '#ffffff',
            color: activeTab === 'users' ? '#1d4ed8' : '#64748b',
            cursor: 'pointer',
          }}
        >
          Active Personnel ({totalUsers})
        </button>
        <button
          onClick={() => { setActiveTab('invitations'); }}
          style={{
            padding: '8px 18px',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: 600,
            border: activeTab === 'invitations' ? '1px solid #2563eb' : '1px solid #cbd5e1',
            backgroundColor: activeTab === 'invitations' ? '#eff6ff' : '#ffffff',
            color: activeTab === 'invitations' ? '#1d4ed8' : '#64748b',
            cursor: 'pointer',
          }}
        >
          Pending Invitations ({invitations.filter(i => i.status === 'pending').length})
        </button>
      </div>

      {/* ── Search & Filter Controls ────────────────────────────────────── */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '12px',
        marginBottom: '20px',
        alignItems: 'center',
      }}>
        {/* Search */}
        <div style={{ flex: '1 1 240px', minWidth: '200px' }}>
          <input
            type="text"
            placeholder="Search name, email, or mobile..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            style={{
              width: '100%',
              padding: '9px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              outline: 'none',
              backgroundColor: '#ffffff',
            }}
          />
        </div>

        {/* Branch Filter */}
        {authorizedBranches.length > 1 && (
          <select
            value={branchFilter}
            onChange={(e) => { setBranchFilter(e.target.value); setPage(1); }}
            style={{
              padding: '9px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              backgroundColor: '#ffffff',
              cursor: 'pointer',
            }}
          >
            <option value="">All Authorized Branches</option>
            {authorizedBranches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name} ({b.code})
              </option>
            ))}
          </select>
        )}

        {/* Role Filter */}
        {activeTab === 'users' && (
          <select
            value={roleFilter}
            onChange={(e) => { setRoleFilter(e.target.value); setPage(1); }}
            style={{
              padding: '9px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              backgroundColor: '#ffffff',
              cursor: 'pointer',
            }}
          >
            <option value="">All Roles</option>
            <option value="STAFF">Staff</option>
            <option value="UPLOADER">Uploader</option>
          </select>
        )}

        {/* Status Filter */}
        {activeTab === 'users' && (
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            style={{
              padding: '9px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              backgroundColor: '#ffffff',
              cursor: 'pointer',
            }}
          >
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        )}
      </div>

      {/* ── Active Personnel Tab Content ────────────────────────────────── */}
      {activeTab === 'users' && (
        <div style={{
          backgroundColor: '#ffffff',
          borderRadius: '12px',
          border: '1px solid #e2e8f0',
          overflow: 'hidden',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}>
          {userError && (
            <div style={{ padding: '16px 20px', backgroundColor: '#fef2f2', color: '#b91c1c', fontSize: '13px', borderBottom: '1px solid #fecaca' }}>
              {userError}
            </div>
          )}

          {loadingUsers ? (
            <div style={{ padding: '64px 0', textAlign: 'center', color: '#64748b' }}>
              <div className="spinner" style={{ margin: '0 auto 12px' }} />
              Loading branch personnel...
            </div>
          ) : users.length === 0 ? (
            <div style={{ padding: '64px 0', textAlign: 'center', color: '#94a3b8', fontSize: '14px' }}>
              No personnel found matching your filter criteria.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    <th style={{ padding: '14px 18px' }}>Employee Details</th>
                    <th style={{ padding: '14px 18px' }}>Role</th>
                    <th style={{ padding: '14px 18px' }}>Branch</th>
                    <th style={{ padding: '14px 18px' }}>MFA Security</th>
                    <th style={{ padding: '14px 18px' }}>Status</th>
                    <th style={{ padding: '14px 18px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const isAdmin = isTargetAdmin(u);
                    return (
                      <tr key={u.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        {/* Employee Details */}
                        <td style={{ padding: '14px 18px' }}>
                          <div style={{ fontWeight: 600, color: '#0f172a' }}>{u.name}</div>
                          <div style={{ fontSize: '12px', color: '#64748b' }}>{u.email}</div>
                          {u.mobile && <div style={{ fontSize: '11px', color: '#94a3b8' }}>{u.mobile}</div>}
                        </td>

                        {/* Role */}
                        <td style={{ padding: '14px 18px' }}>
                          <span style={{
                            padding: '3px 8px',
                            borderRadius: '4px',
                            fontSize: '11px',
                            fontWeight: 700,
                            backgroundColor: u.role === 'ADMIN' ? '#eff6ff' : u.role === 'UPLOADER' ? '#fdf4ff' : '#f1f5f9',
                            color: u.role === 'ADMIN' ? '#1d4ed8' : u.role === 'UPLOADER' ? '#a21caf' : '#334155',
                            border: `1px solid ${u.role === 'ADMIN' ? '#bfdbfe' : u.role === 'UPLOADER' ? '#f5d0fe' : '#e2e8f0'}`,
                          }}>
                            {u.role === 'ADMIN' ? 'Branch Admin' : u.role === 'UPLOADER' ? 'Uploader' : 'Staff'}
                          </span>
                        </td>

                        {/* Branch */}
                        <td style={{ padding: '14px 18px' }}>
                          <span style={{ backgroundColor: '#f1f5f9', color: '#334155', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600 }}>
                            {u.branch_name || `Branch #${u.branch_id}`}
                          </span>
                        </td>

                        {/* MFA Security */}
                        <td style={{ padding: '14px 18px' }}>
                          <span style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '5px',
                            fontSize: '11px',
                            fontWeight: 600,
                            color: u.mfa_enabled ? '#15803d' : '#94a3b8',
                          }}>
                            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: u.mfa_enabled ? '#10b981' : '#cbd5e1' }} />
                            {u.mfa_enabled ? 'Enrolled' : 'Not Configured'}
                          </span>
                        </td>

                        {/* Status */}
                        <td style={{ padding: '14px 18px' }}>
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: '10px',
                            fontSize: '11px',
                            fontWeight: 700,
                            backgroundColor: u.status === 'active' ? '#ecfdf5' : '#fef2f2',
                            color: u.status === 'active' ? '#047857' : '#b91c1c',
                          }}>
                            {(u.status || 'active').toUpperCase()}
                          </span>
                        </td>

                        {/* Actions */}
                        <td style={{ padding: '14px 18px', textAlign: 'right' }}>
                          {isAdmin ? (
                            <span style={{ fontSize: '11px', color: '#94a3b8', fontStyle: 'italic' }}>
                              Admin Account
                            </span>
                          ) : (
                            <div style={{ display: 'inline-flex', gap: '6px' }}>
                              <button
                                onClick={() => handleOpenEditModal(u)}
                                style={{
                                  padding: '5px 10px',
                                  borderRadius: '6px',
                                  border: '1px solid #cbd5e1',
                                  backgroundColor: '#ffffff',
                                  color: '#334155',
                                  fontSize: '12px',
                                  fontWeight: 500,
                                  cursor: 'pointer',
                                }}
                              >
                                Edit
                              </button>

                              {u.status === 'active' ? (
                                <button
                                  onClick={() => handleOpenConfirmModal(u, 'deactivate')}
                                  style={{
                                    padding: '5px 10px',
                                    borderRadius: '6px',
                                    border: '1px solid #fecaca',
                                    backgroundColor: '#fff5f5',
                                    color: '#b91c1c',
                                    fontSize: '12px',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                  }}
                                >
                                  Deactivate
                                </button>
                              ) : (
                                <button
                                  onClick={() => handleOpenConfirmModal(u, 'activate')}
                                  style={{
                                    padding: '5px 10px',
                                    borderRadius: '6px',
                                    border: '1px solid #a7f3d0',
                                    backgroundColor: '#f0fdf4',
                                    color: '#15803d',
                                    fontSize: '12px',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                  }}
                                >
                                  Activate
                                </button>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{
              padding: '12px 18px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              borderTop: '1px solid #e2e8f0',
              fontSize: '13px',
              backgroundColor: '#ffffff',
            }}>
              <span style={{ color: '#64748b' }}>
                Page {page} of {totalPages} ({totalUsers} total users)
              </span>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  style={{
                    padding: '6px 14px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: '#ffffff',
                    cursor: page <= 1 ? 'not-allowed' : 'pointer',
                    color: page <= 1 ? '#94a3b8' : '#334155',
                  }}
                >
                  Previous
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  style={{
                    padding: '6px 14px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: '#ffffff',
                    cursor: page >= totalPages ? 'not-allowed' : 'pointer',
                    color: page >= totalPages ? '#94a3b8' : '#334155',
                  }}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Pending Invitations Tab Content ─────────────────────────────── */}
      {activeTab === 'invitations' && (
        <div style={{
          backgroundColor: '#ffffff',
          borderRadius: '12px',
          border: '1px solid #e2e8f0',
          overflow: 'hidden',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}>
          {invitationError && (
            <div style={{ padding: '16px 20px', backgroundColor: '#fef2f2', color: '#b91c1c', fontSize: '13px', borderBottom: '1px solid #fecaca' }}>
              {invitationError}
            </div>
          )}

          {loadingInvitations ? (
            <div style={{ padding: '64px 0', textAlign: 'center', color: '#64748b' }}>
              <div className="spinner" style={{ margin: '0 auto 12px' }} />
              Loading invitations...
            </div>
          ) : invitations.length === 0 ? (
            <div style={{ padding: '64px 0', textAlign: 'center', color: '#94a3b8', fontSize: '14px' }}>
              No branch invitations found.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    <th style={{ padding: '14px 18px' }}>Invited Email</th>
                    <th style={{ padding: '14px 18px' }}>Role</th>
                    <th style={{ padding: '14px 18px' }}>Branch</th>
                    <th style={{ padding: '14px 18px' }}>Expires At</th>
                    <th style={{ padding: '14px 18px' }}>Status</th>
                    <th style={{ padding: '14px 18px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {invitations.map((inv) => (
                    <tr key={inv.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '14px 18px', fontWeight: 600, color: '#0f172a' }}>
                        {inv.email}
                      </td>
                      <td style={{ padding: '14px 18px' }}>
                        <span style={{
                          padding: '3px 8px',
                          borderRadius: '4px',
                          fontSize: '11px',
                          fontWeight: 700,
                          backgroundColor: inv.invited_role === 'UPLOADER' ? '#fdf4ff' : '#f1f5f9',
                          color: inv.invited_role === 'UPLOADER' ? '#a21caf' : '#334155',
                          border: `1px solid ${inv.invited_role === 'UPLOADER' ? '#f5d0fe' : '#e2e8f0'}`,
                        }}>
                          {inv.invited_role}
                        </span>
                      </td>
                      <td style={{ padding: '14px 18px' }}>
                        {inv.branch_name || `Branch #${inv.branch_id}`}
                      </td>
                      <td style={{ padding: '14px 18px', color: '#64748b', fontSize: '12px' }}>
                        {new Date(inv.expires_at).toLocaleString()}
                      </td>
                      <td style={{ padding: '14px 18px' }}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '10px',
                          fontSize: '11px',
                          fontWeight: 700,
                          backgroundColor: inv.status === 'accepted' ? '#ecfdf5' : inv.status === 'pending' ? '#eff6ff' : '#fef2f2',
                          color: inv.status === 'accepted' ? '#047857' : inv.status === 'pending' ? '#1d4ed8' : '#b91c1c',
                        }}>
                          {(inv.status || 'pending').toUpperCase()}
                        </span>
                      </td>
                      <td style={{ padding: '14px 18px', textAlign: 'right' }}>
                        {inv.status === 'pending' && (
                          <div style={{ display: 'inline-flex', gap: '6px' }}>
                            <button
                              onClick={() => handleResendInvitation(inv)}
                              style={{
                                padding: '5px 10px',
                                borderRadius: '6px',
                                border: '1px solid #cbd5e1',
                                backgroundColor: '#ffffff',
                                color: '#334155',
                                fontSize: '12px',
                                fontWeight: 500,
                                cursor: 'pointer',
                              }}
                            >
                              Resend
                            </button>
                            <button
                              onClick={() => handleRevokeInvitation(inv)}
                              style={{
                                padding: '5px 10px',
                                borderRadius: '6px',
                                border: '1px solid #fecaca',
                                backgroundColor: '#fff5f5',
                                color: '#b91c1c',
                                fontSize: '12px',
                                fontWeight: 600,
                                cursor: 'pointer',
                              }}
                            >
                              Revoke
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Invite User Modal ───────────────────────────────────────────── */}
      {isInviteModalOpen && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(3px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '14px',
            width: '100%',
            maxWidth: '520px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
            overflow: 'hidden',
          }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                  Invite Staff or Uploader
                </h3>
                <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#64748b' }}>
                  Send an invitation to join your authorized branch.
                </p>
              </div>
              <button
                onClick={() => setIsInviteModalOpen(false)}
                style={{ border: 'none', background: 'transparent', fontSize: '20px', cursor: 'pointer', color: '#94a3b8' }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleInviteSubmit} style={{ padding: '24px' }}>
              {inviteError && (
                <div style={{ padding: '12px 14px', backgroundColor: '#fef2f2', color: '#b91c1c', borderRadius: '8px', fontSize: '13px', marginBottom: '16px' }}>
                  {inviteError}
                </div>
              )}

              {inviteSuccessMsg && (
                <div style={{ padding: '14px', backgroundColor: '#ecfdf5', color: '#047857', borderRadius: '8px', fontSize: '13px', marginBottom: '16px' }}>
                  <div style={{ fontWeight: 600 }}>{inviteSuccessMsg}</div>
                </div>
              )}

              {/* Name */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Employee Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Jane Doe"
                  value={inviteForm.name}
                  onChange={(e) => setInviteForm({ ...inviteForm, name: e.target.value })}
                  style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', outline: 'none' }}
                />
              </div>

              {/* Email */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Email Address *
                </label>
                <input
                  type="email"
                  required
                  placeholder="e.g. jane.doe@company.com"
                  value={inviteForm.email}
                  onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                  style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', outline: 'none' }}
                />
              </div>

              {/* Mobile */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Mobile Number (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. +91 9876543210"
                  value={inviteForm.mobile}
                  onChange={(e) => setInviteForm({ ...inviteForm, mobile: e.target.value })}
                  style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', outline: 'none' }}
                />
              </div>

              {/* Role */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Assigned Role *
                </label>
                <select
                  value={inviteForm.role}
                  onChange={(e) => setInviteForm({ ...inviteForm, role: e.target.value })}
                  style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff' }}
                >
                  <option value="STAFF">Staff (Documents, Invoices, Reviews)</option>
                  <option value="UPLOADER">Uploader (Document Ingestion Only)</option>
                </select>
                <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
                  {inviteForm.role === 'STAFF' && 'Staff can upload, view, edit extractions, and manage sales invoices within their branch.'}
                  {inviteForm.role === 'UPLOADER' && 'Uploaders are limited to uploading and searching documents within their branch.'}
                </div>
              </div>

              {/* Branch */}
              <div style={{ marginBottom: '24px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Branch Workspace *
                </label>
                {authorizedBranches.length > 1 ? (
                  <select
                    value={inviteForm.branch_id}
                    onChange={(e) => setInviteForm({ ...inviteForm, branch_id: e.target.value })}
                    style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px', backgroundColor: '#ffffff' }}
                  >
                    {authorizedBranches.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name} ({b.code})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    readOnly
                    value={authorizedBranches[0]?.name || user?.branch_name || 'Primary Branch'}
                    style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #e2e8f0', backgroundColor: '#f8fafc', color: '#64748b', fontSize: '13px' }}
                  />
                )}
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setIsInviteModalOpen(false)}
                  style={{ padding: '9px 16px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  {inviteSuccessMsg ? 'Close' : 'Cancel'}
                </button>
                {!inviteSuccessMsg && (
                  <button
                    type="submit"
                    disabled={submittingInvite}
                    style={{
                      padding: '9px 18px',
                      borderRadius: '8px',
                      border: 'none',
                      backgroundColor: submittingInvite ? '#93c5fd' : '#2563eb',
                      color: '#ffffff',
                      fontSize: '13px',
                      fontWeight: 600,
                      cursor: submittingInvite ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {submittingInvite ? 'Sending...' : 'Send Invitation'}
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Edit User Modal ─────────────────────────────────────────────── */}
      {isEditModalOpen && editingUser && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(3px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '14px',
            width: '100%',
            maxWidth: '480px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
            overflow: 'hidden',
          }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                  Edit Employee Details
                </h3>
                <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#64748b' }}>
                  Update employee profile information.
                </p>
              </div>
              <button
                onClick={() => setIsEditModalOpen(false)}
                style={{ border: 'none', background: 'transparent', fontSize: '20px', cursor: 'pointer', color: '#94a3b8' }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleEditSubmit} style={{ padding: '24px' }}>
              {editError && (
                <div style={{ padding: '12px 14px', backgroundColor: '#fef2f2', color: '#b91c1c', borderRadius: '8px', fontSize: '13px', marginBottom: '16px' }}>
                  {editError}
                </div>
              )}

              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Employee Name *
                </label>
                <input
                  type="text"
                  required
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px' }}
                />
              </div>

              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Email Address *
                </label>
                <input
                  type="email"
                  required
                  value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                  style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px' }}
                />
              </div>

              <div style={{ marginBottom: '24px' }}>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '6px' }}>
                  Mobile Number
                </label>
                <input
                  type="text"
                  value={editForm.mobile}
                  onChange={(e) => setEditForm({ ...editForm, mobile: e.target.value })}
                  style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #cbd5e1', fontSize: '13px' }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setIsEditModalOpen(false)}
                  style={{ padding: '9px 16px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingEdit}
                  style={{
                    padding: '9px 18px',
                    borderRadius: '8px',
                    border: 'none',
                    backgroundColor: submittingEdit ? '#93c5fd' : '#2563eb',
                    color: '#ffffff',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: submittingEdit ? 'not-allowed' : 'pointer',
                  }}
                >
                  {submittingEdit ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Deactivate / Reactivate Confirmation Modal ───────────────────── */}
      {confirmModal.isOpen && confirmModal.user && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(3px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '20px',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '14px',
            width: '100%',
            maxWidth: '440px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
            overflow: 'hidden',
          }}>
            <div style={{ padding: '24px' }}>
              <div style={{
                width: '44px',
                height: '44px',
                borderRadius: '50%',
                backgroundColor: confirmModal.type === 'deactivate' ? '#fee2e2' : '#ecfdf5',
                color: confirmModal.type === 'deactivate' ? '#dc2626' : '#059669',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '20px',
                marginBottom: '16px',
              }}>
                {confirmModal.type === 'deactivate' ? '⚠️' : '✓'}
              </div>

              <h3 style={{ margin: '0 0 8px', fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
                {confirmModal.type === 'deactivate' ? 'Deactivate User Account' : 'Reactivate User Account'}
              </h3>

              <p style={{ margin: '0 0 16px', fontSize: '13px', color: '#64748b', lineHeight: 1.5 }}>
                {confirmModal.type === 'deactivate' ? (
                  <>
                    Are you sure you want to deactivate <strong>{confirmModal.user.name}</strong> ({confirmModal.user.email})?
                    All active sessions will be terminated immediately. The user will be unable to sign in until reactivated.
                  </>
                ) : (
                  <>
                    Are you sure you want to reactivate <strong>{confirmModal.user.name}</strong> ({confirmModal.user.email})?
                    The employee will regain access to their branch workspace.
                  </>
                )}
              </p>

              {confirmModal.error && (
                <div style={{ padding: '10px 14px', backgroundColor: '#fef2f2', color: '#b91c1c', borderRadius: '8px', fontSize: '12px', marginBottom: '16px' }}>
                  {confirmModal.error}
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => setConfirmModal({ isOpen: false, type: 'deactivate', user: null, loading: false, error: '' })}
                  style={{ padding: '9px 16px', borderRadius: '8px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', color: '#475569', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={confirmModal.loading}
                  onClick={handleConfirmAction}
                  style={{
                    padding: '9px 18px',
                    borderRadius: '8px',
                    border: 'none',
                    backgroundColor: confirmModal.type === 'deactivate' ? '#dc2626' : '#16a34a',
                    color: '#ffffff',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: confirmModal.loading ? 'not-allowed' : 'pointer',
                  }}
                >
                  {confirmModal.loading ? 'Processing...' : (confirmModal.type === 'deactivate' ? 'Confirm Deactivation' : 'Confirm Activation')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
