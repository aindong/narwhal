"""Artifact writes that preserve the identities of read input snapshots."""

import os
import stat
from typing import Union


def write_output(path: str, text: Union[str, bytes], input_stats: list, *, label='Report output') -> None:
    """Write text or binary bytes after checking identity against read snapshots."""
    binary = isinstance(text, bytes)
    if not binary:
        try:
            text.encode('utf-8')
        except UnicodeError:
            raise ValueError(f'{label} cannot be encoded as UTF-8.') from None
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(path, flags, 0o666)  # no O_TRUNC until identity is checked
    try:
        with os.fdopen(descriptor, 'wb' if binary else 'w',
                       encoding=None if binary else 'utf-8') as fh:
            descriptor = None
            output_stat = os.fstat(fh.fileno())
            if not stat.S_ISREG(output_stat.st_mode):
                raise ValueError(f'{label} must be a regular file.')
            if any(os.path.samestat(output_stat, source) for source in input_stats):
                raise ValueError(f'{label} aliases an input snapshot; choose a distinct output file.')
            # shortcut: writes are non-atomic; use atomic replacement if interrupted-output recovery is required.
            fh.truncate(0)
            fh.write(text)
    finally:
        if descriptor is not None:
            os.close(descriptor)
