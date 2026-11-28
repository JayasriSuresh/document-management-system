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

  // Edit Template state
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [editingVersion, setEditingVersion] = useState(null);
  const [isCustomizingPlatform, setIsCustomizingPlatform] = useState(false);
  const [loadingEdit, setLoadingEdit] = useState(false);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState('');
  const [editName, setEditName] = useState('');
  const [editDocType, setEditDocType] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editScopeBranchId, setScopeBranchIdEdit] = useState('');
  const [editInstructions, setEditInstructions] = useState('');
  const [editFields, setEditFields] = useState([]);
  const [editRawJson, setEditRawJson] = useState('');
  const [editSchemaMode, setEditSchemaMode] = useState('visual');
  const [editPublishImmediately, setEditPublishImmediately] = useState(true);

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

  const handleOpenEditModal = async (tmpl) => {
    try {
      setLoadingEdit(true);
      setEditingTemplate(tmpl);
      setIsCustomizingPlatform(false);
      setEditName(tmpl.name);
      setEditDocType(tmpl.document_type);
      setEditDescription(tmpl.description || '');
      setScopeBranchIdEdit(tmpl.branch_id ? String(tmpl.branch_id) : '');
      setEditPublishImmediately(true);
      setEditError('');

      let vDetail = null;
      if (tmpl.published_version) {
        vDetail = await api.getTemplateVersionDetail(tmpl.id, tmpl.published_version.id);
      }
      setEditingVersion(vDetail);
      setEditInstructions(vDetail?.extraction_instructions || '');

      const schema = vDetail?.schema_json || {};
      setEditRawJson(JSON.stringify(schema, null, 2));

      const hasNested = Array.isArray(schema.fields) && schema.fields.some((f) => f.fields || f.item_fields);
      if (hasNested) {
        setEditSchemaMode('json');
      } else {
        setEditSchemaMode('visual');
      }

      if (Array.isArray(schema.fields) && schema.fields.length > 0) {
        const flatFields = schema.fields.map((f) => ({
          key: f.key || '',
          label: f.label || f.key || '',
          type: f.type || 'string',
          required: Boolean(f.required),
        }));
        setEditFields(flatFields);
      } else {
        setEditFields([{ key: 'total_amount', label: 'Total Amount', type: 'number', required: true }]);
      }
    } catch (err) {
      showToast?.(err.message || 'Failed to load template detail', 'error');
      setEditingTemplate(null);
    } finally {
      setLoadingEdit(false);
    }
  };

  const handleOpenCustomizeModal = async (tmpl) => {
    try {
      setLoadingEdit(true);
      setEditingTemplate(tmpl);
      setIsCustomizingPlatform(true);
      setEditName(`${tmpl.name} (Custom)`);
      setEditDocType(tmpl.document_type);
      setEditDescription(tmpl.description || '');
      setScopeBranchIdEdit('');
      setEditPublishImmediately(true);
      setEditError('');

      let vDetail = null;
      if (tmpl.published_version) {
        vDetail = await api.getTemplateVersionDetail(tmpl.id, tmpl.published_version.id);
      }
      setEditingVersion(vDetail);
      setEditInstructions(vDetail?.extraction_instructions || '');

      const schema = vDetail?.schema_json || {};
      setEditRawJson(JSON.stringify(schema, null, 2));

      const hasNested = Array.isArray(schema.fields) && schema.fields.some((f) => f.fields || f.item_fields);
      if (hasNested) {
        setEditSchemaMode('json');
      } else {
        setEditSchemaMode('visual');
      }

      if (Array.isArray(schema.fields) && schema.fields.length > 0) {
        const flatFields = schema.fields.map((f) => ({
          key: f.key || '',
          label: f.label || f.key || '',
          type: f.type || 'string',
          required: Boolean(f.required),
        }));
        setEditFields(flatFields);
      } else {
        setEditFields([{ key: 'total_amount', label: 'Total Amount', type: 'number', required: true }]);
      }
    } catch (err) {
      showToast?.(err.message || 'Failed to load template detail', 'error');
      setEditingTemplate(null);
    } finally {
      setLoadingEdit(false);
    }
  };

  const handleAddEditField = () => {
    setEditFields([...editFields, { key: '', label: '', type: 'string', required: false }]);
  };

  const handleRemoveEditField = (idx) => {
    setEditFields(editFields.filter((_, i) => i !== idx));
  };

  const handleEditFieldChange = (idx, prop, val) => {
    const updated = [...editFields];
    updated[idx] = { ...updated[idx], [prop]: val };
    setEditFields(updated);
  };

  const handleSwitchToVisual = () => {
    try {
      const parsed = JSON.parse(editRawJson);
      if (Array.isArray(parsed.fields) && parsed.fields.length > 0) {
        setEditFields(
          parsed.fields.map((f) => ({
            key: f.key || '',
            label: f.label || f.key || '',
            type: f.type || 'string',
            required: Boolean(f.required),
          }))
        );
      }
      setEditSchemaMode('visual');
      setEditError('');
    } catch (e) {
      setEditError('Cannot switch to visual editor: Raw JSON is invalid. Please fix JSON syntax first.');
    }
  };

  const handleSwitchToJson = () => {
    const validFields = editFields.filter((f) => f.key.trim());
    if (validFields.length > 0 && editSchemaMode === 'visual') {
      const generated = {
        type: 'object',
        fields: validFields.map((f) => ({
          key: f.key.trim().toLowerCase().replace(/\s+/g, '_'),
          label: f.label || f.key,
          type: f.type,
          required: Boolean(f.required),
        })),
      };
      setEditRawJson(JSON.stringify(generated, null, 2));
    }
    setEditSchemaMode('json');
    setEditError('');
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editName.trim()) {
      setEditError('Template name is required.');
      return;
    }
    setEditSubmitting(true);
    setEditError('');

    try {
      let schemaJson = {};
      if (editSchemaMode === 'json') {
        try {
          schemaJson = JSON.parse(editRawJson);
        } catch (jsonErr) {
          setEditError(`Invalid JSON schema: ${jsonErr.message}`);
          setEditSubmitting(false);
          return;
        }
      } else {
        const validFields = editFields.filter((f) => f.key.trim());
        if (validFields.length === 0) {
          setEditError('At least one field is required in the schema.');
          setEditSubmitting(false);
          return;
        }
        schemaJson = {
          type: 'object',
          fields: validFields.map((f) => ({
            key: f.key.trim().toLowerCase().replace(/\s+/g, '_'),
            label: f.label || f.key,
            type: f.type,
            required: Boolean(f.required),
          })),
        };
      }

      if (isCustomizingPlatform) {
        const payload = {
          name: editName.trim(),
          document_type: editDocType.trim().toLowerCase().replace(/\s+/g, '_'),
          branch_id: editScopeBranchId ? parseInt(editScopeBranchId, 10) : null,
          description: editDescription.trim() || null,
          schema_json: schemaJson,
          validation_rules: editingVersion?.validation_rules || [
            {
              rule_id: 'required_fields',
              type: 'required',
              fields: (schemaJson.fields || []).filter((f) => f.required).map((f) => f.key),
              severity: 'error',
            },
          ],
          extraction_instructions: editInstructions.trim() || `Extract all fields for ${editName.trim()} in JSON.`,
          publish_initial: true,
        };
        await api.createTemplate(payload);
        showToast?.(`Custom template '${editName}' created successfully!`, 'success');
      } else {
        // 1. Update metadata if changed
        if (editName.trim() !== editingTemplate.name || (editDescription.trim() || null) !== (editingTemplate.description || null)) {
          await api.updateTemplate(editingTemplate.id, {
            name: editName.trim(),
            description: editDescription.trim() || null,
          });
        }

        // 2. Create new draft version
        const versionPayload = {
          schema_json: schemaJson,
          validation_rules: editingVersion?.validation_rules || [
            {
              rule_id: 'required_fields',
              type: 'required',
              fields: (schemaJson.fields || []).filter((f) => f.required).map((f) => f.key),
              severity: 'error',
            },
          ],
          extraction_instructions: editInstructions.trim() || `Extract all fields for ${editName.trim()} in JSON.`,
        };
        const newVer = await api.createTemplateDraftVersion(editingTemplate.id, versionPayload);

        // 3. Publish if requested
        if (editPublishImmediately) {
          await api.publishTemplateVersion(editingTemplate.id, newVer.id);
          showToast?.(`Template '${editName}' updated & version ${newVer.version_number} published!`, 'success');
        } else {
          showToast?.(`Template '${editName}' updated with draft version ${newVer.version_number}!`, 'success');
        }
      }

      setEditingTemplate(null);
      fetchTemplates();
    } catch (err) {
      setEditError(err.message || 'Failed to save template changes.');
    } finally {
      setEditSubmitting(false);
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

                  {tmpl.company_id !== null ? (
                    <button
                      type="button"
                      onClick={() => handleOpenEditModal(tmpl)}
                      disabled={loadingEdit}
                      style={{
                        padding: '0.375rem 0.625rem',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        borderRadius: '4px',
                        border: '1px solid #3b82f6',
                        backgroundColor: '#eff6ff',
                        color: '#1d4ed8',
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                      Edit
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleOpenCustomizeModal(tmpl)}
                      disabled={loadingEdit}
                      style={{
                        padding: '0.375rem 0.625rem',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        borderRadius: '4px',
                        border: '1px solid #7c3aed',
                        backgroundColor: '#f5f3ff',
                        color: '#6d28d9',
                        cursor: 'pointer',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                      title="Clone as editable company template"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                      Customize
                    </button>
                  )}
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

      {/* ── Modal: Edit Existing Template ── */}
      {editingTemplate && (
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
            maxWidth: '740px',
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
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h3 style={{ fontSize: '1.125rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                    {isCustomizingPlatform ? 'Customize Template (Company Copy)' : 'Edit Extraction Template'}
                  </h3>
                  {!isCustomizingPlatform && editingTemplate.published_version && (
                    <span style={{
                      fontSize: '11px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '12px',
                      backgroundColor: '#dcfce7',
                      color: '#15803d',
                    }}>
                      Current: v{editingTemplate.published_version.version_number}
                    </span>
                  )}
                </div>
                <p style={{ fontSize: '0.8125rem', color: '#64748b', margin: '0.25rem 0 0 0' }}>
                  {isCustomizingPlatform
                    ? 'Creates an editable company template pre-filled from this platform default.'
                    : 'Modifying schema or instructions will automatically create and publish a new version.'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditingTemplate(null)}
                style={{ border: 'none', background: 'none', fontSize: '1.5rem', cursor: 'pointer', color: '#64748b' }}
              >
                &times;
              </button>
            </div>

            {/* Error banner */}
            {editError && (
              <div style={{ margin: '12px 1.5rem 0', padding: '10px 14px', borderRadius: '6px', backgroundColor: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', fontSize: '13px' }}>
                {editError}
              </div>
            )}

            {/* Modal Form Body */}
            <form onSubmit={handleSaveEdit} style={{ overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                    Template Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.875rem' }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                    Document Type
                  </label>
                  <input
                    type="text"
                    disabled={!isCustomizingPlatform}
                    value={editDocType}
                    onChange={(e) => setEditDocType(e.target.value)}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.875rem', backgroundColor: isCustomizingPlatform ? '#fff' : '#f1f5f9', color: isCustomizingPlatform ? '#0f172a' : '#64748b' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: '1rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                    Scope
                  </label>
                  <select
                    value={editScopeBranchId}
                    onChange={(e) => setScopeBranchIdEdit(e.target.value)}
                    disabled={!isCustomizingPlatform && Boolean(editingTemplate.branch_id)}
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
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.875rem' }}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600, color: '#334155', marginBottom: '0.25rem' }}>
                  AI Extraction Instructions
                </label>
                <textarea
                  rows={2}
                  placeholder="Instructions for the AI when parsing this document type..."
                  value={editInstructions}
                  onChange={(e) => setEditInstructions(e.target.value)}
                  style={{ width: '100%', padding: '0.5rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '0.875rem' }}
                />
              </div>

              {/* ── Schema Fields Editor ── */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <label style={{ fontSize: '0.875rem', fontWeight: 700, color: '#0f172a' }}>
                      Schema Specification
                    </label>
                    <div style={{ display: 'inline-flex', borderRadius: '6px', border: '1px solid #cbd5e1', overflow: 'hidden' }}>
                      <button
                        type="button"
                        onClick={handleSwitchToVisual}
                        style={{
                          padding: '3px 8px',
                          border: 'none',
                          fontSize: '11px',
                          fontWeight: 600,
                          backgroundColor: editSchemaMode === 'visual' ? '#2563eb' : '#fff',
                          color: editSchemaMode === 'visual' ? '#fff' : '#64748b',
                          cursor: 'pointer',
                        }}
                      >
                        Visual Editor
                      </button>
                      <button
                        type="button"
                        onClick={handleSwitchToJson}
                        style={{
                          padding: '3px 8px',
                          border: 'none',
                          fontSize: '11px',
                          fontWeight: 600,
                          backgroundColor: editSchemaMode === 'json' ? '#2563eb' : '#fff',
                          color: editSchemaMode === 'json' ? '#fff' : '#64748b',
                          cursor: 'pointer',
                        }}
                      >
                        Raw JSON Schema
                      </button>
                    </div>
                  </div>

                  {editSchemaMode === 'visual' && (
                    <button
                      type="button"
                      onClick={handleAddEditField}
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
                  )}
                </div>

                {editSchemaMode === 'visual' ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {editFields.map((f, idx) => (
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
                          onChange={(e) => handleEditFieldChange(idx, 'key', e.target.value)}
                          style={{ padding: '0.375rem', fontSize: '0.8125rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                        />

                        <input
                          type="text"
                          placeholder="Display Label"
                          value={f.label}
                          onChange={(e) => handleEditFieldChange(idx, 'label', e.target.value)}
                          style={{ padding: '0.375rem', fontSize: '0.8125rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                        />

                        <select
                          value={f.type}
                          onChange={(e) => handleEditFieldChange(idx, 'type', e.target.value)}
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
                            onChange={(e) => handleEditFieldChange(idx, 'required', e.target.checked)}
                          />
                          Req
                        </label>

                        <button
                          type="button"
                          onClick={() => handleRemoveEditField(idx)}
                          style={{ border: 'none', background: 'none', color: '#ef4444', cursor: 'pointer', fontWeight: 700 }}
                        >
                          &times;
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div>
                    <textarea
                      rows={12}
                      value={editRawJson}
                      onChange={(e) => setEditRawJson(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '0.75rem',
                        fontFamily: 'monospace',
                        fontSize: '0.8125rem',
                        borderRadius: '6px',
                        border: '1px solid #cbd5e1',
                        backgroundColor: '#0f172a',
                        color: '#38bdf8',
                        lineHeight: '1.4',
                        boxSizing: 'border-box',
                      }}
                    />
                    <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
                      Tip: You can customize full nested objects, line item arrays, or validation rules directly in the JSON schema.
                    </div>
                  </div>
                )}
              </div>

              {!isCustomizingPlatform && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px', backgroundColor: '#f0fdf4', borderRadius: '6px', border: '1px solid #bbf7d0' }}>
                  <input
                    type="checkbox"
                    id="publishImmediately"
                    checked={editPublishImmediately}
                    onChange={(e) => setEditPublishImmediately(e.target.checked)}
                    style={{ cursor: 'pointer' }}
                  />
                  <label htmlFor="publishImmediately" style={{ fontSize: '12.5px', fontWeight: 600, color: '#166534', cursor: 'pointer' }}>
                    Publish immediately as active version
                  </label>
                </div>
              )}

              {/* Modal Footer Actions */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
                <button
                  type="button"
                  onClick={() => setEditingTemplate(null)}
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
                  disabled={editSubmitting}
                  style={{
                    padding: '0.5rem 1.25rem',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: '#2563eb',
                    color: '#ffffff',
                    fontWeight: 600,
                    fontSize: '0.875rem',
                    cursor: editSubmitting ? 'not-allowed' : 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  {editSubmitting ? (
                    <>
                      <div className="spinner" style={{ width: '14px', height: '14px', borderTopColor: '#ffffff' }} />
                      Saving Changes...
                    </>
                  ) : isCustomizingPlatform ? (
                    'Save as Custom Template'
                  ) : (
                    'Save Changes'
                  )}
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
