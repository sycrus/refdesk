"""Image embeddings and a FAISS index over them (issue #32; PRD 10; ADR-010).

- `EmbeddingIndex`: record IDs plus L2-normalised vectors in a FAISS `IndexFlatIP`. On
  normalised vectors inner product equals cosine similarity, and a flat index is exact, so
  its results match a brute-force check. FAISS is used so an approximate index can replace
  it if the corpus grows (Joe, 2026-10-11); at about 2,300 images exact search is instant.
- `build_index`: embeds the cached images of open works (#31) and writes the index with a
  manifest. The build is skipped when the manifest matches: same model, same weights,
  same images (by sha256).
- `OpenClipEmbedder`: the real model, imported lazily so the rest of refdesk (and CI)
  never needs torch. It checks free VRAM before loading: one GPU job at a time (CLAUDE.md).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import faiss
import numpy as np

from refdesk.store import Store

INDEX_TYPE = "faiss.IndexFlatIP"


def normalise(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


class Embedder(Protocol):
    model_id: str
    weights_hash: str

    def embed_images(self, paths: list[Path]) -> np.ndarray: ...

    def embed_texts(self, texts: list[str]) -> np.ndarray: ...


class EmbeddingIndex:
    def __init__(self, ids: list[str], vectors: np.ndarray, manifest: dict | None = None):
        self.ids = list(ids)
        self.vectors = normalise(vectors)
        self.manifest = manifest or {}
        self._row = {record_id: i for i, record_id in enumerate(self.ids)}
        self.faiss = faiss.IndexFlatIP(self.vectors.shape[1])
        self.faiss.add(self.vectors)

    def search(self, query: np.ndarray, k: int) -> list[tuple[str, float]]:
        q = normalise(np.asarray(query, dtype=np.float32)[None, :])
        scores, rows = self.faiss.search(q, min(k, len(self.ids)))
        return [(self.ids[r], float(s)) for r, s in zip(rows[0], scores[0], strict=True) if r >= 0]

    def vector(self, record_id: str) -> np.ndarray:
        return self.vectors[self._row[record_id]]

    def __contains__(self, record_id: str) -> bool:
        return record_id in self._row

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        np.save(path / "vectors.npy", self.vectors)
        (path / "ids.json").write_text(json.dumps(self.ids), encoding="utf-8")
        (path / "manifest.json").write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> EmbeddingIndex:
        ids = json.loads((path / "ids.json").read_text(encoding="utf-8"))
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        return cls(ids, np.load(path / "vectors.npy"), manifest)


@dataclass(frozen=True)
class BuildResult:
    built: bool
    count: int
    manifest: dict


def _images(store: Store, cache_dir: Path) -> list[tuple[str, Path, str]]:
    rows = store.db.execute("SELECT record_id, path, sha256 FROM images ORDER BY record_id")
    return [(rid, cache_dir / path, sha) for rid, path, sha in rows if (cache_dir / path).exists()]


def build_index(
    store: Store, cache_dir: Path, embedder: Embedder, out_dir: Path, *, batch: int = 64
) -> BuildResult:
    images = _images(store, cache_dir)
    images_digest = hashlib.sha256(
        "\n".join(f"{rid} {sha}" for rid, _, sha in images).encode()
    ).hexdigest()[:16]
    manifest = {
        "model_id": embedder.model_id,
        "weights_hash": embedder.weights_hash,
        "index_type": INDEX_TYPE,
        "images_digest": images_digest,
        "count": len(images),
    }
    existing = out_dir / "manifest.json"
    if existing.exists() and json.loads(existing.read_text(encoding="utf-8")) == manifest:
        return BuildResult(False, len(images), manifest)

    vectors = [
        embedder.embed_images([p for _, p, _ in images[i : i + batch]])
        for i in range(0, len(images), batch)
    ]
    EmbeddingIndex([rid for rid, _, _ in images], np.concatenate(vectors), manifest).save(out_dir)
    return BuildResult(True, len(images), manifest)


class OpenClipEmbedder:
    """OpenCLIP image and text encoders (lazy torch import).

    `weights_hash` is a fingerprint, not a full hash: sha256 over the first 4 KiB of every
    tensor. That is fast and changes if a checkpoint is swapped, so the manifest forces a
    rebuild; it is not a cryptographic guarantee of identical weights."""

    def __init__(
        self,
        model: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
        device: str = "cuda",
        min_free_gib: float = 2.0,
    ):
        import open_clip
        import torch

        if device == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is not available; use --device cpu")
            free, _ = torch.cuda.mem_get_info()
            if free / 2**30 < min_free_gib:
                raise RuntimeError(
                    f"only {free / 2**30:.1f} GiB VRAM free, need {min_free_gib}. "
                    "Stop other GPU jobs first (one GPU job at a time)."
                )
        self._torch = torch
        self.device = device
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model, pretrained=pretrained, device=device
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(model)
        self.model_id = f"open_clip/{model}/{pretrained}"
        digest = hashlib.sha256()
        for tensor in self.model.state_dict().values():
            digest.update(tensor.detach().cpu().numpy().tobytes()[:4096])
        self.weights_hash = digest.hexdigest()[:16]

    def embed_images(self, paths: list[Path]) -> np.ndarray:
        from PIL import Image

        torch = self._torch
        batch = torch.stack([self.preprocess(Image.open(p).convert("RGB")) for p in paths])
        with torch.no_grad():
            features = self.model.encode_image(batch.to(self.device))
        return features.float().cpu().numpy()

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        torch = self._torch
        with torch.no_grad():
            features = self.model.encode_text(self.tokenizer(texts).to(self.device))
        return features.float().cpu().numpy()
