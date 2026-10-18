"""Report branding must keep its intended sizes without changing report facts."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import audit
import render_report
from lib import brand
from lib.report import Report,html_document


def documents():
    """Representative native page, combined audit, and Markdown shell."""
    page=Report('https://example.test/controlled',final_url='https://example.test/controlled',fetched_status=200)
    page.add('technical','high','Controlled report finding','Synthetic layout evidence.','Review the controlled example.')
    page.ok('schema','Controlled observation','Synthetic layout evidence only.')
    site={'site':page.url,'page':page,'site_result':{'base':page.url,'avg_score':page.score(),'pages_scanned':1,
          'pages':[{'url':page.url,'score':page.score()}],'recurring':Counter(),
          'links':{'broken':[],'checked':0,'skipped_over_cap':0},'duplicates':[]},
          'sitemap':{'start':page.url,'seeds':[]}}
    return [('page',page.to_html()),('audit',audit.render_html(site)),
            ('markdown',render_report.render('# Controlled report\n\nA literal observation, not a site audit.\n\n| Item | Count |\n|--|--|\n| Sample | 1 |\n'))]


class Images(HTMLParser):
    def __init__(self,markup):
        super().__init__(convert_charrefs=True);self.images=[];self.feed(markup)
    def handle_starttag(self,tag,attrs):
        if tag=='img':self.images.append(dict(attrs))


class TestBrandLayout(unittest.TestCase):
    def test_all_report_shells_keep_inline_mark_bytes_and_declared_sizes(self):
        for name,output in documents():
            images=Images(output).images
            self.assertEqual([46,16],[int(image['height']) for image in images],name)
            self.assertEqual([brand.LOGO_DATA_URI]*2,[image['src'] for image in images],name)
            self.assertEqual(['Narwhal']*2,[image['alt'] for image in images],name)
            self.assertIn('.brand>.brand-logo{height:46px}',output)
            self.assertIn('.foot>.brand-logo{display:inline-block;height:16px;',output)

    def test_custom_document_title_and_body_are_not_replaced_by_sizing_rules(self):
        output=html_document('Controlled title','https://example.test/guide','<p>BODY_MARKER</p>')
        self.assertIn('Controlled title',output);self.assertIn('BODY_MARKER',output)
        self.assertEqual(2,len(Images(output).images))
        self.assertNotIn('<script',output)

    def test_logo_helper_still_honors_its_existing_standalone_markup_contract(self):
        image=Images(brand.logo_img(32,'Controlled label')).images[0]
        self.assertEqual('32',image['height'])
        self.assertEqual('Controlled label',image['alt'])
        self.assertEqual(brand.LOGO_DATA_URI,image['src'])

    def test_cosmetic_brand_failure_still_does_not_fail_a_report(self):
        with mock.patch.object(brand,'logo_img',side_effect=RuntimeError('Controlled unavailable cosmetic asset')):
            output=html_document('Controlled title','','<p>BODY_MARKER</p>')
        self.assertEqual([],Images(output).images)
        self.assertIn('BODY_MARKER',output)

    def test_rendering_is_offline_and_preserves_json_markdown_counts_and_scores(self):
        page=Report('https://example.test/guide',fetched_status=200)
        page.add('technical','high','Controlled issue','Synthetic evidence.','Review only the example.')
        before,markdown=page.to_json(),page.to_markdown();score=page.score();counts=page.counts()
        with mock.patch.object(socket,'socket',side_effect=AssertionError('No network')):
            page.to_html();documents()
        self.assertEqual(before,page.to_json());self.assertEqual(markdown,page.to_markdown())
        self.assertEqual(score,page.score());self.assertEqual(counts,page.counts())


if __name__=='__main__':unittest.main()
