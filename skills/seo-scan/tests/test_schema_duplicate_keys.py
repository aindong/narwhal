"""Ambiguous schema input must not silently choose a price or lose a field."""
import contextlib
import copy
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_schema as schema
import mcp_server


class TestSchemaDuplicateKeys(unittest.TestCase):
    def test_flat_nested_escaped_array_and_identical_duplicates_are_rejected(self):
        for value in ('{"price":99,"price":9}',
                      '{"seller":{"name":"A","name":"B"}}',
                      r'{"price":99,"\u0070rice":9}',
                      '[{"price":99,"price":9}]',
                      '{"price":9,"price":9}',
                      '{"secret-token":1,"secret-token":2}'):
            fields = {'name': 'Widget', 'offers': value}
            original = copy.deepcopy(fields)
            for generate in (schema.build, mcp_server._schema):
                with self.subTest(value=value, generate=generate.__name__):
                    with self.assertRaisesRegex(ValueError, '(?i)duplicate') as caught:
                        generate('Product', fields)
                    self.assertNotIn('secret-token', str(caught.exception))
                    self.assertLess(len(str(caught.exception)), 250)
                    self.assertEqual(original, fields)
            for raw in (False, True):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = schema.main(['Product', '--field', 'offers=' + value] + (['--raw'] if raw else []))
                self.assertEqual(2, code)
                self.assertEqual('', out.getvalue())
                self.assertIn('duplicate', err.getvalue().lower())
                self.assertNotIn('secret-token', err.getvalue())

    def test_native_key_collisions_cannot_lose_data_during_json_detachment(self):
        for value in ({1: 'numeric', '1': 'string'},
                      {None: 'null', 'null': 'string'},
                      {False: 'boolean', 'false': 'string'}):
            with self.subTest(value=value):
                fields = {'offers': {'nested': value}}
                original = copy.deepcopy(fields)
                with self.assertRaisesRegex(ValueError, '(?i)(duplicate|colliding)'):
                    schema.build('Product', fields)
                self.assertEqual(original, fields)

    def test_distinct_objects_literal_text_and_noncolliding_keys_remain_usable(self):
        fields = {'name': 'Widget',
                  'offers': '[{"price":9},{"price":99}]',
                  'description': '{literal text}',
                  'disambiguatingDescription': '{"nested":{"price":99,"price":9},',
                  'additionalProperty': {'text': '{"price":99,"price":9}'},
                  'identifier': {1: 'numeric', 'other': 'string'}}
        original = copy.deepcopy(fields)
        result = schema.build('Product', fields, include_recommended=False)
        self.assertEqual([{'price': 9}, {'price': 99}], result['offers'])
        self.assertEqual(fields['description'], result['description'])
        self.assertEqual(fields['disambiguatingDescription'], result['disambiguatingDescription'])
        self.assertEqual(fields['additionalProperty'], result['additionalProperty'])
        self.assertEqual({'1': 'numeric', 'other': 'string'}, result['identifier'])
        self.assertEqual(original, fields)
        result['offers'][0]['price'] = 123
        self.assertEqual([{'price': 9}, {'price': 99}],
                         schema.build('Product', fields, include_recommended=False)['offers'])


if __name__ == '__main__':
    unittest.main()
