"""ingest：采集与解析。"""

from .loader import SUPPORTED_SUFFIXES, load_directory, load_file
from .model import Document, doc_id_for
from .parsers import docling_available, parse_file

__all__ = [
    "SUPPORTED_SUFFIXES",
    "Document",
    "doc_id_for",
    "docling_available",
    "load_directory",
    "load_file",
    "parse_file",
]
