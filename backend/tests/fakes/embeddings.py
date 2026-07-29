"""Deterministic fake embedding provider for tests only — not a real model."""

from __future__ import annotations

import hashlib
import math

from app.embeddings.exceptions import (
    EmbeddingDimensionMismatchError,
    EmbeddingInvalidResponseError,
    EmbeddingModelUnavailableError,
    EmbeddingProviderUnavailableError,
    EmbeddingTimeoutError,
)
from app.embeddings.schemas import EmbeddingHealthResult, EmbeddingStatus


class FakeEmbeddingProvider:
    """Test-only embedding provider with injectable outcomes.

    Vectors are deterministic hash-based projections of the configured dimension.
    They are never all-zeros. This must never be presented as a real embedding model.
    """

    def __init__(
        self,
        *,
        provider_name: str = "fake",
        model: str = "fake-embed",
        dimension: int = 768,
        provider_reachable: bool = True,
        model_available: bool = True,
        fail_mode: str | None = None,
        identical_vectors: bool = False,
    ) -> None:
        if dimension < 1:
            raise ValueError("dimension must be positive")
        self._provider_name = provider_name
        self._model = model
        self._dimension = dimension
        self.provider_reachable = provider_reachable
        self.model_available = model_available
        self.fail_mode = fail_mode
        self.identical_vectors = identical_vectors
        self.embed_calls = 0
        self.embed_batch_calls = 0

    @property
    def name(self) -> str:
        return self._provider_name

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def health_check(self) -> EmbeddingHealthResult:
        if not self.provider_reachable or self.fail_mode == "unavailable":
            return EmbeddingHealthResult(
                provider=self.name,
                model=self._model,
                provider_reachable=False,
                model_available=False,
                configured_dimension=self._dimension,
                status=EmbeddingStatus.provider_unavailable,
                message="Fake embedding provider is unreachable",
            )
        if not self.model_available or self.fail_mode == "model_missing":
            return EmbeddingHealthResult(
                provider=self.name,
                model=self._model,
                provider_reachable=True,
                model_available=False,
                configured_dimension=self._dimension,
                status=EmbeddingStatus.model_unavailable,
                message="Fake embedding model is not available",
            )
        return EmbeddingHealthResult(
            provider=self.name,
            model=self._model,
            provider_reachable=True,
            model_available=True,
            configured_dimension=self._dimension,
            status=EmbeddingStatus.ready,
            message="Fake embedding provider is ready",
        )

    async def embed(self, text: str) -> list[float]:
        self.embed_calls += 1
        self._raise_if_configured()
        return self._vector_for(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.embed_batch_calls += 1
        self._raise_if_configured()
        if self.fail_mode == "wrong_batch_count":
            if not texts:
                return []
            # Intentionally return the wrong count for tests.
            return [self._vector_for(texts[0])]
        return [self._vector_for(text) for text in texts]

    def _raise_if_configured(self) -> None:
        if self.fail_mode == "unavailable":
            raise EmbeddingProviderUnavailableError("Fake embedding provider is unavailable")
        if self.fail_mode == "model_missing":
            raise EmbeddingModelUnavailableError("Fake embedding model is not available")
        if self.fail_mode == "timeout":
            raise EmbeddingTimeoutError("Fake embedding provider timed out")
        if self.fail_mode == "invalid":
            raise EmbeddingInvalidResponseError("Fake embedding response was invalid")
        if self.fail_mode == "dimension_mismatch":
            raise EmbeddingDimensionMismatchError(
                f"Expected embedding dimension {self._dimension}, received {self._dimension + 1}"
            )

    def _vector_for(self, text: str) -> list[float]:
        if self.identical_vectors:
            values = [0.0] * self._dimension
            values[0] = 1.0
            return values

        seed = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        material = seed
        while len(values) < self._dimension:
            for index in range(0, len(material), 4):
                chunk = material[index : index + 4]
                if len(chunk) < 4:
                    break
                # Map 32-bit unsigned int into (-1, 1), never exactly zero.
                as_int = int.from_bytes(chunk, "big")
                unit = ((as_int / 0xFFFFFFFF) * 2.0) - 1.0
                if unit == 0.0:
                    unit = 0.001
                values.append(unit)
                if len(values) >= self._dimension:
                    break
            material = hashlib.sha256(material).digest()

        # L2-normalize for stable cosine comparisons in tests.
        norm = math.sqrt(sum(value * value for value in values))
        if norm == 0.0:
            values[0] = 1.0
            norm = 1.0
        return [value / norm for value in values]
