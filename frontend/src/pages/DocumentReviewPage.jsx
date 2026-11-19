import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';

export default function DocumentReviewPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [approving, setApproving] = useState(false);
  const [extraction, setExtraction] = useState(null);
  const [formData, setFormData] = useState({});
  const [activeTab, setActiveTab] = useState('review'); // 'review' | 'history'
  const [editsHistory, setEditsHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [toast, setToast] = useState(null);

  // Zoom & Pan interactive viewer state
  const [zoom, setZoom] = useState(1);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0, scrollLeft: 0, scrollTop: 0 });
  const imageContainerRef = useRef(null);

  const handleZoomIn = () => setZoom((prev) => Math.min(Number((prev + 0.25).toFixed(2)), 3.5));
  const handleZoomOut = () => setZoom((prev) => Math.max(Number((prev - 0.25).toFixed(2)), 0.5));
  const handleZoomReset = () => {
    setZoom(1);
    if (imageContainerRef.current) {
      imageContainerRef.current.scrollLeft = 0;
      imageContainerRef.current.scrollTop = 0;
    }
  };

  const handleMouseDown = (e) => {
    if (zoom <= 1 || !imageContainerRef.current) return;
    setIsDragging(true);
    setDragStart({
      x: e.clientX,
      y: e.clientY,
      scrollLeft: imageContainerRef.current.scrollLeft,
      scrollTop: imageContainerRef.current.scrollTop,
    });
  };

  const handleMouseMove = (e) => {
    if (!isDragging || !imageContainerRef.current) return;
    e.preventDefault();
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    imageContainerRef.current.scrollLeft = dragStart.scrollLeft - dx;
    imageContainerRef.current.scrollTop = dragStart.scrollTop - dy;
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Override modal state
  const [showOverrideModal, setShowOverrideModal] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');

  // Raw JSON Mode State
  const [rawJsonText, setRawJsonText] = useState('');
  const [jsonError, setJsonError] = useState('');
  const [addingSection, setAddingSection] = useState(null);
  const [newFieldName, setNewFieldName] = useState('');
  const [copiedJson, setCopiedJson] = useState(false);

  const STANDARD_FIELDS = {
    invoice: ['number', 'date', 'reference_no', 'buyers_order_no', 'payment_terms', 'terms_of_delivery', 'other_references', 'due_date', 'place_of_supply'],
    seller: ['name', 'gstin', 'state', 'state_code', 'phone', 'email', 'address', 'pincode'],
    buyer: ['name', 'gstin', 'state', 'state_code', 'phone', 'email', 'address', 'pincode'],
    delivery: ['name', 'address', 'state', 'pincode'],
    totals: ['taxable_value', 'cgst', 'sgst', 'igst', 'cess', 'round_off', 'grand_total', 'amount_in_words', 'total_qty'],
    bank: ['bank_name', 'account_no', 'ifsc', 'branch', 'holder'],
  };

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  const signatureInputRef = useRef(null);

  const handleSignatureFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg'];
    if (!allowedTypes.includes(file.type)) {
      showToast('Unsupported file type. Please upload a PNG, JPG, or JPEG signature image.', 'error');
      if (signatureInputRef.current) signatureInputRef.current.value = '';
      return;
    }

    if (file.size > 2 * 1024 * 1024) {
      showToast('File size exceeds 2MB limit. Please upload a smaller signature image.', 'error');
      if (signatureInputRef.current) signatureInputRef.current.value = '';
      return;
    }

    const reader = new FileReader();
    reader.onload = (uploadEvent) => {
      const dataUrl = uploadEvent.target.result;
      setFormData((prev) => ({
        ...prev,
        signature_image: dataUrl,
        signature: {
          ...(prev.signature || {}),
          image_data: dataUrl,
          signer_name: prev.signature?.signer_name || prev.signer_name || prev.seller?.name || '',
          signer_title: 'Authorised Signatory',
        },
      }));
      showToast('Signature image uploaded. Click "Save Corrections" to apply.', 'info');
    };
    reader.onerror = () => {
      showToast('Failed to read image file.', 'error');
    };
    reader.readAsDataURL(file);
  };

  const handleRemoveSignature = () => {
    setFormData((prev) => {
      const updated = { ...prev };
      delete updated.signature_image;
      if (updated.signature) {
        delete updated.signature.image_data;
        delete updated.signature.image_url;
      }
      return updated;
    });
    if (signatureInputRef.current) signatureInputRef.current.value = '';
    showToast('Signature removed. Click "Save Corrections" to apply.', 'info');
  };

  const fetchExtraction = async () => {
    try {
      setLoading(true);
      const data = await api.getDocumentExtraction(id);
      setExtraction(data);
      setFormData(data.data || {});
      setRawJsonText(JSON.stringify(data.data || {}, null, 2));
    } catch (err) {
      showToast(err.message || 'Failed to load document extraction', 'error');
    } finally {
      setLoading(false);
    }
  };

  const fetchHistory = async () => {
    try {
      setLoadingHistory(true);
      const edits = await api.getDocumentExtractionEdits(id);
      setEditsHistory(edits || []);
    } catch (err) {
      showToast(err.message || 'Failed to load edit history', 'error');
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    fetchExtraction();
  }, [id]);

  useEffect(() => {
    if (activeTab === 'history') {
      fetchHistory();
    }
  }, [activeTab]);

  const handleJsonChange = (text) => {
    setRawJsonText(text);
    try {
      const parsed = JSON.parse(text);
      setFormData(parsed);
      setJsonError('');
    } catch (e) {
      setJsonError(e.message);
    }
  };

  const handleFormatJson = () => {
    try {
      const parsed = JSON.parse(rawJsonText);
      const formatted = JSON.stringify(parsed, null, 2);
      setRawJsonText(formatted);
      setFormData(parsed);
      setJsonError('');
    } catch (e) {
      setJsonError(e.message);
    }
  };

  const handleFieldChange = (path, val) => {
    const updated = JSON.parse(JSON.stringify(formData));
    const parts = path.split('.');
    let curr = updated;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!curr[parts[i]]) curr[parts[i]] = {};
      curr = curr[parts[i]];
    }
    curr[parts[parts.length - 1]] = val;
    setFormData(updated);
    setRawJsonText(JSON.stringify(updated, null, 2));
  };

  const handleCopyJson = () => {
    navigator.clipboard.writeText(rawJsonText);
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 2000);
  };

  const handleLineItemChange = (itemsPath, index, fieldKey, val) => {
    const updated = JSON.parse(JSON.stringify(formData));
    const items = [...(updated[itemsPath] || [])];
    if (items[index]) {
      const item = { ...items[index] };
      item[fieldKey] = val;
      // Mirror aliases so templates checking hsn or hsn_sac, unit or batch, both find the updated value
      if (fieldKey === 'hsn') item.hsn_sac = val;
      if (fieldKey === 'hsn_sac') item.hsn = val;
      if (fieldKey === 'unit') item.batch = val;
      if (fieldKey === 'batch') item.unit = val;
      items[index] = item;
      updated[itemsPath] = items;
      setFormData(updated);
      setRawJsonText(JSON.stringify(updated, null, 2));
    }
  };

  const handleAddLineItem = (itemsPath = 'items') => {
    const updated = JSON.parse(JSON.stringify(formData));
    const items = [...(updated[itemsPath] || [])];
    items.push({
      sl: items.length + 1,
      description: '',
      hsn: '',
      hsn_sac: '',
      qty: '1',
      unit: 'nos',
      batch: '',
      rate: 0,
      discount: 0,
      gst_rate: 18,
      amount: 0,
    });
    updated[itemsPath] = items;
    setFormData(updated);
    setRawJsonText(JSON.stringify(updated, null, 2));
  };

  const handleDeleteLineItem = (itemsPath, index) => {
    const updated = JSON.parse(JSON.stringify(formData));
    const items = [...(updated[itemsPath] || [])];
    items.splice(index, 1);
    updated[itemsPath] = items;
    setFormData(updated);
    setRawJsonText(JSON.stringify(updated, null, 2));
  };

  const handleAddField = (sectionKey, newFieldKey) => {
    if (!newFieldKey) return;
    const cleanKey = newFieldKey.trim().toLowerCase().replace(/\s+/g, '_');
    const updated = JSON.parse(JSON.stringify(formData));
    if (sectionKey) {
      if (!updated[sectionKey]) updated[sectionKey] = {};
      updated[sectionKey][cleanKey] = '';
    } else {
      updated[cleanKey] = '';
    }
    setFormData(updated);
    setRawJsonText(JSON.stringify(updated, null, 2));
  };

  const handleDeleteField = (sectionKey, fieldKey) => {
    const updated = JSON.parse(JSON.stringify(formData));
    if (sectionKey && updated[sectionKey]) {
      delete updated[sectionKey][fieldKey];
    } else if (!sectionKey) {
      delete updated[fieldKey];
    }
    setFormData(updated);
    setRawJsonText(JSON.stringify(updated, null, 2));
  };

  const handleAddBank = () => {
    const updated = JSON.parse(JSON.stringify(formData));
    if (!updated.bank) {
      updated.bank = {
        bank_name: '',
        account_no: '',
        ifsc: '',
        branch: '',
        holder: '',
      };
      setFormData(updated);
      setRawJsonText(JSON.stringify(updated, null, 2));
    }
  };

  const handleAddDeclaration = (key = 'declaration') => {
    const updated = JSON.parse(JSON.stringify(formData));
    if (updated[key] === undefined) {
      updated[key] = '';
      setFormData(updated);
      setRawJsonText(JSON.stringify(updated, null, 2));
    }
  };

  const handleSave = async () => {
    if (!extraction) return;
    let dataToSave = formData;
    if (activeTab === 'json') {
      try {
        dataToSave = JSON.parse(rawJsonText);
      } catch (err) {
        showToast(`Cannot save: Invalid JSON syntax (${err.message})`, 'error');
        return;
      }
    }
    try {
      setSaving(true);
      const res = await api.saveExtractionCorrections(id, {
        version: extraction.version,
        data: dataToSave,
      });
      setExtraction(res);
      setFormData(res.data || {});
      setRawJsonText(JSON.stringify(res.data || {}, null, 2));
      showToast('Corrections saved and revalidated successfully!', 'success');
      if (activeTab === 'history') fetchHistory();
    } catch (err) {
      showToast(err.message || 'Failed to save corrections', 'error');
      if (err.message && err.message.includes('409')) {
        // Concurrency conflict - reload
        fetchExtraction();
      }
    } finally {
      setSaving(false);
    }
  };

  const handleApprove = async (override = false) => {
    if (!extraction) return;
    try {
      setApproving(true);
      const payload = { override, override_reason: override ? overrideReason : undefined };
      const res = await api.approveDocumentExtraction(id, payload);
      setExtraction(res);
      setShowOverrideModal(false);
      setOverrideReason('');
      showToast('Document extraction successfully approved!', 'success');
    } catch (err) {
      showToast(err.message || 'Failed to approve extraction', 'error');
    } finally {
      setApproving(false);
    }
  };

  // Helper to determine if a field path has an active validation flag
  const getFieldFlag = (path) => {
    if (!extraction?.validation_flags) return null;
    return extraction.validation_flags.find((f) => f.field_path === path);
  };

  const renderFieldInput = (sectionKey, fieldKey, val, isNumeric = false) => {
    const path = sectionKey ? `${sectionKey}.${fieldKey}` : fieldKey;
    const flag = getFieldFlag(path);
    const isCustom = !STANDARD_FIELDS[sectionKey]?.includes(fieldKey);

    return (
      <div key={fieldKey} style={{ position: 'relative' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px' }}>
          <label style={{ fontSize: '0.725rem', fontWeight: 600, color: flag ? '#dc2626' : '#475569' }}>
            {fieldKey.replace(/_/g, ' ').toUpperCase()} {flag && '⚠️'}
          </label>
          {isCustom && !isApproved && (
            <button
              type="button"
              onClick={() => handleDeleteField(sectionKey, fieldKey)}
              title={`Remove ${fieldKey}`}
              style={{ border: 'none', background: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '0.75rem', padding: '0 2px' }}
            >
              ✕
            </button>
          )}
        </div>
        <input
          type={isNumeric ? 'number' : 'text'}
          step={isNumeric ? 'any' : undefined}
          disabled={isApproved}
          value={val ?? ''}
          onChange={(e) => {
            const v = isNumeric ? (e.target.value === '' ? '' : parseFloat(e.target.value) || 0) : e.target.value;
            handleFieldChange(path, v);
          }}
          style={{
            width: '100%',
            padding: '0.35rem 0.5rem',
            fontSize: '0.8125rem',
            borderRadius: '4px',
            border: flag ? '1px solid #dc2626' : '1px solid #cbd5e1',
            backgroundColor: flag ? '#fff5f5' : '#ffffff',
            color: '#0f172a',
          }}
        />
      </div>
    );
  };

  const renderAddFieldInline = (sectionKey) => {
    if (addingSection !== sectionKey) {
      return (
        <button
          type="button"
          disabled={isApproved}
          onClick={() => {
            setAddingSection(sectionKey);
            setNewFieldName('');
          }}
          style={{
            fontSize: '0.75rem',
            color: '#2563eb',
            background: 'none',
            border: '1px dashed #bfdbfe',
            borderRadius: '4px',
            padding: '0.2rem 0.5rem',
            cursor: isApproved ? 'not-allowed' : 'pointer',
            fontWeight: 600,
          }}
        >
          + Add Field
        </button>
      );
    }
    return (
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
        <input
          type="text"
          placeholder="Field name..."
          value={newFieldName}
          autoFocus
          onChange={(e) => setNewFieldName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              handleAddField(sectionKey === 'root' ? null : sectionKey, newFieldName);
              setAddingSection(null);
              setNewFieldName('');
            } else if (e.key === 'Escape') {
              setAddingSection(null);
              setNewFieldName('');
            }
          }}
          style={{
            fontSize: '0.75rem',
            padding: '0.2rem 0.4rem',
            border: '1px solid #3b82f6',
            borderRadius: '4px',
            width: '130px',
          }}
        />
        <button
          type="button"
          onClick={() => {
            handleAddField(sectionKey === 'root' ? null : sectionKey, newFieldName);
            setAddingSection(null);
            setNewFieldName('');
          }}
          style={{
            padding: '0.2rem 0.45rem',
            fontSize: '0.75rem',
            backgroundColor: '#2563eb',
            color: '#ffffff',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontWeight: 600,
          }}
        >
          Add
        </button>
        <button
          type="button"
          onClick={() => {
            setAddingSection(null);
            setNewFieldName('');
          }}
          style={{
            padding: '0.2rem 0.35rem',
            fontSize: '0.75rem',
            backgroundColor: '#f1f5f9',
            color: '#64748b',
            border: '1px solid #cbd5e1',
            borderRadius: '4px',
            cursor: 'pointer',
          }}
        >
          Cancel
        </button>
      </div>
    );
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '80vh', color: '#64748b' }}>
        Loading document review and extraction data...
      </div>
    );
  }

  const isApproved = extraction?.status === 'approved';
  const hasErrors = extraction?.has_errors;
  const isPdf = extraction?.mime_type === 'application/pdf';
  const fileUrl = api.getFileUrl(id);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px)', backgroundColor: '#f8fafc' }}>
      {/* ── Top Header Toolbar ── */}
      <div style={{
        padding: '0.75rem 1.5rem',
        backgroundColor: '#ffffff',
        borderBottom: '1px solid #e2e8f0',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '0.75rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button
            type="button"
            onClick={() => navigate(`/documents/${id}`)}
            style={{
              padding: '0.375rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              backgroundColor: '#ffffff',
              fontSize: '0.8125rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
            }}
          >
            &larr; Document View
          </button>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <h1 style={{ fontSize: '1.125rem', fontWeight: 700, margin: 0, color: '#0f172a' }}>
                Review: {extraction?.original_filename}
              </h1>
              <span style={{
                fontSize: '0.75rem',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: '12px',
                backgroundColor: isApproved ? '#dcfce7' : hasErrors ? '#fee2e2' : '#fef3c7',
                color: isApproved ? '#15803d' : hasErrors ? '#b91c1c' : '#b45309',
                textTransform: 'uppercase',
              }}>
                {extraction?.status?.replace('_', ' ')}
              </span>
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>
              Pinned Template: <strong>{extraction?.template_name}</strong> (v{extraction?.template_version_number}) &bull; Lock Version: #{extraction?.version}
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ display: 'flex', borderRadius: '6px', border: '1px solid #cbd5e1', overflow: 'hidden' }}>
            <button
              type="button"
              onClick={() => setActiveTab('review')}
              style={{
                padding: '0.375rem 0.75rem',
                fontSize: '0.8125rem',
                fontWeight: 600,
                border: 'none',
                backgroundColor: activeTab === 'review' ? '#dc2626' : '#ffffff',
                color: activeTab === 'review' ? '#ffffff' : '#475569',
                cursor: 'pointer',
              }}
            >
              Verify &amp; Edit
            </button>
            <button
              type="button"
              onClick={() => {
                setRawJsonText(JSON.stringify(formData, null, 2));
                setJsonError('');
                setActiveTab('json');
              }}
              style={{
                padding: '0.375rem 0.75rem',
                fontSize: '0.8125rem',
                fontWeight: 600,
                border: 'none',
                borderLeft: '1px solid #cbd5e1',
                backgroundColor: activeTab === 'json' ? '#dc2626' : '#ffffff',
                color: activeTab === 'json' ? '#ffffff' : '#475569',
                cursor: 'pointer',
              }}
            >
              {'{ }'} Raw JSON
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('history')}
              style={{
                padding: '0.375rem 0.75rem',
                fontSize: '0.8125rem',
                fontWeight: 600,
                border: 'none',
                borderLeft: '1px solid #cbd5e1',
                backgroundColor: activeTab === 'history' ? '#dc2626' : '#ffffff',
                color: activeTab === 'history' ? '#ffffff' : '#475569',
                cursor: 'pointer',
              }}
            >
              Edit History ({extraction?.edits_count || 0})
            </button>
          </div>

          {!isApproved && (
            <>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                style={{
                  padding: '0.4rem 1rem',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  cursor: saving ? 'not-allowed' : 'pointer',
                }}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>

              <button
                type="button"
                onClick={() => {
                  if (hasErrors) {
                    setShowOverrideModal(true);
                  } else {
                    handleApprove(false);
                  }
                }}
                disabled={approving}
                style={{
                  padding: '0.4rem 1.25rem',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: hasErrors ? '#f59e0b' : '#16a34a',
                  color: '#ffffff',
                  fontSize: '0.8125rem',
                  fontWeight: 600,
                  cursor: approving ? 'not-allowed' : 'pointer',
                }}
              >
                {approving ? 'Approving...' : hasErrors ? 'Override & Approve' : 'Approve Extraction'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* ── Toast Alert ── */}
      {toast && (
        <div style={{
          backgroundColor: toast.type === 'error' ? '#fee2e2' : toast.type === 'success' ? '#dcfce7' : '#eff6ff',
          color: toast.type === 'error' ? '#991b1b' : toast.type === 'success' ? '#166534' : '#1e40af',
          padding: '0.625rem 1.5rem',
          fontSize: '0.875rem',
          fontWeight: 600,
          borderBottom: '1px solid rgba(0,0,0,0.05)',
        }}>
          {toast.message}
        </div>
      )}

      {/* ── Main Split View Body ── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* LEFT PANEL: Original Document Preview */}
        <div style={{
          width: '50%',
          borderRight: '1px solid #cbd5e1',
          backgroundColor: '#f8fafc',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
        }}>
          {/* Subheader Toolbar with Zoom Controls & Open in Tab */}
          <div style={{
            padding: '0.45rem 1rem',
            backgroundColor: '#ffffff',
            borderBottom: '1px solid #e2e8f0',
            color: '#334155',
            fontSize: '0.8rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            zIndex: 10,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ color: '#0f172a', fontWeight: 700 }}>Original Document</span>
              <span style={{
                fontSize: '0.7rem',
                backgroundColor: '#f1f5f9',
                color: '#64748b',
                padding: '0.1rem 0.45rem',
                borderRadius: '4px',
                border: '1px solid #e2e8f0',
              }}>
                {extraction?.mime_type || 'image/jpeg'}
              </span>
            </div>

            {/* Interactive Zoom Controls & Open Tab */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
              {!isPdf && (
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  backgroundColor: '#f8fafc',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  overflow: 'hidden',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                }}>
                  <button
                    type="button"
                    onClick={handleZoomOut}
                    disabled={zoom <= 0.5}
                    title="Zoom Out (−)"
                    style={{
                      border: 'none',
                      background: 'none',
                      padding: '0.2rem 0.6rem',
                      cursor: zoom <= 0.5 ? 'not-allowed' : 'pointer',
                      fontSize: '0.9rem',
                      fontWeight: 'bold',
                      color: zoom <= 0.5 ? '#94a3b8' : '#1e293b',
                    }}
                  >
                    −
                  </button>
                  <span style={{
                    padding: '0.15rem 0.4rem',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    minWidth: '3.4rem',
                    textAlign: 'center',
                    color: '#0f172a',
                    borderLeft: '1px solid #e2e8f0',
                    borderRight: '1px solid #e2e8f0',
                    userSelect: 'none',
                  }}>
                    {Math.round(zoom * 100)}%
                  </span>
                  <button
                    type="button"
                    onClick={handleZoomIn}
                    disabled={zoom >= 3.5}
                    title="Zoom In (+)"
                    style={{
                      border: 'none',
                      background: 'none',
                      padding: '0.2rem 0.6rem',
                      cursor: zoom >= 3.5 ? 'not-allowed' : 'pointer',
                      fontSize: '0.9rem',
                      fontWeight: 'bold',
                      color: zoom >= 3.5 ? '#94a3b8' : '#1e293b',
                    }}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    onClick={handleZoomReset}
                    title="Reset to Fit Width (100%)"
                    style={{
                      border: 'none',
                      borderLeft: '1px solid #e2e8f0',
                      background: 'none',
                      padding: '0.2rem 0.55rem',
                      cursor: 'pointer',
                      fontSize: '0.725rem',
                      fontWeight: 600,
                      color: '#2563eb',
                    }}
                  >
                    Reset
                  </button>
                </div>
              )}

              <a
                href={fileUrl}
                target="_blank"
                rel="noreferrer"
                title="Open original file in new browser tab"
                style={{
                  color: '#2563eb',
                  textDecoration: 'none',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.25rem',
                  padding: '0.25rem 0.55rem',
                  borderRadius: '5px',
                  backgroundColor: '#eff6ff',
                  border: '1px solid #bfdbfe',
                }}
              >
                Open In New Tab ↗
              </a>
            </div>
          </div>

          {/* Document Viewer Container with Left-Right Drag & Scroll */}
          <div
            ref={imageContainerRef}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            style={{
              flex: 1,
              overflow: 'auto',
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: zoom > 1 ? 'flex-start' : 'center',
              padding: '0.75rem',
              backgroundColor: '#f1f5f9',
              cursor: zoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default',
              userSelect: isDragging ? 'none' : 'auto',
            }}
          >
            {isPdf ? (
              <iframe
                src={`${fileUrl}#toolbar=0`}
                title="Document PDF"
                style={{
                  width: '100%',
                  height: '100%',
                  border: 'none',
                  backgroundColor: '#ffffff',
                  borderRadius: '6px',
                  boxShadow: '0 2px 4px rgba(0,0,0,0.06)',
                }}
              />
            ) : (
              <div style={{
                width: `${zoom * 100}%`,
                maxWidth: zoom === 1 ? '100%' : 'none',
                minWidth: zoom > 1 ? `${zoom * 100}%` : '100%',
                display: 'flex',
                justifyContent: 'center',
                transition: isDragging ? 'none' : 'width 0.12s ease-out',
              }}>
                <img
                  src={fileUrl}
                  alt="Document Preview"
                  draggable={false}
                  style={{
                    width: '100%',
                    height: 'auto',
                    objectFit: 'contain',
                    borderRadius: '6px',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.05)',
                    backgroundColor: '#ffffff',
                    display: 'block',
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {/* RIGHT PANEL: Extraction Fields & Verification */}
        <div style={{ width: '50%', display: 'flex', flexDirection: 'column', backgroundColor: '#ffffff', overflowY: 'auto' }}>
          {activeTab === 'history' ? (
            /* ── Tab: Edit History ── */
            <div style={{ padding: '1.5rem' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
                Field Correction History
              </h3>
              <p style={{ fontSize: '0.8125rem', color: '#64748b', marginBottom: '1rem' }}>
                Granular, immutable audit trail of all human review adjustments. Original OCR text remains unchanged.
              </p>

              {loadingHistory ? (
                <div style={{ color: '#64748b', fontSize: '0.875rem' }}>Loading history...</div>
              ) : editsHistory.length === 0 ? (
                <div style={{ backgroundColor: '#f8fafc', padding: '2rem', textAlign: 'center', color: '#94a3b8', borderRadius: '8px' }}>
                  No manual edits recorded yet.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {editsHistory.map((edit) => (
                    <div
                      key={edit.id}
                      style={{
                        padding: '0.75rem',
                        border: '1px solid #e2e8f0',
                        borderRadius: '6px',
                        backgroundColor: '#f8fafc',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                        <span style={{ fontWeight: 700, fontSize: '0.8125rem', color: '#0f172a' }}>
                          {edit.field_path}
                        </span>
                        <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                          {new Date(edit.edited_at).toLocaleString()}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: '#475569', marginBottom: '0.25rem' }}>
                        Editor: <strong>{edit.editor_name || `User #${edit.edited_by}`}</strong>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.75rem' }}>
                        <div style={{ backgroundColor: '#fee2e2', padding: '0.375rem', borderRadius: '4px', color: '#991b1b' }}>
                          <span style={{ fontWeight: 600 }}>Old:</span> {JSON.stringify(edit.old_value)}
                        </div>
                        <div style={{ backgroundColor: '#dcfce7', padding: '0.375rem', borderRadius: '4px', color: '#166534' }}>
                          <span style={{ fontWeight: 600 }}>New:</span> {JSON.stringify(edit.new_value)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : activeTab === 'json' ? (
            /* ── Tab: Raw JSON Code Editor ── */
            <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', flex: 1, gap: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                <div>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#0f172a', margin: 0 }}>
                    Raw JSON Document Data
                  </h3>
                  <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>
                    Edit any key, nested field, line item or custom attribute directly.
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <button
                    type="button"
                    onClick={handleFormatJson}
                    style={{
                      padding: '0.3rem 0.65rem',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      borderRadius: '5px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: '#f8fafc',
                      color: '#334155',
                      cursor: 'pointer',
                    }}
                  >
                    ✨ Format JSON
                  </button>
                  <button
                    type="button"
                    onClick={handleCopyJson}
                    style={{
                      padding: '0.3rem 0.65rem',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      borderRadius: '5px',
                      border: '1px solid #cbd5e1',
                      backgroundColor: '#f8fafc',
                      color: '#334155',
                      cursor: 'pointer',
                    }}
                  >
                    {copiedJson ? '✓ Copied!' : '📋 Copy JSON'}
                  </button>
                </div>
              </div>

              {jsonError ? (
                <div style={{
                  padding: '0.5rem 0.75rem',
                  borderRadius: '6px',
                  backgroundColor: '#fee2e2',
                  border: '1px solid #fecaca',
                  color: '#991b1b',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                }}>
                  ⚠️ Syntax Error: {jsonError}
                </div>
              ) : (
                <div style={{
                  padding: '0.3rem 0.75rem',
                  borderRadius: '6px',
                  backgroundColor: '#f0fdf4',
                  border: '1px solid #bbf7d0',
                  color: '#166534',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  width: 'fit-content',
                }}>
                  ✓ Valid JSON Syntax
                </div>
              )}

              <textarea
                value={rawJsonText}
                onChange={(e) => handleJsonChange(e.target.value)}
                disabled={isApproved}
                spellCheck={false}
                style={{
                  flex: 1,
                  minHeight: '520px',
                  width: '100%',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  fontSize: '0.8125rem',
                  lineHeight: '1.45',
                  padding: '0.875rem',
                  backgroundColor: '#0f172a',
                  color: '#f8fafc',
                  border: jsonError ? '2px solid #ef4444' : '1px solid #334155',
                  borderRadius: '8px',
                  resize: 'vertical',
                  whiteSpace: 'pre',
                  outline: 'none',
                  boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.2)',
                }}
              />
            </div>
          ) : (
            /* ── Tab: Fields Verification Editor ── */
            <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {/* Validation Flags Banner */}
              {extraction?.validation_flags && extraction.validation_flags.length > 0 && (
                <div style={{
                  backgroundColor: hasErrors ? '#fef2f2' : '#fffbeb',
                  border: `1px solid ${hasErrors ? '#fecaca' : '#fde68a'}`,
                  borderRadius: '8px',
                  padding: '1rem',
                }}>
                  <div style={{
                    fontWeight: 700,
                    fontSize: '0.875rem',
                    color: hasErrors ? '#b91c1c' : '#b45309',
                    marginBottom: '0.5rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  }}>
                    <span>{hasErrors ? '⚠️' : 'ℹ️'}</span>
                    <span>
                      {hasErrors
                        ? `${extraction.validation_flags.filter((f) => f.severity === 'error').length} Validation Error(s) Detected`
                        : `${extraction.validation_flags.length} Validation Warning(s)`}
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.375rem' }}>
                    {extraction.validation_flags.map((flag, idx) => (
                      <div
                        key={idx}
                        style={{
                          fontSize: '0.8125rem',
                          color: flag.severity === 'error' ? '#991b1b' : '#92400e',
                          padding: '0.25rem 0.5rem',
                          backgroundColor: flag.severity === 'error' ? '#fee2e2' : '#fef3c7',
                          borderRadius: '4px',
                        }}
                      >
                        <strong>{flag.field_path || 'General'}:</strong> {flag.message}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Dynamic Field Form according to Schema */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                {/* 1. Header / Document Metadata & Invoice Fields */}
                <div style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <h4 style={{ fontSize: '0.875rem', fontWeight: 700, margin: 0, color: '#1e293b' }}>
                      Document Metadata &amp; Invoice
                    </h4>
                    {renderAddFieldInline('invoice')}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
                    {Array.from(new Set([...STANDARD_FIELDS.invoice, ...Object.keys(formData.invoice || {})])).map((k) =>
                      renderFieldInput('invoice', k, formData.invoice?.[k])
                    )}
                  </div>
                </div>

                {/* 2. Seller & Buyer Sections */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  {/* Seller */}
                  <div style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                      <h4 style={{ fontSize: '0.875rem', fontWeight: 700, margin: 0, color: '#1e293b' }}>
                        Seller Details
                      </h4>
                      {renderAddFieldInline('seller')}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {Array.from(new Set([...STANDARD_FIELDS.seller, ...Object.keys(formData.seller || {})])).map((k) =>
                        renderFieldInput('seller', k, formData.seller?.[k])
                      )}
                    </div>
                  </div>

                  {/* Buyer */}
                  <div style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                      <h4 style={{ fontSize: '0.875rem', fontWeight: 700, margin: 0, color: '#1e293b' }}>
                        Buyer Details
                      </h4>
                      {renderAddFieldInline('buyer')}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {Array.from(new Set([...STANDARD_FIELDS.buyer, ...Object.keys(formData.buyer || {})])).map((k) =>
                        renderFieldInput('buyer', k, formData.buyer?.[k])
                      )}
                    </div>
                  </div>
                </div>

                {/* 3. Delivery Details (if present or user adds fields) */}
                {formData.delivery && (
                  <div style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                      <h4 style={{ fontSize: '0.875rem', fontWeight: 700, margin: 0, color: '#1e293b' }}>
                        Delivery / Consignee Details
                      </h4>
                      {renderAddFieldInline('delivery')}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
                      {Array.from(new Set([...STANDARD_FIELDS.delivery, ...Object.keys(formData.delivery || {})])).map((k) =>
                        renderFieldInput('delivery', k, formData.delivery?.[k])
                      )}
                    </div>
                  </div>
                )}

                {/* 4. Complete Line Items Table */}
                <div style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <h4 style={{ fontSize: '0.875rem', fontWeight: 700, margin: 0, color: '#1e293b' }}>
                      Line Items ({(formData.items || []).length})
                    </h4>
                    {!isApproved && (
                      <button
                        type="button"
                        onClick={() => handleAddLineItem('items')}
                        style={{
                          fontSize: '0.75rem',
                          color: '#2563eb',
                          background: 'none',
                          border: '1px dashed #bfdbfe',
                          borderRadius: '4px',
                          padding: '0.2rem 0.5rem',
                          cursor: 'pointer',
                          fontWeight: 600,
                        }}
                      >
                        + Add Line Item
                      </button>
                    )}
                  </div>

                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid #cbd5e1', textAlign: 'left', color: '#64748b', fontSize: '0.725rem' }}>
                          <th style={{ padding: '0.375rem 0.25rem', width: '28px' }}>#</th>
                          <th style={{ padding: '0.375rem 0.25rem', minWidth: '150px' }}>Description</th>
                          <th style={{ padding: '0.375rem 0.25rem', width: '75px' }}>HSN/SAC</th>
                          <th style={{ padding: '0.375rem 0.25rem', width: '65px' }}>Qty</th>
                          <th style={{ padding: '0.375rem 0.25rem', width: '65px' }}>Unit</th>
                          <th style={{ padding: '0.375rem 0.25rem', width: '80px' }}>Rate (₹)</th>
                          <th style={{ padding: '0.375rem 0.25rem', width: '60px' }}>Disc %</th>
                          <th style={{ padding: '0.375rem 0.25rem', width: '65px' }}>GST %</th>
                          <th style={{ padding: '0.375rem 0.25rem', width: '90px' }}>Amount (₹)</th>
                          <th style={{ padding: '0.375rem 0.25rem', width: '30px', textAlign: 'center' }}></th>
                        </tr>
                      </thead>
                      <tbody>
                        {Array.isArray(formData.items) && formData.items.map((it, idx) => {
                          const flag = getFieldFlag(`items[${idx}].amount`);
                          return (
                            <tr key={idx} style={{ borderBottom: '1px solid #e2e8f0', backgroundColor: flag ? '#fee2e2' : 'transparent' }}>
                              <td style={{ padding: '0.25rem', color: '#94a3b8', fontSize: '0.75rem' }}>{idx + 1}</td>
                              <td style={{ padding: '0.25rem' }}>
                                <input
                                  type="text"
                                  disabled={isApproved}
                                  value={it.description || ''}
                                  onChange={(e) => handleLineItemChange('items', idx, 'description', e.target.value)}
                                  placeholder="Description"
                                  style={{ width: '100%', padding: '0.25rem 0.35rem', fontSize: '0.75rem', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                                />
                              </td>
                              <td style={{ padding: '0.25rem' }}>
                                <input
                                  type="text"
                                  disabled={isApproved}
                                  value={it.hsn ?? it.hsn_sac ?? ''}
                                  onChange={(e) => handleLineItemChange('items', idx, 'hsn', e.target.value)}
                                  placeholder="HSN"
                                  style={{ width: '100%', padding: '0.25rem 0.35rem', fontSize: '0.75rem', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                                />
                              </td>
                              <td style={{ padding: '0.25rem' }}>
                                <input
                                  type="text"
                                  disabled={isApproved}
                                  value={it.qty ?? ''}
                                  onChange={(e) => handleLineItemChange('items', idx, 'qty', e.target.value)}
                                  placeholder="Qty"
                                  style={{ width: '100%', padding: '0.25rem 0.35rem', fontSize: '0.75rem', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                                />
                              </td>
                              <td style={{ padding: '0.25rem' }}>
                                <input
                                  type="text"
                                  disabled={isApproved}
                                  value={it.unit ?? it.batch ?? ''}
                                  onChange={(e) => handleLineItemChange('items', idx, 'unit', e.target.value)}
                                  placeholder="Unit"
                                  style={{ width: '100%', padding: '0.25rem 0.35rem', fontSize: '0.75rem', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                                />
                              </td>
                              <td style={{ padding: '0.25rem' }}>
                                <input
                                  type="number"
                                  step="any"
                                  disabled={isApproved}
                                  value={it.rate ?? ''}
                                  onChange={(e) => handleLineItemChange('items', idx, 'rate', parseFloat(e.target.value) || 0)}
                                  placeholder="Rate"
                                  style={{ width: '100%', padding: '0.25rem 0.35rem', fontSize: '0.75rem', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                                />
                              </td>
                              <td style={{ padding: '0.25rem' }}>
                                <input
                                  type="number"
                                  step="any"
                                  disabled={isApproved}
                                  value={it.discount ?? it.discount_percent ?? ''}
                                  onChange={(e) => handleLineItemChange('items', idx, 'discount', parseFloat(e.target.value) || 0)}
                                  placeholder="Disc"
                                  style={{ width: '100%', padding: '0.25rem 0.35rem', fontSize: '0.75rem', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                                />
                              </td>
                              <td style={{ padding: '0.25rem' }}>
                                <input
                                  type="number"
                                  step="any"
                                  disabled={isApproved}
                                  value={it.gst_rate ?? it.tax_rate ?? ''}
                                  onChange={(e) => handleLineItemChange('items', idx, 'gst_rate', parseFloat(e.target.value) || 0)}
                                  placeholder="GST %"
                                  style={{ width: '100%', padding: '0.25rem 0.35rem', fontSize: '0.75rem', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                                />
                              </td>
                              <td style={{ padding: '0.25rem' }}>
                                <input
                                  type="number"
                                  step="any"
                                  disabled={isApproved}
                                  value={it.amount ?? ''}
                                  onChange={(e) => handleLineItemChange('items', idx, 'amount', parseFloat(e.target.value) || 0)}
                                  placeholder="Amount"
                                  style={{
                                    width: '100%',
                                    padding: '0.25rem 0.35rem',
                                    fontSize: '0.75rem',
                                    border: flag ? '1px solid #dc2626' : '1px solid #cbd5e1',
                                    borderRadius: '4px',
                                    backgroundColor: flag ? '#fff5f5' : '#ffffff',
                                    fontWeight: 600,
                                  }}
                                />
                              </td>
                              <td style={{ padding: '0.25rem', textAlign: 'center' }}>
                                {!isApproved && (
                                  <button
                                    type="button"
                                    onClick={() => handleDeleteLineItem('items', idx)}
                                    title="Delete line item"
                                    style={{
                                      border: 'none',
                                      background: 'none',
                                      cursor: 'pointer',
                                      color: '#ef4444',
                                      fontSize: '0.85rem',
                                      padding: '2px',
                                    }}
                                  >
                                    🗑️
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* 5. Calculated Taxes & Grand Totals Section */}
                <div style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <h4 style={{ fontSize: '0.875rem', fontWeight: 700, margin: 0, color: '#1e293b' }}>
                      Calculated Taxes &amp; Grand Totals
                    </h4>
                    {renderAddFieldInline('totals')}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem' }}>
                    {Array.from(new Set([...STANDARD_FIELDS.totals, ...Object.keys(formData.totals || {})])).map((k) => {
                      const isNumeric = !['amount_in_words', 'total_qty'].includes(k);
                      return renderFieldInput('totals', k, formData.totals?.[k], isNumeric);
                    })}
                  </div>
                </div>

                {/* 6. Bank & Payment Details Section */}
                {formData.bank || formData.bank_details ? (
                  <div style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                      <h4 style={{ fontSize: '0.875rem', fontWeight: 700, margin: 0, color: '#1e293b' }}>
                        Bank &amp; Payment Details
                      </h4>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        {renderAddFieldInline(formData.bank ? 'bank' : 'bank_details')}
                        {!isApproved && (
                          <button
                            type="button"
                            onClick={() => handleDeleteField(null, formData.bank ? 'bank' : 'bank_details')}
                            style={{
                              fontSize: '0.75rem',
                              color: '#ef4444',
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              padding: 0,
                            }}
                          >
                            Remove Bank
                          </button>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
                      {Array.from(new Set([...STANDARD_FIELDS.bank, ...Object.keys(formData.bank || formData.bank_details || {})])).map((k) =>
                        renderFieldInput(formData.bank ? 'bank' : 'bank_details', k, (formData.bank || formData.bank_details)?.[k])
                      )}
                    </div>
                  </div>
                ) : (
                  !isApproved && (
                    <button
                      type="button"
                      onClick={handleAddBank}
                      style={{
                        padding: '0.5rem',
                        fontSize: '0.8125rem',
                        fontWeight: 600,
                        color: '#475569',
                        backgroundColor: '#f8fafc',
                        border: '1px dashed #cbd5e1',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        textAlign: 'center',
                      }}
                    >
                      + Add Bank &amp; Payment Details
                    </button>
                  )
                )}

                {/* 7. Notes, Declaration & Warranty Section */}
                {(formData.declaration !== undefined || formData.warranty_note !== undefined) && (
                  <div style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <h4 style={{ fontSize: '0.875rem', fontWeight: 700, margin: '0 0 0.75rem 0', color: '#1e293b' }}>
                      Declarations &amp; Terms
                    </h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      {formData.declaration !== undefined && (
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px' }}>
                            <label style={{ fontSize: '0.725rem', fontWeight: 600, color: '#475569' }}>
                              DECLARATION
                            </label>
                            {!isApproved && (
                              <button
                                type="button"
                                onClick={() => handleDeleteField(null, 'declaration')}
                                style={{ border: 'none', background: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '0.75rem' }}
                              >
                                ✕
                              </button>
                            )}
                          </div>
                          <textarea
                            rows={2}
                            disabled={isApproved}
                            value={formData.declaration || ''}
                            onChange={(e) => handleFieldChange('declaration', e.target.value)}
                            style={{ width: '100%', padding: '0.35rem 0.5rem', fontSize: '0.8125rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                          />
                        </div>
                      )}
                      {formData.warranty_note !== undefined && (
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px' }}>
                            <label style={{ fontSize: '0.725rem', fontWeight: 600, color: '#475569' }}>
                              WARRANTY NOTE
                            </label>
                            {!isApproved && (
                              <button
                                type="button"
                                onClick={() => handleDeleteField(null, 'warranty_note')}
                                style={{ border: 'none', background: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '0.75rem' }}
                              >
                                ✕
                              </button>
                            )}
                          </div>
                          <textarea
                            rows={2}
                            disabled={isApproved}
                            value={formData.warranty_note || ''}
                            onChange={(e) => handleFieldChange('warranty_note', e.target.value)}
                            style={{ width: '100%', padding: '0.35rem 0.5rem', fontSize: '0.8125rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Authorised Signatory & Signature (Optional) */}
                <div style={{ backgroundColor: '#ffffff', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <h4 style={{ fontSize: '0.875rem', fontWeight: 700, margin: 0, color: '#1e293b' }}>
                      🖋️ Authorised Signatory &amp; Signature
                    </h4>
                    <span style={{ fontSize: '0.7rem', backgroundColor: '#f1f5f9', color: '#64748b', padding: '0.15rem 0.5rem', borderRadius: '4px', fontWeight: 600 }}>
                      Optional
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                    <div>
                      <label style={{ fontSize: '0.725rem', fontWeight: 600, color: '#475569', display: 'block', marginBottom: '2px' }}>
                        SIGNATORY NAME / LABEL
                      </label>
                      <input
                        type="text"
                        disabled={isApproved}
                        value={formData.signature?.signer_name || formData.signer_name || ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          setFormData((prev) => ({
                            ...prev,
                            signer_name: val,
                            signature: {
                              ...(prev.signature || {}),
                              signer_name: val,
                            },
                          }));
                        }}
                        placeholder={`For ${formData.seller?.name || 'Company'} (Authorised Signatory)`}
                        style={{ width: '100%', padding: '0.35rem 0.5rem', fontSize: '0.8125rem', borderRadius: '4px', border: '1px solid #cbd5e1' }}
                      />
                    </div>

                    <div>
                      <label style={{ fontSize: '0.725rem', fontWeight: 600, color: '#475569', display: 'block', marginBottom: '4px' }}>
                        SIGNATURE IMAGE
                      </label>
                      {(formData.signature_image || formData.signature?.image_data) ? (
                        <div style={{ border: '1px solid #cbd5e1', borderRadius: '6px', padding: '0.75rem', background: '#f8fafc', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '4px', padding: '4px 8px', display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: '90px', minHeight: '45px' }}>
                              <img
                                src={formData.signature_image || formData.signature?.image_data}
                                alt="Authorised Signature"
                                style={{ maxHeight: '45px', maxWidth: '140px', objectFit: 'contain' }}
                              />
                            </div>
                            <div>
                              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#0f172a' }}>Signature Attached</div>
                              <div style={{ fontSize: '0.72rem', color: '#64748b' }}>Appears on the standardised invoice</div>
                            </div>
                          </div>
                          {!isApproved && (
                            <div style={{ display: 'flex', gap: '0.4rem' }}>
                              <button
                                type="button"
                                className="btn btn-secondary"
                                style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}
                                onClick={() => signatureInputRef.current?.click()}
                              >
                                Replace
                              </button>
                              <button
                                type="button"
                                className="btn btn-secondary"
                                style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem', color: '#ef4444', borderColor: '#fca5a5' }}
                                onClick={handleRemoveSignature}
                              >
                                Remove
                              </button>
                            </div>
                          )}
                        </div>
                      ) : (
                        !isApproved ? (
                          <div
                            onClick={() => signatureInputRef.current?.click()}
                            style={{
                              border: '2px dashed #cbd5e1',
                              borderRadius: '6px',
                              padding: '0.875rem',
                              textAlign: 'center',
                              background: '#ffffff',
                              cursor: 'pointer',
                              transition: 'all 0.15s ease',
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--brand)'; e.currentTarget.style.background = '#fff5f5'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#cbd5e1'; e.currentTarget.style.background = '#ffffff'; }}
                          >
                            <div style={{ fontSize: '1.15rem', marginBottom: '0.2rem' }}>🖋️</div>
                            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--brand)' }}>Upload Signature</div>
                            <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '0.15rem' }}>
                              PNG, JPG, or JPEG up to 2MB (Optional)
                            </div>
                          </div>
                        ) : (
                          <div style={{ fontSize: '0.78rem', color: '#94a3b8', fontStyle: 'italic', padding: '0.35rem 0' }}>
                            No signature attached
                          </div>
                        )
                      )}
                      <input
                        type="file"
                        ref={signatureInputRef}
                        accept="image/png,image/jpeg,image/jpg"
                        style={{ display: 'none' }}
                        onChange={handleSignatureFileSelect}
                      />
                    </div>
                  </div>
                </div>

                {/* 8. Additional / Custom Root Fields */}
                <div style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <h4 style={{ fontSize: '0.875rem', fontWeight: 700, margin: 0, color: '#1e293b' }}>
                      Additional / Custom Root Fields
                    </h4>
                    {renderAddFieldInline('root')}
                  </div>
                  {Object.keys(formData).filter((k) => !['invoice', 'seller', 'buyer', 'delivery', 'items', 'totals', 'bank', 'bank_details', 'declaration', 'warranty_note', 'footer'].includes(k) && typeof formData[k] !== 'object').length === 0 ? (
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontStyle: 'italic' }}>
                      No additional custom fields. Click &quot;+ Add Field&quot; above to create one.
                    </div>
                  ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
                      {Object.keys(formData)
                        .filter((k) => !['invoice', 'seller', 'buyer', 'delivery', 'items', 'totals', 'bank', 'bank_details', 'declaration', 'warranty_note', 'footer'].includes(k) && typeof formData[k] !== 'object')
                        .map((k) => renderFieldInput(null, k, formData[k]))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Modal: Override Validation Errors & Approve ── */}
      {showOverrideModal && (
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
            maxWidth: '500px',
            width: '100%',
            padding: '1.5rem',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
          }}>
            <h3 style={{ fontSize: '1.125rem', fontWeight: 700, margin: '0 0 0.5rem 0', color: '#991b1b' }}>
              Override Validation Errors
            </h3>
            <p style={{ fontSize: '0.875rem', color: '#64748b', margin: '0 0 1rem 0' }}>
              This extraction has unresolved error-level flags. To approve it anyway, please provide an authoritative audit justification.
            </p>

            <textarea
              rows={3}
              required
              placeholder="e.g. Document arithmetic verified manually against original vendor statement..."
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '0.875rem',
                marginBottom: '1rem',
              }}
            />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                type="button"
                onClick={() => setShowOverrideModal(false)}
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
                type="button"
                disabled={overrideReason.trim().length < 5 || approving}
                onClick={() => handleApprove(true)}
                style={{
                  padding: '0.5rem 1.25rem',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: '#dc2626',
                  color: '#ffffff',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                  cursor: overrideReason.trim().length < 5 ? 'not-allowed' : 'pointer',
                }}
              >
                {approving ? 'Overriding...' : 'Confirm Override & Approve'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
