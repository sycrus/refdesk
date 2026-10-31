"""Every retriever by name, built through `build_retriever`.

Retrievers need different things: the metadata baseline only needs records, the CLIP
retriever also needs the image index and a text encoder. `Resources` supplies those
lazily, so nothing heavy (the index, torch) is loaded unless a retriever asks for it.
The CLI passes real resources; tests pass small fakes.

Shared tests (e.g. the reproduction rights filter) run over every registered name, so a
new retriever is covered as soon as it is added here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from refdesk.retrieval import Retriever
from refdesk.retrieval.metadata import JaccardRetriever
from refdesk.schema import ArtworkRecord


@dataclass
class Resources:
    load_index: Callable[[], object]
    load_embedder: Callable[[], object]

    @classmethod
    def default(cls, index_dir: str = "data/index/met-clip") -> Resources:
        def load_index():
            from refdesk.embeddings import EmbeddingIndex

            return EmbeddingIndex.load(Path(index_dir))

        def load_embedder():
            # The query embedder must match the model the index was built with.
            from refdesk.embeddings import EmbeddingIndex, OpenClipEmbedder

            model_id = EmbeddingIndex.load(Path(index_dir)).manifest["model_id"]
            _, model, pretrained = model_id.split("/")
            return OpenClipEmbedder(model, pretrained)

        return cls(load_index, load_embedder)


def _clip(records: list[ArtworkRecord], resources: Resources) -> Retriever:
    from refdesk.retrieval.clip import EmbeddingRetriever

    return EmbeddingRetriever(records, resources.load_index(), resources.load_embedder())


def _combined(records: list[ArtworkRecord], resources: Resources) -> Retriever:
    from refdesk.retrieval.combined import CombinedRetriever, load_config

    return CombinedRetriever(
        records, resources.load_index(), resources.load_embedder(), load_config()
    )


def retriever_params(name: str) -> dict:
    """Settings that change a retriever's output, recorded in the eval config (and so its
    hash). Without this, re-weighting `combined` would overwrite the earlier report."""
    if name == "combined":
        from refdesk.retrieval.combined import load_config

        return load_config().model_dump()
    return {}


RETRIEVERS: dict[str, Callable[[list[ArtworkRecord], Resources], Retriever]] = {
    "jaccard": lambda records, resources: JaccardRetriever(records),
    "clip": _clip,
    "combined": _combined,
}

# Retrievers that load the image index (`Resources.load_index`). /readyz checks the
# index only when the configured retriever needs it (issue #168): a metadata-only
# deployment is ready without one. Add a name here when a retriever starts reading the
# index, or readiness will not watch it.
NEEDS_INDEX = frozenset({"clip", "combined"})


def build_retriever(
    name: str, records: list[ArtworkRecord], resources: Resources | None = None
) -> Retriever:
    return RETRIEVERS[name](records, resources or Resources.default())
