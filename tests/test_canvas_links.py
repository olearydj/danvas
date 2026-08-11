from __future__ import annotations

import pytest

from danvas.canvas_links import (
    canonical_canvas_object_url,
    canvas_file_reference,
    extract_canvas_file_references,
    stable_course_file_url,
)


def test_stable_course_file_url_uses_origin_and_wrap() -> None:
    assert stable_course_file_url("https://Canvas.Example/path", 101, 44) == (
        "https://canvas.example/courses/101/files/44?wrap=1"
    )


@pytest.mark.parametrize(
    "value",
    [
        "/courses/101/files/44?wrap=1",
        "/courses/101/files/44/download?verifier=secret",
        "https://canvas.example/courses/101/files/44/preview?x-amz-signature=secret",
        "/api/v1/courses/101/files/44",
        "/files/44/download?verifier=secret",
    ],
)
def test_canvas_file_reference_normalizes_supported_shapes(value: str) -> None:
    result = canvas_file_reference(
        value,
        current_course_id=101,
        canvas_origin="https://canvas.example/",
    )

    assert result is not None
    assert result["status"] == "valid"
    assert result["course_id"] == 101
    assert result["file_id"] == 44
    assert result["canvas_url"] == "https://canvas.example/courses/101/files/44?wrap=1"
    assert "secret" not in str(result)


def test_canvas_file_reference_rejects_cross_course_and_foreign_origin() -> None:
    cross_course = canvas_file_reference(
        "/courses/202/files/44",
        current_course_id=101,
        canvas_origin="https://canvas.example/",
    )
    foreign = canvas_file_reference(
        "https://evil.example/courses/101/files/44?token=secret",
        current_course_id=101,
        canvas_origin="https://canvas.example/",
    )

    assert cross_course is not None and cross_course["status"] == "cross_course"
    assert foreign is not None and foreign["status"] == "foreign_origin"
    assert "secret" not in str(foreign)


def test_extract_canvas_file_references_merges_endpoint_attributes() -> None:
    refs = extract_canvas_file_references(
        """<a href="/courses/101/files/44/download?verifier=secret"
        data-api-endpoint="https://canvas.example/api/v1/courses/101/files/44"
        data-api-returntype="File">Case</a>""",
        current_course_id=101,
        canvas_origin="https://canvas.example/",
    )

    assert len(refs) == 1
    assert refs[0]["status"] == "valid"
    assert refs[0]["file_id"] == 44
    assert refs[0]["attributes"] == ["data-api-endpoint", "href"]
    assert refs[0]["volatile_query_names"] == ["verifier"]
    assert "secret" not in str(refs)


def test_extract_canvas_file_references_detects_conflicting_attributes() -> None:
    refs = extract_canvas_file_references(
        """<a href="/courses/101/files/44"
        data-api-endpoint="/api/v1/courses/101/files/45"
        data-api-returntype="File">Case</a>""",
        current_course_id=101,
        canvas_origin="https://canvas.example/",
    )

    assert refs[0]["status"] == "conflict"
    assert refs[0]["conflicting_identities"] == [
        {"course_id": 101, "file_id": 44},
        {"course_id": 101, "file_id": 45},
    ]


def test_extract_canvas_file_references_marks_relative_assets() -> None:
    refs = extract_canvas_file_references(
        '<a href="../files/case.pdf?token=secret">Case</a>',
        current_course_id=101,
        canvas_origin="https://canvas.example/",
    )

    assert refs[0]["status"] == "relative_asset"
    assert refs[0]["reason"] == "relative_local_asset"
    assert "secret" not in str(refs)


def test_canonical_canvas_object_url_drops_query_and_foreign_urls() -> None:
    assert canonical_canvas_object_url(
        "https://canvas.example/courses/101/assignments/8?verifier=secret#fragment",
        canvas_origin="https://canvas.example/",
    ) == "https://canvas.example/courses/101/assignments/8"
    assert (
        canonical_canvas_object_url(
            "https://evil.example/courses/101/assignments/8",
            canvas_origin="https://canvas.example/",
        )
        == ""
    )
