"""Google Recipe base fields: name/image required; ingredients/steps recommended."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_schema
import generate_schema
import scan
from lib import config, htmlx, http
from lib.report import Report

URL = 'https://example.test/soup'
ORG = {'@type': 'Organization', 'name': 'Example', 'url': 'https://example.test',
       'logo': 'https://example.test/logo.png'}


def recipe():
    return {'@type': 'Recipe', 'name': 'Soup', 'image': 'https://example.test/soup.jpg',
            'recipeIngredient': ['Water'], 'recipeInstructions': ['Boil the water.'],
            'author': {'@type': 'Person', 'name': 'Cook'},
            'aggregateRating': {'@type': 'AggregateRating', 'ratingValue': '5', 'ratingCount': '2'}}


def page(node):
    return '<h1>Soup</h1><script type="application/ld+json">' + json.dumps([node, ORG]) + '</script>'


def inspect(html, parser=htmlx.parse, ignore=None):
    result = Report(URL, ignore=ignore)
    audit_schema.audit(parser(html, URL), None, result, {})
    return result


def problems(result):
    return {f.rule_id: f for f in result.findings if f.severity != 'good'}


class TestRecipeFields(unittest.TestCase):
    def test_name_and_image_only_do_not_get_false_required_ingredient_or_step_errors(self):
        result = inspect(page({'@type': 'Recipe', 'name': 'Soup', 'image': '/soup.jpg'}))
        self.assertEqual(99, result.score())
        self.assertFalse(any(f.severity == 'high' for f in result.findings))
        finding = problems(result)['schema.recipe.missing.recommended.properties']
        self.assertIn('recipeIngredient, recipeInstructions, author, aggregateRating', finding.detail)
        self.assertIn('do not invent authors or ratings', finding.recommendation)

    def test_missing_image_is_high_with_source_backed_narrow_scope(self):
        node = recipe(); del node['image']
        result = inspect(page(node))
        self.assertEqual(94, result.score())
        finding = problems(result)['schema.recipe.missing.required.image']
        self.assertEqual('high', finding.severity)
        self.assertIn('completed-dish image', finding.recommendation)
        self.assertIn('not full eligibility or schema.org validity', finding.recommendation)
        self.assertIn(audit_schema.RECIPE_SOURCE, finding.recommendation)

    def test_blank_required_values_are_not_disguised_as_present(self):
        for field in ('name', 'image'):
            for value in (None, '', ' \n ', [], {}, [None, ' '], {'@value': '', '@language': 'en'}):
                with self.subTest(field=field, value=value):
                    node = recipe(); node[field] = value
                    result = inspect(page(node))
                    self.assertEqual(94, result.score())
                    self.assertIn('schema.recipe.missing.required.' + field, problems(result))

    def test_missing_name_retains_its_historical_finding_id_and_ignore(self):
        node = recipe(); del node['name']
        result = inspect(page(node))
        self.assertIn('schema.recipe.missing.required.name', problems(result))
        cfg = config.Config({'ignore': {'titles': ["Recipe missing required 'name'"]}})
        self.assertEqual(100, inspect(page(node), ignore=cfg.is_ignored).score())

    def test_blank_recommended_fields_are_one_low_note_not_invalidity(self):
        node = recipe(); node.update(recipeIngredient=[], recipeInstructions={'@value': ' '}, author=None, aggregateRating={})
        result = inspect(page(node))
        self.assertEqual(99, result.score())
        self.assertEqual(['schema.recipe.missing.recommended.properties'], list(problems(result)))

    def test_complete_control_keeps_full_score(self):
        self.assertEqual(100, inspect(page(recipe())).score())

    def test_legacy_ingredient_and_instruction_optouts_stay_field_scoped(self):
        cfg = config.Config({'ignore': {'titles': ["Recipe missing required 'recipeIngredient'",
                                                  "Recipe missing required 'recipeInstructions'"]}})
        node = recipe(); del node['recipeIngredient']; del node['recipeInstructions']
        self.assertEqual(100, inspect(page(node), ignore=cfg.is_ignored).score())
        del node['author']
        finding = problems(inspect(page(node), ignore=cfg.is_ignored))['schema.recipe.missing.recommended.properties']
        self.assertIn('author', finding.detail)
        self.assertNotIn('recipeIngredient', finding.detail)
        self.assertNotIn('recipeInstructions', finding.detail)

    def test_recommendation_ignore_does_not_hide_new_required_image_check(self):
        cfg = config.Config({'ignore': {'titles': ['Recipe missing recommended properties']}})
        result = inspect(page({'@type': 'Recipe', 'name': 'Soup'}), ignore=cfg.is_ignored)
        self.assertEqual(['schema.recipe.missing.required.image'], list(problems(result)))

    def test_policy_is_dated_scoped_and_lists_unverified_conditional_requirements(self):
        node = recipe(); node['nutrition'] = {'@type': 'NutritionInformation', 'calories': '120 calories'}
        result = inspect(page(node))
        policy = result.meta['structured_data']['recipe_field_policy']
        self.assertEqual(['name', 'image'], policy['required_properties'])
        self.assertEqual(audit_schema.RECIPE_FIELDS, policy['checked_recommendations'])
        self.assertEqual('2026-10-12', policy['checked_on'])
        self.assertEqual(audit_schema.RECIPE_SOURCE, policy['source'])
        self.assertIn('not full eligibility or schema.org validity', policy['scope'])
        self.assertIn('conditional nutrition/yield and time relationships', policy['not_checked'])
        # A full score is not an eligibility verdict, and the unverified scope is explicit.
        self.assertEqual(100, result.score())

    def test_unknown_nonempty_references_shapes_and_datatypes_are_not_asserted_absent(self):
        for value in ({'@id': '#image'}, {'@type': 'ImageObject', 'url': '/soup.jpg'},
                      {'@value': '/soup.jpg', '@type': 'https://schema.org/URL'}, False, 0):
            node = recipe(); node['image'] = value
            self.assertNotIn('schema.recipe.missing.required.image', problems(inspect(page(node))))
        deep = None
        for _ in range(20): deep = [deep, None]
        node = recipe(); node['image'] = deep
        self.assertNotIn('schema.recipe.missing.required.image', problems(inspect(page(node))))
        # Singleton arrays normalize to their scalar: repeated [null] is proven blank.
        deep = None
        for _ in range(20): deep = [deep]
        node['image'] = deep
        self.assertIn('schema.recipe.missing.required.image', problems(inspect(page(node))))

    def test_generators_align_minimal_fields_and_preserve_explicit_and_default_scaffolds(self):
        default = generate_schema.build('Recipe', {})
        self.assertIn('(required)', default['image'])
        self.assertIn('(required)', default['name'])
        self.assertIn('recipeIngredient', default)
        self.assertIn('recipeInstructions', default)
        minimal = generate_schema.build('Recipe', {}, include_recommended=False)
        self.assertEqual({'@context', '@type', 'name', 'image'}, set(minimal))
        explicit = generate_schema.build('Recipe', {'name': 'Soup', 'image': '/soup.jpg',
                                                   'recipeIngredient': '["Water"]'}, include_recommended=False)
        self.assertEqual(['Water'], explicit['recipeIngredient'])
        self.assertEqual('/soup.jpg', explicit['image'])

    def test_jsonld_microdata_rdfa_and_backends_agree_on_missing_required_image(self):
        pages = ('<script type="application/ld+json">{"@type":"Recipe","name":"Soup"}</script>',
                 '<div itemscope itemtype="https://schema.org/Recipe"><h1 itemprop="name">Soup</h1></div>',
                 '<div vocab="https://schema.org/" typeof="Recipe"><h1 property="name">Soup</h1></div>')
        signatures = []
        for html in pages:
            results = [inspect(html, parser) for parser in (htmlx._parse_stdlib, htmlx.parse)]
            self.assertEqual([(f.rule_id, f.severity) for f in results[0].findings],
                             [(f.rule_id, f.severity) for f in results[1].findings])
            self.assertEqual(results[0].meta['structured_data']['recipe_field_policy'],
                             results[1].meta['structured_data']['recipe_field_policy'])
            signatures.append(set(problems(results[0])))
        self.assertEqual(signatures[0], signatures[1])
        self.assertEqual(signatures[0], signatures[2])

    def test_all_formats_name_image_only_have_recommendations_not_high_errors(self):
        pages = ('<script type="application/ld+json">{"@type":"Recipe","name":"Soup","image":"/soup.jpg"}</script>',
                 '<div itemscope itemtype="https://schema.org/Recipe"><h1 itemprop="name">Soup</h1><img itemprop="image" src="/soup.jpg"></div>',
                 '<div vocab="https://schema.org/" typeof="Recipe"><h1 property="name">Soup</h1><img property="image" src="/soup.jpg"></div>')
        for html in pages:
            for parser in (htmlx._parse_stdlib, htmlx.parse):
                result = inspect(html, parser)
                self.assertFalse(any(f.severity == 'high' for f in result.findings))
                self.assertIn('schema.recipe.missing.recommended.properties', problems(result))

    def test_duplicate_required_defects_score_once_across_formats(self):
        html = '<script type="application/ld+json">{"@type":"Recipe","name":"Soup"}</script>'
        html += '<div itemscope itemtype="https://schema.org/Recipe"><span itemprop="name">Soup</span></div>'
        html += '<div vocab="https://schema.org/" typeof="Recipe"><span property="name">Soup</span></div>'
        result = inspect(html)
        self.assertEqual(1, sum(f.rule_id == 'schema.recipe.missing.required.image' for f in result.findings))

    def test_article_event_and_howto_step_controls_are_not_changed_by_recipe_policy(self):
        for node in ({'@type': 'Article'}, {'@type': 'Event', 'name': 'Meetup'}, {'@type': 'HowToStep', 'text': 'Boil water.'}):
            result = inspect(page(node))
            self.assertNotIn('recipe_field_policy', result.meta['structured_data'])
            self.assertNotIn('schema.deprecated.rich.result.type.howto', problems(result))
        self.assertIn('schema.event.missing.required.startdate', problems(inspect(page({'@type': 'Event'}))))

    def test_html_and_scan_json_show_scope_without_fetching_source_or_image(self):
        html = page({'@type': 'Recipe', 'name': 'Soup'})
        rendered = inspect(html).to_html()
        for text in ('completed-dish image', 'do not invent authors or ratings',
                     'verify conditional, nested and image requirements separately', audit_schema.RECIPE_SOURCE):
            self.assertIn(text, rendered)
        response = http.Response(URL, URL, 200, {'content-type': 'text/html'}, html, 1)
        with mock.patch.object(scan.http, 'fetch', return_value=response) as fetch:
            payload = json.loads(scan.scan(URL, only=['schema'], ctx={}, check_images=False).to_json())
        self.assertEqual(1, fetch.call_count)
        self.assertEqual(['name', 'image'], payload['meta']['structured_data']['recipe_field_policy']['required_properties'])


if __name__ == '__main__':
    unittest.main()
