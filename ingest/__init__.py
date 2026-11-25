"""ingest：采集与解析。"""

from .loader import Document, load_directory, load_file

__all__ = ["Document", "load_directory", "load_file"]
