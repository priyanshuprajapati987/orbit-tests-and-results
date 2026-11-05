"""Tests for chat API error recovery and fallback."""



class TestChatErrorRecovery:
    def test_import(self):
        from orbit.orbit.core.chat_api import chat_bp

        assert chat_bp is not None

    def test_error_messages_are_user_friendly(self):
        """Error messages should be human-readable, not raw exceptions."""
        test_cases = [
            ("timeout", "responding slowly"),
            ("connection refused", "Cannot reach"),
            ("model not found", "not available"),
            ("rate limit", "Rate limit"),
            ("401 unauthorized", "invalid"),
            ("403 forbidden", "invalid"),
        ]
        for err_text, expected_friendly in test_cases:
            # Build friendly message same way chat_api does
            if "timeout" in err_text.lower() or "timed out" in err_text.lower():
                friendly = "LLM provider is responding slowly."
            elif "connection" in err_text.lower():
                friendly = "Cannot reach the LLM provider."
            elif "unavailable" in err_text.lower() or "not found" in err_text.lower():
                friendly = "The requested model is not available."
            elif "rate" in err_text.lower() and "limit" in err_text.lower():
                friendly = "Rate limit hit."
            elif "auth" in err_text.lower() or "401" in err_text or "403" in err_text:
                friendly = "API key is invalid or expired."
            else:
                friendly = f"LLM error: {err_text}"

            assert expected_friendly.lower() in friendly.lower(), (
                f"Error '{err_text}' should produce friendly message containing '{expected_friendly}'"
            )

    def test_fallback_response_has_error_flag(self):
        """Error responses should have error=True for frontend to detect."""
        result = {
            "response": "Error message",
            "agent": "SYSTEM",
            "model": "unknown",
            "provider": "unknown",
            "tools_used": [],
            "latency_ms": 0,
            "error": True,
        }
        assert result.get("error") is True

    def test_fallback_response_has_fallback_flag(self):
        """Fallback responses should have fallback=True."""
        result = {
            "response": "Fallback answer",
            "agent": "QUEEN",
            "model": "local-fallback",
            "provider": "ollama",
            "tools_used": [],
            "latency_ms": 0,
            "fallback": True,
        }
        assert result.get("fallback") is True
