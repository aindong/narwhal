"""Open native measurement details when checking their full evidence contents."""


def expand_measurements(page):
    page.emulate_media(media='screen')
    for summary in page.locator('details.measurement-details:not([open]) > summary').all():
        summary.click()
