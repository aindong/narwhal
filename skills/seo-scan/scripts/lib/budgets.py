"""Integer request caps shared by crawl and sitemap entrypoints."""


def nonnegative_integer(value, name: str) -> None:
    """Reject invalid caps without coercing booleans, fractions or missing data."""
    if type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a nonnegative integer.')
