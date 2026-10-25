"""Integer request and byte limits shared by toolkit entrypoints."""


def nonnegative_integer(value, name: str) -> None:
    """Reject invalid caps without coercing booleans, fractions or missing data."""
    if type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a nonnegative integer.')


def positive_integer(value, name: str) -> None:
    """Reject zero and invalid byte budgets without coercing caller data."""
    if type(value) is not int or value <= 0:
        raise ValueError(f'{name} must be a positive integer.')
