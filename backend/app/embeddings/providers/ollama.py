"""Ollama embedding provider."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import request_id_ctx
from app.embeddings.exceptions import (
    EmbeddingDimensionMismatchError,
    EmbeddingInvalidResponseError,
    EmbeddingModelUnavailableError,
    EmbeddingProviderUnavailableError,
    EmbeddingTimeoutError,
)
from app.embeddings.schemas import EmbeddingHealthResult, EmbeddingStatus

logger = logging.getLogger("cortexa.embeddings.ollama")


def _model_matches(installed: str, requested: str) -> bool:
    left = installed.strip().lower().split("@", 1)[0]
    right = requested.strip().lower().split("@", 1)[0]
    if left == right:
        return True
    left_name, _, left_tag = left.partition(":")
    right_name, _, right_tag = right.partition(":")
    if left_name != right_name:
        return False
    # Treat missing tag as matching any tag (including :latest).
    if not left_tag or not right_tag:
        return True
    return left_tag == right_tag


class OllamaEmbeddingProvider:
    """Ollama `/api/embeddings` and `/api/embed` compatible provider."""

    def __init__(self, *, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._base_url = settings.ollama_base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._settings.ollama_embedding_model

    @property
    def dimension(self) -> int:
        return self._settings.embedding_dimension

    async def health_check(self) -> EmbeddingHealthResult:
        model = self.model
        request_id = request_id_ctx.get() or "-"
        logger.info(
            "embedding_status_check_start provider=%s model=%s request_id=%s",
            self.name,
            model,
            request_id,
        )
        try:
            response = await self._http.get(f"{self._base_url}/api/tags")
        except httpx.TimeoutException:
            return EmbeddingHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=False,
                model_available=False,
                configured_dimension=self.dimension,
                status=EmbeddingStatus.provider_unavailable,
                message="Ollama did not respond before the configured timeout",
            )
        except httpx.HTTPError:
            return EmbeddingHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=False,
                model_available=False,
                configured_dimension=self.dimension,
                status=EmbeddingStatus.provider_unavailable,
                message="Ollama embedding provider is unreachable",
            )

        if response.status_code >= 400:
            return EmbeddingHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=False,
                model_available=False,
                configured_dimension=self.dimension,
                status=EmbeddingStatus.provider_unavailable,
                message="Ollama embedding provider is unavailable",
            )

        try:
            payload = response.json()
            models = payload.get("models", [])
            names = [str(item.get("name", "")).strip() for item in models if isinstance(item, dict)]
        except Exception:  # noqa: BLE001
            return EmbeddingHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=True,
                model_available=False,
                configured_dimension=self.dimension,
                status=EmbeddingStatus.misconfigured,
                message="Ollama returned an invalid model listing",
            )

        available = any(_model_matches(name, model) for name in names if name)
        if not available:
            return EmbeddingHealthResult(
                provider=self.name,
                model=model,
                provider_reachable=True,
                model_available=False,
                configured_dimension=self.dimension,
                status=EmbeddingStatus.model_unavailable,
                message="Configured embedding model is not available in Ollama",
            )
        return EmbeddingHealthResult(
            provider=self.name,
            model=model,
            provider_reachable=True,
            model_available=True,
            configured_dimension=self.dimension,
            status=EmbeddingStatus.ready,
            message="Ollama is reachable and the configured embedding model is available",
        )

    async def embed(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        cleaned: list[str] = []
        for text in texts:
            value = text.strip()
            if not value:
                raise EmbeddingInvalidResponseError("Cannot embed empty text")
            if len(value) > self._settings.embedding_max_input_characters:
                value = value[: self._settings.embedding_max_input_characters]
            cleaned.append(value)

        # Prefer modern /api/embed; fall back to /api/embeddings for older Ollama.
        try:
            return await self._embed_via_embed_endpoint(cleaned)
        except EmbeddingModelUnavailableError:
            raise
        except EmbeddingProviderUnavailableError:
            raise
        except EmbeddingTimeoutError:
            raise
        except EmbeddingInvalidResponseError:
            # Legacy single-input endpoint path.
            return await self._embed_via_legacy_endpoint(cleaned)

    async def _embed_via_embed_endpoint(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": texts if len(texts) > 1 else texts[0]}
        data = await self._post_json("/api/embed", payload)
        embeddings = data.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            return self._validate_batch(embeddings, expected=len(texts))
        single = data.get("embedding")
        if isinstance(single, list) and len(texts) == 1:
            return [self._validate_vector(single)]
        raise EmbeddingInvalidResponseError("Ollama embed response was malformed")

    async def _embed_via_legacy_endpoint(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            data = await self._post_json(
                "/api/embeddings",
                {"model": self.model, "prompt": text},
            )
            embedding = data.get("embedding")
            if not isinstance(embedding, list):
                raise EmbeddingInvalidResponseError("Ollama embeddings response was malformed")
            vectors.append(self._validate_vector(embedding))
        return vectors

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = request_id_ctx.get() or "-"
        try:
            response = await self._http.post(
                f"{self._base_url}{path}",
                json=payload,
                timeout=httpx.Timeout(
                    self._settings.embedding_request_timeout_seconds,
                    connect=self._settings.ollama_connect_timeout_seconds,
                ),
            )
        except httpx.TimeoutException as exc:
            logger.warning(
                "embedding_timeout provider=%s model=%s request_id=%s",
                self.name,
                self.model,
                request_id,
            )
            raise EmbeddingTimeoutError() from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "embedding_provider_unreachable provider=%s model=%s request_id=%s",
                self.name,
                self.model,
                request_id,
            )
            raise EmbeddingProviderUnavailableError() from exc

        if response.status_code == 404:
            # Endpoint or model missing — let caller decide fallback vs model error.
            body = response.text.lower()
            if "model" in body and ("not found" in body or "pull" in body):
                raise EmbeddingModelUnavailableError()
            raise EmbeddingInvalidResponseError("Ollama embed endpoint was not found")
        if response.status_code >= 500:
            raise EmbeddingProviderUnavailableError()
        if response.status_code >= 400:
            body = response.text.lower()
            if "not found" in body or "pull" in body:
                raise EmbeddingModelUnavailableError()
            raise EmbeddingInvalidResponseError("Ollama rejected the embedding request")

        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingInvalidResponseError() from exc
        if not isinstance(data, dict):
            raise EmbeddingInvalidResponseError()
        return data

    def _validate_batch(self, embeddings: list[Any], *, expected: int) -> list[list[float]]:
        if len(embeddings) != expected:
            raise EmbeddingInvalidResponseError("Embedding batch length did not match the request")
        return [self._validate_vector(item) for item in embeddings]

    def _validate_vector(self, values: Any) -> list[float]:
        if not isinstance(values, list) or not values:
            raise EmbeddingInvalidResponseError("Embedding vector was empty or malformed")
        try:
            vector = [float(item) for item in values]
        except (TypeError, ValueError) as exc:
            raise EmbeddingInvalidResponseError(
                "Embedding vector contained invalid values"
            ) from exc
        if len(vector) != self.dimension:
            raise EmbeddingDimensionMismatchError(
                f"Expected embedding dimension {self.dimension}, received {len(vector)}"
            )
        if all(value == 0.0 for value in vector):
            raise EmbeddingInvalidResponseError("Embedding provider returned an empty vector")
        return vector
