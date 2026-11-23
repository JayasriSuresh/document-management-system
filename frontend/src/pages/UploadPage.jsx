import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

const ALLOWED_EXT = ['.jpg', '.jpeg', '.png', '.pdf'];
const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB
const MAX_BATCH_FILES = 10;

export const INVOICE_TYPES = [
  'Tax Invoice',
  'Invoice',
  'Bill of Supply',
  'Cash Memo',
  'Retail Invoice',
  'Export Invoice',
  'Proforma Invoice',
  'Credit Note',
  'Debit Note',
  'Receipt Voucher',
  'Payment Voucher',
  'Refund Voucher',
  'Revised Invoice',
  'Delivery Challan',
  'Other',
];

// SVG Icons
const IconUploadCloud = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
    <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
  </svg>
);
const IconCamera = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
    <circle cx="12" cy="13" r="4"/>
  </svg>
);
const IconCheck = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);
const IconAlert = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
  </svg>
);
const IconFilePdf = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
  </svg>
);
const IconFileImg = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
  </svg>
);
const IconTrash = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/>
  </svg>
);

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadPage() {
  const navigate = useNavigate();
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [invoiceType, setInvoiceType] = useState('');
  const [validationError, setValidationError] = useState('');
  const [hasAttemptedUpload, setHasAttemptedUpload] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [globalError, setGlobalError] = useState('');
  const [batchResults, setBatchResults] = useState(null);
  const [duplicateWarning, setDuplicateWarning] = useState(null);
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);

  const handleFilesSelect = (fileList) => {
    setGlobalError('');
    setValidationError('');
    setDuplicateWarning(null);
    setShowDuplicateModal(false);
    if (!fileList || fileList.length === 0) return;

    const incoming = Array.from(fileList);
    const combined = [...selectedFiles];

    for (const f of incoming) {
      if (combined.length >= MAX_BATCH_FILES) {
        setGlobalError(`Maximum batch upload limit is ${MAX_BATCH_FILES} files.`);
        break;
      }
      const ext = '.' + f.name.split('.').pop().toLowerCase();
      if (!ALLOWED_EXT.includes(ext)) {
        setGlobalError(`File "${f.name}" has an unsupported format. Allowed: JPG, PNG, PDF.`);
        continue;
      }
      if (f.size > MAX_FILE_SIZE) {
        setGlobalError(`File "${f.name}" exceeds the 20 MB size limit.`);
        continue;
      }
      // Avoid duplicate selections in same form
      if (!combined.some(item => item.name === f.name && item.size === f.size)) {
        combined.push(f);
      }
    }

    setSelectedFiles(combined);
  };

  const removeFile = (index) => {
    const updated = selectedFiles.filter((_, i) => i !== index);
    setSelectedFiles(updated);
    if (updated.length === 0) {
      setDuplicateWarning(null);
      setShowDuplicateModal(false);
      setInvoiceType('');
      setValidationError('');
      setHasAttemptedUpload(false);
    }
  };

  const resetAll = () => {
    setSelectedFiles([]);
    setGlobalError('');
    setDuplicateWarning(null);
    setShowDuplicateModal(false);
    setBatchResults(null);
    setUploading(false);
    setInvoiceType('');
    setValidationError('');
    setHasAttemptedUpload(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (cameraInputRef.current) cameraInputRef.current.value = '';
  };

  const handleCancelDuplicate = () => {
    setShowDuplicateModal(false);
    setDuplicateWarning(null);
    setSelectedFiles([]);
    setGlobalError('');
    setValidationError('');
    setHasAttemptedUpload(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (cameraInputRef.current) cameraInputRef.current.value = '';
  };

  const handleUpload = async (allowDuplicate = false) => {
    const shouldAllowDuplicate = allowDuplicate === true;
    if (selectedFiles.length === 0) return;

    // Enforce compulsory invoice type selection
    const effectiveInvoiceType = (invoiceType || '').trim();
    if (!effectiveInvoiceType) {
      setHasAttemptedUpload(true);
      setValidationError('Invoice type is compulsory. Please select an invoice type before uploading.');
      return;
    }
    setValidationError('');
    setHasAttemptedUpload(false);

    setUploading(true);
    setGlobalError('');
    if (!shouldAllowDuplicate) {
      setDuplicateWarning(null);
    }
    setShowDuplicateModal(false);
    setBatchResults(null);

    try {
      if (selectedFiles.length === 1) {
        // Single file upload mode
        const doc = await api.uploadDocument(selectedFiles[0], shouldAllowDuplicate, effectiveInvoiceType);
        setBatchResults({
          total: 1,
          successful: 1,
          failed: 0,
          results: [{
            filename: selectedFiles[0].name,
            status: 'success',
            document: doc,
          }],
        });
        setDuplicateWarning(null);
      } else {
        // Multi-file batch upload mode
        const res = await api.uploadDocuments(selectedFiles, shouldAllowDuplicate, effectiveInvoiceType);
        setBatchResults(res);
        setDuplicateWarning(null);
      }
    } catch (err) {
      if (err.status === 409) {
        const errorMsg = err.message || 'Duplicate document: exact identical file already exists.';
        let docId = null;
        let filename = null;

        // Try extracting doc ID from response headers
        if (err.headers && typeof err.headers.get === 'function') {
          const headerId = err.headers.get('X-Duplicate-Document-Id');
          if (headerId) docId = headerId;
        }

        // Try parsing regex from error detail: "Document #492 '17905982699145377177312188690039 (1).jpg'"
        const idMatch = errorMsg.match(/Document #(\d+)/i);
        if (idMatch && !docId) {
          docId = idMatch[1];
        }
        const fileMatch = errorMsg.match(/'([^']+)'/);
        if (fileMatch) {
          filename = fileMatch[1];
        }

        const info = {
          docId,
          filename,
          message: errorMsg,
          attemptedFile: selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files`,
        };
        setDuplicateWarning(info);
        setShowDuplicateModal(true);
      } else if (err.status === 413) {
        setGlobalError(err.message || 'Storage quota exceeded for your company.');
      } else {
        setGlobalError(err.message || 'Upload failed. Please check your files and try again.');
      }
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer?.files) {
      handleFilesSelect(e.dataTransfer.files);
    }
  };

  const handleDragOver = (e) => e.preventDefault();

  return (
    <div className="page-content">
      <div className="page-header">
        <div>
          <h2 className="page-title">Upload Documents</h2>
          <p className="page-subtitle">
            Supported formats: PDF, JPEG, PNG &middot; Max 20 MB per file &middot; Up to 10 files per batch
          </p>
        </div>
        <button className="btn btn-secondary" onClick={() => navigate('/')}>Back</button>
      </div>

      {batchResults ? (
        <div className="upload-results-card" style={{ background: '#fff', borderRadius: 8, padding: 24, border: '1px solid var(--border-color, #e2e8f0)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <div style={{
              width: 42, height: 42, borderRadius: '50%',
              background: batchResults.failed === 0 ? '#ecfdf5' : '#fef2f2',
              color: batchResults.failed === 0 ? '#10b981' : '#ef233c',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              {batchResults.failed === 0 ? <IconCheck /> : <IconAlert />}
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>
                {batchResults.failed === 0 ? 'Batch Upload Completed' : 'Batch Upload Completed with Warnings'}
              </h3>
              <p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>
                {batchResults.successful} of {batchResults.total} documents uploaded and queued for processing.
              </p>
            </div>
          </div>

          <div className="result-items-list" style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {batchResults.results.map((item, idx) => (
              <div key={idx} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 16px', borderRadius: 6,
                background: item.status === 'success' ? '#f8fafc' : '#fef2f2',
                border: `1px solid ${item.status === 'success' ? '#e2e8f0' : '#fecaca'}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ color: item.status === 'success' ? '#10b981' : '#ef4444' }}>
                    {item.status === 'success' ? '✓' : '✕'}
                  </span>
                  <span style={{ fontWeight: 500, fontSize: 14 }}>{item.filename}</span>
                </div>

                <div>
                  {item.status === 'success' ? (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => navigate(`/documents/${item.document.id}`)}
                    >
                      View Document #{item.document.id}
                    </button>
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ color: '#ef4444', fontSize: 13 }}>
                        {item.error || item.error_code || 'Upload failed'}
                      </span>
                      {item.duplicate_document_id && (
                        <a
                          href={`/documents/${item.duplicate_document_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn btn-secondary btn-sm"
                          style={{
                            textDecoration: 'none',
                            padding: '3px 8px',
                            fontSize: 12,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 4,
                          }}
                        >
                          <span>Open Document #{item.duplicate_document_id}</span>
                          <span>↗</span>
                        </a>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
            <button className="btn btn-primary" onClick={() => navigate('/')}>
              Go to Document List
            </button>
            <button className="btn btn-secondary" onClick={resetAll}>
              Upload More Files
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="upload-grid">
            {/* File drop zone */}
            <div
              className={`drop-zone ${selectedFiles.length > 0 ? 'drop-zone-active' : ''}`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onClick={() => fileInputRef.current?.click()}
              style={{ cursor: 'pointer' }}
            >
              <div className="drop-zone-icon"><IconUploadCloud /></div>
              <p className="drop-main">Drop documents here</p>
              <p className="drop-sub">or click to browse multiple files from your device</p>
              <span className="drop-types">PDF &middot; JPG &middot; PNG (Up to 10 files)</span>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".jpg,.jpeg,.png,.pdf"
                style={{ display: 'none' }}
                onChange={e => handleFilesSelect(e.target.files)}
              />
            </div>

            {/* Camera capture */}
            <div className="camera-zone" onClick={() => cameraInputRef.current?.click()}>
              <div className="camera-zone-icon"><IconCamera /></div>
              <p className="camera-main">Take a Photo</p>
              <p className="camera-sub">Use mobile camera or webcam to capture an invoice</p>
              <input
                ref={cameraInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                style={{ display: 'none' }}
                onChange={e => handleFilesSelect(e.target.files)}
              />
            </div>
          </div>

          {/* Selected files queue */}
          {selectedFiles.length > 0 && (
            <div className="selected-files-card" style={{ marginTop: 20, background: '#fff', borderRadius: 8, padding: 16, border: '1px solid #e2e8f0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontWeight: 600, fontSize: 14 }}>
                  Selected Files ({selectedFiles.length} of {MAX_BATCH_FILES})
                </span>
                <span style={{ fontSize: 12, color: '#64748b' }}>
                  Total Size: {formatBytes(selectedFiles.reduce((acc, f) => acc + f.size, 0))}
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {selectedFiles.map((file, idx) => {
                  const isPdf = file.name.toLowerCase().endsWith('.pdf');
                  return (
                    <div key={idx} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '8px 12px', borderRadius: 6, background: '#f8fafc', border: '1px solid #edf2f7',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ color: '#64748b' }}>{isPdf ? <IconFilePdf /> : <IconFileImg />}</span>
                        <span style={{ fontSize: 14, fontWeight: 500 }}>{file.name}</span>
                        <span style={{ fontSize: 12, color: '#94a3b8' }}>({formatBytes(file.size)})</span>
                        {invoiceType ? (
                          <span style={{ fontSize: 11, fontWeight: 600, color: '#b91c1c', background: '#fef2f2', border: '1px solid #fecaca', padding: '2px 8px', borderRadius: 4 }}>
                            {invoiceType}
                          </span>
                        ) : (
                          <span style={{ fontSize: 11, fontWeight: 600, color: '#dc2626', background: '#fff1f2', border: '1px dashed #fca5a5', padding: '2px 8px', borderRadius: 4 }}>
                            * Type Required
                          </span>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); removeFile(idx); }}
                        style={{ border: 'none', background: 'transparent', color: '#94a3b8', cursor: 'pointer', padding: 4 }}
                        title="Remove file"
                      >
                        <IconTrash />
                      </button>
                    </div>
                  );
                })}
              </div>

              {/* Compulsory Invoice Type Selection */}
              <div
                style={{
                  marginTop: 14,
                  padding: '12px 16px',
                  background: (!invoiceType && hasAttemptedUpload) ? '#fff1f2' : '#f8fafc',
                  borderRadius: 6,
                  border: (!invoiceType && hasAttemptedUpload) ? '1.5px solid #fda4af' : '1px solid #e2e8f0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 16,
                  flexWrap: 'wrap',
                }}
              >
                <div>
                  <label
                    htmlFor="invoice-type-compulsory"
                    style={{
                      display: 'block',
                      fontSize: 13,
                      fontWeight: 700,
                      color: (!invoiceType && hasAttemptedUpload) ? '#be123c' : '#1e293b',
                      marginBottom: 2,
                    }}
                  >
                    Invoice Type <span style={{ color: '#ef233c', fontWeight: 800 }}>* (Compulsory)</span>
                  </label>
                  <span style={{ fontSize: 12, color: (!invoiceType && hasAttemptedUpload) ? '#e11d48' : '#64748b' }}>
                    Select the legal document or invoice type before uploading
                  </span>
                </div>
                <div style={{ minWidth: 240, flex: '0 1 300px' }}>
                  <select
                    id="invoice-type-compulsory"
                    value={invoiceType}
                    onChange={(e) => {
                      setInvoiceType(e.target.value);
                      if (e.target.value) setValidationError('');
                    }}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: 13,
                      fontWeight: 600,
                      color: invoiceType ? '#0f172a' : '#64748b',
                      background: '#ffffff',
                      border: (!invoiceType && hasAttemptedUpload) ? '2px solid #ef233c' : '1.5px solid #cbd5e1',
                      borderRadius: 6,
                      outline: 'none',
                      cursor: 'pointer',
                    }}
                  >
                    <option value="">-- Choose Invoice Type (Required) * --</option>
                    {INVOICE_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {validationError && (
                <div
                  style={{
                    marginTop: 10,
                    padding: '8px 12px',
                    borderRadius: 6,
                    background: '#fef2f2',
                    border: '1px solid #fecaca',
                    color: '#b91c1c',
                    fontSize: 12,
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <span>⚠️</span>
                  <span>{validationError}</span>
                </div>
              )}

              <div className="upload-actions" style={{ marginTop: 16, display: 'flex', gap: 12 }}>
                <button
                  className="btn btn-primary btn-lg"
                  onClick={() => handleUpload(false)}
                  disabled={uploading}
                >
                  {uploading
                    ? <><span className="spinner-sm" /> Processing &amp; Enqueueing&hellip;</>
                    : `Upload ${selectedFiles.length} File${selectedFiles.length !== 1 ? 's' : ''} & Start OCR`
                  }
                </button>
                <button className="btn btn-ghost" onClick={resetAll} disabled={uploading}>
                  Clear All
                </button>
              </div>
            </div>
          )}

          {globalError && (
            <div className="alert alert-error" style={{ marginTop: 16 }}>
              {globalError}
            </div>
          )}
        </>
      )}

      {/* Duplicate Confirmation Pop-up Modal */}
      {showDuplicateModal && duplicateWarning && (
        <div
          className="modal-overlay"
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(3px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: 20,
          }}
          onClick={handleCancelDuplicate}
        >
          <div
            className="modal-container"
            style={{
              background: '#ffffff',
              borderRadius: 12,
              maxWidth: 520,
              width: '100%',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.15), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
              overflow: 'hidden',
              border: '1px solid #fecaca',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: '20px 24px',
                background: '#fff5f5',
                borderBottom: '1px solid #fee2e2',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: '50%',
                    background: '#ffffff',
                    border: '2px solid #ef233c',
                    color: '#ef233c',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <IconAlert />
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: '#991b1b' }}>
                    Duplicate Document Detected
                  </h3>
                  <p style={{ margin: '2px 0 0 0', fontSize: 13, color: '#b91c1c' }}>
                    Confirmation required before proceeding
                  </p>
                </div>
              </div>
              <button
                onClick={handleCancelDuplicate}
                style={{
                  background: 'transparent',
                  border: 'none',
                  fontSize: 22,
                  lineHeight: 1,
                  color: '#991b1b',
                  cursor: 'pointer',
                  padding: 4,
                }}
                aria-label="Close"
              >
                &times;
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ padding: '24px 24px 20px 24px', background: '#ffffff' }}>
              <p style={{ margin: '0 0 16px 0', fontSize: 14, color: '#334155', lineHeight: 1.5 }}>
                An identical file with matching checksum fingerprint already exists in your company records.
              </p>

              {/* Existing file info card */}
              <div
                style={{
                  background: '#fef2f2',
                  border: '1px solid #fee2e2',
                  borderRadius: 8,
                  padding: '14px 16px',
                  marginBottom: 16,
                }}
              >
                <div style={{ fontSize: 11, fontWeight: 700, color: '#991b1b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                  Existing Document Reference
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 14 }}>
                  {duplicateWarning.docId && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#475569' }}>Document ID:</span>
                      <span style={{ fontWeight: 600, color: '#0f172a' }}>#{duplicateWarning.docId}</span>
                    </div>
                  )}
                  {duplicateWarning.filename && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#475569' }}>File Name:</span>
                      <span
                        style={{
                          fontWeight: 500,
                          color: '#0f172a',
                          maxWidth: 260,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={duplicateWarning.filename}
                      >
                        {duplicateWarning.filename}
                      </span>
                    </div>
                  )}
                  {duplicateWarning.docId && (
                    <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px dashed #fca5a5' }}>
                      <a
                        href={`/documents/${duplicateWarning.docId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          color: '#ef233c',
                          fontWeight: 600,
                          fontSize: 13,
                          textDecoration: 'none',
                        }}
                        onMouseOver={(e) => (e.currentTarget.style.textDecoration = 'underline')}
                        onMouseOut={(e) => (e.currentTarget.style.textDecoration = 'none')}
                      >
                        <span>Open &amp; Inspect Document #{duplicateWarning.docId} in New Tab</span>
                        <span style={{ fontSize: 14 }}>↗</span>
                      </a>
                    </div>
                  )}
                </div>
              </div>

              <p style={{ margin: 0, fontSize: 13, color: '#64748b', lineHeight: 1.5 }}>
                If this is a revision, duplicate invoice, or separate transaction requiring new OCR extraction, you can proceed to upload anyway.
              </p>
            </div>

            {/* Modal Actions */}
            <div
              style={{
                padding: '16px 24px',
                background: '#ffffff',
                borderTop: '1px solid #f1f5f9',
                display: 'flex',
                justifyContent: 'flex-end',
                gap: 12,
              }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleCancelDuplicate}
                disabled={uploading}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                style={{
                  background: '#ef233c',
                  borderColor: '#dc2626',
                  color: '#ffffff',
                  fontWeight: 600,
                }}
                onClick={() => handleUpload(true)}
                disabled={uploading}
              >
                {uploading ? (
                  <><span className="spinner-sm" /> Processing &amp; Enqueueing&hellip;</>
                ) : (
                  'Upload Anyway & Start OCR'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
