import numpy as np
from unittest.mock import patch, MagicMock
from aicc_demo.assembly import Chunk
from aicc_demo.retrieval import Retriever


def _fake_encode(texts, **kwargs):
    vectors = []
    for text in texts:
        vec = np.zeros(3)
        if "needle" in text:
            vec[0] = 1.0
        if "suture" in text:
            vec[1] = 1.0
        if "wound" in text:
            vec[2] = 1.0
        vectors.append(vec)
    return np.array(vectors)


def test_query_returns_most_similar_chunk_first():
    chunks = [
        Chunk("Knot Tying", 0, "Hold the needle driver correctly.", "Knot Tying @ 0:00"),
        Chunk("Wound Care", 1, "Clean the wound thoroughly.", "Wound Care @ 0:10"),
    ]

    with patch("aicc_demo.retrieval.SentenceTransformer") as mock_st_cls:
        mock_model = MagicMock()
        mock_model.encode.side_effect = _fake_encode
        mock_st_cls.return_value = mock_model

        retriever = Retriever(chunks)
        results = retriever.query("how do I hold the needle")

    assert results[0][0].citation == "Knot Tying @ 0:00"
    assert results[0][1] > results[1][1]


def test_query_respects_top_k():
    chunks = [
        Chunk("A", 0, "needle text", "A @ 0:00"),
        Chunk("B", 1, "suture text", "B @ 0:00"),
        Chunk("C", 2, "wound text", "C @ 0:00"),
    ]

    with patch("aicc_demo.retrieval.SentenceTransformer") as mock_st_cls:
        mock_model = MagicMock()
        mock_model.encode.side_effect = _fake_encode
        mock_st_cls.return_value = mock_model

        retriever = Retriever(chunks)
        results = retriever.query("needle", top_k=2)

    assert len(results) == 2
