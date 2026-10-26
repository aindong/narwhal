"""Schema tools preserve JSON data and isolate separate callers/results."""
import contextlib
import asyncio
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_schema as schema
import mcp_server


class TestSchemaJsonFields(unittest.TestCase):
    def setUp(self):
        original = copy.deepcopy(schema.STRUCT_PLACEHOLDER)
        self.addCleanup(self.restore_templates, original)

    @staticmethod
    def restore_templates(original):
        schema.STRUCT_PLACEHOLDER.clear()
        schema.STRUCT_PLACEHOLDER.update(original)

    def test_mcp_preserves_nested_offers_lists_numbers_booleans_and_null(self):
        fields = {'name': 'Widget', 'offers': {'@type': 'Offer', 'price': 12.5,
                  'priceCurrency': 'USD', 'eligibleQuantity': {'@type': 'QuantitativeValue', 'minValue': 1}},
                  'additionalProperty': [{'@type': 'PropertyValue', 'name': 'Tracked', 'value': False}],
                  'isAccessibleForFree': True, 'identifier': None}
        before = copy.deepcopy(fields)
        result = mcp_server._schema('Product', fields)
        for key, value in fields.items():
            self.assertEqual(value, result[key])
            self.assertIs(type(value), type(result[key]))
        self.assertEqual(before, fields)
        self.assertEqual(result, json.loads(json.dumps(result, allow_nan=False)))

    def test_python_build_accepts_json_values_and_detaches_both_directions(self):
        fields = {'offers': {'@type': 'Offer', 'price': 10, 'priceCurrency': 'USD'},
                  'additionalProperty': [{'value': True}]}
        expected = copy.deepcopy(fields)
        result = schema.build('Product', fields)
        result['offers']['price'] = 20
        result['additionalProperty'][0]['value'] = False
        self.assertEqual(expected, fields)
        fields['offers']['price'] = 30
        self.assertEqual(20, result['offers']['price'])
        another = schema.build('Product', expected)
        self.assertEqual(expected['offers'], another['offers'])

    def test_placeholder_mutation_cannot_change_templates_or_later_results(self):
        cases = [('Product', 'offers'), ('Article', 'author'),
                 ('LocalBusiness', 'address'), ('BreadcrumbList', 'itemListElement')]
        for type_name, key in cases:
            with self.subTest(type_name=type_name):
                expected = copy.deepcopy(schema.STRUCT_PLACEHOLDER[key])
                first = schema.build(type_name, {})
                if key == 'offers':
                    first[key]['seller']['name'] = 'Earlier caller'
                elif isinstance(first[key], list):
                    first[key][0]['name'] = 'Earlier caller'
                else:
                    first[key]['name'] = 'Earlier caller'
                self.assertEqual(expected, schema.STRUCT_PLACEHOLDER[key])
                self.assertEqual(expected, schema.build(type_name, {})[key])

    def test_mcp_results_do_not_share_placeholder_state(self):
        first = mcp_server._schema('Product', {})
        original = copy.deepcopy(first['offers'])
        first['offers']['seller']['name'] = 'Earlier request'
        self.assertEqual(original, mcp_server._schema('Product', {})['offers'])

    def test_legacy_string_interpretation_is_preserved(self):
        fields = {'offers': '{"@type":"Offer","price":10}', 'identifier': '007',
                  'description': '{literal text}', 'isAccessibleForFree': 'true'}
        result = schema.build('Product', fields)
        self.assertEqual({'@type': 'Offer', 'price': 10}, result['offers'])
        self.assertEqual('007', result['identifier'])
        self.assertEqual('{literal text}', result['description'])
        self.assertEqual('true', result['isAccessibleForFree'])

    def test_nonfinite_and_unserializable_values_fail_as_value_errors(self):
        cycle = []
        cycle.append(cycle)
        for value in (float('nan'), float('inf'), {'price': float('-inf')}, {1, 2}, cycle,
                      '\ud800', {'\ud800': 'invalid key'}):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(ValueError, '(?i)JSON-compatible'):
                    schema.build('Product', {'offers': value})
        self.assertIn('TODO', schema.build('Product', {})['offers']['price'])

    def test_cli_emits_no_artifact_for_nonfinite_or_parser_limit_failures(self):
        values = ['{"price":NaN}', '{"price":Infinity}', r'{"description":"\ud800"}']
        for value in values:
            for raw in (False, True):
                out, err = io.StringIO(), io.StringIO()
                args = ['Product', '--field', 'offers=' + value] + (['--raw'] if raw else [])
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = schema.main(args)
                self.assertEqual(2, code)
                self.assertEqual('', out.getvalue())
                self.assertTrue(err.getvalue().startswith('Error: '))
                self.assertLess(len(err.getvalue()), 300)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(schema.json, 'loads', side_effect=RecursionError), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = schema.main(['Product', '--field', 'offers=[]'])
        self.assertEqual(2, code)
        self.assertEqual('', out.getvalue())
        self.assertIn('supported parser limits', err.getvalue())

    def test_stdio_tool_preserves_json_and_recovers_after_invalid_type_when_sdk_present(self):
        try:
            __import__('mcp')
        except ImportError:
            self.skipTest('Optional MCP client SDK is not installed')
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        def node(result):
            wire = result.model_dump(by_alias=True)
            self.assertFalse(wire['isError'])
            if wire['structuredContent'] is not None:
                return wire['structuredContent']
            return json.loads(next(item['text'] for item in wire['content'] if item['type'] == 'text'))

        async def exercise(errors):
            params = StdioServerParameters(command=sys.executable, args=[str(Path(mcp_server.__file__).resolve())])
            async with stdio_client(params, errlog=errors) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    fields = {'name': 'Widget', 'offers': {'@type': 'Offer', 'price': 12.5, 'priceCurrency': 'USD'},
                              'isAccessibleForFree': False, 'identifier': None}
                    generated = node(await session.call_tool('generate_schema', {'type': 'Product', 'fields': fields}))
                    for key, value in fields.items():
                        self.assertEqual(value, generated[key])
                        self.assertIs(type(value), type(generated[key]))
                    rejected = await session.call_tool('generate_schema', {'type': 'Unsupported', 'fields': {}})
                    self.assertTrue(rejected.model_dump(by_alias=True)['isError'])
                    ambiguous = await session.call_tool('generate_schema', {
                        'type': 'Product', 'fields': {'offers': '{"secret-token":99,"secret-token":9}'}})
                    wire = ambiguous.model_dump(by_alias=True)
                    self.assertTrue(wire['isError'])
                    diagnostic = ' '.join(item['text'] for item in wire['content'] if item['type'] == 'text')
                    self.assertIn('duplicate', diagnostic.lower())
                    self.assertNotIn('secret-token', diagnostic)
                    self.assertLess(len(diagnostic), 500)
                    again = node(await session.call_tool('generate_schema', {'type': 'Article', 'fields': {'headline': 'Still running'}}))
                    self.assertEqual('Still running', again['headline'])

        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as errors:
            asyncio.run(asyncio.wait_for(exercise(errors), timeout=20))

    def test_unsupported_mcp_type_is_recoverable_without_system_exit(self):
        with self.assertRaisesRegex(ValueError, 'supported'):
            mcp_server._schema('Unsupported', {})
        self.assertEqual('Article', mcp_server._schema('Article', {'headline': 'Next request'})['@type'])


if __name__ == '__main__':
    unittest.main()
