"""
Module 9 — Content-Based File Validation.

Validates files using actual binary signatures / magic bytes, structural integrity,
and safety limits rather than trusting frontend MIME types or extensions.
Protects against:
- Renamed executables / scripts (e.g. payload.exe renamed to invoice.pdf)
- Corrupted images / PDFs
- Password-protected / encrypted PDFs
- Decompression bombs / pixel bombs
- Excessive PDF page counts
- Excessive image dimensions
"""

import hashlib
import io
import os
import tempfile
from dataclasses import dataclass
from typing import Optional, Tuple
from pathlib import Path

from fastapi import HTTPException, status
from PIL import Image

import pdf2image
from app.config import settings


# Error Codes
ERR_UNSUPPORTED_TYPE = "UNSUPPORTED_FILE_TYPE"
ERR_CONTENT_MISMATCH = "EXTENSION_CONTENT_MISMATCH"
ERR_FILE_TOO_LARGE = "FILE_TOO_LARGE"
ERR_MALFORMED_PDF = "MALFORMED_PDF"
ERR_ENCRYPTED_PDF = "ENCRYPTED_PDF_NOT_ALLOWED"
ERR_PDF_PAGE_COUNT = "PDF_PAGE_COUNT_EXCEEDED"
ERR_CORRUPTED_IMAGE = "CORRUPTED_IMAGE"
ERR_IMAGE_DIMENSIONS = "IMAGE_DIMENSIONS_EXCEEDED"
ERR_DECOMPRESSION_BOMB = "DECOMPRESSION_BOMB_DETECTED"
ERR_DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"


