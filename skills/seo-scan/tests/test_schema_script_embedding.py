"""Generated JSON-LD must remain data when pasted into an HTML script element."""
import contextlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_schema
import mcp_server

PAYLOADS = (
    '</script><script>window.narwhalProbe=1</script>',
    '</ScRiPt ><img src="https://example.invalid/probe" onerror="window.narwhalProbe=1">',
    '<!--<script>literal & < comparison > and café\u2028text',
)


class ScriptElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.scripts = []
        self.inside = False

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == 'script':
            self.inside = True
            self.scripts.append('')

    def handle_endtag(self, tag):
        if tag == 'script':
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.scripts[-1] += data


def generate(fields, raw=False):
    args = ['Article', '--no-recommended']
    for key, value in fields.items():
        args += ['--field', key + '=' + value]
    if raw:
        args.append('--raw')
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = generate_schema.main(args)
    assert code == 0
    return out.getvalue()


class TestSchemaScriptEmbedding(unittest.TestCase):
    def test_script_delimiters_cannot_create_other_html_elements(self):
        for payload in PAYLOADS:
            with self.subTest(payload=payload):
                output = generate({'headline': payload})
                parsed = ScriptElements()
                parsed.feed(output)
                self.assertEqual([('script', {'type': 'application/ld+json'})], parsed.tags)
                self.assertEqual(1, len(parsed.scripts))
                self.assertEqual(payload, json.loads(parsed.scripts[0])['headline'])
                self.assertNotIn('<', parsed.scripts[0])

    def test_nested_values_and_property_names_round_trip_without_html_escaping(self):
        value = {'</script>': [PAYLOADS[0], {'description': PAYLOADS[1]}]}
        fields = {'headline': 'A "quoted" title & café', 'extra': json.dumps(value)}
        parsed = ScriptElements()
        parsed.feed(generate(fields))
        self.assertEqual(generate_schema.build('Article', fields, include_recommended=False),
                         json.loads(parsed.scripts[0]))
        self.assertEqual(1, len(parsed.tags))
        self.assertNotIn('&lt;', parsed.scripts[0])

    def test_raw_json_and_mcp_object_preserve_original_values(self):
        for payload in PAYLOADS:
            raw = generate({'headline': payload}, raw=True)
            self.assertEqual(payload, json.loads(raw)['headline'])
            self.assertIn(json.dumps(payload, ensure_ascii=False), raw)
            self.assertEqual(payload, mcp_server._schema('Article', {'headline': payload})['headline'])

    def test_todo_warning_and_ordinary_script_format_remain(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(0, generate_schema.main(['Product']))
        self.assertTrue(out.getvalue().startswith('<script type="application/ld+json">\n{'))
        self.assertTrue(out.getvalue().endswith('\n</script>\n'))
        self.assertIn('replace all TODO placeholders', err.getvalue())
        parsed = ScriptElements()
        parsed.feed(out.getvalue())
        self.assertEqual('Product', json.loads(parsed.scripts[0])['@type'])


if __name__ == '__main__':
    unittest.main()
