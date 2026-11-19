import React, { useState, useEffect, useRef } from 'react';

const A4_WIDTH_MM = 210.0;
const A4_HEIGHT_MM = 297.0;
const MIN_WIDTH_MM = 10.0;
const MIN_HEIGHT_MM = 5.0;

/**
 * Draggable, 4-corner resizable signature element with aspect ratio locking,
 * boundary clamping, and keyboard accessibility.
 */
export default function DraggableSignature({
  signature,
  isSelected,
  onSelect,
  onChange,
  onDelete,
  canvasWidthPx,
  canvasHeightPx,
  readOnly = false,
}) {
  const containerRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [resizeHandle, setResizeHandle] = useState(null);
  const [dragStart, setDragStart] = useState({ mouseX: 0, mouseY: 0, xMm: 0, yMm: 0 });
  const [resizeStart, setResizeStart] = useState({
    mouseX: 0,
    mouseY: 0,
    xMm: 0,
    yMm: 0,
    widthMm: 0,
    heightMm: 0,
    aspectRatio: 1,
  });

  // Millimeters to pixels scale factor
  const scaleX = canvasWidthPx / A4_WIDTH_MM;
  const scaleY = canvasHeightPx / A4_HEIGHT_MM;

  const xPx = signature.x_mm * scaleX;
  const yPx = signature.y_mm * scaleY;
  const widthPx = signature.width_mm * scaleX;
  const heightPx = signature.height_mm * scaleY;

  // Clamping helper in millimeters
  const clampMm = (x, y, w, h) => {
    const clampedW = Math.max(MIN_WIDTH_MM, Math.min(w, A4_WIDTH_MM));
    const clampedH = Math.max(MIN_HEIGHT_MM, Math.min(h, A4_HEIGHT_MM));
    const clampedX = Math.max(0, Math.min(x, A4_WIDTH_MM - clampedW));
    const clampedY = Math.max(0, Math.min(y, A4_HEIGHT_MM - clampedH));
    return {
      x_mm: Number(clampedX.toFixed(2)),
      y_mm: Number(clampedY.toFixed(2)),
      width_mm: Number(clampedW.toFixed(2)),
      height_mm: Number(clampedH.toFixed(2)),
    };
  };

  // Keyboard accessibility
  useEffect(() => {
    if (!isSelected || readOnly) return;

    const handleKeyDown = (e) => {
      const step = e.shiftKey ? 5.0 : 1.0;
      let dx = 0;
      let dy = 0;

      if (e.key === 'ArrowLeft') dx = -step;
      else if (e.key === 'ArrowRight') dx = step;
      else if (e.key === 'ArrowUp') dy = -step;
      else if (e.key === 'ArrowDown') dy = step;
      else if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault();
        onDelete();
        return;
      } else {
        return;
      }

      e.preventDefault();
      const updated = clampMm(
        signature.x_mm + dx,
        signature.y_mm + dy,
        signature.width_mm,
        signature.height_mm
      );
      onChange(updated);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isSelected, signature, readOnly]);

  // Pointer drag start
  const handlePointerDown = (e) => {
    if (readOnly) return;
    if (e.target.dataset.handle) return; // Handled by resize
    e.stopPropagation();
    onSelect();

    setIsDragging(true);
    setDragStart({
      mouseX: e.clientX,
      mouseY: e.clientY,
      xMm: signature.x_mm,
      yMm: signature.y_mm,
    });
  };

  // Pointer resize start
  const handleResizePointerDown = (e, handle) => {
    if (readOnly) return;
    e.stopPropagation();
    onSelect();

    const ar = (signature.width_mm / signature.height_mm) || (signature.aspect_ratio || 1.8);
    setResizeHandle(handle);
    setResizeStart({
      mouseX: e.clientX,
      mouseY: e.clientY,
      xMm: signature.x_mm,
      yMm: signature.y_mm,
      widthMm: signature.width_mm,
      heightMm: signature.height_mm,
      aspectRatio: ar,
    });
  };

  // Window pointer move and pointer up
  useEffect(() => {
    if (!isDragging && !resizeHandle) return;

    const handlePointerMove = (e) => {
      if (isDragging) {
        const deltaXpx = e.clientX - dragStart.mouseX;
        const deltaYpx = e.clientY - dragStart.mouseY;
        const deltaXmm = deltaXpx / scaleX;
        const deltaYmm = deltaYpx / scaleY;

        const updated = clampMm(
          dragStart.xMm + deltaXmm,
          dragStart.yMm + deltaYmm,
          signature.width_mm,
          signature.height_mm
        );
        onChange(updated);
      } else if (resizeHandle) {
        const deltaXpx = e.clientX - resizeStart.mouseX;
        const deltaXmm = deltaXpx / scaleX;
        const ar = resizeStart.aspectRatio;

        let newW = resizeStart.widthMm;
        let newH = resizeStart.heightMm;
        let newX = resizeStart.xMm;
        let newY = resizeStart.yMm;

        if (resizeHandle === 'se') {
          newW = Math.max(MIN_WIDTH_MM, resizeStart.widthMm + deltaXmm);
          newH = newW / ar;
          // check page boundaries
          if (newX + newW > A4_WIDTH_MM) {
            newW = A4_WIDTH_MM - newX;
            newH = newW / ar;
          }
          if (newY + newH > A4_HEIGHT_MM) {
            newH = A4_HEIGHT_MM - newY;
            newW = newH * ar;
          }
        } else if (resizeHandle === 'sw') {
          newW = Math.max(MIN_WIDTH_MM, resizeStart.widthMm - deltaXmm);
          newH = newW / ar;
          newX = resizeStart.xMm + (resizeStart.widthMm - newW);
          if (newX < 0) {
            newW = resizeStart.xMm + resizeStart.widthMm;
            newX = 0;
            newH = newW / ar;
          }
          if (newY + newH > A4_HEIGHT_MM) {
            newH = A4_HEIGHT_MM - newY;
            newW = newH * ar;
            newX = resizeStart.xMm + (resizeStart.widthMm - newW);
          }
        } else if (resizeHandle === 'ne') {
          newW = Math.max(MIN_WIDTH_MM, resizeStart.widthMm + deltaXmm);
          newH = newW / ar;
          newY = resizeStart.yMm + (resizeStart.heightMm - newH);
          if (newX + newW > A4_WIDTH_MM) {
            newW = A4_WIDTH_MM - newX;
            newH = newW / ar;
            newY = resizeStart.yMm + (resizeStart.heightMm - newH);
          }
          if (newY < 0) {
            newH = resizeStart.yMm + resizeStart.heightMm;
            newY = 0;
            newW = newH * ar;
          }
        } else if (resizeHandle === 'nw') {
          newW = Math.max(MIN_WIDTH_MM, resizeStart.widthMm - deltaXmm);
          newH = newW / ar;
          newX = resizeStart.xMm + (resizeStart.widthMm - newW);
          newY = resizeStart.yMm + (resizeStart.heightMm - newH);
          if (newX < 0) {
            newW = resizeStart.xMm + resizeStart.widthMm;
            newX = 0;
            newH = newW / ar;
            newY = resizeStart.yMm + (resizeStart.heightMm - newH);
          }
          if (newY < 0) {
            newH = resizeStart.yMm + resizeStart.heightMm;
            newY = 0;
            newW = newH * ar;
            newX = resizeStart.xMm + (resizeStart.widthMm - newW);
          }
        }

        const clamped = clampMm(newX, newY, newW, newH);
        onChange(clamped);
      }
    };

    const handlePointerUp = () => {
      setIsDragging(false);
      setResizeHandle(null);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [isDragging, resizeHandle, dragStart, resizeStart, scaleX, scaleY, signature]);

  const imgSrc = signature.preview_blob_url || signature.temp_view_url || signature.image_url;

  return (
    <div
      ref={containerRef}
      onPointerDown={handlePointerDown}
      style={{
        position: 'absolute',
        left: `${xPx}px`,
        top: `${yPx}px`,
        width: `${widthPx}px`,
        height: `${heightPx}px`,
        border: isSelected ? '2px solid #2563eb' : '1px dashed #64748b',
        boxShadow: isSelected ? '0 0 0 1px #fff, 0 4px 12px rgba(37,99,235,0.25)' : 'none',
        cursor: readOnly ? 'default' : isDragging ? 'grabbing' : 'grab',
        userSelect: 'none',
        touchAction: 'none',
        boxSizing: 'border-box',
        zIndex: isSelected ? 20 : 10,
        backgroundColor: 'rgba(255, 255, 255, 0.05)',
      }}
      title={`Signature at X: ${signature.x_mm}mm, Y: ${signature.y_mm}mm`}
    >
      {/* Signature Image */}
      <img
        src={imgSrc}
        alt="Handwritten signature"
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          display: 'block',
          pointerEvents: 'none',
        }}
        draggable={false}
      />

      {/* Selected Controls & Resize Handles */}
      {isSelected && !readOnly && (
        <>
          {/* Coordinates HUD Tag */}
          <div
            style={{
              position: 'absolute',
              top: '-24px',
              left: '0',
              background: '#0f172a',
              color: '#f8fafc',
              fontSize: '10px',
              fontWeight: 600,
              padding: '2px 6px',
              borderRadius: '3px',
              whiteSpace: 'nowrap',
              pointerEvents: 'none',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
            }}
          >
            {signature.x_mm}mm, {signature.y_mm}mm ({signature.width_mm}×{signature.height_mm}mm)
          </div>

          {/* Delete Button */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            style={{
              position: 'absolute',
              top: '-12px',
              right: '-12px',
              width: '24px',
              height: '24px',
              borderRadius: '50%',
              background: '#ef4444',
              color: '#ffffff',
              border: '2px solid #ffffff',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '14px',
              fontWeight: 700,
              boxShadow: '0 2px 5px rgba(0,0,0,0.2)',
              zIndex: 30,
            }}
            title="Delete signature"
          >
            ×
          </button>

          {/* 4 Corner Resize Handles */}
          {['nw', 'ne', 'se', 'sw'].map((handle) => {
            const isNorth = handle.includes('n');
            const isWest = handle.includes('w');
            return (
              <div
                key={handle}
                data-handle={handle}
                onPointerDown={(e) => handleResizePointerDown(e, handle)}
                style={{
                  position: 'absolute',
                  top: isNorth ? '-5px' : 'auto',
                  bottom: !isNorth ? '-5px' : 'auto',
                  left: isWest ? '-5px' : 'auto',
                  right: !isWest ? '-5px' : 'auto',
                  width: '10px',
                  height: '10px',
                  backgroundColor: '#ffffff',
                  border: '2px solid #2563eb',
                  borderRadius: '2px',
                  cursor: `${handle}-resize`,
                  zIndex: 25,
                }}
              />
            );
          })}
        </>
      )}
    </div>
  );
}
