from invoice_extraction.utils.cache import InMemoryCache, cache_key


def test_cache_key_is_stable_for_same_inputs():
    assert cache_key("v1", "agent1_output", "some text") == cache_key("v1", "agent1_output", "some text")


def test_cache_key_differs_for_different_inputs():
    assert cache_key("v1", "agent1_output", "text a") != cache_key("v1", "agent1_output", "text b")
    assert cache_key("v1", "agent1_output", "text a") != cache_key("v1", "agent2_output", "text a")
    assert cache_key("v1", "agent1_output", "text a") != cache_key("v2", "agent1_output", "text a")


def test_cache_key_avoids_concatenation_collisions():
    # "ab" + "c" must not equal "a" + "bc" once combined naively
    assert cache_key("ab", "c") != cache_key("a", "bc")


def test_in_memory_cache_get_set_roundtrip():
    cache = InMemoryCache()
    key = cache_key("v1", "agent1_output", "invoice text")
    assert cache.get(key) is None
    cache.set(key, [{"a": 1}])
    assert cache.get(key) == [{"a": 1}]


def test_in_memory_cache_tracks_hit_rate():
    cache = InMemoryCache()
    key = cache_key("v1", "agent1_output", "invoice text")
    cache.get(key)  # miss
    cache.set(key, [{"a": 1}])
    cache.get(key)  # hit
    cache.get(key)  # hit
    stats = cache.stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 2
    assert stats["hit_rate"] == round(2 / 3, 4)


def test_in_memory_cache_evicts_when_full():
    cache = InMemoryCache(max_entries=2)
    cache.set("k1", [{"a": 1}])
    cache.set("k2", [{"a": 2}])
    cache.set("k3", [{"a": 3}])  # should evict k1
    assert cache.stats()["size"] == 2
    assert cache.get("k3") == [{"a": 3}]
