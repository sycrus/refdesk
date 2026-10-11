"""Image cache for open works only (issue #31; PRD 9; CLAUDE.md hard rules).

Downloads `image_url` for records whose rights status is Open, into
`<cache>/<source>/<object_id>.jpg`, and records each file's URL, path and sha256 in the
store. Image embeddings (#32) read from this cache.

Rights rule, enforced here as well as in the adapter: an image is fetched only when the
record's rights status is Open. A non-open record is skipped even if it somehow carries an
image URL. Resumable: a record whose file exists with the recorded hash is not fetched again.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from refdesk.schema import RightsStatus
from refdesk.sources.met import MetClient
from refdesk.store import Store


@dataclass
class CacheResult:
    downloaded: int = 0
    already_cached: int = 0
    skipped: Counter = field(default_factory=Counter)


def _cached(store: Store, record_id: str, cache_dir: Path) -> bool:
    row = store.get_image(record_id)
    if row is None:
        return False
    path = cache_dir / row["path"]
    return path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]


def cache_images(
    store: Store, client: MetClient, cache_dir: Path, *, limit: int | None = None
) -> CacheResult:
    result = CacheResult()
    for record in store.iter_records():
        if record.rights.status is not RightsStatus.OPEN:
            result.skipped["not_open"] += 1
            continue
        if not record.image_url:
            result.skipped["no_image_url"] += 1
            continue
        if _cached(store, record.id, cache_dir):
            result.already_cached += 1
            continue
        if limit is not None and result.downloaded >= limit:
            result.skipped["over_limit"] += 1  # keep counting so the totals stay complete
            continue
        data = client.get_bytes(record.image_url)  # MetUnavailable propagates; progress kept
        suffix = PurePosixPath(urlsplit(record.image_url).path).suffix or ".jpg"
        relative = Path(record.source) / f"{record.object_id}{suffix}"
        target = cache_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        partial.write_bytes(data)
        partial.replace(target)  # atomic: never a half-written file under the real name
        digest = hashlib.sha256(data).hexdigest()
        store.save_image(record.id, record.image_url, relative.as_posix(), digest, len(data))
        result.downloaded += 1
    return result
