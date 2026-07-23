"""Word-count for rendered EPUBs, with an mtime-keyed in-memory cache.

The Library view wants to show "how long is this?" next to each item. The
only length signal we have is the rendered `.epub` on disk - there's no
word count in the state DB - so we open the archive and count words across
its content documents.

Counting is ~18ms/EPUB (measured), which is negligible once but a multi-
second event-loop freeze across a few hundred items. So callers compute
off the UI thread (see LibraryView's worker) and read results back through
this module's cache. The cache is keyed by (path, mtime): a rebuilt EPUB
gets a new mtime and is recounted; an untouched one is counted once per
process.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import lxml.html
from ebooklib import ITEM_DOCUMENT, epub

_log = logging.getLogger("pulpline.util.booklen")

# path -> (mtime_ns, word_count | None). None means "we tried and failed"
# (missing file, corrupt zip, no content document) - cached so we don't
# retry a doomed file on every refresh.
_cache: dict[str, tuple[int, int | None]] = {}

# Sentinel distinct from `None`: `None` is a cached failure, `PENDING`
# means "not in the cache for the current mtime - compute it".
PENDING = object()


def lookup(path: str) -> int | None | object:
    """Return the cached count for `path`, or `PENDING` if not cached.

    Non-blocking: never touches the archive. Returns `PENDING` when the
    file is absent from the cache or its mtime has moved (stale entry). The
    UI thread uses this to paint what it already knows and defer the rest.
    """
    try:
        mtime = Path(path).stat().st_mtime_ns
    except OSError:
        return None
    cached = _cache.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    return PENDING


def ensure(path: str) -> int | None:
    """Return the word count for `path`, computing and caching on a miss.

    Blocking (does the unzip + parse). Meant to run off the UI thread. Safe
    to call from a worker: it only mutates the module cache, never any
    widget.
    """
    cached = lookup(path)
    if cached is not PENDING:
        return cached  # type: ignore[return-value]
    try:
        mtime = Path(path).stat().st_mtime_ns
    except OSError:
        return None
    count = _count_words(path)
    _cache[path] = (mtime, count)
    return count


def _count_words(path: str) -> int | None:
    """Count whitespace-separated words across an EPUB's content documents.

    Reads the OPF manifest via ebooklib rather than guessing filenames: the
    library holds arbitrary published books (Anna's Archive downloads), whose
    chapters are named however the publisher chose and often end in `.html`,
    not the `article.xhtml` our own renderer emits. We sum every content
    document except the nav doc (its TOC would inflate the count) so the
    total reflects actual prose. Returns None on any failure - the caller
    renders that as "no length shown".

    Non-EPUB outputs (the mangadex source emits image-only `.cbz`) have no
    words, so we skip them up front rather than letting ebooklib fail on a
    format it can't read.
    """
    if not path.lower().endswith(".epub"):
        return None
    try:
        # ignore_ncx silences ebooklib's FutureWarning and skips the legacy
        # NCX; the catch_warnings scope keeps ebooklib's other parse warnings
        # (malformed manifests in the wild) off stderr without muting globally.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            book = epub.read_epub(path, options={"ignore_ncx": True})
        words = 0
        for item in book.get_items_of_type(ITEM_DOCUMENT):
            # EpubNav is an ITEM_DOCUMENT subtype; skip it structurally rather
            # than by filename so we don't depend on publisher naming.
            if isinstance(item, epub.EpubNav):
                continue
            text = lxml.html.fromstring(item.get_content()).text_content()
            words += len(text.split())
    except Exception as exc:
        _log.debug("word count failed path=%s err=%s", path, exc)
        return None
    return words


def format_words(count: int | None) -> str:
    """Render a word count as a compact label, or '' when unknown.

    Under 1000 reads as a plain count ('780 words'); at/above 1000 it
    switches to a 'k' suffix with one decimal ('3.2k words') so long books
    stay short on screen. Zero-word items (empty extractions) show nothing
    rather than a misleading '0 words'.
    """
    if not count:  # None or 0
        return ""
    if count == 1:
        return "1 word"
    if count < 1000:
        return f"{count} words"
    return f"{count / 1000:.1f}k words"
