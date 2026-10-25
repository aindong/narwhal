"""Shared and IPv6 site-local addresses require the explicit private-host opt-in."""
from pathlib import Path
from contextlib import ExitStack
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from lib import http

SHARED = ('100.64.0.0', '100.100.100.100', '100.127.255.255')
SITE_LOCAL = ('fec0::', 'fec0::1', 'feff:ffff:ffff:ffff:ffff:ffff:ffff:ffff')
PUBLIC = ('100.63.255.255', '100.128.0.0', '8.8.8.8', '2606:4700:4700::1111')
URL = 'https://example.test/document'


def answer(ip):
    family = socket.AF_INET6 if ':' in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, 443))


class TestNonpublicHostGuard(unittest.TestCase):
    def test_shared_range_boundaries_and_site_local_ipv6_are_blocked(self):
        for ip in SHARED + SITE_LOCAL:
            with self.subTest(ip=ip):
                self.assertTrue(http._is_blocked_ip(ip))

    def test_public_neighbors_and_global_controls_remain_allowed(self):
        for ip in PUBLIC:
            with self.subTest(ip=ip):
                self.assertFalse(http._is_blocked_ip(ip))

    def test_existing_private_reserved_multicast_and_invalid_controls_remain_blocked(self):
        for ip in ('127.0.0.1', '10.0.0.1', '192.168.1.1', '169.254.1.1',
                   '224.0.0.1', '0.0.0.0', '::1', '::', 'fd00::1', 'fe80::1',
                   'ff02::1', '::ffff:100.100.100.100', '4000::1', '8000::1', 'not an IP'):
            with self.subTest(ip=ip):
                self.assertTrue(http._is_blocked_ip(ip))

    def test_any_nonpublic_dns_answer_rejects_the_host_regardless_of_order(self):
        for ip in SHARED + SITE_LOCAL:
            for ips in ((PUBLIC[2], ip), (ip, PUBLIC[2])):
                with self.subTest(ips=ips), mock.patch.object(http.socket, 'getaddrinfo', return_value=[answer(v) for v in ips]):
                    with self.assertRaises(http.SSRFError):
                        http.assert_public_host(URL)

    def test_explicit_private_opt_in_skips_dns_without_changing_public_controls(self):
        with mock.patch.object(http.socket, 'getaddrinfo', side_effect=AssertionError('No DNS with opt-in')):
            self.assertIsNone(http.assert_public_host(URL, allow_private=True))
        with mock.patch.object(http.socket, 'getaddrinfo', return_value=[answer(v) for v in PUBLIC]) as dns:
            self.assertIsNone(http.assert_public_host(URL))
            self.assertEqual(1, dns.call_count)
            self.assertEqual('example.test', dns.call_args[0][0])

    def test_primary_fetch_is_rejected_before_either_transport_or_browser(self):
        for ip in (SHARED[1], SITE_LOCAL[1]):
            with self.subTest(ip=ip), \
                    mock.patch.object(http.socket, 'getaddrinfo', return_value=[answer(ip)]), \
                    mock.patch.object(http, '_fetch_requests') as requests, \
                    mock.patch.object(http, '_fetch_urllib') as urllib, \
                    mock.patch.object(http, '_try_render') as browser:
                with self.assertRaises(http.SSRFError):
                    http.fetch(URL, render=True)
                requests.assert_not_called(); urllib.assert_not_called(); browser.assert_not_called()

    def test_redirect_targets_are_rejected_before_a_second_request(self):
        for ip in (SHARED[1], SITE_LOCAL[1]):
            target = 'http://' + ('[' + ip + ']' if ':' in ip else ip) + '/internal'
            redirect = mock.Mock(is_redirect=True, is_permanent_redirect=False, headers={'location': target})
            transport = mock.Mock()
            transport.request.return_value = redirect
            with self.subTest(ip=ip), mock.patch.object(http.socket, 'getaddrinfo', return_value=[answer(ip)]):
                with self.assertRaises(http.SSRFError):
                    http._requests_safe(transport, 'GET', URL, timeout=1, headers={}, allow_private=False)
                transport.request.assert_called_once()
                redirect.close.assert_called_once()
                self.assertEqual(target, http._redirect_target(URL, target, allow_private=True))

    def test_optional_resource_checks_return_guard_errors_without_transport_io(self):
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(http.socket, 'getaddrinfo', return_value=[answer(SHARED[1])]))
            transports = [stack.enter_context(mock.patch.object(http, name)) for name in
                          ('_requests_safe', '_urllib_safe_open', '_head_requests', '_head_urllib')]
            self.assertEqual(0, http.head(URL)[0])
            self.assertEqual(0, http.head_info(URL)[0])
            self.assertIsNone(http.fetch_range(URL, 16)[0])
            self.assertIsNone(http.fetch_bytes(URL)[0])
            for transport in transports:
                transport.assert_not_called()


class TestEmptyHostResolution(unittest.TestCase):
    def test_missing_host_is_rejected_before_dns_with_a_useful_reason(self):
        with mock.patch.object(http.socket, 'getaddrinfo') as dns:
            with self.assertRaises(http.SSRFError) as error:
                http.assert_public_host('https:///document')
        self.assertIn('no host', str(error.exception).casefold())
        dns.assert_not_called()

    def test_empty_resolution_is_a_controlled_error_without_url_credentials(self):
        with mock.patch.object(http.socket, 'getaddrinfo', return_value=[]):
            with self.assertRaisesRegex(http.SSRFError, 'no addresses') as error:
                http.assert_public_host('https://fixture:canary_password@example.test/document')
        self.assertNotIn('canary_password', str(error.exception))
        self.assertNotIn('fixture:', str(error.exception))

    def test_primary_fetch_rejects_empty_answers_before_transports_or_browser(self):
        response = http.Response(URL, URL, 200, {}, '<html></html>', 0)
        for render in (False, True):
            with self.subTest(render=render), \
                    mock.patch.object(http.socket, 'getaddrinfo', return_value=[]), \
                    mock.patch.object(http, '_fetch_requests', return_value=response) as requests, \
                    mock.patch.object(http, '_fetch_urllib', return_value=response) as urllib, \
                    mock.patch.object(http, '_try_render', return_value=response) as browser:
                with self.assertRaises(http.SSRFError):
                    http.fetch(URL, render=render)
                requests.assert_not_called(); urllib.assert_not_called(); browser.assert_not_called()

    def test_resource_checks_return_empty_resolution_errors_without_io(self):
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(http.socket, 'getaddrinfo', return_value=[]))
            transports = [stack.enter_context(mock.patch.object(http, name)) for name in
                          ('_requests_safe', '_urllib_safe_open', '_head_requests', '_head_urllib')]
            for outcome in (http.head(URL), http.head_info(URL), http.fetch_range(URL, 16), http.fetch_bytes(URL)):
                self.assertIn('no addresses', outcome[-1])
            for transport in transports:
                transport.assert_not_called()

    def test_redirect_empty_resolution_stops_after_first_response(self):
        response = mock.Mock(is_redirect=True, is_permanent_redirect=False, headers={'location': '/next'})
        final = mock.Mock(is_redirect=False, is_permanent_redirect=False)
        transport = mock.Mock()
        transport.request.side_effect = [response, final]
        with mock.patch.object(http.socket, 'getaddrinfo', return_value=[]):
            with self.assertRaises(http.SSRFError):
                http._requests_safe(transport, 'GET', URL, timeout=1, headers={}, allow_private=False)
        transport.request.assert_called_once()
        response.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
