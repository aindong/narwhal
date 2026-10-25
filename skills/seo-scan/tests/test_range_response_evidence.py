"""Only successful range responses can supply image-probe bytes."""
from pathlib import Path
import struct
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib import htmlx, http, images
from lib.report import Report

URL = 'https://example.test/card.png'
PNG = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 1200, 630)


class ProbeError(OSError):
    pass


class TestRangeResponseEvidence(unittest.TestCase):
    def test_non_2xx_responses_are_closed_without_reading_or_returning_bytes(self):
        client = types.SimpleNamespace(RequestException=ProbeError)
        for status in (199, 300, 301, 304, 399, 400, 403, 404, 429, 500, 599):
            response = mock.Mock(status_code=status)
            response.iter_content.side_effect = AssertionError('Error body must remain unread')
            with self.subTest(status=status), mock.patch.dict(sys.modules, {'requests': client}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, '_requests_safe', autospec=True, return_value=(response, URL, [])):
                self.assertEqual((None, 'HTTP ' + str(status)), http.fetch_range(URL, 24))
                response.close.assert_called_once()
                response.iter_content.assert_not_called()

    def test_successful_2xx_prefixes_keep_their_budget_and_close(self):
        client = types.SimpleNamespace(RequestException=ProbeError)
        for status in (200, 206, 299):
            response = mock.Mock(status_code=status)
            response.iter_content.return_value = [b'ab', b'cdef']
            with self.subTest(status=status), mock.patch.dict(sys.modules, {'requests': client}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, '_requests_safe', autospec=True, return_value=(response, URL, [])):
                self.assertEqual((b'abc', None), http.fetch_range(URL, 3))
                response.close.assert_called_once()

    def test_png_looking_error_body_cannot_make_social_image_look_healthy(self):
        doc = htmlx.parse('<meta property="og:image" content="/card.png">', base_url=URL)
        for status in (206, 304, 404, 500):
            response = mock.Mock(status_code=status)
            response.iter_content.return_value = [PNG]
            with self.subTest(status=status), \
                    mock.patch.dict(sys.modules, {'requests': types.SimpleNamespace(RequestException=ProbeError)}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, '_requests_safe', autospec=True, return_value=(response, URL, [])):
                facts = images.audit_images(doc, URL, head_info=lambda *args, **kwargs: (200, {'content-type': 'image/png'}, None))
                report = Report(URL)
                images.findings(facts, report)
                self.assertEqual((1200, 630) if status == 206 else None, facts['og_image']['dimensions'])
                self.assertEqual(status == 206, 'og:image looks healthy' in [f.title for f in report.findings])
                response.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
