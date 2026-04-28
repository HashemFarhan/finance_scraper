import unittest

from extractors.consent_extractor import extract_consent_lines
from vision.llm_client import parse_json_response


class ConsentExtractorTests(unittest.TestCase):
    def test_extracts_by_clicking_language(self):
        text = """
        First name
        By clicking Submit, you agree to our Terms and Privacy Policy.
        Footer copy
        """

        self.assertEqual(
            extract_consent_lines(text),
            ["By clicking Submit, you agree to our Terms and Privacy Policy."],
        )

    def test_extracts_sentence_when_text_has_no_line_breaks(self):
        text = "Welcome. I agree to the Terms and Privacy Policy. Continue."

        self.assertEqual(
            extract_consent_lines(text),
            ["I agree to the Terms and Privacy Policy."],
        )

    def test_parse_json_response_accepts_fenced_json(self):
        payload = parse_json_response(
            """```json
            {"action":"click","text":"Get Started","confidence":0.82}
            ```"""
        )

        self.assertEqual(
            payload,
            {"action": "click", "text": "Get Started", "confidence": 0.82},
        )


if __name__ == "__main__":
    unittest.main()
