"""Tests for Library click-to-open target resolution.

Web articles open their source URL in the browser; downloaded artifacts
(Anna's Archive books, arXiv PDFs, MangaDex chapters) open the local file.
"""

from __future__ import annotations

from pulpline.state import LibraryItem
from pulpline.tui.views.library import _open_target


def _item(canonical_url: str, output_path: str | None) -> LibraryItem:
    return LibraryItem(
        id=1,
        title="x",
        canonical_url=canonical_url,
        subscription_name=None,
        ingested_at="2026-01-01",
        pub_date=None,
        output_path=output_path,
    )


def test_substack_article_opens_url() -> None:
    item = _item("https://etymology.substack.com/p/slop-realism", "/lib/slop realism.epub")
    assert _open_target(item) == "https://etymology.substack.com/p/slop-realism"


def test_custom_domain_article_opens_url() -> None:
    # substack-saves cross-posts land on the author's own domain, still a
    # web article -> should open in the browser, not the local file.
    item = _item("https://12gramsofcarbon.com/p/notes", "/lib/notes.epub")
    target = _open_target(item)
    assert target is not None and target.startswith("http")


def test_annas_book_opens_local_file() -> None:
    item = _item(
        "https://annas-archive.gl/md5/61b788be65cf5e02ea8c83656a5c021", "/lib/Moby Dick.epub"
    )
    assert _open_target(item) == "/lib/Moby Dick.epub"


def test_mangadex_chapter_opens_local_file() -> None:
    item = _item("https://mangadex.org/chapter/08d98058", "/lib/Berserk Ch 1.cbz")
    assert _open_target(item) == "/lib/Berserk Ch 1.cbz"


def test_arxiv_pdf_opens_local_file() -> None:
    item = _item("https://arxiv.org/abs/2401.00001", "/lib/paper.pdf")
    assert _open_target(item) == "/lib/paper.pdf"


def test_deleted_book_without_file_has_no_target() -> None:
    # A downloaded book whose file is gone (tombstone view): no reader target,
    # so the caller falls back to showing the URL rather than opening nothing.
    item = _item("https://annas-archive.gl/md5/deadbeefdeadbeefdeadbeefdeadbeef", None)
    assert _open_target(item) is None
