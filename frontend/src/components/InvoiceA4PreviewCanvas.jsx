import React, { useState, useEffect, useRef } from 'react';
import DraggableSignature from './DraggableSignature';
import { api } from '../api';

const A4_WIDTH_MM = 210.0;
const A4_HEIGHT_MM = 297.0;

export default function InvoiceA4PreviewCanvas({
  invoiceId,
  signatures = [],
  selectedSigIndex,
  onSelectSig,
  onUpdateSig,
  onDeleteSig,
  onAddSignatureFile,
  readOnly = false,
  uploading = false,
}) {
  const containerRef = useRef(null);
  const fileInputRef = useRef(null);

  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [pageImageUrl, setPageImageUrl] = useState(null);
  const [loadingPage, setLoadingPage] = useState(false);
  const [pageError, setPageError] = useState(null);

  const [canvasDimensions, setCanvasDimensions] = useState({ width: 794, height: 1123 });

  // Update canvas pixel dimensions on resize
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const width = entry.contentRect.width;
        if (width > 0) {
          const height = (width * A4_HEIGHT_MM) / A4_WIDTH_MM;
          setCanvasDimensions({ width, height });
        }
      }
    });

    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Fetch page preview whenever invoiceId or currentPage changes
  useEffect(() => {
    if (!invoiceId) {
      setPageImageUrl(null);
      setTotalPages(1);
      return;
    }

    let isMounted = true;
    setLoadingPage(true);
    setPageError(null);

    api.fetchDraftPreviewPageBlob(invoiceId, currentPage)
      .then(({ objectUrl, totalPages: tPages, currentPage: cPage }) => {
        if (!isMounted) return;
        setPageImageUrl(objectUrl);
        setTotalPages(tPages || 1);
        setCurrentPage(cPage || 1);
        setLoadingPage(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        console.error('Failed to load draft preview page:', err);
        setPageError(err.message || 'Failed to render draft page preview');
        setLoadingPage(false);
      });

    return () => {
      isMounted = false;
    };
  }, [invoiceId, currentPage]);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      onAddSignatureFile(file, currentPage);
      e.target.value = '';
    }
  };

  const selectedSig = selectedSigIndex !== null ? signatures[selectedSigIndex] : null;

  // Filter signatures visible on this page:
  // Either sig.page_number matches currentPage (and not pinned),
  // OR sig.is_pinned_to_last_page is true and currentPage === totalPages.
  const visibleSignatures = signatures.map((sig, index) => ({ sig, index })).filter(({ sig }) => {
    if (sig.is_pinned_to_last_page) {
      return currentPage === totalPages;
    }
    return sig.page_number === currentPage;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', width: '100%' }}>
      {/* Canvas Toolbar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.75rem',
          padding: '0.75rem 1rem',
          background: '#f8fafc',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
        }}
      >
        {/* Pagination controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1 || loadingPage}
            title="Previous page"
          >
            ‹ Prev
          </button>
          <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
            Page {currentPage} of {totalPages}
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages || loadingPage}
            title="Next page"
          >
            Next ›
          </button>
          {loadingPage && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>
              Rendering PDF preview…
            </span>
          )}
        </div>

        {/* Action: Upload Signature */}
        {!readOnly && (
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".png,.jpg,.jpeg,image/png,image/jpeg"
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
            >
              <span>🖋️</span>
              <span>{uploading ? 'Processing Image…' : '+ Add Signature'}</span>
            </button>
          </div>
        )}
      </div>

      {pageError && (
        <div className="alert alert-error" style={{ margin: 0 }}>
          {pageError}
        </div>
      )}

      {!invoiceId && (
        <div
          className="alert alert-info"
          style={{
            margin: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>💡 Save invoice as a draft to see the live server-rendered PDF page preview. You can still upload and arrange signatures!</span>
        </div>
      )}

      {/* A4 Canvas Outer Container */}
      <div
        style={{
          width: '100%',
          maxWidth: '820px',
          margin: '0 auto',
          background: '#cbd5e1',
          padding: '1.5rem',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'inset 0 2px 6px rgba(0,0,0,0.08)',
          display: 'flex',
          justifyContent: 'center',
        }}
      >
        {/* A4 Sheet Container */}
        <div
          ref={containerRef}
          onClick={() => onSelectSig(null)}
          style={{
            position: 'relative',
            width: '100%',
            maxWidth: '750px',
            height: `${canvasDimensions.height}px`,
            backgroundColor: '#ffffff',
            boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
            borderRadius: '2px',
            overflow: 'hidden',
          }}
        >
          {/* Background: Server-rendered PDF page image */}
          {pageImageUrl ? (
            <img
              src={pageImageUrl}
              alt={`Invoice Page ${currentPage}`}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                pointerEvents: 'none',
              }}
              draggable={false}
            />
          ) : (
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted)',
                backgroundColor: '#ffffff',
              }}
            >
              <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>📄</div>
              <p style={{ fontWeight: 600, margin: 0 }}>A4 Page {currentPage}</p>
              <p style={{ fontSize: '0.8125rem', color: '#94a3b8', marginTop: '0.25rem' }}>
                {invoiceId ? 'Rendering draft layout…' : 'Save draft to render live preview'}
              </p>
            </div>
          )}

          {/* Informational Printable Margin Guideline (5mm border) */}
          <div
            style={{
              position: 'absolute',
              top: `${(5.0 / A4_HEIGHT_MM) * 100}%`,
              left: `${(5.0 / A4_WIDTH_MM) * 100}%`,
              right: `${(5.0 / A4_WIDTH_MM) * 100}%`,
              bottom: `${(5.0 / A4_HEIGHT_MM) * 100}%`,
              border: '1px dashed rgba(148, 163, 184, 0.4)',
              pointerEvents: 'none',
            }}
            title="Informational 5mm Printable Margin"
          />

          {/* Signatures Layer */}
          {visibleSignatures.map(({ sig, index }) => (
            <DraggableSignature
              key={sig.id ? `sig-${sig.id}` : `tmp-${sig.upload_token || index}`}
              signature={sig}
              isSelected={selectedSigIndex === index}
              onSelect={() => onSelectSig(index)}
              onChange={(updated) => onUpdateSig(index, updated)}
              onDelete={() => onDeleteSig(index)}
              canvasWidthPx={canvasDimensions.width}
              canvasHeightPx={canvasDimensions.height}
              readOnly={readOnly}
            />
          ))}
        </div>
      </div>

      {/* Selected Signature Inspector Panel */}
      {selectedSig && !readOnly && (
        <div
          className="table-container"
          style={{
            padding: '1rem',
            background: '#ffffff',
            border: '1px solid var(--border)',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              Selected Signature #{selectedSigIndex + 1}
            </span>

            {/* Page Selector */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                Page:
              </label>
              <input
                type="number"
                min={1}
                max={totalPages}
                value={selectedSig.page_number}
                disabled={selectedSig.is_pinned_to_last_page}
                onChange={(e) => {
                  const p = parseInt(e.target.value, 10) || 1;
                  onUpdateSig(selectedSigIndex, { page_number: Math.max(1, p) });
                }}
                style={{ width: '60px', padding: '0.25rem 0.5rem', fontSize: '0.875rem', borderRadius: '4px', border: '1px solid var(--border)' }}
              />
            </div>

            {/* Pin to last page toggle */}
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8125rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={selectedSig.is_pinned_to_last_page || false}
                onChange={(e) => onUpdateSig(selectedSigIndex, { is_pinned_to_last_page: e.target.checked })}
              />
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Always Pin to Last Page</span>
            </label>

            {/* Coordinates Display */}
            <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              <span>X: <strong>{selectedSig.x_mm} mm</strong></span>
              <span>Y: <strong>{selectedSig.y_mm} mm</strong></span>
              <span>W: <strong>{selectedSig.width_mm} mm</strong></span>
              <span>H: <strong>{selectedSig.height_mm} mm</strong></span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => onSelectSig(null)}
            >
              Deselect
            </button>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              onClick={() => onDeleteSig(selectedSigIndex)}
            >
              Delete
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
