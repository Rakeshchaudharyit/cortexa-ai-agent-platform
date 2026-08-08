from pathlib import Path

ROOT = Path(__file__).parents[2]
BACKEND = ROOT / "backend"


def test_exhausted_jobs_move_to_dead_letter() -> None:
    worker = (BACKEND / "app" / "jobs" / "worker.py").read_text()
    enums = (BACKEND / "app" / "models" / "enums.py").read_text()
    assert 'dead_lettered = "dead_lettered"' in enums
    assert "JobStatus.dead_lettered.value" in worker
    assert "Moved to dead letter after maximum attempts" in worker


def test_admin_job_operations_are_available() -> None:
    routes = (BACKEND / "app" / "api" / "routes" / "admin" / "jobs.py").read_text()
    service = (BACKEND / "app" / "jobs" / "service.py").read_text()
    assert '@router.post("/{job_id}/requeue"' in routes
    assert '@router.post("/bulk"' in routes
    assert "async def requeue_job" in service
    assert "async def bulk_action" in service
    assert "async def queue_metrics" in service


def test_requeue_resets_durable_execution_state() -> None:
    service = (BACKEND / "app" / "jobs" / "service.py").read_text()
    for fragment in (
        "job.progress_percent = 0",
        "job.attempt_count = 0",
        "job.cancellation_requested = False",
        "job.finished_at = None",
        "await self.enqueue(job.id)",
    ):
        assert fragment in service


def test_admin_monitor_exposes_dead_letter_and_bulk_controls() -> None:
    page = (ROOT / "frontend" / "app" / "admin" / "jobs" / "page.tsx").read_text()
    assert "Dead letter" in page
    assert "Requeue failed" in page
    assert "Cancel selected" in page
    assert "queue_metrics.ready_depth" in page
    assert "queue_metrics.stale_running_count" in page
