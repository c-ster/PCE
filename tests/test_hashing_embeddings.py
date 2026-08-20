import math

from pce.providers.hashing_embeddings import HashingEmbeddingProvider


def test_embed_is_deterministic_across_instances():
    a = HashingEmbeddingProvider().embed(["hello world"])[0]
    b = HashingEmbeddingProvider().embed(["hello world"])[0]
    assert a == b


def test_vectors_are_l2_normalized():
    [vector] = HashingEmbeddingProvider().embed(["some reasonably long piece of text"])
    norm = math.sqrt(sum(v * v for v in vector))
    assert math.isclose(norm, 1.0, abs_tol=1e-9)


def test_empty_text_yields_zero_vector():
    [vector] = HashingEmbeddingProvider().embed([""])
    assert vector == [0.0] * HashingEmbeddingProvider().dimensions


def test_shared_vocabulary_scores_more_similar_than_disjoint_vocabulary():
    provider = HashingEmbeddingProvider()
    base, similar, different = provider.embed(
        [
            "the price for the nightingale project is five thousand dollars",
            "the nightingale project price was approved at five thousand",
            "sourdough bread needs a long slow overnight rise",
        ]
    )

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b))  # already normalized

    assert cosine(base, similar) > cosine(base, different)


def test_respects_custom_dimensions():
    provider = HashingEmbeddingProvider(dimensions=32)
    [vector] = provider.embed(["anything"])
    assert len(vector) == 32
