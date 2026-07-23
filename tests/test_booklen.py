"""Tests for booklen - word counting rendered EPUBs + label formatting."""

from __future__ import annotations

import os
from pathlib import Path

from pulpline.models import RawArticle
from pulpline.renderers.epub import EpubRenderer
from pulpline.util import booklen


def _write_epub(tmp_path: Path, body_html: str, name: str = "out.epub") -> str:
    article = RawArticle(
        title="Sample",
        body_html=body_html,
        canonical_url="https://example.com/sample",
        source_url="direct",
    )
    out = tmp_path / name
    out.write_bytes(EpubRenderer().render(article))
    return str(out)


def test_format_words_thresholds() -> None:
    assert booklen.format_words(None) == ""
    assert booklen.format_words(0) == ""
    assert booklen.format_words(1) == "1 word"
    assert booklen.format_words(780) == "780 words"
    assert booklen.format_words(999) == "999 words"
    assert booklen.format_words(1000) == "1.0k words"
    assert booklen.format_words(3210) == "3.2k words"


def test_ensure_counts_body_words(tmp_path: Path) -> None:
    path = _write_epub(tmp_path, "<p>one two three four five</p>")
    # The count includes the <h1> title and canonical-URL footer the renderer
    # wraps around the body, so assert on the body words being present rather
    # than an exact total that couples to the wrapper's boilerplate.
    count = booklen.ensure(path)
    assert count is not None
    assert count >= 5


def test_lookup_is_pending_before_ensure_then_cached(tmp_path: Path) -> None:
    path = _write_epub(tmp_path, "<p>hello world</p>", name="fresh.epub")
    assert booklen.lookup(path) is booklen.PENDING
    computed = booklen.ensure(path)
    assert booklen.lookup(path) == computed


def test_missing_file_caches_none(tmp_path: Path) -> None:
    missing = str(tmp_path / "nope.epub")
    # A file that doesn't exist can't be counted; lookup/ensure both yield
    # None (rendered as "no length") rather than raising.
    assert booklen.lookup(missing) is None
    assert booklen.ensure(missing) is None


def test_non_epub_is_not_counted(tmp_path: Path) -> None:
    # mangadex emits image-only .cbz archives; word count is meaningless, so
    # ensure() should yield None without trying to parse it as an EPUB.
    cbz = tmp_path / "chapter.cbz"
    cbz.write_bytes(b"PK\x03\x04 not really a book")
    assert booklen.ensure(str(cbz)) is None


def test_recount_after_mtime_change(tmp_path: Path) -> None:
    path = _write_epub(tmp_path, "<p>short</p>", name="rebuilt.epub")
    first = booklen.ensure(path)
    assert first is not None

    # Rewrite with much longer body. The renderer stamps a fresh calibre
    # timestamp, so the new file differs; bump mtime explicitly to be sure
    # the (path, mtime) cache key invalidates.
    longer = " ".join(f"word{i}" for i in range(200))
    _write_epub(tmp_path, f"<p>{longer}</p>", name="rebuilt.epub")
    st = Path(path).stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    assert booklen.lookup(path) is booklen.PENDING
    second = booklen.ensure(path)
    assert second is not None
    assert second > first
