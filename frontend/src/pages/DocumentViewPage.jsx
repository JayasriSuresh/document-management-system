import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';
import ConfirmModal from '../components/ConfirmModal';

const STATUS_INFO = {
  UPLOADED:   { label: 'Uploaded',       cls: 'status-uploaded' },
  PROCESSING: { label: 'Processing OCR', cls: 'status-processing' },
  COMPLETED:  { label: 'OCR Completed',  cls: 'status-completed' },
  FAILED:     { label: 'OCR Failed',     cls: 'status-failed' },
};

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  return new Date(isoStr).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function formatCurrency(amount, currency = 'INR') {
  if (amount === null || amount === undefined || amount === '') return '—';
  const num = typeof amount === 'number' ? amount : parseFloat(amount);
  if (isNaN(num)) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: currency || 'INR',
    maximumFractionDigits: 2,
  }).format(num);
}

// Clean SVG icons for inspector tabs, preview tabs, and section cards
const IconFileText = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
    <polyline points="10 9 9 9 8 9" />
  </svg>
);

const IconInfoCircle = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="16" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
);

const IconCode2 = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <polyline points="16 18 22 12 16 6" />
    <polyline points="8 6 2 12 8 18" />
  </svg>
);

const IconEye = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const IconCheckCopy = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
);

const IconBuilding = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <line x1="9" y1="22" x2="9" y2="2" />
    <line x1="8" y1="6" x2="10" y2="6" />
    <line x1="14" y1="6" x2="16" y2="6" />
    <line x1="14" y1="10" x2="16" y2="10" />
    <line x1="8" y1="10" x2="10" y2="10" />
    <line x1="14" y1="14" x2="16" y2="14" />
    <line x1="8" y1="14" x2="10" y2="14" />
  </svg>
);

const IconUser = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const IconPackage = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <line x1="16.5" y1="9.4" x2="7.5" y2="4.21" />
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
    <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
    <line x1="12" y1="22.08" x2="12" y2="12" />
  </svg>
);

const IconCalculator = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <line x1="8" y1="6" x2="16" y2="6" />
    <line x1="16" y1="14" x2="16" y2="18" />
    <path d="M16 10h.01" />
    <path d="M12 10h.01" />
    <path d="M8 10h.01" />
    <path d="M12 14h.01" />
    <path d="M8 14h.01" />
    <path d="M12 18h.01" />
    <path d="M8 18h.01" />
  </svg>
);

const IconBank = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <line x1="3" y1="21" x2="21" y2="21" />
    <line x1="3" y1="10" x2="21" y2="10" />
    <polyline points="5 6 12 3 19 6" />
    <line x1="4" y1="10" x2="4" y2="21" />
    <line x1="20" y1="10" x2="20" y2="21" />
    <line x1="8" y1="14" x2="8" y2="17" />
    <line x1="12" y1="14" x2="12" y2="17" />
    <line x1="16" y1="14" x2="16" y2="17" />
  </svg>
);

const IconFileCheck = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <path d="M9 15l2 2 4-4" />
  </svg>
);

const IconArrowLeft = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <line x1="19" y1="12" x2="5" y2="12" />
    <polyline points="12 19 5 12 12 5" />
  </svg>
);

const IconRefresh = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <polyline points="23 4 23 10 17 10" />
    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
  </svg>
);

const IconEdit = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
  </svg>
);

const IconCheck = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const IconAlertTriangle = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);

const IconPen = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <path d="M12 19l7-7 3 3-7 7-3-3z" />
    <path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z" />
    <path d="M2 2l7.586 7.586" />
    <circle cx="11" cy="11" r="2" />
  </svg>
);

const IconTrash = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
  </svg>
);

