from unittest.mock import patch, MagicMock

import pytest

from aicc_demo.assembly import Chunk
from aicc_demo.generate import generate_answer


def _chunks():
    return [
        Chunk("Knot Tying", 0, "Hold the needle driver like a pencil.", "Knot Tying @ 0:00"),
        Chunk("Knot Tying", 1, "Keep your wrist relaxed while suturing.", "Knot Tying @ 0:15"),
    ]


def test_generate_answer_builds_prompt_with_question_and_chunks(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    with patch("aicc_demo.generate.genai") as mock_genai:
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "  You should hold it like a pencil (Knot Tying @ 0:00).  "
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        result = generate_answer("How do I hold the needle driver?", _chunks())

        mock_genai.configure.assert_called_once()
        mock_genai.GenerativeModel.assert_called_once_with("gemini-2.5-flash")

        assert mock_model.generate_content.call_count == 1
        prompt = mock_model.generate_content.call_args[0][0]
        assert "How do I hold the needle driver?" in prompt
        assert "Hold the needle driver like a pencil." in prompt
        assert "Keep your wrist relaxed while suturing." in prompt
        assert "Knot Tying @ 0:00" in prompt
        assert "Knot Tying @ 0:15" in prompt

        assert result == "You should hold it like a pencil (Knot Tying @ 0:00)."


def test_generate_answer_propagates_api_errors(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    with patch("aicc_demo.generate.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = RuntimeError("network error")
        mock_genai.GenerativeModel.return_value = mock_model

        with pytest.raises(RuntimeError, match="network error"):
            generate_answer("How do I hold the needle driver?", _chunks())
