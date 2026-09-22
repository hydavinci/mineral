import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import patch, MagicMock
from http.server import HTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import metadata
import api


class MetadataTests(unittest.TestCase):
    def test_html_entities_and_multiline(self):
        self.assertEqual(metadata.parse_metadata(b'<TITLE> A &amp; B\n Library </TITLE><meta content="A &quot;quote&quot;" name="description">'), ('A & B Library', 'A "quote"'))

    def test_attribute_order_case_and_unquoted(self):
        self.assertEqual(metadata.parse_metadata(b'<META content="Book &amp; docs" PROPERTY="og:title"><meta content="Info" name=description>'), ('Book & docs', 'Info'))

    def test_ignore_svg_titles(self):
        self.assertEqual(metadata.parse_metadata(b'<head><title>Page</title></head><body><svg><title>Logo</title></svg></body>')[0], 'Page')
        self.assertEqual(metadata.parse_metadata(b'<body><svg><title>Logo</title></svg></body>')[0], '')

    def test_twitter_fallback(self):
        self.assertEqual(metadata.parse_metadata(b'<meta name="twitter:title" content="Twitter title"><meta property="og:description" content="Details">'), ('Twitter title', 'Details'))

    def test_gbk(self):
        self.assertEqual(metadata.parse_metadata('<meta charset=gbk><title>中文图书馆</title>'.encode('gbk'))[0], '中文图书馆')

    def test_http_charset(self):
        self.assertEqual(metadata.parse_metadata('<title>Café</title>'.encode('latin1'), 'iso-8859-1')[0], 'Café')

    def test_normalize(self):
        self.assertEqual(metadata.normalize_url(' example.com '), 'https://example.com/')
        self.assertEqual(metadata.normalize_url('https://example.com/a?q=1#x'), 'https://example.com/a?q=1')

    def test_invalid_urls(self):
        for value in ('', None, 123, 'file:///etc/passwd', 'ftp://example.com', 'https://user:pass@example.com', 'http://example.com:bad', 'http://example.com:22'):
            with self.subTest(value=value), self.assertRaises(metadata.InvalidURL):
                metadata.normalize_url(value)

    def test_private_addresses(self):
        for address in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '192.168.0.1'):
            with self.subTest(address=address), patch('socket.getaddrinfo', return_value=[(None, None, None, None, (address, 80))]):
                with self.assertRaises(metadata.InvalidURL):
                    metadata.validate_public_url('https://example.com')

    def test_redirect_guard(self):
        handler = metadata.PublicRedirectHandler()
        with patch('metadata.validate_public_url', side_effect=metadata.InvalidURL('private')):
            with self.assertRaises(metadata.InvalidURL):
                handler.redirect_request(urllib.request.Request('https://example.com'), None, 302, '', {}, 'http://127.0.0.1')

    def fetch_mock(self, html, content_type='text/html; charset=utf-8'):
        response = MagicMock()
        response.headers = Message()
        response.headers['Content-Type'] = content_type
        response.read.return_value = html
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with patch('metadata.validate_public_url'), patch('urllib.request.build_opener', return_value=opener):
            return metadata.fetch_metadata('example.com')

    def test_success(self):
        result = self.fetch_mock(b'<title>Real title</title>')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['title_source'], 'page')
        self.assertEqual(result['title'], 'Real title')

    def test_not_html(self):
        result = self.fetch_mock(b'PDF', 'application/pdf')
        self.assertEqual(result['status'], 'fallback')
        self.assertIn('HTML', result['warning'])

    def test_missing_title_and_challenge(self):
        for html in (b'<body>JS-only app</body>', b'<title>Just a moment...</title>'):
            result = self.fetch_mock(html)
            self.assertEqual(result['status'], 'fallback')
            self.assertEqual(result['title'], 'example.com')
            self.assertIn('warning', result)

    def test_upstream_error(self):
        with patch('metadata.validate_public_url'), patch('urllib.request.build_opener') as builder:
            builder.return_value.open.side_effect = urllib.error.HTTPError('https://example.com', 503, 'down', {}, io.BytesIO())
            result = metadata.fetch_metadata('example.com')
        self.assertEqual(result['status'], 'fallback')
        self.assertIn('503', result['warning'])
        self.assertEqual(result['description'], '')


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), api.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, body, auth=True):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + api.API_TOKEN
        request = urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/api/fetch-meta', data=body, headers=headers)
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    def test_requires_auth(self):
        self.assertEqual(self.post(b'{}', auth=False)[0], 401)

    def test_bad_input(self):
        for body in (b'{', b'[]', b'{}', b'{"url": 1}', b'{"url":"file:///etc/passwd"}'):
            self.assertEqual(self.post(body)[0], 400)

    def test_endpoint_success(self):
        with patch('api.fetch_metadata', return_value={'url': 'https://example.com/', 'title': 'Example', 'description': '', 'status': 'ok', 'title_source': 'page'}):
            status, result = self.post(b'{"url":"example.com"}')
        self.assertEqual(status, 200)
        self.assertEqual(result['title'], 'Example')
        self.assertIn('category', result)


if __name__ == '__main__':
    unittest.main()
