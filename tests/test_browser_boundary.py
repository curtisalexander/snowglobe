from pathlib import Path

VIEWER_SOURCE = Path("apps/viewer/src")


def production_viewer_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(VIEWER_SOURCE.iterdir())
        if path.suffix in {".svelte", ".ts", ".tsx"} and ".test." not in path.name
    )


def test_viewer_has_no_result_persistence_or_service_worker_surface() -> None:
    source = production_viewer_source().lower()

    for forbidden in (
        "indexeddb",
        "localstorage",
        "sessionstorage",
        "navigator.serviceworker",
        "caches.open",
        "storage.getdirectory",
    ):
        assert forbidden not in source

    assert not any(
        "service-worker" in path.name or "serviceworker" in path.name
        for path in Path("apps/viewer").rglob("*")
    )


def test_duckdb_worker_has_no_external_reader_or_extension_surface() -> None:
    source = (VIEWER_SOURCE / "duckdb.worker.ts").read_text(encoding="utf-8").lower()

    for forbidden in (
        "registerfile",
        "registeropfs",
        "registerfileurl",
        "registerfilehandle",
        "read_csv",
        "read_json",
        "read_parquet",
        "parquet_scan",
        "httpfs",
        "install ",
        "load ",
        "attach ",
    ):
        assert forbidden not in source


def test_result_stream_is_opened_only_by_explicit_request_action() -> None:
    app = (VIEWER_SOURCE / "App.svelte").read_text(encoding="utf-8")

    assert app.count("openResultStream(") == 1
    assert "onclick={() => void loadRequest(request.requestId)}" in app
    assert "onMount(() => {\n    void loadRequest" not in app
