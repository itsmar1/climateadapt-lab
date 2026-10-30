"""Offline unit tests for the in-memory background job store."""

from __future__ import annotations

import json
import threading
import time

import pytest

from climateadapt.api.dependencies import (
    close_shared_clients,
    get_chirps_client,
    get_era5_client,
    get_job_store,
)
from climateadapt.api.errors import JobStoreFullError
from climateadapt.api.jobs import JobStore
from climateadapt.data.errors import DownloadError

TERMINAL = ("succeeded", "failed", "timed_out")


def wait_for(store, job_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while True:
        snapshot = store.get(job_id)
        assert snapshot is not None
        if snapshot["status"] in TERMINAL:
            return snapshot
        assert time.monotonic() < deadline, "job never reached a terminal state"
        time.sleep(0.02)


def test_success_records_result_and_progress():
    store = JobStore()
    try:
        job_id = store.submit("demo", 2, lambda progress: (progress(2, 2), {"answer": 42})[1])

        snapshot = wait_for(store, job_id)

        assert snapshot["status"] == "succeeded"
        assert snapshot["result"] == {"answer": 42}
        assert snapshot["progress"] == {"completed_steps": 2, "total_steps": 2}
        assert snapshot["error"] is None
        assert snapshot["finished_at"] is not None
    finally:
        store.shutdown()


def test_domain_failure_reports_type_and_message():
    store = JobStore()
    try:
        def outage(progress):
            raise DownloadError("synthetic outage")

        job_id = store.submit("demo", 1, outage)

        snapshot = wait_for(store, job_id)

        assert snapshot["status"] == "failed"
        assert snapshot["error"] == {"type": "download_error", "message": "synthetic outage"}
        assert snapshot["result"] is None
    finally:
        store.shutdown()


def test_unexpected_failure_is_scrubbed_to_internal():
    store = JobStore()
    try:
        def crash(progress):
            raise RuntimeError("boom-secret-xyz")

        job_id = store.submit("demo", 1, crash)

        snapshot = wait_for(store, job_id)

        assert snapshot["status"] == "failed"
        assert snapshot["error"]["type"] == "internal"
        assert "boom-secret-xyz" not in json.dumps(snapshot, default=str)
    finally:
        store.shutdown()


def test_timeout_marks_the_job_and_ignores_the_late_finish():
    store = JobStore(timeout_seconds=0.05)
    try:
        job_id = store.submit("slow", 1, lambda progress: time.sleep(0.5) or {"late": True})

        snapshot = wait_for(store, job_id)

        assert snapshot["status"] == "timed_out"
        assert snapshot["error"]["type"] == "timeout"
        time.sleep(0.6)  # let the worker finish late
        assert store.get(job_id)["status"] == "timed_out"
        assert store.get(job_id)["result"] is None
    finally:
        store.shutdown()


def test_unknown_job_returns_none():
    store = JobStore()
    try:
        assert store.get("no-such-job") is None
    finally:
        store.shutdown()


def test_finished_jobs_expire_after_ttl():
    store = JobStore(ttl_seconds=0.05)
    try:
        job_id = store.submit("demo", 1, lambda progress: {"ok": True})
        assert wait_for(store, job_id)["status"] == "succeeded"
        time.sleep(0.1)
        assert store.get(job_id) is None
    finally:
        store.shutdown()


def test_progress_is_visible_while_running():
    store = JobStore()
    release = threading.Event()
    try:
        def slow(progress):
            progress(1, 3)
            assert release.wait(timeout=10.0)
            return {"ok": True}

        job_id = store.submit("demo", 3, slow)
        deadline = time.monotonic() + 10.0
        while store.get(job_id)["progress"]["completed_steps"] == 0:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        release.set()
        assert wait_for(store, job_id)["status"] == "succeeded"
    finally:
        store.shutdown()


def test_store_evicts_oldest_finished_jobs_past_the_cap():
    store = JobStore(max_jobs=2)
    try:
        first = store.submit("one", 1, lambda progress: {"n": 1})
        wait_for(store, first)
        second = store.submit("two", 1, lambda progress: {"n": 2})
        wait_for(store, second)
        third = store.submit("three", 1, lambda progress: {"n": 3})
        wait_for(store, third)
        assert store.get(first) is None
        assert store.get(second)["status"] == "succeeded"
        assert store.get(third)["status"] == "succeeded"
    finally:
        store.shutdown()


def test_shutdown_refuses_new_jobs_and_is_idempotent():
    store = JobStore()
    store.shutdown()
    store.shutdown()
    with pytest.raises(RuntimeError, match="shut down"):
        store.submit("late", 1, lambda progress: {})


def test_submit_up_to_limit_then_rejects_when_full():
    store = JobStore(max_jobs=3)
    release = threading.Event()
    try:
        def gated(progress):
            assert release.wait(timeout=10.0)
            return {"ok": True}

        ids = [store.submit("job", 1, gated) for _ in range(3)]
        assert len({store.get(job_id)["job_id"] for job_id in ids}) == 3
        with pytest.raises(JobStoreFullError, match="capacity"):
            store.submit("extra", 1, gated)
        release.set()
        for job_id in ids:
            assert wait_for(store, job_id)["status"] == "succeeded"
    finally:
        release.set()
        store.shutdown()


def test_finished_job_eviction_frees_capacity():
    store = JobStore(max_jobs=1)
    try:
        first = store.submit("one", 1, lambda progress: {"n": 1})
        assert wait_for(store, first)["status"] == "succeeded"
        second = store.submit("two", 1, lambda progress: {"n": 2})
        assert wait_for(store, second)["status"] == "succeeded"
        assert store.get(first) is None  # evicted to make room
    finally:
        store.shutdown()


def test_concurrent_submits_never_exceed_capacity():
    store = JobStore(max_workers=8, max_jobs=8)
    release = threading.Event()
    accepted: list = []
    rejected: list = []
    tally = threading.Lock()

    def gated(progress):
        assert release.wait(timeout=30.0)
        return {"ok": True}

    def attempt():
        try:
            job_id = store.submit("race", 1, gated)
        except JobStoreFullError:
            with tally:
                rejected.append(1)
        else:
            with tally:
                accepted.append(job_id)

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert all(not thread.is_alive() for thread in threads)
        assert len(accepted) == 8
        assert len(set(accepted)) == 8
        assert len(rejected) == 12
    finally:
        release.set()
        store.shutdown()


def test_close_shared_clients_clears_caches_without_raising():
    close_shared_clients()
    assert get_chirps_client.cache_info().currsize == 0
    assert get_era5_client.cache_info().currsize == 0
    assert get_job_store.cache_info().currsize == 0