export default function DocumentViewPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();

  // Document & Extraction state
  const [doc, setDoc] = useState(null);
  const [extraction, setExtraction] = useState(null);
  const [formData, setFormData] = useState({});
  const [loading, setLoading] = useState(true);
  const [loadingExtraction, setLoadingExtraction] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState(null);

  // Review & Edit state
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [approving, setApproving] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [showOverrideModal, setShowOverrideModal] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Preview Mode: 'original' | 'standardised'
  const [viewMode, setViewMode] = useState('original');
  const [copies, setCopies] = useState([]);
  const [selectedCopyVersion, setSelectedCopyVersion] = useState(null);
  const [regeneratingCopy, setRegeneratingCopy] = useState(false);
  const [copyMsg, setCopyMsg] = useState('');

  // Interactive Zoom, Pan & Rotate
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0, scrollLeft: 0, scrollTop: 0 });
  const imageContainerRef = useRef(null);
  const fullScreenImageRef = useRef(null);

  // Inspector Tabs & Collapsible Sections
  const [inspectorTab, setInspectorTab] = useState('extracted'); // 'extracted' | 'technical' | 'raw'
  const [showDetails, setShowDetails] = useState(false);
  const [showRawData, setShowRawData] = useState(false);
  const [rawTab, setRawTab] = useState('json'); // 'json' | 'text' | 'history'
  const [editsHistory, setEditsHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [copiedHash, setCopiedHash] = useState(false);
  const [copiedJson, setCopiedJson] = useState(false);
  const [copiedText, setCopiedText] = useState(false);

  const showToast = (message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  // Optional Signature Attachment for Document / Standardised Copy
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
      showToast('Signature image uploaded. Click "Save Changes" to save and apply.', 'info');
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
    showToast('Signature removed. Click "Save Changes" to save.', 'info');
  };

  // Zoom handlers
  const handleZoomIn = () => setZoom((prev) => Math.min(Number((prev + 0.25).toFixed(2)), 3.5));
  const handleZoomOut = () => setZoom((prev) => Math.max(Number((prev - 0.25).toFixed(2)), 0.5));
  const handleZoomReset = () => {
    setZoom(1);
    setRotation(0);
    if (imageContainerRef.current) {
      imageContainerRef.current.scrollLeft = 0;
      imageContainerRef.current.scrollTop = 0;
    }
  };
  const handleRotate = () => {
    setRotation((prev) => (prev + 90) % 360);
  };

  // Drag pan handlers
  const handleMouseDown = (e, containerRef) => {
    const targetRef = containerRef || imageContainerRef;
    if (zoom <= 1 || !targetRef.current) return;
    setIsDragging(true);
    setDragStart({
      x: e.clientX,
      y: e.clientY,
      scrollLeft: targetRef.current.scrollLeft,
      scrollTop: targetRef.current.scrollTop,
    });
  };

  const handleMouseMove = (e, containerRef) => {
    const targetRef = containerRef || imageContainerRef;
    if (!isDragging || !targetRef.current) return;
    e.preventDefault();
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    targetRef.current.scrollLeft = dragStart.scrollLeft - dx;
    targetRef.current.scrollTop = dragStart.scrollTop - dy;
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Initial Fetch & Polling
  const fetchDoc = async () => {
    try {
      const data = await api.getDocument(id);
      setDoc(data);
      if (data.ocr_status === 'COMPLETED') {
        fetchExtraction();
      }
    } catch (err) {
      setError(err.message || 'Failed to load document');
    } finally {
      setLoading(false);
    }
  };

  const fetchExtraction = async () => {
    try {
      setLoadingExtraction(true);
      const data = await api.getDocumentExtraction(id);
      setExtraction(data);
      setFormData(data?.data || {});
    } catch (err) {
      // If extraction is 404 or fails, fall back to doc.structured_data if present
      console.warn('Extraction fetch error or not ready:', err);
    } finally {
      setLoadingExtraction(false);
    }
  };

  const fetchCopies = async () => {
    try {
      const data = await api.listDocumentCopies(id);
      setCopies(data || []);
      if (data && data.length > 0 && !selectedCopyVersion) {
        const current = data.find((c) => c.is_current) || data[0];
        setSelectedCopyVersion(current.copy_version);
      }
    } catch {
      // non-blocking
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
    fetchDoc();
    const interval = setInterval(async () => {
      const data = await api.getDocument(id).catch(() => null);
      if (data) {
        setDoc(data);
        if (data.ocr_status === 'COMPLETED' || data.ocr_status === 'FAILED') {
          clearInterval(interval);
          if (data.ocr_status === 'COMPLETED' && !extraction) {
            fetchExtraction();
          }
        }
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [id]);

  useEffect(() => {
    if (viewMode === 'standardised') {
      fetchCopies();
    }
  }, [id, viewMode]);

  useEffect(() => {
    if ((showRawData || inspectorTab === 'raw') && rawTab === 'history') {
      fetchHistory();
    }
  }, [showRawData, inspectorTab, rawTab]);

  // Actions
  const handleRegenerateCopy = async () => {
    setRegeneratingCopy(true);
    setCopyMsg('');
    setError('');
    try {
      const res = await api.regenerateDocumentCopy(id);
      setCopyMsg(`Standardised copy updated to v${res.copy_version}!`);
      fetchCopies();
      setSelectedCopyVersion(res.copy_version);
    } catch (err) {
      setError(err.message || 'Failed to regenerate standardised copy');
    } finally {
      setRegeneratingCopy(false);
    }
  };

  const handleReprocess = async () => {
    setReprocessing(true);
    try {
      const updated = await api.reprocessDocument(id);
      setDoc(updated);
      setError('');
      showToast('OCR re-processing initiated', 'info');
    } catch (err) {
      if (err.status === 409 || err.message?.includes('active job')) {
        setError('Document is currently being processed by an active job. Please wait a moment.');
      } else {
        setError(err.message || 'Failed to reprocess document.');
      }
    } finally {
      setReprocessing(false);
    }
  };

  const handleRestore = async () => {
    setRestoring(true);
    try {
      const updated = await api.restoreDocument(id);
      setDoc(updated);
      setError('');
      showToast('Document restored successfully', 'success');
    } catch (err) {
      setError(err.message || 'Failed to restore document.');
    } finally {
      setRestoring(false);
    }
  };

  const handleDelete = () => {
    setShowDeleteConfirm(true);
  };

  const confirmDelete = async () => {
    try {
      setDeleting(true);
      await api.deleteDocument(id);
      navigate('/documents');
    } catch (err) {
      setError(err.message || 'Failed to delete document.');
      setShowDeleteConfirm(false);
    } finally {
      setDeleting(false);
    }
  };

  // Field Edit Handlers
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
  };

  const handleLineItemChange = (index, fieldKey, val) => {
    const updated = JSON.parse(JSON.stringify(formData));
    const items = [...(updated.items || [])];
    if (items[index]) {
      const item = { ...items[index] };
      item[fieldKey] = val;
      if (fieldKey === 'hsn') item.hsn_sac = val;
      if (fieldKey === 'hsn_sac') item.hsn = val;
      if (fieldKey === 'unit') item.batch = val;
      if (fieldKey === 'batch') item.unit = val;
      items[index] = item;
      updated.items = items;
      setFormData(updated);
    }
  };

  const handleAddLineItem = () => {
    const updated = JSON.parse(JSON.stringify(formData));
    const items = [...(updated.items || [])];
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
    updated.items = items;
    setFormData(updated);
  };

  const handleDeleteLineItem = (index) => {
    const updated = JSON.parse(JSON.stringify(formData));
    const items = [...(updated.items || [])];
    items.splice(index, 1);
    updated.items = items;
    setFormData(updated);
  };

  const handleSaveCorrections = async () => {
    if (!extraction) return;
    try {
      setSaving(true);
      const res = await api.saveExtractionCorrections(id, {
        version: extraction.version,
        data: formData,
      });
      setExtraction(res);
      setFormData(res.data || {});
      setIsEditing(false);
      showToast('Corrections saved and revalidated successfully!', 'success');
      fetchCopies();
      if (showRawData && rawTab === 'history') fetchHistory();
    } catch (err) {
      showToast(err.message || 'Failed to save corrections', 'error');
      if (err.message && err.message.includes('409')) {
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
      showToast('Document extraction verified and approved!', 'success');
    } catch (err) {
      showToast(err.message || 'Failed to approve extraction', 'error');
    } finally {
      setApproving(false);
    }
  };

  // Helper for field validation flags
  const getFieldFlag = (path) => {
    if (!extraction?.validation_flags) return null;
    return extraction.validation_flags.find((f) => f.field_path === path);
  };

  if (loading) {
    return (
      <div className="page-content">
        <div className="loading-state">
          <div className="spinner" />
          <p>Loading document review workspace…</p>
        </div>
      </div>
    );
  }

  if (error && !doc) {
    return (
      <div className="page-content">
        <div className="alert alert-error">{error}</div>
        <button className="btn btn-ghost" onClick={() => navigate('/documents')}>
          ← Back to Documents
        </button>
      </div>
    );
  }

  const fileUrl = api.getFileUrl(id);
  const isPdf = doc?.mime_type === 'application/pdf';
  const statusInfo = STATUS_INFO[doc?.ocr_status] || STATUS_INFO.UPLOADED;
  const isApproved = extraction?.status === 'approved';
  const hasErrors = extraction?.has_errors || (extraction?.validation_flags || []).some(f => f.severity === 'error');
  const activeData = (extraction && extraction.data) ? formData : (doc?.structured_data ? JSON.parse(doc.structured_data || '{}') : {});

  const canReprocess = !doc?.deleted_at &&
    (doc?.ocr_status === 'COMPLETED' || doc?.ocr_status === 'FAILED') &&
    (hasPermission('document.reprocess') || user?.role === 'GLOBAL_ADMIN' || user?.role === 'ADMIN' || doc?.uploaded_by === user?.id);

  const canDelete = !doc?.deleted_at &&
    (hasPermission('document.delete') || user?.role === 'GLOBAL_ADMIN' || user?.role === 'ADMIN' || doc?.uploaded_by === user?.id);

  const canRestore = Boolean(doc?.deleted_at) &&
    (hasPermission('document.restore') || user?.role === 'GLOBAL_ADMIN' || user?.role === 'ADMIN');

  // Readable display title (prioritize invoice number over technical filename)
  const displayTitle = activeData?.invoice?.number || doc?.invoice_number
    ? `Invoice: ${activeData?.invoice?.number || doc.invoice_number}`
    : `Document #${doc.id}`;

  return (
    <div className="page-content" style={{ maxWidth: '1720px', margin: '0 auto', padding: '0.875rem 1.25rem 2.5rem' }}>
      {/* Toast Notification */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            top: '1.25rem',
            right: '1.5rem',
            zIndex: 10000,
            padding: '0.75rem 1.25rem',
            borderRadius: '8px',
            backgroundColor: toast.type === 'error' ? '#ef4444' : toast.type === 'success' ? '#16a34a' : '#2563eb',
            color: '#ffffff',
            fontWeight: 600,
            fontSize: '0.875rem',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
          }}
        >
          <span>{toast.type === 'error' ? '⚠️' : toast.type === 'success' ? '✓' : 'ℹ️'}</span>
          <span>{toast.message}</span>
        </div>
      )}

      {/* Top Error / Alert Banner */}
      {error && (
        <div className="alert alert-error" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
          <span>{error}</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setError('')}
            style={{ padding: '0.1rem 0.4rem', color: '#dc2626', fontWeight: 'bold' }}
            title="Dismiss error"
          >
            ✕
          </button>
        </div>
      )}

      {/* Soft-deleted Trash Banner */}
      {doc.deleted_at && (
        <div className="alert alert-warning" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.875rem', padding: '0.75rem 1.25rem' }}>
          <div>
            <strong>⚠️ Document in Trash</strong> — Soft-deleted on {formatDate(doc.deleted_at)}.
          </div>
          {canRestore && (
            <button className="btn btn-primary btn-sm" onClick={handleRestore} disabled={restoring}>
              {restoring ? 'Restoring…' : 'Restore Document'}
            </button>
          )}
        </div>
      )}

      {/* ── Document Details Page Header ── */}
      <div className="doc-page-header">
        {/* Back Link */}
        <div>
          <button
            type="button"
            className="doc-breadcrumb-back"
            onClick={() => navigate('/documents')}
            title="Return to documents list"
          >
            <IconArrowLeft />
            <span>Back to Documents</span>
          </button>
        </div>

        {/* Main Title, Status & Actions Bar */}
        <div className="doc-header-main-row">
          {/* Left: Identity & Metadata */}
          <div className="doc-header-identity">
            <div className="doc-header-title-group">
              <h1 className="doc-header-title">{displayTitle}</h1>

              {/* Status Badge */}
              {isApproved ? (
                <span className="status-badge status-completed">
                  Approved
                </span>
              ) : extraction?.status === 'needs_review' ? (
                <span className="status-badge status-processing">
                  Needs Review
                </span>
              ) : (
                <span className={`status-badge ${statusInfo.cls}`}>
                  {statusInfo.label}
                </span>
              )}

              {/* Invoice Type Badge */}
              {doc.invoice_type && (
                <span
                  style={{
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    background: '#fef2f2',
                    color: '#b91c1c',
                    border: '1px solid #fecaca',
                    padding: '0.2rem 0.55rem',
                    borderRadius: '4px',
                    display: 'inline-flex',
                    alignItems: 'center',
                  }}
                >
                  {doc.invoice_type}
                </span>
              )}
            </div>

            <div className="doc-header-meta">
              <span style={{ fontWeight: 500, color: '#334155' }}>{doc.original_filename}</span>
              <span>•</span>
              <span>{formatBytes(doc.file_size)}</span>
              <span>•</span>
              <span>Uploaded {formatDate(doc.created_at)}</span>
              {doc.uploader_name && (
                <>
                  <span>•</span>
                  <span>By {doc.uploader_name}</span>
                </>
              )}
            </div>
          </div>

          {/* Right: Action Toolbar */}
          <div className="doc-header-actions">
            {canReprocess && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleReprocess}
                disabled={reprocessing || doc.ocr_status === 'PROCESSING' || doc.ocr_status === 'UPLOADED'}
                title="Re-run OCR and extraction pipeline"
                style={{ fontSize: '0.8125rem' }}
              >
                {reprocessing ? 'Reprocessing…' : 'Re-process OCR'}
              </button>
            )}

            {doc.ocr_status === 'COMPLETED' && (
              <>
                {isEditing ? (
                  <>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        setFormData(extraction?.data || {});
                        setIsEditing(false);
                      }}
                      disabled={saving}
                      style={{ fontSize: '0.8125rem' }}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={handleSaveCorrections}
                      disabled={saving}
                      style={{ fontSize: '0.8125rem' }}
                    >
                      {saving ? 'Saving…' : 'Save Changes'}
                    </button>
                  </>
                ) : (
                  !isApproved && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => setIsEditing(true)}
                      style={{ fontSize: '0.8125rem' }}
                    >
                      Edit Fields
                    </button>
                  )
                )}

                {!isApproved && !isEditing && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => {
                      if (hasErrors) {
                        setShowOverrideModal(true);
                      } else {
                        handleApprove(false);
                      }
                    }}
                    disabled={approving}
                    style={{ fontSize: '0.8125rem' }}
                  >
                    {approving ? 'Approving…' : hasErrors ? 'Override & Approve' : 'Approve Extraction'}
                  </button>
                )}

                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setViewMode(viewMode === 'standardised' ? 'original' : 'standardised')}
                  title="Toggle between Original Document and Standardised Invoice Copy"
                  style={{ fontSize: '0.8125rem' }}
                >
                  {viewMode === 'standardised' ? 'Original Document' : 'Standardised Invoice'}
                </button>
              </>
            )}

            {canDelete && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleDelete}
                disabled={deleting}
                style={{ color: '#dc2626', borderColor: '#fca5a5', fontSize: '0.8125rem' }}
                title="Delete document"
              >
                Delete
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Main Two-Column Document Review Workspace ── */}
      <div className="doc-review-layout">
        {/* ── LEFT COLUMN: Spacious Document Preview (58% width, full height) ── */}
        <div className="doc-review-panel">
          {/* Preview Tab Bar */}
          <div className="doc-inspector-tabs">
            <button
              type="button"
              className={`doc-inspector-tab-btn ${viewMode === 'original' ? 'active' : ''}`}
              onClick={() => setViewMode('original')}
            >
              <IconEye />
              <span>Original Document</span>
            </button>

            {doc?.ocr_status === 'COMPLETED' && (
              <button
                type="button"
                className={`doc-inspector-tab-btn ${viewMode === 'standardised' ? 'active' : ''}`}
                onClick={() => setViewMode('standardised')}
              >
                <IconCheckCopy />
                <span>Standardised Copy</span>
                {copies.some((c) => c.is_current && c.is_stale) && (
                  <span className="doc-tab-badge badge-warning">
                    Stale
                  </span>
                )}
              </button>
            )}
          </div>

          {/* Standardised Copy Sub-bar & Notices */}
          {viewMode === 'standardised' && (
            <div style={{ padding: '0.5rem 0.875rem', background: '#ffffff', borderBottom: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
              {copyMsg && <div className="alert alert-success" style={{ fontSize: '0.8rem', padding: '0.35rem 0.6rem', margin: 0 }}>{copyMsg}</div>}

              {copies.find((c) => c.is_current)?.is_stale && (
                <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '6px', padding: '0.45rem 0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem' }}>
                  <div style={{ fontSize: '0.75rem', color: '#92400e' }}>
                    ⚠️ Document OCR data was modified after this copy was rendered.
                  </div>
                  <button
                    className="btn btn-sm btn-primary"
                    style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem', whiteSpace: 'nowrap' }}
                    onClick={handleRegenerateCopy}
                    disabled={regeneratingCopy}
                  >
                    {regeneratingCopy ? 'Regenerating…' : 'Regenerate Copy'}
                  </button>
                </div>
              )}

              {copies.length > 1 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Version History:</span>
                  <select
                    className="form-control"
                    style={{ width: 'auto', padding: '0.2rem 0.5rem', fontSize: '0.78rem' }}
                    value={selectedCopyVersion || ''}
                    onChange={(e) => setSelectedCopyVersion(parseInt(e.target.value, 10))}
                  >
                    {copies.map((c) => (
                      <option key={c.id} value={c.copy_version}>
                        v{c.copy_version} {c.is_current ? '(Current)' : '(Historical)'} {c.is_stale ? '[Stale]' : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          )}

          {/* Interactive Preview Toolbar */}
          <div className="doc-preview-toolbar">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <span style={{ fontSize: '0.72rem', backgroundColor: '#f1f5f9', color: '#475569', padding: '0.15rem 0.5rem', borderRadius: '4px', border: '1px solid #e2e8f0', fontWeight: 600 }}>
                {viewMode === 'original' ? (doc.mime_type || 'image/jpeg') : 'PDF Copy'}
              </span>

              {/* Download button */}
              {viewMode === 'original' ? (
                <a
                  href={fileUrl}
                  target="_blank"
                  rel="noreferrer"
                  download={doc.original_filename}
                  onClick={async (e) => {
                    e.preventDefault();
                    try {
                      await api.downloadDocumentOriginal(id, doc.original_filename);
                    } catch {
                      window.open(fileUrl, '_blank');
                    }
                  }}
                  style={{ fontSize: '0.75rem', color: 'var(--brand)', textDecoration: 'none', fontWeight: 600, padding: '0.2rem 0.45rem', borderRadius: '4px', backgroundColor: '#fff1f2', cursor: 'pointer' }}
                  title="Download original uploaded file"
                >
                  Download Original
                </a>
              ) : (
                <a
                  href={selectedCopyVersion ? api.getDocumentCopyPdfUrl(id, selectedCopyVersion, true) : `${api.getInvoiceUrl(id)}&download=true`}
                  target="_blank"
                  rel="noreferrer"
                  download={`supplier_copy_${id}_v${selectedCopyVersion || 1}.pdf`}
                  onClick={async (e) => {
                    e.preventDefault();
                    try {
                      if (selectedCopyVersion) {
                        await api.downloadDocumentCopyPdf(id, selectedCopyVersion, `supplier_copy_${id}_v${selectedCopyVersion}.pdf`);
                      } else {
                        await api.downloadDocumentInvoicePdf(id, `invoice_${id}.pdf`);
                      }
                    } catch {
                      window.open(selectedCopyVersion ? api.getDocumentCopyPdfUrl(id, selectedCopyVersion, true) : `${api.getInvoiceUrl(id)}&download=true`, '_blank');
                    }
                  }}
                  style={{ fontSize: '0.75rem', color: 'var(--brand)', textDecoration: 'none', fontWeight: 600, padding: '0.2rem 0.45rem', borderRadius: '4px', backgroundColor: '#fff1f2', cursor: 'pointer' }}
                  title="Download standardised invoice PDF"
                >
                  Download PDF
                </a>
              )}
            </div>

            {/* Interactive Zoom, Pan, Rotate & Fullscreen Controls */}
            {!isPdf && viewMode === 'original' && (
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
                <div style={{ display: 'inline-flex', alignItems: 'center', backgroundColor: '#f8fafc', borderRadius: '6px', border: '1px solid #cbd5e1', overflow: 'hidden' }}>
                  <button
                    type="button"
                    onClick={handleZoomOut}
                    disabled={zoom <= 0.5}
                    title="Zoom Out (−)"
                    style={{ border: 'none', background: 'none', padding: '0.2rem 0.5rem', cursor: zoom <= 0.5 ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: 'bold', color: '#334155' }}
                  >
                    −
                  </button>
                  <span style={{ padding: '0.15rem 0.35rem', fontSize: '0.72rem', fontWeight: 700, minWidth: '3.2rem', textAlign: 'center', color: '#0f172a', borderLeft: '1px solid #e2e8f0', borderRight: '1px solid #e2e8f0' }}>
                    {Math.round(zoom * 100)}%
                  </span>
                  <button
                    type="button"
                    onClick={handleZoomIn}
                    disabled={zoom >= 3.5}
                    title="Zoom In (+)"
                    style={{ border: 'none', background: 'none', padding: '0.2rem 0.5rem', cursor: zoom >= 3.5 ? 'not-allowed' : 'pointer', fontSize: '0.85rem', fontWeight: 'bold', color: '#334155' }}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    onClick={handleZoomReset}
                    title="Reset to 100% Fit"
                    style={{ border: 'none', borderLeft: '1px solid #e2e8f0', background: 'none', padding: '0.2rem 0.45rem', cursor: 'pointer', fontSize: '0.72rem', fontWeight: 600, color: 'var(--brand)' }}
                  >
                    Fit
                  </button>
                </div>

                <button
                  type="button"
                  onClick={handleRotate}
                  title="Rotate 90 degrees"
                  style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', fontWeight: 600, borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', cursor: 'pointer', color: '#334155' }}
                >
                  Rotate {rotation > 0 ? `(${rotation}°)` : ''}
                </button>

                <button
                  type="button"
                  onClick={() => setIsFullScreen(true)}
                  title="Expand to Fullscreen"
                  style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', fontWeight: 600, borderRadius: '6px', border: '1px solid #cbd5e1', backgroundColor: '#ffffff', cursor: 'pointer', color: '#334155' }}
                >
                  Fullscreen
                </button>
              </div>
            )}
          </div>

          {/* Document Viewport */}
          <div
            ref={imageContainerRef}
            onMouseDown={(e) => handleMouseDown(e, imageContainerRef)}
            onMouseMove={(e) => handleMouseMove(e, imageContainerRef)}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            className="doc-preview-viewport"
            style={{
              cursor: zoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default',
              userSelect: isDragging ? 'none' : 'auto',
            }}
          >
            {viewMode === 'original' ? (
              isPdf ? (
                <div style={{ width: '100%', height: '100%', minHeight: '520px' }}>
                  <iframe src={`${fileUrl}#toolbar=0`} title={doc.original_filename} className="pdf-iframe" style={{ width: '100%', height: '100%', border: 'none', borderRadius: '6px', backgroundColor: '#ffffff' }} />
                </div>
              ) : (
                <div
                  style={{
                    transform: `scale(${zoom}) rotate(${rotation}deg)`,
                    transformOrigin: 'top center',
                    transition: isDragging ? 'none' : 'transform 0.12s ease-out',
                    maxWidth: zoom <= 1 ? '100%' : 'none',
                    display: 'flex',
                    justifyContent: 'center',
                  }}
                >
                  <img
                    src={fileUrl}
                    alt={doc.original_filename}
                    draggable={false}
                    style={{
                      maxWidth: '100%',
                      height: 'auto',
                      objectFit: 'contain',
                      borderRadius: '6px',
                      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.08)',
                      backgroundColor: '#ffffff',
                      display: 'block',
                    }}
                  />
                </div>
              )
            ) : (
              <div style={{ width: '100%', height: '100%', minHeight: '520px' }}>
                <iframe
                  src={
                    selectedCopyVersion
                      ? `${api.getDocumentCopyPdfUrl(id, selectedCopyVersion)}#toolbar=0`
                      : `${api.getInvoiceUrl(id)}#toolbar=0`
                  }
                  title="Standardised Supplier Copy"
                  style={{ width: '100%', height: '100%', border: 'none', borderRadius: '6px', backgroundColor: '#ffffff' }}
                />
              </div>
            )}
          </div>
        </div>

        {/* ── RIGHT COLUMN: Structured Document Inspector (42% width, independent scroll) ── */}
        <div className="doc-inspector-panel">
          {/* Inspector Tab Bar */}
          <div className="doc-inspector-tabs">
            <button
              type="button"
              className={`doc-inspector-tab-btn ${inspectorTab === 'extracted' ? 'active' : ''}`}
              onClick={() => setInspectorTab('extracted')}
            >
              <IconFileText />
              <span>Extracted Data</span>
              {Array.isArray(activeData.items) && activeData.items.length > 0 && (
                <span className="doc-tab-badge" title={`${activeData.items.length} extracted line item${activeData.items.length === 1 ? '' : 's'}`}>
                  {activeData.items.length}
                </span>
              )}
            </button>

            <button
              type="button"
              className={`doc-inspector-tab-btn ${inspectorTab === 'technical' ? 'active' : ''}`}
              onClick={() => setInspectorTab('technical')}
            >
              <IconInfoCircle />
              <span>Document Info</span>
            </button>

            <button
              type="button"
              className={`doc-inspector-tab-btn ${inspectorTab === 'raw' ? 'active' : ''}`}
              onClick={() => {
                setInspectorTab('raw');
                setShowRawData(true);
              }}
            >
              <IconCode2 />
              <span>OCR &amp; Audit</span>
              {extraction?.edits_count > 0 && (
                <span
                  className="doc-tab-badge badge-edits"
                  title={`${extraction.edits_count} manual edit${extraction.edits_count === 1 ? '' : 's'}`}
                >
                  {extraction.edits_count}
                  <span className="tab-badge-text">
                    {' '}{extraction.edits_count === 1 ? 'edit' : 'edits'}
                  </span>
                </span>
              )}
            </button>
          </div>

          {/* Inspector Body with Independent Scroll */}
          <div className="doc-inspector-body">
            {/* ── TAB 1: Extracted Invoice Information ── */}
            {inspectorTab === 'extracted' && (
              <>
                {/* Validation Flags Alert Banner */}
                {extraction?.validation_flags && extraction.validation_flags.length > 0 && (
                  <div
                    style={{
                      backgroundColor: hasErrors ? '#fef2f2' : '#fffbeb',
                      border: `1px solid ${hasErrors ? '#fecaca' : '#fde68a'}`,
                      borderRadius: '8px',
                      padding: '0.75rem 1rem',
                    }}
                  >
                    <div style={{ fontWeight: 700, fontSize: '0.85rem', color: hasErrors ? '#b91c1c' : '#b45309', marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span>{hasErrors ? '⚠️' : 'ℹ️'}</span>
                      <span>
                        {hasErrors
                          ? `${extraction.validation_flags.filter((f) => f.severity === 'error').length} Validation Error(s) Detected`
                          : `${extraction.validation_flags.length} Validation Warning(s)`}
                      </span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                      {extraction.validation_flags.map((flag, idx) => (
                        <div
                          key={idx}
                          style={{
                            fontSize: '0.78rem',
                            color: flag.severity === 'error' ? '#991b1b' : '#92400e',
                            padding: '0.2rem 0.4rem',
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

                {/* OCR Processing / Failed Notice */}
                {doc.ocr_status === 'FAILED' && (
                  <div className="alert alert-error" style={{ margin: 0 }}>
                    <div style={{ fontWeight: 700, marginBottom: '0.25rem' }}>OCR Processing Failed</div>
                    <div style={{ fontSize: '0.825rem' }}>{doc.ocr_text || 'OCR pipeline could not extract text from this document.'}</div>
                    {doc.ocr_text && doc.ocr_text.includes('consent') && (
                      <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', background: '#ffffff', padding: '0.5rem', borderRadius: '4px', color: '#991b1b' }}>
                        💡 <strong>Action Required:</strong> A Company Administrator must grant external AI consent in <strong>Company Admin → AI &amp; Providers</strong> before reprocessing.
                      </div>
                    )}
                  </div>
                )}

                {doc.ocr_status === 'PROCESSING' && (
                  <div style={{ padding: '2rem', textAlign: 'center', background: '#ffffff', border: '1px solid var(--border)', borderRadius: '8px' }}>
                    <div className="spinner" style={{ margin: '0 auto 0.75rem' }} />
                    <div style={{ fontWeight: 600, color: '#0f172a' }}>OCR Extraction in Progress…</div>
                    <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                      This workspace will automatically refresh once field analysis completes.
                    </div>
                  </div>
                )}

                {/* SECTION 1: Supplier Details */}
                <div className="extracted-section-card">
                  <div className="extracted-section-header">
                    <h3 className="extracted-section-title">
                      <IconBuilding />
                      <span>Supplier Details</span>
                    </h3>
                    {activeData.seller?.state_code && (
                      <span style={{ fontSize: '0.72rem', backgroundColor: '#f1f5f9', color: '#475569', padding: '0.15rem 0.45rem', borderRadius: '4px', fontWeight: 600 }}>
                        State Code: {activeData.seller.state_code}
                      </span>
                    )}
                  </div>

                  {isEditing ? (
                    <div className="field-grid-2">
                      <div className="field-cell">
                        <span className="field-label">Supplier Name</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.seller?.name || ''}
                          onChange={(e) => handleFieldChange('seller.name', e.target.value)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">GSTIN</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.seller?.gstin || ''}
                          onChange={(e) => handleFieldChange('seller.gstin', e.target.value)}
                        />
                      </div>
                      <div className="field-cell" style={{ gridColumn: 'span 2' }}>
                        <span className="field-label">Address</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.seller?.address || ''}
                          onChange={(e) => handleFieldChange('seller.address', e.target.value)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Phone</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.seller?.phone || ''}
                          onChange={(e) => handleFieldChange('seller.phone', e.target.value)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Email</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.seller?.email || ''}
                          onChange={(e) => handleFieldChange('seller.email', e.target.value)}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="field-grid-2">
                      <div className="field-cell">
                        <span className="field-label">Supplier Name</span>
                        <span className="field-value" style={{ fontWeight: 700, fontSize: '0.92rem' }}>
                          {activeData.seller?.name || <span className="field-value-empty">Not detected</span>}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">GSTIN</span>
                        <span className="field-value" style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                          {activeData.seller?.gstin || <span className="field-value-empty">Not detected</span>}
                        </span>
                      </div>
                      <div className="field-cell" style={{ gridColumn: 'span 2' }}>
                        <span className="field-label">Address</span>
                        <span className="field-value">
                          {activeData.seller?.address || <span className="field-value-empty">Not detected</span>}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Phone</span>
                        <span className="field-value">
                          {activeData.seller?.phone || <span className="field-value-empty">—</span>}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Email</span>
                        <span className="field-value">
                          {activeData.seller?.email || <span className="field-value-empty">—</span>}
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* SECTION 2: Invoice Details */}
                <div className="extracted-section-card">
                  <div className="extracted-section-header">
                    <h3 className="extracted-section-title">
                      <IconFileText />
                      <span>Invoice Details</span>
                    </h3>
                  </div>

                  {isEditing ? (
                    <div className="field-grid-2">
                      <div className="field-cell">
                        <span className="field-label">Invoice Number</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.invoice?.number || ''}
                          onChange={(e) => handleFieldChange('invoice.number', e.target.value)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Invoice Date</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.invoice?.date || ''}
                          onChange={(e) => handleFieldChange('invoice.date', e.target.value)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Due Date</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.invoice?.due_date || ''}
                          onChange={(e) => handleFieldChange('invoice.due_date', e.target.value)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Place of Supply / Terms</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.invoice?.place_of_supply || formData.invoice?.payment_terms || ''}
                          onChange={(e) => handleFieldChange('invoice.place_of_supply', e.target.value)}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="field-grid-2">
                      <div className="field-cell">
                        <span className="field-label">Invoice Number</span>
                        <span className="field-value" style={{ fontWeight: 700 }}>
                          {activeData.invoice?.number || doc?.invoice_number || <span className="field-value-empty">Not detected</span>}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Invoice Date</span>
                        <span className="field-value">
                          {activeData.invoice?.date || (doc?.invoice_date ? formatDate(doc.invoice_date) : <span className="field-value-empty">Not detected</span>)}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Due Date</span>
                        <span className="field-value">
                          {activeData.invoice?.due_date || <span className="field-value-empty">—</span>}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Place of Supply / Terms</span>
                        <span className="field-value">
                          {activeData.invoice?.place_of_supply || activeData.invoice?.payment_terms || <span className="field-value-empty">—</span>}
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* SECTION 3: Customer / Buyer Details */}
                <div className="extracted-section-card">
                  <div className="extracted-section-header">
                    <h3 className="extracted-section-title">
                      <IconUser />
                      <span>Customer / Buyer Details</span>
                    </h3>
                  </div>

                  {isEditing ? (
                    <div className="field-grid-2">
                      <div className="field-cell">
                        <span className="field-label">Customer Name</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.buyer?.name || ''}
                          onChange={(e) => handleFieldChange('buyer.name', e.target.value)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Customer GSTIN</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.buyer?.gstin || ''}
                          onChange={(e) => handleFieldChange('buyer.gstin', e.target.value)}
                        />
                      </div>
                      <div className="field-cell" style={{ gridColumn: 'span 2' }}>
                        <span className="field-label">Billing Address</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.buyer?.address || ''}
                          onChange={(e) => handleFieldChange('buyer.address', e.target.value)}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="field-grid-2">
                      <div className="field-cell">
                        <span className="field-label">Customer Name</span>
                        <span className="field-value" style={{ fontWeight: 600 }}>
                          {activeData.buyer?.name || doc?.buyer_name || <span className="field-value-empty">Not detected</span>}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Customer GSTIN</span>
                        <span className="field-value" style={{ fontFamily: 'monospace' }}>
                          {activeData.buyer?.gstin || doc?.buyer_gstin || <span className="field-value-empty">Not detected</span>}
                        </span>
                      </div>
                      <div className="field-cell" style={{ gridColumn: 'span 2' }}>
                        <span className="field-label">Billing Address</span>
                        <span className="field-value">
                          {activeData.buyer?.address || <span className="field-value-empty">—</span>}
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* SECTION 4: Line Items Table */}
                <div className="extracted-section-card">
                  <div className="extracted-section-header">
                    <h3 className="extracted-section-title">
                      <IconPackage />
                      <span>Line Items ({Array.isArray(activeData.items) ? activeData.items.length : 0})</span>
                    </h3>
                    {isEditing && (
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={handleAddLineItem}
                        style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem', fontWeight: 600 }}
                      >
                        + Add Line Item
                      </button>
                    )}
                  </div>

                  <div style={{ overflowX: 'auto' }}>
                    <table className="doc-table-compact">
                      <thead>
                        <tr>
                          <th style={{ width: '28px' }}>#</th>
                          <th style={{ minWidth: '150px' }}>Description</th>
                          <th style={{ width: '70px' }}>HSN</th>
                          <th style={{ width: '60px' }}>Qty</th>
                          <th style={{ width: '60px' }}>Unit</th>
                          <th style={{ width: '85px', textAlign: 'right' }}>Rate (₹)</th>
                          <th style={{ width: '55px', textAlign: 'right' }}>Disc %</th>
                          <th style={{ width: '55px', textAlign: 'right' }}>GST %</th>
                          <th style={{ width: '95px', textAlign: 'right' }}>Amount (₹)</th>
                          {isEditing && <th style={{ width: '32px', textAlign: 'center' }}></th>}
                        </tr>
                      </thead>
                      <tbody>
                        {Array.isArray(activeData.items) && activeData.items.length > 0 ? (
                          activeData.items.map((item, idx) => {
                            const flag = getFieldFlag(`items[${idx}].amount`);
                            return (
                              <tr key={idx} style={{ backgroundColor: flag ? '#fef2f2' : 'transparent' }}>
                                <td style={{ color: '#94a3b8', fontSize: '0.75rem' }}>{idx + 1}</td>
                                <td>
                                  {isEditing ? (
                                    <input
                                      type="text"
                                      className="form-control"
                                      style={{ fontSize: '0.78rem', padding: '0.2rem 0.4rem' }}
                                      value={item.description || ''}
                                      onChange={(e) => handleLineItemChange(idx, 'description', e.target.value)}
                                    />
                                  ) : (
                                    <span style={{ fontWeight: 600 }}>{item.description || '—'}</span>
                                  )}
                                </td>
                                <td>
                                  {isEditing ? (
                                    <input
                                      type="text"
                                      className="form-control"
                                      style={{ fontSize: '0.78rem', padding: '0.2rem 0.4rem' }}
                                      value={item.hsn ?? item.hsn_sac ?? ''}
                                      onChange={(e) => handleLineItemChange(idx, 'hsn', e.target.value)}
                                    />
                                  ) : (
                                    <span style={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>{item.hsn || item.hsn_sac || '—'}</span>
                                  )}
                                </td>
                                <td>
                                  {isEditing ? (
                                    <input
                                      type="text"
                                      className="form-control"
                                      style={{ fontSize: '0.78rem', padding: '0.2rem 0.4rem' }}
                                      value={item.qty ?? ''}
                                      onChange={(e) => handleLineItemChange(idx, 'qty', e.target.value)}
                                    />
                                  ) : (
                                    <span>{item.qty || '—'}</span>
                                  )}
                                </td>
                                <td>
                                  {isEditing ? (
                                    <input
                                      type="text"
                                      className="form-control"
                                      style={{ fontSize: '0.78rem', padding: '0.2rem 0.4rem' }}
                                      value={item.unit ?? item.batch ?? ''}
                                      onChange={(e) => handleLineItemChange(idx, 'unit', e.target.value)}
                                    />
                                  ) : (
                                    <span style={{ color: 'var(--text-muted)' }}>{item.unit || item.batch || '—'}</span>
                                  )}
                                </td>
                                <td style={{ textAlign: 'right' }}>
                                  {isEditing ? (
                                    <input
                                      type="number"
                                      step="any"
                                      className="form-control"
                                      style={{ fontSize: '0.78rem', padding: '0.2rem 0.4rem', textAlign: 'right' }}
                                      value={item.rate ?? ''}
                                      onChange={(e) => handleLineItemChange(idx, 'rate', parseFloat(e.target.value) || 0)}
                                    />
                                  ) : (
                                    <span style={{ fontVariantNumeric: 'tabular-nums' }}>{formatCurrency(item.rate)}</span>
                                  )}
                                </td>
                                <td style={{ textAlign: 'right' }}>
                                  {isEditing ? (
                                    <input
                                      type="number"
                                      step="any"
                                      className="form-control"
                                      style={{ fontSize: '0.78rem', padding: '0.2rem 0.4rem', textAlign: 'right' }}
                                      value={item.discount ?? item.discount_percent ?? ''}
                                      onChange={(e) => handleLineItemChange(idx, 'discount', parseFloat(e.target.value) || 0)}
                                    />
                                  ) : (
                                    <span>{item.discount !== null && item.discount !== undefined ? `${item.discount}%` : '—'}</span>
                                  )}
                                </td>
                                <td style={{ textAlign: 'right' }}>
                                  {isEditing ? (
                                    <input
                                      type="number"
                                      step="any"
                                      className="form-control"
                                      style={{ fontSize: '0.78rem', padding: '0.2rem 0.4rem', textAlign: 'right' }}
                                      value={item.gst_rate ?? item.tax_rate ?? ''}
                                      onChange={(e) => handleLineItemChange(idx, 'gst_rate', parseFloat(e.target.value) || 0)}
                                    />
                                  ) : (
                                    <span style={{ fontSize: '0.75rem', backgroundColor: '#f1f5f9', padding: '0.1rem 0.35rem', borderRadius: '4px' }}>
                                      {item.gst_rate !== null && item.gst_rate !== undefined ? `${item.gst_rate}%` : '—'}
                                    </span>
                                  )}
                                </td>
                                <td style={{ textAlign: 'right' }}>
                                  {isEditing ? (
                                    <input
                                      type="number"
                                      step="any"
                                      className="form-control"
                                      style={{
                                        fontSize: '0.78rem',
                                        padding: '0.2rem 0.4rem',
                                        textAlign: 'right',
                                        fontWeight: 600,
                                        borderColor: flag ? '#ef4444' : undefined,
                                        backgroundColor: flag ? '#fef2f2' : undefined,
                                      }}
                                      value={item.amount ?? ''}
                                      onChange={(e) => handleLineItemChange(idx, 'amount', parseFloat(e.target.value) || 0)}
                                    />
                                  ) : (
                                    <span style={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: flag ? '#dc2626' : undefined }}>
                                      {formatCurrency(item.amount)}
                                    </span>
                                  )}
                                </td>
                                {isEditing && (
                                  <td style={{ textAlign: 'center' }}>
                                    <button
                                      type="button"
                                      onClick={() => handleDeleteLineItem(idx)}
                                      style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#ef4444', fontSize: '0.85rem' }}
                                      title="Remove line item"
                                    >
                                      ✕
                                    </button>
                                  </td>
                                )}
                              </tr>
                            );
                          })
                        ) : (
                          <tr>
                            <td colSpan={isEditing ? 10 : 9} style={{ textAlign: 'center', padding: '1.25rem', color: '#94a3b8' }}>
                              No individual line items parsed.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* SECTION 5: Invoice Summary & Totals */}
                <div className="totals-summary-box">
                  <h4 style={{ fontSize: '0.85rem', fontWeight: 700, margin: '0 0 0.75rem 0', color: '#1e293b', display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                    <IconCalculator />
                    <span>Invoice Summary &amp; Taxes</span>
                  </h4>

                  {isEditing ? (
                    <div className="field-grid-3" style={{ marginBottom: '0.75rem' }}>
                      <div className="field-cell">
                        <span className="field-label">Taxable Subtotal</span>
                        <input
                          type="number"
                          step="any"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.totals?.taxable_value ?? ''}
                          onChange={(e) => handleFieldChange('totals.taxable_value', parseFloat(e.target.value) || 0)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">CGST</span>
                        <input
                          type="number"
                          step="any"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.totals?.cgst ?? ''}
                          onChange={(e) => handleFieldChange('totals.cgst', parseFloat(e.target.value) || 0)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">SGST</span>
                        <input
                          type="number"
                          step="any"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.totals?.sgst ?? ''}
                          onChange={(e) => handleFieldChange('totals.sgst', parseFloat(e.target.value) || 0)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">IGST</span>
                        <input
                          type="number"
                          step="any"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.totals?.igst ?? ''}
                          onChange={(e) => handleFieldChange('totals.igst', parseFloat(e.target.value) || 0)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Round Off</span>
                        <input
                          type="number"
                          step="any"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                          value={formData.totals?.round_off ?? ''}
                          onChange={(e) => handleFieldChange('totals.round_off', parseFloat(e.target.value) || 0)}
                        />
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Grand Total (₹)</span>
                        <input
                          type="number"
                          step="any"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem', fontWeight: 700 }}
                          value={formData.totals?.grand_total ?? ''}
                          onChange={(e) => handleFieldChange('totals.grand_total', parseFloat(e.target.value) || 0)}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="field-grid-3" style={{ marginBottom: '0.75rem' }}>
                      <div className="field-cell">
                        <span className="field-label">Taxable Subtotal</span>
                        <span className="field-value" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {formatCurrency(activeData.totals?.taxable_value)}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">CGST</span>
                        <span className="field-value" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {formatCurrency(activeData.totals?.cgst)}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">SGST</span>
                        <span className="field-value" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {formatCurrency(activeData.totals?.sgst)}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">IGST</span>
                        <span className="field-value" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {formatCurrency(activeData.totals?.igst)}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Round Off</span>
                        <span className="field-value" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {formatCurrency(activeData.totals?.round_off)}
                        </span>
                      </div>
                      <div className="field-cell">
                        <span className="field-label">Total Quantity</span>
                        <span className="field-value">
                          {activeData.totals?.total_qty || '—'}
                        </span>
                      </div>
                    </div>
                  )}

                  <div className="totals-grand-row">
                    <div>
                      <span className="totals-grand-label">Total Amount Payable</span>
                      {activeData.totals?.amount_in_words && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px', fontStyle: 'italic' }}>
                          {activeData.totals.amount_in_words}
                        </div>
                      )}
                    </div>
                    <div className="totals-grand-value">
                      {formatCurrency(activeData.totals?.grand_total || doc?.grand_total)}
                    </div>
                  </div>
                </div>

                {/* SECTION 6: Bank & Payment Details (If Present or Editing) */}
                {(activeData.bank || activeData.bank_details || isEditing) && (
                  <div className="extracted-section-card">
                    <div className="extracted-section-header">
                      <h3 className="extracted-section-title">
                        <IconBank />
                        <span>Bank &amp; Payment Details</span>
                      </h3>
                    </div>
                    {isEditing ? (
                      <div className="field-grid-2">
                        <div className="field-cell">
                          <span className="field-label">Bank Name</span>
                          <input
                            type="text"
                            className="form-control"
                            style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                            value={formData.bank?.bank_name || formData.bank_details?.bank_name || ''}
                            onChange={(e) => {
                              const val = e.target.value;
                              if (formData.bank_details && !formData.bank) {
                                handleFieldChange('bank_details.bank_name', val);
                              } else {
                                handleFieldChange('bank.bank_name', val);
                              }
                            }}
                            placeholder="Bank name"
                          />
                        </div>
                        <div className="field-cell">
                          <span className="field-label">Account Number</span>
                          <input
                            type="text"
                            className="form-control"
                            style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem', fontFamily: 'monospace' }}
                            value={formData.bank?.account_no || formData.bank?.account_number || formData.bank_details?.account_no || formData.bank_details?.account_number || ''}
                            onChange={(e) => {
                              const val = e.target.value;
                              if (formData.bank_details && !formData.bank) {
                                handleFieldChange('bank_details.account_no', val);
                              } else {
                                handleFieldChange('bank.account_no', val);
                              }
                            }}
                            placeholder="Account number"
                          />
                        </div>
                        <div className="field-cell">
                          <span className="field-label">IFSC Code</span>
                          <input
                            type="text"
                            className="form-control"
                            style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem', fontFamily: 'monospace' }}
                            value={formData.bank?.ifsc || formData.bank_details?.ifsc || ''}
                            onChange={(e) => {
                              const val = e.target.value;
                              if (formData.bank_details && !formData.bank) {
                                handleFieldChange('bank_details.ifsc', val);
                              } else {
                                handleFieldChange('bank.ifsc', val);
                              }
                            }}
                            placeholder="IFSC code"
                          />
                        </div>
                        <div className="field-cell">
                          <span className="field-label">Branch</span>
                          <input
                            type="text"
                            className="form-control"
                            style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
                            value={formData.bank?.branch || formData.bank_details?.branch || ''}
                            onChange={(e) => {
                              const val = e.target.value;
                              if (formData.bank_details && !formData.bank) {
                                handleFieldChange('bank_details.branch', val);
                              } else {
                                handleFieldChange('bank.branch', val);
                              }
                            }}
                            placeholder="Branch name"
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="field-grid-2">
                        <div className="field-cell">
                          <span className="field-label">Bank Name</span>
                          <span className="field-value">{(activeData.bank || activeData.bank_details)?.bank_name || '—'}</span>
                        </div>
                        <div className="field-cell">
                          <span className="field-label">Account Number</span>
                          <span className="field-value" style={{ fontFamily: 'monospace' }}>{(activeData.bank || activeData.bank_details)?.account_no || (activeData.bank || activeData.bank_details)?.account_number || '—'}</span>
                        </div>
                        <div className="field-cell">
                          <span className="field-label">IFSC Code</span>
                          <span className="field-value" style={{ fontFamily: 'monospace' }}>{(activeData.bank || activeData.bank_details)?.ifsc || '—'}</span>
                        </div>
                        <div className="field-cell">
                          <span className="field-label">Branch</span>
                          <span className="field-value">{(activeData.bank || activeData.bank_details)?.branch || '—'}</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* SECTION 7: Declarations & Terms (If Present or Editing) */}
                {(activeData.declaration || activeData.warranty_note || isEditing) && (
                  <div className="extracted-section-card">
                    <div className="extracted-section-header">
                      <h3 className="extracted-section-title">
                        <IconFileCheck />
                        <span>Declarations &amp; Warranty Terms</span>
                      </h3>
                    </div>
                    {isEditing ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                        <div className="field-cell">
                          <span className="field-label">Declaration</span>
                          <textarea
                            className="form-control"
                            rows={3}
                            style={{ fontSize: '0.8125rem', padding: '0.4rem 0.5rem', lineHeight: 1.45, resize: 'vertical' }}
                            value={formData.declaration || ''}
                            onChange={(e) => handleFieldChange('declaration', e.target.value)}
                            placeholder="Enter declaration statement..."
                          />
                        </div>
                        <div className="field-cell">
                          <span className="field-label">Warranty Note</span>
                          <textarea
                            className="form-control"
                            rows={3}
                            style={{ fontSize: '0.8125rem', padding: '0.4rem 0.5rem', lineHeight: 1.45, resize: 'vertical' }}
                            value={formData.warranty_note || ''}
                            onChange={(e) => handleFieldChange('warranty_note', e.target.value)}
                            placeholder="Enter warranty terms and conditions..."
                          />
                        </div>
                      </div>
                    ) : (
                      <>
                        {activeData.declaration && (
                          <div style={{ marginBottom: '0.5rem' }}>
                            <span className="field-label">Declaration</span>
                            <p style={{ margin: '0.2rem 0 0', fontSize: '0.78rem', color: '#475569', lineHeight: 1.45 }}>
                              {activeData.declaration}
                            </p>
                          </div>
                        )}
                        {activeData.warranty_note && (
                          <div>
                            <span className="field-label">Warranty Note</span>
                            <p style={{ margin: '0.2rem 0 0', fontSize: '0.78rem', color: '#475569', lineHeight: 1.45 }}>
                              {activeData.warranty_note}
                            </p>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}

                {/* SECTION 8: Authorised Signatory & Signature (Optional) */}
                <div className="extracted-section-card">
                  <div className="extracted-section-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3 className="extracted-section-title">
                      <IconPen />
                      <span>Authorised Signatory &amp; Signature</span>
                    </h3>
                    <span style={{ fontSize: '0.7rem', backgroundColor: '#f1f5f9', color: '#64748b', padding: '0.15rem 0.5rem', borderRadius: '4px', fontWeight: 600 }}>
                      Optional
                    </span>
                  </div>

                  {isEditing ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      <div className="field-cell">
                        <span className="field-label">Signatory Name / Label</span>
                        <input
                          type="text"
                          className="form-control"
                          style={{ fontSize: '0.8125rem', padding: '0.35rem 0.5rem' }}
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
                        />
                      </div>

                      <div className="field-cell">
                        <span className="field-label">Signature Image</span>
                        {(formData.signature_image || formData.signature?.image_data) ? (
                          <div style={{ border: '1px solid #cbd5e1', borderRadius: '8px', padding: '0.75rem', background: '#f8fafc', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                              <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '4px 8px', display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: '90px', minHeight: '45px' }}>
                                <img
                                  src={formData.signature_image || formData.signature?.image_data}
                                  alt="Authorised Signature"
                                  style={{ maxHeight: '45px', maxWidth: '140px', objectFit: 'contain' }}
                                />
                              </div>
                              <div>
                                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#0f172a' }}>Signature Attached</div>
                                <div style={{ fontSize: '0.72rem', color: '#64748b' }}>Will appear on the standardised invoice</div>
                              </div>
                            </div>
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
                          </div>
                        ) : (
                          <div
                            onClick={() => signatureInputRef.current?.click()}
                            style={{
                              border: '2px dashed #cbd5e1',
                              borderRadius: '8px',
                              padding: '1rem',
                              textAlign: 'center',
                              background: '#ffffff',
                              cursor: 'pointer',
                              transition: 'all 0.15s ease',
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--brand)'; e.currentTarget.style.background = '#fff5f5'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#cbd5e1'; e.currentTarget.style.background = '#ffffff'; }}
                          >
                            <div style={{ fontSize: '1.25rem', marginBottom: '0.2rem' }}>🖋️</div>
                            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--brand)' }}>Upload Signature</div>
                            <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '0.15rem' }}>
                              PNG, JPG, or JPEG up to 2MB (Optional)
                            </div>
                          </div>
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
                  ) : (
                    (activeData.signature_image || activeData.signature?.image_data) ? (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', padding: '0.25rem 0' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '4px 8px', display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: '90px', minHeight: '45px' }}>
                            <img
                              src={activeData.signature_image || activeData.signature?.image_data}
                              alt="Authorised Signature"
                              style={{ maxHeight: '45px', maxWidth: '140px', objectFit: 'contain' }}
                            />
                          </div>
                          <div>
                            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#0f172a' }}>
                              {activeData.signature?.signer_name || activeData.signer_name || `For ${activeData.seller?.name || 'Authorised Signatory'}`}
                            </div>
                            <div style={{ fontSize: '0.72rem', color: '#16a34a', fontWeight: 600 }}>✓ Attached to standardised invoice</div>
                          </div>
                        </div>
                        {!isApproved && (
                          <button
                            type="button"
                            className="btn btn-secondary"
                            style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}
                            onClick={() => setIsEditing(true)}
                          >
                            Edit
                          </button>
                        )}
                      </div>
                    ) : (
                      <div style={{ padding: '0.35rem 0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontStyle: 'italic' }}>
                          No signature attached (Optional)
                        </span>
                        {!isApproved && (
                          <button
                            type="button"
                            className="btn btn-secondary"
                            style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}
                            onClick={() => {
                              setIsEditing(true);
                              setTimeout(() => signatureInputRef.current?.click(), 80);
                            }}
                          >
                            + Add Signature
                          </button>
                        )}
                      </div>
                    )
                  )}
                </div>

                {/* Secondary Accordion Quick-Links in Extracted tab for seamless access */}
                <div className="accordion-card">
                  <div
                    className={`accordion-header ${showDetails ? 'open' : ''}`}
                    onClick={() => setShowDetails(!showDetails)}
                  >
                    <span className="accordion-title">
                      ℹ️ Technical Document Details &amp; Checksums
                    </span>
                    <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                      {showDetails ? '▲ Hide' : '▼ View Technical Details'}
                    </span>
                  </div>

                  {showDetails && (
                    <div className="accordion-body">
                      <dl className="info-list" style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: '0.5rem 1rem', margin: 0 }}>
                        <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem' }}>Original Filename</dt>
                        <dd style={{ margin: 0, fontSize: '0.8125rem', wordBreak: 'break-all' }}>{doc.original_filename}</dd>

                        <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem' }}>Uploaded By</dt>
                        <dd style={{ margin: 0, fontSize: '0.8125rem' }}>{doc.uploader_name || `User #${doc.uploaded_by}`}</dd>

                        <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem' }}>Upload Timestamp</dt>
                        <dd style={{ margin: 0, fontSize: '0.8125rem' }}>{formatDate(doc.created_at)}</dd>

                        <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem' }}>MIME Content Type</dt>
                        <dd style={{ margin: 0, fontSize: '0.8125rem' }}>{doc.mime_type}</dd>

                        <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem' }}>File Size</dt>
                        <dd style={{ margin: 0, fontSize: '0.8125rem' }}>{formatBytes(doc.file_size)}</dd>

                        {doc.page_count !== undefined && doc.page_count !== null && (
                          <>
                            <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem' }}>Page Count</dt>
                            <dd style={{ margin: 0, fontSize: '0.8125rem' }}>{doc.page_count}</dd>
                          </>
                        )}

                        {doc.sha256 && (
                          <>
                            <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem' }}>SHA-256 Hash</dt>
                            <dd style={{ margin: 0, fontSize: '0.8125rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                              <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}>
                                {doc.sha256}
                              </span>
                              <button
                                type="button"
                                className="btn btn-ghost"
                                style={{ padding: '0.1rem 0.35rem', fontSize: '0.72rem' }}
                                onClick={() => {
                                  navigator.clipboard.writeText(doc.sha256);
                                  setCopiedHash(true);
                                  setTimeout(() => setCopiedHash(false), 2000);
                                }}
                                title="Copy SHA-256 Checksum"
                              >
                                {copiedHash ? '✓ Copied' : '📋 Copy'}
                              </button>
                            </dd>
                          </>
                        )}

                        {doc.error_code && (
                          <>
                            <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem' }}>Error Code</dt>
                            <dd style={{ margin: 0, color: '#ef4444', fontWeight: 600, fontSize: '0.8125rem' }}>{doc.error_code}</dd>
                          </>
                        )}
                      </dl>
                    </div>
                  )}
                </div>

                <div className="accordion-card">
                  <div
                    className={`accordion-header ${showRawData ? 'open' : ''}`}
                    onClick={() => setShowRawData(!showRawData)}
                  >
                    <span className="accordion-title">
                      {'{ }'} Advanced: Raw OCR Data &amp; Field Audit Trail
                    </span>
                    <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
                      {showRawData ? '▲ Hide' : '▼ View Raw Data & History'}
                    </span>
                  </div>

                  {showRawData && (
                    <div className="accordion-body">
                      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '0.5rem' }}>
                        <button
                          type="button"
                          onClick={() => setRawTab('json')}
                          style={{
                            border: 'none',
                            background: rawTab === 'json' ? '#e2e8f0' : 'transparent',
                            padding: '0.25rem 0.6rem',
                            borderRadius: '4px',
                            fontSize: '0.78rem',
                            fontWeight: 600,
                            cursor: 'pointer',
                            color: rawTab === 'json' ? '#0f172a' : '#64748b',
                          }}
                        >
                          Structured JSON
                        </button>
                        <button
                          type="button"
                          onClick={() => setRawTab('text')}
                          style={{
                            border: 'none',
                            background: rawTab === 'text' ? '#e2e8f0' : 'transparent',
                            padding: '0.25rem 0.6rem',
                            borderRadius: '4px',
                            fontSize: '0.78rem',
                            fontWeight: 600,
                            cursor: 'pointer',
                            color: rawTab === 'text' ? '#0f172a' : '#64748b',
                          }}
                        >
                          Raw OCR Text ({doc.ocr_text ? doc.ocr_text.split(/\s+/).filter(Boolean).length : 0} words)
                        </button>
                        <button
                          type="button"
                          onClick={() => setRawTab('history')}
                          style={{
                            border: 'none',
                            background: rawTab === 'history' ? '#e2e8f0' : 'transparent',
                            padding: '0.25rem 0.6rem',
                            borderRadius: '4px',
                            fontSize: '0.78rem',
                            fontWeight: 600,
                            cursor: 'pointer',
                            color: rawTab === 'history' ? '#0f172a' : '#64748b',
                          }}
                        >
                          Edit Audit History ({extraction?.edits_count || editsHistory.length})
                        </button>
                      </div>

                      {rawTab === 'json' && (
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.4rem' }}>
                            <button
                              type="button"
                              className="btn btn-sm btn-secondary"
                              onClick={() => {
                                navigator.clipboard.writeText(JSON.stringify(extraction?.data || activeData, null, 2));
                                setCopiedJson(true);
                                setTimeout(() => setCopiedJson(false), 2000);
                              }}
                              style={{ fontSize: '0.72rem', padding: '0.15rem 0.45rem' }}
                            >
                              {copiedJson ? '✓ Copied' : '📋 Copy JSON'}
                            </button>
                          </div>
                          <pre
                            style={{
                              margin: 0,
                              maxHeight: '360px',
                              overflow: 'auto',
                              padding: '0.75rem',
                              backgroundColor: '#0f172a',
                              color: '#f8fafc',
                              borderRadius: '6px',
                              fontSize: '0.75rem',
                              fontFamily: 'monospace',
                              lineHeight: 1.45,
                            }}
                          >
                            {JSON.stringify(extraction?.data || activeData, null, 2)}
                          </pre>
                        </div>
                      )}

                      {rawTab === 'text' && (
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.4rem' }}>
                            <button
                              type="button"
                              className="btn btn-sm btn-secondary"
                              onClick={() => {
                                navigator.clipboard.writeText(doc.ocr_text || '');
                                setCopiedText(true);
                                setTimeout(() => setCopiedText(false), 2000);
                              }}
                              style={{ fontSize: '0.72rem', padding: '0.15rem 0.45rem' }}
                            >
                              {copiedText ? '✓ Copied' : '📋 Copy Text'}
                            </button>
                          </div>
                          <pre
                            style={{
                              margin: 0,
                              maxHeight: '360px',
                              overflow: 'auto',
                              padding: '0.75rem',
                              backgroundColor: '#f8fafc',
                              color: '#334155',
                              border: '1px solid #e2e8f0',
                              borderRadius: '6px',
                              fontSize: '0.75rem',
                              fontFamily: 'monospace',
                              lineHeight: 1.45,
                              whiteSpace: 'pre-wrap',
                            }}
                          >
                            {doc.ocr_text || 'No raw OCR text available.'}
                          </pre>
                        </div>
                      )}

                      {rawTab === 'history' && (
                        <div>
                          {loadingHistory ? (
                            <div style={{ fontSize: '0.8rem', color: '#64748b' }}>Loading field edit history…</div>
                          ) : editsHistory.length === 0 ? (
                            <div style={{ fontSize: '0.8rem', color: '#94a3b8', fontStyle: 'italic', padding: '1rem', textAlign: 'center' }}>
                              No human review adjustments recorded yet.
                            </div>
                          ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                              {editsHistory.map((edit) => (
                                <div key={edit.id} style={{ padding: '0.5rem 0.75rem', border: '1px solid #e2e8f0', borderRadius: '4px', background: '#f8fafc', fontSize: '0.78rem' }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                                    <span style={{ fontWeight: 700, color: '#0f172a' }}>{edit.field_path}</span>
                                    <span style={{ color: '#64748b' }}>{formatDate(edit.edited_at)}</span>
                                  </div>
                                  <div style={{ color: '#64748b', fontSize: '0.72rem', marginBottom: '0.2rem' }}>
                                    By: <strong>{edit.editor_name || `User #${edit.edited_by}`}</strong>
                                  </div>
                                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.72rem' }}>
                                    <div style={{ backgroundColor: '#fee2e2', padding: '0.25rem', borderRadius: '4px', color: '#991b1b' }}>
                                      <strong>Old:</strong> {JSON.stringify(edit.old_value)}
                                    </div>
                                    <div style={{ backgroundColor: '#dcfce7', padding: '0.25rem', borderRadius: '4px', color: '#166534' }}>
                                      <strong>New:</strong> {JSON.stringify(edit.new_value)}
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}

            {/* ── TAB 2: Dedicated Technical Document Information ── */}
            {inspectorTab === 'technical' && (
              <div className="extracted-section-card">
                <div className="extracted-section-header">
                  <h3 className="extracted-section-title">
                    <IconInfoCircle />
                    <span>Technical Document Details &amp; Checksums</span>
                  </h3>
                </div>
                <dl className="info-list" style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '0.75rem 1rem', margin: 0 }}>
                  <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>Original Filename</dt>
                  <dd style={{ margin: 0, fontSize: '0.84rem', fontWeight: 600, wordBreak: 'break-all' }}>{doc.original_filename}</dd>

                  <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>Uploaded By</dt>
                  <dd style={{ margin: 0, fontSize: '0.84rem' }}>{doc.uploader_name || `User #${doc.uploaded_by}`}</dd>

                  <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>Upload Timestamp</dt>
                  <dd style={{ margin: 0, fontSize: '0.84rem' }}>{formatDate(doc.created_at)}</dd>

                  <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>MIME Content Type</dt>
                  <dd style={{ margin: 0, fontSize: '0.84rem' }}>
                    <span style={{ backgroundColor: '#f1f5f9', padding: '0.15rem 0.45rem', borderRadius: '4px', border: '1px solid #e2e8f0', fontFamily: 'monospace', fontSize: '0.78rem' }}>
                      {doc.mime_type}
                    </span>
                  </dd>

                  <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>File Size</dt>
                  <dd style={{ margin: 0, fontSize: '0.84rem' }}>{formatBytes(doc.file_size)}</dd>

                  {doc.page_count !== undefined && doc.page_count !== null && (
                    <>
                      <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>Page Count</dt>
                      <dd style={{ margin: 0, fontSize: '0.84rem' }}>{doc.page_count}</dd>
                    </>
                  )}

                  {doc.sha256 && (
                    <>
                      <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>SHA-256 Hash</dt>
                      <dd style={{ margin: 0, fontSize: '0.84rem', display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <span style={{ fontFamily: 'monospace', fontSize: '0.78rem', wordBreak: 'break-all', backgroundColor: '#f8fafc', padding: '0.2rem 0.4rem', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
                          {doc.sha256}
                        </span>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          style={{ padding: '0.15rem 0.45rem', fontSize: '0.75rem', fontWeight: 600 }}
                          onClick={() => {
                            navigator.clipboard.writeText(doc.sha256);
                            setCopiedHash(true);
                            setTimeout(() => setCopiedHash(false), 2000);
                          }}
                          title="Copy SHA-256 Checksum"
                        >
                          {copiedHash ? '✓ Copied' : '📋 Copy'}
                        </button>
                      </dd>
                    </>
                  )}

                  <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>OCR Status</dt>
                  <dd style={{ margin: 0, fontSize: '0.84rem' }}>
                    <span className={`status-badge ${statusInfo.cls}`}>{statusInfo.label}</span>
                  </dd>

                  {doc.error_code && (
                    <>
                      <dt style={{ fontWeight: 600, color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase' }}>Error Code</dt>
                      <dd style={{ margin: 0, color: '#ef4444', fontWeight: 700, fontSize: '0.84rem' }}>{doc.error_code}</dd>
                    </>
                  )}
                </dl>
              </div>
            )}

            {/* ── TAB 3: Dedicated Raw OCR & Field Audit Trail ── */}
            {inspectorTab === 'raw' && (
              <div className="extracted-section-card">
                <div className="extracted-section-header">
                  <h3 className="extracted-section-title">
                    <IconCode2 />
                    <span>Raw OCR &amp; Field Audit Trail</span>
                  </h3>
                </div>

                <div className="doc-subtab-group">
                  <button
                    type="button"
                    className={`doc-subtab-btn ${rawTab === 'json' ? 'active' : ''}`}
                    onClick={() => setRawTab('json')}
                  >
                    Structured JSON
                  </button>
                  <button
                    type="button"
                    className={`doc-subtab-btn ${rawTab === 'text' ? 'active' : ''}`}
                    onClick={() => setRawTab('text')}
                  >
                    Raw OCR Text ({doc.ocr_text ? doc.ocr_text.split(/\s+/).filter(Boolean).length : 0} words)
                  </button>
                  <button
                    type="button"
                    className={`doc-subtab-btn ${rawTab === 'history' ? 'active' : ''}`}
                    onClick={() => setRawTab('history')}
                  >
                    Edit Audit History ({extraction?.edits_count || editsHistory.length})
                  </button>
                </div>

                {rawTab === 'json' && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.5rem' }}>
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => {
                          navigator.clipboard.writeText(JSON.stringify(extraction?.data || activeData, null, 2));
                          setCopiedJson(true);
                          setTimeout(() => setCopiedJson(false), 2000);
                        }}
                        style={{ fontSize: '0.75rem', padding: '0.2rem 0.55rem', fontWeight: 600 }}
                      >
                        {copiedJson ? '✓ Copied' : '📋 Copy JSON'}
                      </button>
                    </div>
                    <pre
                      style={{
                        margin: 0,
                        maxHeight: '480px',
                        overflow: 'auto',
                        padding: '0.875rem',
                        backgroundColor: '#0f172a',
                        color: '#f8fafc',
                        borderRadius: '6px',
                        fontSize: '0.78rem',
                        fontFamily: 'monospace',
                        lineHeight: 1.45,
                      }}
                    >
                      {JSON.stringify(extraction?.data || activeData, null, 2)}
                    </pre>
                  </div>
                )}

                {rawTab === 'text' && (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.5rem' }}>
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => {
                          navigator.clipboard.writeText(doc.ocr_text || '');
                          setCopiedText(true);
                          setTimeout(() => setCopiedText(false), 2000);
                        }}
                        style={{ fontSize: '0.75rem', padding: '0.2rem 0.55rem', fontWeight: 600 }}
                      >
                        {copiedText ? '✓ Copied' : '📋 Copy Text'}
                      </button>
                    </div>
                    <pre
                      style={{
                        margin: 0,
                        maxHeight: '480px',
                        overflow: 'auto',
                        padding: '0.875rem',
                        backgroundColor: '#f8fafc',
                        color: '#334155',
                        border: '1px solid #e2e8f0',
                        borderRadius: '6px',
                        fontSize: '0.78rem',
                        fontFamily: 'monospace',
                        lineHeight: 1.45,
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {doc.ocr_text || 'No raw OCR text available.'}
                    </pre>
                  </div>
                )}

                {rawTab === 'history' && (
                  <div>
                    {loadingHistory ? (
                      <div style={{ fontSize: '0.84rem', color: '#64748b' }}>Loading field edit history…</div>
                    ) : editsHistory.length === 0 ? (
                      <div style={{ fontSize: '0.84rem', color: '#94a3b8', fontStyle: 'italic', padding: '1.5rem', textAlign: 'center' }}>
                        No human review adjustments recorded yet.
                      </div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
                        {editsHistory.map((edit) => (
                          <div key={edit.id} style={{ padding: '0.625rem 0.875rem', border: '1px solid #e2e8f0', borderRadius: '6px', background: '#f8fafc', fontSize: '0.8125rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                              <span style={{ fontWeight: 700, color: '#0f172a' }}>{edit.field_path}</span>
                              <span style={{ color: '#64748b', fontSize: '0.75rem' }}>{formatDate(edit.edited_at)}</span>
                            </div>
                            <div style={{ color: '#64748b', fontSize: '0.75rem', marginBottom: '0.35rem' }}>
                              By: <strong>{edit.editor_name || `User #${edit.edited_by}`}</strong>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.75rem' }}>
                              <div style={{ backgroundColor: '#fee2e2', padding: '0.35rem 0.5rem', borderRadius: '4px', color: '#991b1b' }}>
                                <strong>Old:</strong> {JSON.stringify(edit.old_value)}
                              </div>
                              <div style={{ backgroundColor: '#dcfce7', padding: '0.35rem 0.5rem', borderRadius: '4px', color: '#166534' }}>
                                <strong>New:</strong> {JSON.stringify(edit.new_value)}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── MODAL: Fullscreen Image Preview ── */}
      {isFullScreen && (
        <div className="fullscreen-overlay">
          <div className="fullscreen-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>
                {displayTitle} — Original Document View
              </span>
              <span style={{ fontSize: '0.75rem', opacity: 0.8 }}>
                {Math.round(zoom * 100)}% {rotation > 0 ? `• Rotated ${rotation}°` : ''}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={handleZoomOut}
                disabled={zoom <= 0.5}
                style={{ color: '#ffffff', borderColor: 'rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.1)' }}
              >
                −
              </button>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={handleZoomIn}
                disabled={zoom >= 3.5}
                style={{ color: '#ffffff', borderColor: 'rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.1)' }}
              >
                +
              </button>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={handleRotate}
                style={{ color: '#ffffff', borderColor: 'rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.1)' }}
              >
                ↻ Rotate
              </button>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={handleZoomReset}
                style={{ color: '#ffffff', borderColor: 'rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.1)' }}
              >
                Reset
              </button>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={() => setIsFullScreen(false)}
                style={{ marginLeft: '0.5rem' }}
              >
                ✕ Close
              </button>
            </div>
          </div>

          <div
            ref={fullScreenImageRef}
            onMouseDown={(e) => handleMouseDown(e, fullScreenImageRef)}
            onMouseMove={(e) => handleMouseMove(e, fullScreenImageRef)}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            className="fullscreen-body"
            style={{
              cursor: zoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default',
              userSelect: isDragging ? 'none' : 'auto',
            }}
          >
            {isPdf ? (
              <iframe
                src={`${fileUrl}#toolbar=0`}
                title={doc.original_filename}
                style={{ width: '90%', height: '90%', border: 'none', backgroundColor: '#ffffff', borderRadius: '8px' }}
              />
            ) : (
              <div
                style={{
                  transform: `scale(${zoom}) rotate(${rotation}deg)`,
                  transformOrigin: 'center center',
                  transition: isDragging ? 'none' : 'transform 0.12s ease-out',
                }}
              >
                <img
                  src={fileUrl}
                  alt={doc.original_filename}
                  draggable={false}
                  style={{
                    maxHeight: '85vh',
                    maxWidth: '85vw',
                    objectFit: 'contain',
                    borderRadius: '8px',
                    boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
                  }}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── MODAL: Override Validation Errors & Approve ── */}
      {showOverrideModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            backdropFilter: 'blur(2px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10000,
            padding: '1rem',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: '12px',
              maxWidth: '520px',
              width: '100%',
              padding: '1.5rem',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
            }}
          >
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, margin: '0 0 0.5rem 0', color: '#b91c1c' }}>
              ⚠️ Override Validation Errors &amp; Approve
            </h3>
            <p style={{ fontSize: '0.84rem', color: '#64748b', margin: '0 0 1rem 0', lineHeight: 1.45 }}>
              This document contains active validation errors (e.g. calculation mismatch). To approve and finalize extraction anyway, please provide an authoritative audit justification.
            </p>

            <textarea
              rows={3}
              required
              placeholder="e.g. Vendor arithmetic confirmed against signed physical purchase order..."
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              className="form-control"
              style={{
                width: '100%',
                padding: '0.5rem',
                fontSize: '0.84rem',
                marginBottom: '1rem',
              }}
            />

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowOverrideModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={overrideReason.trim().length < 5 || approving}
                onClick={() => handleApprove(true)}
                style={{ backgroundColor: '#dc2626', borderColor: '#dc2626' }}
              >
                {approving ? 'Overriding…' : 'Confirm Override & Approve'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={showDeleteConfirm}
        title="Delete Document"
        message={`Are you sure you want to delete "${doc?.original_filename || 'this document'}"?`}
        details={<span style={{ color: '#dc2626' }}>This document will be soft-deleted and moved to trash.</span>}
        confirmText="Delete Document"
        variant="danger"
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  );
}