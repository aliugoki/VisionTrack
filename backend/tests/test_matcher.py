"""Pure-logic tests for the P2.5 matcher's centroid + similarity math.

No DB / Redis / Milvus — these exercise the deterministic vector helpers in
isolation. The full consumer->writer->matcher->API integration is covered by
the manual end-to-end seed test documented in the plan (and verified against
the running stack).
"""

import math

from app.modules.persons.matcher import (
    _l2_normalize,
    cosine_similarity,
    update_centroid,
)

DIM = 512


def _basis(i: int, dim: int = DIM) -> list[float]:
    v = [0.0] * dim
    v[i] = 1.0
    return v


def _is_unit(v: list[float]) -> bool:
    return math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, abs_tol=1e-9)


def test_l2_normalize_makes_unit_vector():
    v = [3.0, 4.0]  # norm 5
    out = _l2_normalize(v)
    assert out == [0.6, 0.8]
    assert _is_unit(out)


def test_l2_normalize_zero_vector_is_safe():
    assert _l2_normalize([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]


def test_cosine_similarity_orthogonal_and_identical():
    a, b = _basis(0), _basis(1)
    assert math.isclose(cosine_similarity(a, b), 0.0, abs_tol=1e-9)   # orthogonal
    assert math.isclose(cosine_similarity(a, a), 1.0, abs_tol=1e-9)   # identical
    # threshold decision: identical clusters merge, orthogonal don't (0.65)
    assert cosine_similarity(a, a) >= 0.65
    assert cosine_similarity(a, b) < 0.65


def test_update_centroid_stays_unit_and_pulls_toward_new_vector():
    # Start at basis-0; fold in basis-1 with equal weight.
    c0, w0 = _basis(0), 1.0
    c1 = update_centroid(c0, w0, _basis(1), 1.0)
    assert _is_unit(c1)
    # Equal weights -> centroid is the normalized [1,1,0,...] = 1/sqrt(2) each.
    assert math.isclose(c1[0], 1 / math.sqrt(2), abs_tol=1e-9)
    assert math.isclose(c1[1], 1 / math.sqrt(2), abs_tol=1e-9)


def test_update_centroid_respects_weight():
    # Heavy existing weight should keep the centroid close to its prior axis.
    c0, w0 = _basis(0), 100.0
    c1 = update_centroid(c0, w0, _basis(1), 1.0)
    assert c1[0] > 0.99          # barely moved off axis 0
    assert 0.0 < c1[1] < 0.02
    assert _is_unit(c1)


def test_clustering_decision_end_to_end_math():
    """Simulate the matcher's per-row decision over 3 well-separated clusters,
    asserting the same outcome the DB integration produced (3 identities)."""
    threshold = 0.65
    centroids: list[tuple[list[float], float]] = []  # (centroid, weight_sum)
    samples = []
    for cluster in range(3):
        for _ in range(4):
            samples.append(_basis(cluster))  # 4 identical samples per cluster

    for v in samples:
        v = _l2_normalize(v)
        best_i, best_sim = -1, -1.0
        for i, (c, _w) in enumerate(centroids):
            sim = cosine_similarity(c, v)
            if sim > best_sim:
                best_i, best_sim = i, sim
        if best_i >= 0 and best_sim >= threshold:
            c, w = centroids[best_i]
            centroids[best_i] = (update_centroid(c, w, v, 0.9), w + 0.9)
        else:
            centroids.append((_l2_normalize(v), 0.9))

    assert len(centroids) == 3                       # 3 identities
    assert all(math.isclose(w, 3.6, abs_tol=1e-9) for _, w in centroids)  # 4*0.9
    assert all(_is_unit(c) for c, _ in centroids)