class FileValidationError(HTTPException):
    """Structured validation exception with machine-readable error code."""
    def __init__(self, error_code: str, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


@dataclass
class ValidationResult:
    is_valid: bool
    filename: str
    mime_type: str
    sha256: str
    file_size: int
    page_count: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class FileValidator:
    """Server-side deep content file validator."""

    # Magic byte signatures
    MAGIC_SIGNATURES = [
        (b"%PDF-", "application/pdf", [".pdf"]),
        (b"\xff\xd8\xff", "image/jpeg", [".jpg", ".jpeg"]),
        (b"\x89PNG\r\n\x1a\n", "image/png", [".png"]),
    ]

    @classmethod
    def detect_signature(cls, header: bytes) -> Optional[Tuple[str, list]]:
        """Inspect binary prefix to determine true content format."""
        for sig, mime, exts in cls.MAGIC_SIGNATURES:
            if header.startswith(sig):
                return mime, exts
        return None

    @classmethod
    def validate(cls, filename: str, contents: bytes, max_size: Optional[int] = None) -> ValidationResult:
        """
        Perform complete content validation on raw file bytes.
        Returns ValidationResult or raises FileValidationError.
        """
        file_size = len(contents)
        limit_size = max_size or settings.MAX_UPLOAD_FILE_SIZE_BYTES
        sha256 = hashlib.sha256(contents).hexdigest()
        clean_ext = Path(filename).suffix.lower()

        # 1. Size check
        if file_size == 0:
            return ValidationResult(
                is_valid=False,
                filename=filename,
                mime_type="application/octet-stream",
                sha256=sha256,
                file_size=0,
                error_code=ERR_UNSUPPORTED_TYPE,
                error_message="Uploaded file is empty (0 bytes).",
            )

        if file_size > limit_size:
            max_mb = limit_size // (1024 * 1024)
            return ValidationResult(
                is_valid=False,
                filename=filename,
                mime_type="application/octet-stream",
                sha256=sha256,
                file_size=file_size,
                error_code=ERR_FILE_TOO_LARGE,
                error_message=f"File exceeds maximum allowed size of {max_mb} MB.",
            )

        # 2. Magic signature check
        sig_result = cls.detect_signature(contents[:16])
        if not sig_result:
            return ValidationResult(
                is_valid=False,
                filename=filename,
                mime_type="application/octet-stream",
                sha256=sha256,
                file_size=file_size,
                error_code=ERR_UNSUPPORTED_TYPE,
                error_message="Unsupported file format. File format is not allowed. Only valid PDF, JPEG, and PNG files are allowed.",
            )

        detected_mime, valid_exts = sig_result

        # 3. Extension vs Content match
        if clean_ext not in valid_exts:
            return ValidationResult(
                is_valid=False,
                filename=filename,
                mime_type=detected_mime,
                sha256=sha256,
                file_size=file_size,
                error_code=ERR_CONTENT_MISMATCH,
                error_message=f"Extension '{clean_ext}' does not match verified file content ({detected_mime}).",
            )

        # 4. Deep structural inspection
        if detected_mime == "application/pdf":
            return cls._validate_pdf(filename, contents, sha256, file_size)
        else:
            return cls._validate_image(filename, contents, detected_mime, sha256, file_size)

    @classmethod
    def _validate_pdf(cls, filename: str, contents: bytes, sha256: str, file_size: int) -> ValidationResult:
        """Validate PDF structure, page count, and encryption."""
        # Write to temporary file for poppler pdfinfo analysis
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        try:
            try:
                info = pdf2image.pdfinfo_from_path(tmp_path)
            except Exception as e:
                err_str = str(e).lower()
                if "password" in err_str or "encrypted" in err_str:
                    return ValidationResult(
                        is_valid=False,
                        filename=filename,
                        mime_type="application/pdf",
                        sha256=sha256,
                        file_size=file_size,
                        error_code=ERR_ENCRYPTED_PDF,
                        error_message="Encrypted or password-protected PDFs are not supported.",
                    )
                return ValidationResult(
                    is_valid=False,
                    filename=filename,
                    mime_type="application/pdf",
                    sha256=sha256,
                    file_size=file_size,
                    error_code=ERR_MALFORMED_PDF,
                    error_message="Malformed or corrupted PDF file. Structure cannot be parsed.",
                )

            # Check encryption
            if str(info.get("Encrypted", "")).lower() in ("yes", "true", "1"):
                return ValidationResult(
                    is_valid=False,
                    filename=filename,
                    mime_type="application/pdf",
                    sha256=sha256,
                    file_size=file_size,
                    error_code=ERR_ENCRYPTED_PDF,
                    error_message="Encrypted or password-protected PDFs are not supported.",
                )

            # Check page count
            try:
                pages = int(info.get("Pages", 1))
            except (ValueError, TypeError):
                pages = 1

            if pages > settings.MAX_PDF_PAGES:
                return ValidationResult(
                    is_valid=False,
                    filename=filename,
                    mime_type="application/pdf",
                    sha256=sha256,
                    file_size=file_size,
                    page_count=pages,
                    error_code=ERR_PDF_PAGE_COUNT,
                    error_message=f"PDF exceeds maximum page limit of {settings.MAX_PDF_PAGES} pages (found {pages}).",
                )

            return ValidationResult(
                is_valid=True,
                filename=filename,
                mime_type="application/pdf",
                sha256=sha256,
                file_size=file_size,
                page_count=pages,
            )
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @classmethod
    def _validate_image(cls, filename: str, contents: bytes, mime_type: str, sha256: str, file_size: int) -> ValidationResult:
        """Validate image dimensions, format, and decompression bomb safety."""
        # Configure decompression bomb protection
        Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_PIXELS

        try:
            bio = io.BytesIO(contents)
            im = Image.open(bio)

            # Verify format matches
            expected_format = "JPEG" if mime_type == "image/jpeg" else "PNG"
            if im.format != expected_format:
                return ValidationResult(
                    is_valid=False,
                    filename=filename,
                    mime_type=mime_type,
                    sha256=sha256,
                    file_size=file_size,
                    error_code=ERR_CONTENT_MISMATCH,
                    error_message=f"Image content format '{im.format}' does not match expected '{expected_format}'.",
                )

            width, height = im.size

            # Check dimensions
            if width > settings.MAX_IMAGE_WIDTH or height > settings.MAX_IMAGE_HEIGHT:
                return ValidationResult(
                    is_valid=False,
                    filename=filename,
                    mime_type=mime_type,
                    sha256=sha256,
                    file_size=file_size,
                    width=width,
                    height=height,
                    error_code=ERR_IMAGE_DIMENSIONS,
                    error_message=f"Image dimensions ({width}x{height}) exceed maximum allowed ({settings.MAX_IMAGE_WIDTH}x{settings.MAX_IMAGE_HEIGHT}).",
                )

            # Check total pixels
            if (width * height) > settings.MAX_IMAGE_PIXELS:
                return ValidationResult(
                    is_valid=False,
                    filename=filename,
                    mime_type=mime_type,
                    sha256=sha256,
                    file_size=file_size,
                    width=width,
                    height=height,
                    error_code=ERR_DECOMPRESSION_BOMB,
                    error_message=f"Image pixel count exceeds maximum limit of {settings.MAX_IMAGE_PIXELS} pixels.",
                )

            # Verify structural integrity
            im.verify()

            return ValidationResult(
                is_valid=True,
                filename=filename,
                mime_type=mime_type,
                sha256=sha256,
                file_size=file_size,
                width=width,
                height=height,
            )
        except Image.DecompressionBombError:
            return ValidationResult(
                is_valid=False,
                filename=filename,
                mime_type=mime_type,
                sha256=sha256,
                file_size=file_size,
                error_code=ERR_DECOMPRESSION_BOMB,
                error_message="Decompression bomb detected. Image cannot be processed safely.",
            )
        except Exception:
            return ValidationResult(
                is_valid=False,
                filename=filename,
                mime_type=mime_type,
                sha256=sha256,
                file_size=file_size,
                error_code=ERR_CORRUPTED_IMAGE,
                error_message="Corrupted or invalid image data.",
            )
