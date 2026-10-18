#!/usr/bin/env python3
"""Real keyboard/screen/print proof for native measurement disclosure."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import audit
from test_measurement_disclosure import measured, audit_data


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path)
    parser.add_argument('--html',type=Path,action='append',default=[])
    args=parser.parse_args(argv)
    if args.artifacts:args.artifacts.mkdir(parents=True,exist_ok=True)
    report=measured(meta='<meta name="author" content="AUTHOR_WITNESS_ONLY">'
                         '<meta name="date" content="DATE_WITNESS_ONLY &lt;script&gt;window.measurementProbe=1&lt;/script&gt;">')
    report.add('technical','high','FIX_FIRST','A controlled reported defect.','Repair only this confirmed example.')
    before,markdown=report.to_json(),report.to_markdown()
    docs=[('page',report.to_html()),('audit',audit.render_html(audit_data(report))),
          ('mixed',measured(text='API 这是使用说明。').to_html())]
    docs += [('installed-'+str(i),p.read_text(encoding='utf-8')) for i,p in enumerate(args.html)]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            tab=browser.new_page()
            requests=[]

            def deny(route):
                requests.append(route.request.url);route.abort()

            tab.route('http://**/*',deny);tab.route('https://**/*',deny)
            for name,output in docs:
                tab.emulate_media(media='screen');tab.set_content(output)
                details=tab.locator('details.measurement-details')
                summary=details.locator('summary')
                print_copy=tab.locator('.measurement-print')
                assert details.count()==1 and summary.count()==1,name
                for width in (320,390,1100):
                    tab.set_viewport_size({'width':width,'height':1000})
                    assert details.get_attribute('open') is None,name
                    assert print_copy.is_hidden(),name
                    overview=tab.locator('.measurement-overview').inner_text()
                    assert 'not verified page quality' in overview
                    assert 'publication dates and freshness are unverified' in overview
                    if name=='mixed':
                        assert 'Readability formula: unassessed' in overview
                        assert 'threshold review not applied' in overview
                    if name in ('page','audit'):
                        assert 'FIX_FIRST' in tab.inner_text('body')
                        assert 'DATE_WITNESS_ONLY' not in tab.inner_text('body')
                        assert 'AUTHOR_WITNESS_ONLY' not in tab.inner_text('body')
                    collapsed=tab.evaluate('document.documentElement.scrollHeight')
                    tab.keyboard.press('Tab')  # enter keyboard modality, not programmatic/pointer focus
                    summary.focus()
                    assert summary.evaluate('(n)=>document.activeElement===n && getComputedStyle(n).outlineWidth==="2px"'),(name,width)
                    tab.keyboard.press('Enter')
                    assert details.get_attribute('open') is not None,name
                    assert tab.evaluate('document.documentElement.scrollHeight')>collapsed,name
                    if name in ('page','audit'):
                        text=tab.inner_text('body')
                        assert text.count('DATE_WITNESS_ONLY')==1,name
                        assert text.count('AUTHOR_WITNESS_ONLY')==1,name
                        assert '<script>window.measurementProbe=1</script>' in text,name
                    assert tab.evaluate('window.measurementProbe===undefined'),name
                    assert tab.evaluate('document.documentElement.scrollWidth<=innerWidth'),(name,width)
                    if args.artifacts and width==390:
                        tab.screenshot(path=str(args.artifacts/(name+'-expanded.png')),full_page=True)
                    tab.keyboard.press('Space')
                    assert details.get_attribute('open') is None,name
                    assert tab.evaluate('document.documentElement.scrollWidth<=innerWidth'),(name,width)
                    if args.artifacts and width==390:
                        tab.screenshot(path=str(args.artifacts/(name+'-collapsed.png')),full_page=True)
                for opened in (False,True):
                    if opened:summary.click()
                    tab.emulate_media(media='print');tab.set_viewport_size({'width':794,'height':1123})
                    assert details.is_hidden() and print_copy.is_visible(),(name,opened)
                    assert tab.get_by_role('heading',name='Text-length observation (not content quality)',exact=True).count()==1,name
                    text=tab.inner_text('body')
                    if name in ('page','audit'):
                        assert text.count('DATE_WITNESS_ONLY')==1,name
                        assert text.count('AUTHOR_WITNESS_ONLY')==1,name
                    assert tab.evaluate('document.documentElement.scrollWidth<=innerWidth'),name
                    if args.artifacts:
                        tab.pdf(path=str(args.artifacts/(name+'-print-'+str(opened)+'.pdf')),format='A4',print_background=True)
                    tab.emulate_media(media='screen')
                    assert (details.get_attribute('open') is not None)==opened,name
                assert tab.locator('.measurement-overview script,.measurement-overview img').count()==0,name
            assert not requests,requests
        finally:browser.close()
    assert before==report.to_json() and markdown==report.to_markdown()
    print('OK: compact uncertainty/count overview, keyboard expansion, literal witnesses and one complete print copy whether open/closed; native page/audit/mobile/desktop, no scripts/network/data changes.')
    return 0


if __name__=='__main__':raise SystemExit(main())
