class DocumentError(Exception):
    """Base exception for document ingestion failures."""


class InvalidDocument(DocumentError):
    """Raised when an upload is not a valid readable PDF."""


class DocumentTooLarge(InvalidDocument):
    """Raised when an upload exceeds the configured byte limit."""


class DocumentTooManyPages(InvalidDocument):
    """Raised when a PDF exceeds the configured page limit."""


class DocumentWithoutText(InvalidDocument):
    """Raised when no extractable text exists in a PDF."""


class DuplicateDocument(DocumentError):
    """Raised when a document with the same SHA-256 was already indexed."""

    def __init__(self, document_id: str) -> None:
        super().__init__("该文档已经建立索引")
        self.document_id = document_id


class DocumentNotFound(DocumentError):
    """Raised when a requested document does not exist."""
