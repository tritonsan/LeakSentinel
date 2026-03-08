from pathlib import Path

from leaksentinel.retrieval.memory import EmbeddingsCache, _cache_key_for_file, _cache_key_for_query


def test_embeddings_cache_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "cache.json"
    cache = EmbeddingsCache.load(p)
    assert cache.hits == 0
    assert cache.misses == 0

    cache.set("k1", [0.1, 0.2])
    cache.save()

    cache2 = EmbeddingsCache.load(p)
    v = cache2.get("k1")
    assert v == [0.1, 0.2]
    assert cache2.hits == 1


def test_cache_keys(tmp_path: Path) -> None:
    f = tmp_path / "bundle.json"
    f.write_text("{}", encoding="utf-8")
    kf = _cache_key_for_file(model_id="m", dim=256, p=f)
    assert "model_id" not in kf  # sanity: key is compact, not dict string
    kq = _cache_key_for_query(model_id="m", dim=256, text="hello")
    assert "query=" in kq
