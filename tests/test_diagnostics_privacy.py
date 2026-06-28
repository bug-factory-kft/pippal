"""AC-P1 — Privacy + whitelist tests for PipPal core diagnostics.

Moved from pippal-pro; imports repointed to pippal.diagnostics.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import pytest


@pytest.fixture(autouse=True)
def isolated_diag_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect DIAG_DIR to a temp dir for every test."""
    diag = tmp_path / "diagnostics"
    diag.mkdir()

    import pippal.diagnostics as diag_mod

    monkeypatch.setattr(diag_mod, "DIAG_DIR", diag)
    diag_mod._current_level = "off"
    _remove_all_diag_handlers()
    yield diag
    diag_mod._current_level = "off"
    _remove_all_diag_handlers()


def _remove_all_diag_handlers():
    root = logging.getLogger()
    from pippal.diagnostics import _HANDLER_MARKER

    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            root.removeHandler(handler)
            handler.close()


def _read_all_diag_bytes(diag_dir: Path) -> bytes:
    content = b""
    for path in sorted(diag_dir.rglob("*")):
        if path.is_file():
            content += path.read_bytes()
    return content


class TestPrivacyLeakPrevention:
    """The hard invariant: read text / document content never reaches disk."""

    SECRETS: ClassVar[list[str]] = [
        "LORUM_IPSUM_SECRET_" + ("The quick brown fox jumps over the lazy dog. " * 1200),
        "user.secret.email@example.com",
        "https://secret.example.com/private/document/abc123",
        '{"secret_key": "do_not_log_this_value_ever_12345"}',
        "PIPPAL_PRIVACY_SECRET_XYZ_7f3a",
        "Títolo secreto del documento 中文内容 segreto",
    ]

    def test_diag_event_never_logs_free_text(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        for secret in self.SECRETS:
            event(EVT_DOC_IMPORT, char_count=42, nonexistent_key=secret)
            event(EVT_DOC_IMPORT, char_count=secret)  # type: ignore[arg-type]
            event(EVT_DOC_IMPORT, encoding=secret)
        event(EVT_DOC_IMPORT, char_count=100, encoding="utf-8", ok=True)

        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert all_bytes, "Expected at least one log file to exist."
        for secret in self.SECRETS:
            assert secret.encode("utf-8") not in all_bytes, (
                f"Secret leaked into log: {secret[:60]!r}..."
            )

    def test_raw_logger_info_body_never_logged(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        event(EVT_DOC_IMPORT, char_count=1, ok=True)
        for secret in self.SECRETS:
            logging.getLogger("pippal.document_import").info("Imported: %s", secret)
            logging.getLogger("some.third.party").warning("Processing: %s", secret)
            logging.getLogger("pippal.core").error("Error body: %s", secret)

        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert all_bytes, "Expected at least one log file."
        for secret in self.SECRETS:
            assert secret.encode("utf-8") not in all_bytes, (
                f"Legacy logger secret leaked: {secret[:60]!r}..."
            )

    def test_exception_message_never_logged(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT_ERROR, configure_diagnostics, error_event

        configure_diagnostics("trace")
        secret = "SECRET_EXCEPTION_CONTENT_abc123_do_not_log"
        try:
            raise ValueError(f"Failed to parse document: {secret}")
        except ValueError as exc:
            error_event(EVT_DOC_IMPORT_ERROR, exc=exc, stage="parse")

        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert all_bytes
        assert secret.encode("utf-8") not in all_bytes
        assert b"ValueError" in all_bytes
        assert b"<redacted>" in all_bytes

    def test_fifty_thousand_char_body_never_logged(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        doc_body = "FIFTY_K_SECRET_MARKER_" + ("A" * 49_978)
        assert len(doc_body) == 50_000

        event(EVT_DOC_IMPORT, char_count=len(doc_body))
        event(EVT_DOC_IMPORT, content=doc_body)  # type: ignore[arg-type]
        event(EVT_DOC_IMPORT, encoding=doc_body)
        logging.getLogger("pippal.document_import").info(doc_body)

        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert b"FIFTY_K_SECRET_MARKER_" not in all_bytes

    def test_error_level_also_redacts(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("error")
        secret = "ERROR_LEVEL_SECRET_CONTENT_xyz987"
        logging.getLogger("pippal.some_module").error("Content: %s", secret)
        event(EVT_DOC_IMPORT, encoding=secret, char_count=5)
        logging.getLogger("pippal.some_module").error("An error occurred.")

        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        if all_bytes:
            assert secret.encode("utf-8") not in all_bytes

    def test_legitimate_metadata_does_appear(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        event(EVT_DOC_IMPORT, char_count=48213, byte_size=91200,
              encoding="utf-8", src_format="pdf", duration_ms=812, ok=True)

        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert b"document.import" in all_bytes
        assert b"48213" in all_bytes
        assert b"utf-8" in all_bytes
        assert b"pdf" in all_bytes


class TestWhitelistAPI:
    def test_unknown_keys_dropped_and_marked(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        event(EVT_DOC_IMPORT, char_count=5, secret_content="SHOULD_NOT_APPEAR", ok=True)

        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert b"SHOULD_NOT_APPEAR" not in all_bytes
        assert b"_dropped" in all_bytes
        assert b"secret_content" in all_bytes

    def test_enum_key_valid_value_written(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        event(EVT_DOC_IMPORT, src_format="pdf", char_count=100)
        assert b"pdf" in _read_all_diag_bytes(isolated_diag_dir)

    def test_enum_key_long_value_dropped(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        long_value = "a" * 100
        event(EVT_DOC_IMPORT, encoding=long_value, char_count=5)

        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert long_value.encode() not in all_bytes
        assert b"_dropped" in all_bytes

    def test_enum_key_with_spaces_dropped(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        free_text = "this is a sentence with spaces"
        event(EVT_DOC_IMPORT, encoding=free_text, char_count=5)
        assert free_text.encode() not in _read_all_diag_bytes(isolated_diag_dir)

    def test_numeric_values_written(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        event(EVT_DOC_IMPORT, char_count=12345, duration_ms=500.5, ok=True)
        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert b"12345" in all_bytes
        assert b"500.5" in all_bytes

    def test_dict_list_values_dropped(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        event(EVT_DOC_IMPORT, char_count={"nested": "SHOULD_NOT_APPEAR"})  # type: ignore[arg-type]
        event(EVT_DOC_IMPORT, char_count=[1, 2, "ALSO_NOT_APPEAR"])  # type: ignore[arg-type]

        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert b"SHOULD_NOT_APPEAR" not in all_bytes
        assert b"ALSO_NOT_APPEAR" not in all_bytes


class TestErrorEvent:
    def test_error_event_records_type_not_message(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT_ERROR, configure_diagnostics, error_event

        configure_diagnostics("trace")
        secret_msg = "SECRET_IN_EXCEPTION_MESSAGE_abc789"
        try:
            raise RuntimeError(secret_msg)
        except RuntimeError as exc:
            error_event(EVT_DOC_IMPORT_ERROR, exc=exc, stage="parse")

        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert secret_msg.encode() not in all_bytes
        assert b"RuntimeError" in all_bytes
        assert b"<redacted>" in all_bytes

    def test_error_event_no_exc(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_AI_ACTION_ERROR, configure_diagnostics, error_event

        configure_diagnostics("trace")
        error_event(EVT_AI_ACTION_ERROR, stage="request", http_status=500)
        assert b"ai.action.error" in _read_all_diag_bytes(isolated_diag_dir)


class TestOffModeAndIdempotency:
    def test_off_mode_writes_zero_files(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("off")
        event(EVT_DOC_IMPORT, char_count=100, ok=True)
        logging.getLogger("pippal.test").info("some message")
        files = list(isolated_diag_dir.rglob("*.log"))
        assert files == []

    def test_configure_idempotent_no_duplicate_handlers(self, isolated_diag_dir: Path):
        from pippal.diagnostics import _HANDLER_MARKER, configure_diagnostics

        configure_diagnostics("trace")
        configure_diagnostics("trace")
        configure_diagnostics("error")
        configure_diagnostics("trace")

        root = logging.getLogger()
        diag_handlers = [h for h in root.handlers if getattr(h, _HANDLER_MARKER, False)]
        assert len(diag_handlers) == 1

    def test_configure_off_removes_handler(self, isolated_diag_dir: Path):
        from pippal.diagnostics import _HANDLER_MARKER, configure_diagnostics

        configure_diagnostics("trace")
        configure_diagnostics("off")
        root = logging.getLogger()
        assert not any(getattr(h, _HANDLER_MARKER, False) for h in root.handlers)

    def test_delete_logs_removes_all(self, isolated_diag_dir: Path):
        from pippal.diagnostics import (
            EVT_DOC_IMPORT,
            configure_diagnostics,
            delete_logs,
            event,
            list_log_files,
        )

        configure_diagnostics("trace")
        event(EVT_DOC_IMPORT, char_count=10, ok=True)
        files_before = list_log_files()
        assert len(files_before) >= 1
        removed = delete_logs()
        assert removed == len(files_before)
        assert list_log_files() == []

    def test_trace_level_writes_events(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("trace")
        event(EVT_DOC_IMPORT, char_count=99, ok=True)
        all_bytes = _read_all_diag_bytes(isolated_diag_dir)
        assert b"document.import" in all_bytes
        assert b"99" in all_bytes

    def test_error_level_filters_debug_events(self, isolated_diag_dir: Path):
        from pippal.diagnostics import EVT_DOC_IMPORT, configure_diagnostics, event

        configure_diagnostics("error")
        event(EVT_DOC_IMPORT, char_count=100, ok=True)
        assert b"document.import" not in _read_all_diag_bytes(isolated_diag_dir)


class TestRedactingFilterNoSharedMutation:
    def test_second_handler_sees_original_message(self, isolated_diag_dir: Path):
        import io as _io

        from pippal.diagnostics import configure_diagnostics

        configure_diagnostics("trace")
        captured_stream = _io.StringIO()
        second_handler = logging.StreamHandler(captured_stream)
        second_handler.setLevel(logging.DEBUG)
        root = logging.getLogger()
        root.addHandler(second_handler)
        try:
            msg = "host-app-message-UNIQUE_SENTINEL_42"
            logging.getLogger("host.app").info(msg)
        finally:
            root.removeHandler(second_handler)
            second_handler.close()

        assert msg in captured_stream.getvalue()
        assert msg.encode("utf-8") not in _read_all_diag_bytes(isolated_diag_dir)
