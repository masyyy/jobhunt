from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from backend.core.interfaces.data_warehouse import DataWarehouse
from backend.core.interfaces.document_chunk_repository import DocumentChunkRepository
from backend.core.interfaces.embedding_provider import EmbeddingProvider
from backend.core.interfaces.filesystem import FileSystem

DocumentChunkRepoFactory = Callable[[], AbstractAsyncContextManager[DocumentChunkRepository]]


@dataclass
class AgentDeps:
    fs: FileSystem
    db: DataWarehouse
    embedder: EmbeddingProvider
    chunk_repo_factory: DocumentChunkRepoFactory
