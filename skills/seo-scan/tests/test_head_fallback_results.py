"""A rejected HEAD cannot replace the outcome of its fallback GET."""
import io
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import validate_sitemap as sitemap
from lib import http, links

URL = 'https://example.test/target'
XML = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.test/target</loc></url></urlset>'


class ProbeError(OSError):
    pass


class TestHeadFallbackResults(unittest.TestCase):
    def setUp(self):
        for target in ('socket.getaddrinfo', 'socket.socket.connect'):
            patcher = mock.patch(target, side_effect=AssertionError('Unexpected network access'))
            blocked = patcher.start()
            self.addCleanup(patcher.stop)
            self.addCleanup(blocked.assert_not_called)

    def probe(self, backend, head_status, outcome):
        bodies = []
        methods = []
        def opened(*args, **kwargs):
            method = args[1] if backend == 'requests' else kwargs['method']
            methods.append(method)
            status = head_status if method == 'HEAD' else outcome
            if isinstance(status, Exception):
                raise status
            body = mock.Mock(wraps=io.BytesIO(b'unread response body'))
            bodies.append(body)
            if backend == 'requests':
                body.status_code = status
            else:
                if status >= 300:
                    raise HTTPError(URL, status, 'origin detail', {}, body)
                body.status = status
                body.__enter__ = mock.Mock(return_value=body)
                body.__exit__ = mock.Mock(side_effect=lambda *args: body.close())
            return body, URL, []
        client = types.SimpleNamespace(RequestException=ProbeError) if backend == 'requests' else None
        helper = '_requests_safe' if backend == 'requests' else '_urllib_safe_open'
        with mock.patch.dict(sys.modules, {'requests': client}), \
                mock.patch.object(http, 'assert_public_host'), \
                mock.patch.object(http, helper, autospec=True, side_effect=opened):
            result = http.head(URL)
        self.assertEqual(['HEAD', 'GET'], methods)
        for body in bodies:
            body.close.assert_called_once()
            body.read.assert_not_called()
        return result

    def test_backends_report_the_get_http_status_after_each_head_rejection(self):
        cases = ((200, 'successful_2xx'), (204, 'successful_2xx'), (399, 'unverified'),
                 (400, 'broken'), (401, 'unverified'), (403, 'unverified'),
                 (404, 'broken'), (405, 'broken'), (410, 'broken'),
                 (429, 'unverified'), (451, 'unverified'), (500, 'broken'),
                 (501, 'broken'), (503, 'broken'), (999, 'unverified'))
        for backend in ('requests', 'urllib'):
            for head_status in (403, 405, 501):
                for status, state in cases:
                    with self.subTest(backend=backend, head=head_status, get=status):
                        result = self.probe(backend, head_status, status)
                        self.assertEqual((status, None), result)
                        self.assertEqual(state, links.http_check_state(*result))

    def test_failed_get_is_unverified_with_a_controlled_error_in_both_backends(self):
        for backend in ('requests', 'urllib'):
            for head_status in (403, 405, 501):
                for error in (ProbeError, http.SSRFError, ValueError):
                    with self.subTest(backend=backend, head=head_status, error=error.__name__):
                        result = self.probe(backend, head_status, error('origin detail'))
                        self.assertEqual((0, error.__name__), result)
                        self.assertEqual('unverified', links.http_check_state(*result))

    def test_sitemap_uses_real_fallback_outcomes_for_response_coverage(self):
        for outcome, state in ((404, 'broken'), (ProbeError('origin detail'), 'unverified')):
            bodies = []
            def opened(url, **kwargs):
                status = 405 if kwargs['method'] == 'HEAD' else outcome
                if isinstance(status, Exception):
                    raise status
                body = io.BytesIO(b'unread error body')
                bodies.append(body)
                raise HTTPError(url, status, 'origin detail', {}, body)
            with self.subTest(state=state), mock.patch.dict(sys.modules, {'requests': None}), \
                    mock.patch.object(http, 'assert_public_host'), \
                    mock.patch.object(http, 'fetch_bytes', return_value=(XML, None)), \
                    mock.patch.object(http, '_urllib_safe_open', autospec=True, side_effect=opened):
                result = sitemap.analyze('https://example.test/sitemap.xml', sample=1)
                self.assertEqual(1, result['sample_response_coverage'][state])
                self.assertEqual(0, result['sample_response_coverage']['successful_2xx'])
                self.assertEqual(404 if state == 'broken' else 0, result['sample'][0]['status'])
                self.assertEqual(None if state == 'broken' else 'ProbeError', result['sample'][0]['error'])
                self.assertTrue(all(body.closed for body in bodies))


if __name__ == '__main__':
    unittest.main()
