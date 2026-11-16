"""Build-time model prefetch. No inference or repository indexing occurs on startup."""

import os
from pathlib import Path


def main():
    from huggingface_hub import snapshot_download

    cache = Path(os.getenv("ASKREPO_MODEL_CACHE", "data/models"))
    for name in (
        os.getenv("ASKREPO_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        os.getenv("ASKREPO_RERANKER_MODEL", "BAAI/bge-reranker-base"),
    ):
        print(f"Downloading {name}", flush=True)
        snapshot_download(
            name,
            cache_dir=cache,
            allow_patterns=["*.json", "*.txt", "*.safetensors", "*.model", "1_Pooling/*"],
        )
        print(f"Cached {name}", flush=True)


if __name__ == "__main__":
    main()
