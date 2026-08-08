from pathlib import Path


def test_retrieval_uses_only_active_versions() -> None:
    source = Path("app/services/retrieval.py").read_text(encoding="utf-8")
    assert "Document.is_active_version.is_(True)" in source


def test_versioning_routes_are_registered() -> None:
    source = Path("app/api/routes/documents.py").read_text(encoding="utf-8")
    assert '"/{document_id}/versions"' in source
    assert '"/{document_id}/timeline"' in source
    assert '"/{document_id}/activate"' in source
    assert '"/{document_id}/compare/{other_document_id}"' in source


def test_version_upload_links_to_existing_lineage() -> None:
    source = Path("app/services/documents.py").read_text(encoding="utf-8")
    assert "knowledge_document_id=knowledge.id" in source
    assert 'lifecycle_state="superseded"' in source
    assert 'event_type="version_activated"' in source
