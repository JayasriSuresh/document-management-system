import { useState, useEffect } from 'react';
import { api } from '../api';

export default function TemplateManagementView({ branchesList = [], showToast }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedBranch, setSelectedBranch] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [viewingVersionModal, setViewingVersionModal] = useState(null);
  const [versionHistoryModal, setVersionHistoryModal] = useState(null);
  const [versionsList, setVersionsList] = useState([]);

  // Create Template form state
  const [name, setName] = useState('');
  const [docType, setDocType] = useState('');
  const [scopeBranchId, setScopeBranchId] = useState('');
  const [description, setDescription] = useState('');
  const [instructions, setInstructions] = useState('');
  const [fields, setFields] = useState([
    { key: 'merchant_name', label: 'Merchant / Vendor Name', type: 'string', required: true },
    { key: 'date', label: 'Receipt Date', type: 'date', required: true },
    { key: 'total_amount', label: 'Total Amount', type: 'number', required: true },
    { key: 'tax_amount', label: 'Tax Amount', type: 'number', required: false },
    { key: 'category', label: 'Expense Category', type: 'string', required: false },
  ]);
  const [submitting, setSubmitting] = useState(false);

  const fetchTemplates = async () => {
    try {
      setLoading(true);
      const params = {};
      if (selectedBranch) params.branch_id = selectedBranch;
      const data = await api.getTemplates(params);
      setTemplates(data || []);
    } catch (err) {
      showToast?.(err.message || 'Failed to load templates', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, [selectedBranch]);

  const handleAddField = () => {
    setFields([...fields, { key: '', label: '', type: 'string', required: false }]);
  };

  const handleRemoveField = (idx) => {
    setFields(fields.filter((_, i) => i !== idx));
  };

  const handleFieldChange = (idx, prop, val) => {
    const updated = [...fields];
    updated[idx] = { ...updated[idx], [prop]: val };
    setFields(updated);
  };

  const handleCreateTemplate = async (e) => {
    e.preventDefault();
    if (!name.trim() || !docType.trim()) {
      showToast?.('Template name and document type are required', 'error');
      return;
    }
    // Filter empty fields
    const validFields = fields.filter((f) => f.key.trim());
    if (validFields.length === 0) {
      showToast?.('At least one field must be declared in the schema', 'error');
      return;
    }

    const schema_json = {
      type: 'object',
      fields: validFields.map((f) => ({
        key: f.key.trim().toLowerCase().replace(/\s+/g, '_'),
        label: f.label || f.key,
        type: f.type,
        required: !!f.required,
      })),
    };

    const payload = {
      name: name.trim(),
      document_type: docType.trim().toLowerCase().replace(/\s+/g, '_'),
      branch_id: scopeBranchId ? parseInt(scopeBranchId, 10) : null,
      description: description.trim() || null,
      schema_json,
      validation_rules: [
        {
          rule_id: 'required_fields',
          type: 'required',
          fields: validFields.filter((f) => f.required).map((f) => f.key.trim().toLowerCase().replace(/\s+/g, '_')),
          severity: 'error',
        },
      ],
      extraction_instructions: instructions.trim() || `Extract all relevant fields for ${name.trim()} and return matching JSON.`,
      publish_initial: true,
    };

    try {
      setSubmitting(true);
      await api.createTemplate(payload);
      showToast?.(`Template '${name}' created and published successfully!`, 'success');
      setShowCreateModal(false);
      setName('');
      setDocType('');
      setDescription('');
      setScopeBranchId('');
      fetchTemplates();
    } catch (err) {
      showToast?.(err.message || 'Failed to create template', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleViewVersions = async (template) => {
    try {
      const v = await api.getTemplateVersions(template.id);
      setVersionsList(v || []);
      setVersionHistoryModal(template);
    } catch (err) {
      showToast?.(err.message || 'Failed to fetch version history', 'error');
    }
  };

  const handleViewVersionDetail = async (templateId, versionId) => {
    try {
      const detail = await api.getTemplateVersionDetail(templateId, versionId);
      setViewingVersionModal(detail);
    } catch (err) {
      showToast?.(err.message || 'Failed to fetch version detail', 'error');
    }
  };

  const handleDeactivate = async (tmpl) => {
    if (!window.confirm(`Are you sure you want to deactivate template '${tmpl.name}'? Existing documents will retain historical extraction data.`)) {
      return;
    }
    try {
      await api.deactivateTemplate(tmpl.id);
      showToast?.(`Template '${tmpl.name}' deactivated.`, 'success');
      fetchTemplates();
    } catch (err) {
      showToast?.(err.message || 'Failed to deactivate template', 'error');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* ── Header & Actions ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
            Document Extraction Templates
          </h2>
          <p style={{ fontSize: '0.875rem', color: '#64748b', margin: '0.25rem 0 0 0' }}>
            Configure custom extraction schemas, immutable versions, and deterministic validation rules.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          {branchesList.length > 0 && (
            <select
              value={selectedBranch}
              onChange={(e) => setSelectedBranch(e.target.value)}
              style={{
                padding: '0.5rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '0.875rem',
                backgroundColor: '#ffffff',
                color: '#334155',
              }}
            >
              <option value="">All Scopes (Company & Branches)</option>
              {branchesList.map((b) => (
                <option key={b.id} value={b.id}>{b.name} ({b.branch_code})</option>
              ))}
            </select>
          )}

          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              backgroundColor: '#dc2626',
              color: '#ffffff',
              padding: '0.5rem 1rem',
              borderRadius: '6px',
              border: 'none',
              fontWeight: 600,
              fontSize: '0.875rem',
              cursor: 'pointer',
            }}
          >
            <span>+</span> New Extraction Template
          </button>
        </div>
      </div>

      {/* ── Templates List / Cards ── */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: '#64748b' }}>
          Loading extraction templates...
        </div>
      ) : templates.length === 0 ? (
        <div style={{
          backgroundColor: '#f8fafc',
          border: '1px dashed #cbd5e1',
          borderRadius: '8px',
          padding: '3rem',
          textAlign: 'center',
          color: '#64748b',
        }}>
          <p style={{ margin: 0, fontWeight: 600 }}>No extraction templates found.</p>
          <p style={{ fontSize: '0.875rem', margin: '0.25rem 0 1rem 0' }}>
            Create custom templates for receipts, purchase orders, or bills.
          </p>
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            style={{
              backgroundColor: '#dc2626',
              color: '#ffffff',
              padding: '0.5rem 1rem',
              borderRadius: '6px',
              border: 'none',
              fontWeight: 600,
              fontSize: '0.875rem',
              cursor: 'pointer',
            }}
          >
            Create Your First Custom Template
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: '1rem' }}>
          {templates.map((tmpl) => (
            <div
              key={tmpl.id}
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                padding: '1.25rem',
                boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                    {tmpl.name}
                  </h3>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '12px',
                      backgroundColor: tmpl.status === 'active' ? '#ecfdf5' : '#f1f5f9',
                      color: tmpl.status === 'active' ? '#047857' : '#64748b',
                      textTransform: 'uppercase',
                    }}
                  >
                    {tmpl.status}
                  </span>
                </div>

                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                  <span style={{
                    fontSize: '0.75rem',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    backgroundColor: '#e0f2fe',
                    color: '#0369a1',
                    fontWeight: 600,
                  }}>
                    Type: {tmpl.document_type}
                  </span>

                  <span style={{
                    fontSize: '0.75rem',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    backgroundColor: tmpl.branch_id ? '#fef3c7' : '#f3e8ff',
                    color: tmpl.branch_id ? '#92400e' : '#6b21a8',
                    fontWeight: 600,
                  }}>
                    {tmpl.branch_name ? `Branch: ${tmpl.branch_name}` : 'Scope: Company-wide'}
                  </span>

                  {tmpl.published_version && (
                    <span style={{
                      fontSize: '0.75rem',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      backgroundColor: '#dcfce7',
                      color: '#15803d',
                      fontWeight: 600,
                    }}>
                      Published: v{tmpl.published_version.version_number}
                    </span>
                  )}
                </div>

                {tmpl.description && (
                  <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0 0 1rem 0' }}>
                    {tmpl.description}
                  </p>
                )}
              </div>

              {/* Actions Footer */}
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                borderTop: '1px solid #f1f5f9',
                paddingTop: '0.75rem',
                marginTop: '0.5rem',
              }}>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  {tmpl.published_version && (
                    <button
                      type="button"
                      onClick={() => handleViewVersionDetail(tmpl.id, tmpl.published_version.id)}
                      style={{
                        padding: '0.375rem 0.625rem',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        borderRadius: '4px',
                        border: '1px solid #cbd5e1',
                        backgroundColor: '#ffffff',
                        color: '#334155',
                        cursor: 'pointer',
                      }}
                    >
                      View Schema
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => handleViewVersions(tmpl)}
                    style={{
                      padding: '0.375rem 0.625rem',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      borderRadius: '4px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: '#ffffff',
                      color: '#334155',
                      cursor: 'pointer',
                    }}
                  >
                    History ({tmpl.versions_count})
                  </button>
                </div>

                {tmpl.status === 'active' && tmpl.company_id !== null && (
                  <button
                    type="button"
                    onClick={() => handleDeactivate(tmpl)}
                    style={{
                      padding: '0.375rem 0.625rem',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      borderRadius: '4px',
                      border: 'none',
                      backgroundColor: '#fee2e2',
                      color: '#991b1b',
                      cursor: 'pointer',
                    }}
                  >
                    Deactivate
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Modal: Constrained Template Editor (Create) ── */}
      {showCreateModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(2px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '1rem',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            maxWidth: '700px',
            width: '100%',
            maxHeight: '90vh',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
          }}>
            {/* Modal Header */}
            <div style={{
              padding: '1.25rem 1.5rem',
              borderBottom: '1px solid #e2e8f0',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <div>
                <h3 style={{ fontSize: '1.125rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                  Create Extraction Template
                </h3>
                <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0.25rem 0 0 0' }}>
                  Define schema fields and instructions. A published version 1 will be created.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                style={{ border: 'none', background: 'none', fontSize: '1.5rem', cursor: 'pointer', color: '#64748b' }}
              >
                &times;
              </button>
            </div>

            {/* Modal Form Body */}
            <form onSubmit={handleCreateTemplate} style={{ overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                    Template Name *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Expense Receipt"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.875rem' }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                    Document Type Key *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. expense_receipt"
                    value={docType}
                    onChange={(e) => setDocType(e.target.value)}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.875rem' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                    Scope
                  </label>
                  <select
                    value={scopeBranchId}
                    onChange={(e) => setScopeBranchId(e.target.value)}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.875rem', backgroundColor: '#ffffff' }}
                  >
                    <option value="">Company-Wide (All Branches)</option>
                    {branchesList.map((b) => (
                      <option key={b.id} value={b.id}>Branch: {b.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                    Description
                  </label>
                  <input
                    type="text"
                    placeholder="Brief description of this document template"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.875rem' }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                  AI Extraction Instructions (Optional)
                </label>
                <textarea
                  rows={2}
                  placeholder="Instructions for the AI when parsing this document type..."
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.875rem' }}
                />
              </div>

              {/* ── Fields Definition ── */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <label style={{ fontSize: '0.875rem', fontWeight: 700, color: '#0f172a' }}>
                    Extracted Schema Fields
                  </label>
                  <button
                    type="button"
                    onClick={handleAddField}
                    style={{
                      border: 'none',
                      backgroundColor: '#eff6ff',
                      color: '#2563eb',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    + Add Field
                  </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {fields.map((f, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1.2fr 1.2fr 1fr auto auto',
                        gap: '0.5rem',
                        alignItems: 'center',
                        backgroundColor: '#f8fafc',
                        padding: '0.5rem',
                        borderRadius: '6px',
                        border: '1px solid #e2e8f0',
                      }}
                    >
                      <input
                        type="text"
                        placeholder="Field Key (e.g. total)"
                        value={f.key}
                        onChange={(e) => handleFieldChange(idx, 'key', e.target.value)}
                        style={{ padding: '0.375rem', fontSize: '0.8125rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                      />

                      <input
                        type="text"
                        placeholder="Display Label"
                        value={f.label}
                        onChange={(e) => handleFieldChange(idx, 'label', e.target.value)}
                        style={{ padding: '0.375rem', fontSize: '0.8125rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                      />

                      <select
                        value={f.type}
                        onChange={(e) => handleFieldChange(idx, 'type', e.target.value)}
                        style={{ padding: '0.375rem', fontSize: '0.8125rem', borderRadius: '4px', border: '1px solid #cbd5e1', backgroundColor: '#fff' }}
                      >
                        <option value="string">String</option>
                        <option value="number">Number</option>
                        <option value="integer">Integer</option>
                        <option value="date">Date</option>
                        <option value="boolean">Boolean</option>
                      </select>

                      <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem', color: '#475569', cursor: 'pointer' }}>
                        <input
                          type="checkbox"
                          checked={f.required}
                          onChange={(e) => handleFieldChange(idx, 'required', e.target.checked)}
                        />
                        Req
                      </label>

                      <button
                        type="button"
                        onClick={() => handleRemoveField(idx)}
                        style={{ border: 'none', background: 'none', color: '#ef4444', cursor: 'pointer', fontWeight: 700 }}
                      >
                        &times;
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Modal Footer Actions */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem' }}>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  style={{
                    padding: '0.5rem 1rem',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: '#ffffff',
                    fontWeight: 600,
                    fontSize: '0.875rem',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  style={{
                    padding: '0.5rem 1.25rem',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: '#dc2626',
                    color: '#ffffff',
                    fontWeight: 600,
                    fontSize: '0.875rem',
                    cursor: submitting ? 'not-allowed' : 'pointer',
                  }}
                >
                  {submitting ? 'Publishing...' : 'Save & Publish Version 1'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: View Schema Detail ── */}
      {viewingVersionModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(2px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '1rem',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            maxWidth: '600px',
            width: '100%',
            maxHeight: '85vh',
            display: 'flex',
            flexDirection: 'column',
          }}>
            <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, margin: 0 }}>
                Template Schema (Version {viewingVersionModal.version_number})
              </h3>
              <button
                type="button"
                onClick={() => setViewingVersionModal(null)}
                style={{ border: 'none', background: 'none', fontSize: '1.25rem', cursor: 'pointer' }}
              >
                &times;
              </button>
            </div>
            <div style={{ padding: '1rem', overflowY: 'auto' }}>
              <pre style={{
                backgroundColor: '#0f172a',
                color: '#38bdf8',
                padding: '1rem',
                borderRadius: '8px',
                fontSize: '0.75rem',
                overflowX: 'auto',
                margin: 0,
              }}>
                {JSON.stringify(viewingVersionModal.schema_json, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Version History ── */}
      {versionHistoryModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(2px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '1rem',
        }}>
          <div style={{
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            maxWidth: '550px',
            width: '100%',
            maxHeight: '85vh',
            display: 'flex',
            flexDirection: 'column',
          }}>
            <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ fontSize: '1rem', fontWeight: 700, margin: 0 }}>
                  Version History: {versionHistoryModal.name}
                </h3>
                <p style={{ fontSize: '0.75rem', color: '#64748b', margin: '0.125rem 0 0 0' }}>
                  All published and historical versions are immutable.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setVersionHistoryModal(null)}
                style={{ border: 'none', background: 'none', fontSize: '1.25rem', cursor: 'pointer' }}
              >
                &times;
              </button>
            </div>
            <div style={{ padding: '1rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {versionsList.map((v) => (
                <div
                  key={v.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.75rem',
                    borderRadius: '6px',
                    border: '1px solid #e2e8f0',
                    backgroundColor: v.status === 'published' ? '#f0fdf4' : '#f8fafc',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontWeight: 700, fontSize: '0.875rem' }}>v{v.version_number}</span>
                      <span style={{
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        padding: '1px 6px',
                        borderRadius: '4px',
                        backgroundColor: v.status === 'published' ? '#bbf7d0' : '#e2e8f0',
                        color: v.status === 'published' ? '#166534' : '#64748b',
                      }}>
                        {v.status.toUpperCase()}
                      </span>
                    </div>
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                      Created: {new Date(v.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleViewVersionDetail(versionHistoryModal.id, v.id)}
                    style={{
                      padding: '0.25rem 0.5rem',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      borderRadius: '4px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: '#ffffff',
                      cursor: 'pointer',
                    }}
                  >
                    Inspect
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
