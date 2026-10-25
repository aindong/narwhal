"""Run a fresh, bounded mutation gate without changing the working tree."""
import argparse
import fnmatch
import json
from importlib.metadata import PackageNotFoundError, version
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ('lib.links.x_http_check_state__mutmut_*', 'lib.links.x_is_broken__mutmut_*',
                   'lib.urlpaths.x_remove_dot_segments__mutmut_*',
                   'lib.budgets.x_nonnegative_integer__mutmut_*',
                   'lib.budgets.x_positive_integer__mutmut_*')


def check_results(records, patterns):
    """Require results for every pattern and explicit pytest test-failure exits."""
    patterns = [patterns] if isinstance(patterns, str) else list(patterns)
    if not patterns:
        raise ValueError('No mutation targets requested; refusing an empty pass.')
    results = {}
    for record in records:
        for name, exit_code in record['exit_code_by_key'].items():
            if not any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns):
                continue
            if name in results:
                raise ValueError('Duplicate mutant result: ' + name)
            results[name] = exit_code
    # Mutmut also calls pytest internal errors (exit 3) "killed". Fail closed.
    failures = {name: code for name, code in results.items() if type(code) is not int or code != 1}
    for pattern in patterns:
        if not any(fnmatch.fnmatchcase(name, pattern) for name in results):
            raise ValueError('No mutants matched target {!r}; refusing an empty pass.'.format(pattern))
    return results, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'scripts/mutation/pyproject.toml',
                        help='Mutmut TOML profile to copy into fresh staging (default: existing CI profile)')
    parser.add_argument('targets', nargs='*', default=DEFAULT_TARGETS,
                        help='Mutmut function patterns within the configured source scope; every pattern must match')
    args = parser.parse_args()
    if not args.config.is_file():
        parser.error('Mutation configuration must be a file: ' + str(args.config))
    executable = Path(sys.executable).parent / 'mutmut'
    if not executable.is_file():
        parser.error('Install requirements-mutation.txt in this Python environment first.')
    try:
        installed_version = version('mutmut')
    except PackageNotFoundError:
        installed_version = None
    if installed_version != '3.7.0':
        parser.error('Install the pinned Mutmut version from requirements-mutation.txt.')
    # Mutmut strips src/ from module names. Narwhal tests can then import lib.*
    # from the mutated copy, rather than the repository's nested script path.
    with tempfile.TemporaryDirectory(prefix='narwhal-mutation-') as directory:
        work = Path(directory)
        shutil.copytree(ROOT / 'skills/seo-scan/scripts', work / 'src',
                        ignore=shutil.ignore_patterns('__pycache__'))
        # Preserve fixture paths without adding an unmutated source copy beside tests.
        shutil.copytree(ROOT / 'skills/seo-scan/tests', work / 'skills/seo-scan/tests',
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(args.config, work / 'pyproject.toml')
        subprocess.run([str(executable), 'run', '--max-children', '4', *args.targets],
                       cwd=work, check=True)
        records = [json.loads(path.read_text())
                   for path in sorted((work / 'mutants/src').rglob('*.py.meta'))]
        results, failures = check_results(records, args.targets)
        for name, code in failures.items():
            print('{}: unresolved (recorded exit {!r})'.format(name, code), flush=True)
            subprocess.run([str(executable), 'show', name], cwd=work, check=True)
        print('Mutation gate: {}/{} killed.'.format(len(results) - len(failures), len(results)))
        return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
