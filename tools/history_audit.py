"""Read-only lane audit; scan the FULL pinned-base range, not just the last commit."""
import argparse
import ast
import collections
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

APP_BASE = 'afb6d5f9a153de5e7f5cf6c93afcc4788e604ff6'
CORE_BASE = '6289b3a91284d5e2412a0740c6d40c713d8496a2'
MAIN = '356ebf455f000255206420deedd45afb7a40f5ae'
BRANCH = 'eval/ttk-history-reports'
ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, encoding='utf-8')
    if p.returncode:
        raise AssertionError('git ' + ' '.join(args) + '\n' + p.stdout + p.stderr)
    return p.stdout.strip()


def scan(text, label):
    patterns = [r'AKIA[0-9A-Z]{16}', r'gh[pousr]_[A-Za-z0-9]{30,}',
                r'github_pat_[A-Za-z0-9_]{40,}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                r'(?i)(?:api[_-]?key|secret[_-]?key|password|access[_-]?token)\s*[:=]\s*[\"\'][A-Za-z0-9/+_=.-]{16,}[\"\']']
    for pattern in patterns:
        if re.search(pattern, text):
            raise AssertionError('Potential secret in ' + label + ' (value NOT printed)')


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-root', required=True, type=Path)
    parser.add_argument('--evidence-dir', required=True, type=Path)
    parser.add_argument('--candidate', action='store_true', help='include uncommitted candidate paths before commit')
    parser.add_argument('--published', action='store_true', help='require remote eval equals exact local HEAD')
    args = parser.parse_args()
    core = args.core_root.resolve()
    output = dict(appHead=git(ROOT, 'rev-parse', 'HEAD'), coreHead=git(core, 'rev-parse', 'HEAD'), lanes={})
    for name, repo, base in (('app', ROOT, APP_BASE), ('core', core, CORE_BASE)):
        assert git(repo, 'branch', '--show-current') == BRANCH
        git(repo, 'merge-base', '--is-ancestor', base, 'HEAD')
        commits = git(repo, 'rev-list', '--parents', '--reverse', base + '..HEAD').splitlines()
        assert all(len(c.split()) == 2 for c in commits), 'unexpected merge or root commit'
        names = git(repo, 'diff', '--name-status', base, 'HEAD').splitlines()
        diff = git(repo, 'diff', '--no-ext-diff', base, 'HEAD')
        if args.candidate:
            diff += git(repo, 'diff', '--no-ext-diff', base)
            names = git(repo, 'diff', '--name-status', base).splitlines()
            names += ['?\t' + p for p in git(repo, 'ls-files', '--others', '--exclude-standard').splitlines()]
        scan(diff, name + ' complete base..HEAD/candidate diff')
        # Historical commits must also be secret-free even if a later commit removes a value.
        for commit in commits:
            scan(git(repo, 'show', '--format=', commit.split()[0]), name + ' historical commit')
        tracked = git(repo, 'ls-files').splitlines()
        if args.candidate:
            tracked += git(repo, 'ls-files', '--others', '--exclude-standard').splitlines()
        for path in tracked:
            p = repo / path
            if p.is_file():
                data = p.read_bytes()
                if b'\x00' not in data:
                    scan(data.decode('utf-8', errors='replace'), name + ' source ' + path)
        git(repo, 'diff', '--check', base)
        output['lanes'][name] = dict(commits=commits, changedFiles=names, status=git(repo, 'status', '--short', '--branch'),
                                     diffSecretScan='pass', historicalSecretScan='pass', sourceSecretScan='pass', ancestry='pass')
    canonical = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (core / 'timetracker_core').glob('*.py')}
    vendored = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'timetracker_core').glob('*.py')}
    assert canonical == vendored, 'vendored source does not equal canonical source'
    output['vendorHashes'] = canonical
    assert output['coreHead'] in (ROOT / 'CORE-VERSION').read_text(encoding='utf-8'), 'CORE-VERSION not exact canonical HEAD'
    # Standard-library-only check over executable imports, not prose.
    for p in (core / 'timetracker_core').glob('*.py'):
        for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split('.')[0] in sys.stdlib_module_names, str(p) + ' non-stdlib import'
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert (node.module or '').split('.')[0] in sys.stdlib_module_names, str(p) + ' non-stdlib import'
    refs = dict((line.split()[1], line.split()[0]) for line in git(ROOT, 'ls-remote', 'origin',
            'refs/heads/dev', 'refs/heads/main', 'refs/heads/' + BRANCH).splitlines())
    assert refs.get('refs/heads/dev') == APP_BASE, 'protected dev changed externally; never repair it'
    assert refs.get('refs/heads/main') == MAIN, 'protected main changed externally; never repair it'
    if args.published:
        assert refs.get('refs/heads/' + BRANCH) == output['appHead'], 'remote eval is not exact tested HEAD'
    output['remoteRefs'] = refs
    original = {}
    for name, path, expected, status in (
        ('app', '/home/hermes/keeper-of-time', APP_BASE, '?? .worktrees/'),
        ('core', '/home/hermes/keeper-of-time-core', CORE_BASE, '')):
        original[name] = dict(head=git(path, 'rev-parse', 'HEAD'), status=git(path, 'status', '--porcelain'))
        assert original[name]['head'] == expected and original[name]['status'] == status, 'original checkout changed'
    output['originalCheckouts'] = original
    evidence = args.evidence_dir.resolve()
    browser = json.loads((evidence / 'browser-results.json').read_text(encoding='utf-8'))
    assert browser['ok'] is True and browser['acceptance']['ok'] is True
    layouts = browser['layouts']
    assert {(r['theme'], r['width'], r['height']) for r in layouts} == {
        (t,w,h) for t in ('cute','cyber','poolside','evergreen','citrus-pop','dune') for w,h in ((300,420),(380,680))}
    assert len(layouts) == 12
    for r in layouts:
        assert len(r['controls']) == 10 and all(c['hit'] for c in r['controls'])
        assert r['documentWidth'] <= r['width'] + 1 and r['bodyScrollWidth'] <= r['bodyClientWidth'] + 1
        png = evidence / (r['theme'] + '-' + str(r['width']) + '.png')
        assert png.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'), 'missing real rendered snapshot'
    calls = [json.loads(line) for line in (evidence / 'relay-calls.jsonl').read_text(encoding='utf-8').splitlines()]
    readonly = [c for c in calls if c['readOnly']]
    assert readonly and all(c['before'] == c['after'] and c['invariantPassed'] for c in readonly)
    methods = collections.Counter(c['method'] for c in calls)
    for m in ('get_history', 'save_history_csv', 'start_session', 'resume_session', 'stop_and_start_entry',
              'stop_tracking', 'edit_entry', 'delete_entry', 'restore_entry', 'log_task_group', 'unlog_task_group'):
        assert methods[m] > 0, 'missing actual frontend call: ' + m
    output['browser'] = dict(engine=browser['engine'], driverPython=browser['driverPython'],
        checks=browser['acceptance']['checks'], checkCount=len(browser['acceptance']['checks']), layoutCount=len(layouts),
        readonlyCalls=len(readonly), callCounts=dict(methods),
        layouts=[{k:r[k] for k in ('theme','width','height','bodyClientWidth','bodyScrollWidth','scrollHeight','clientHeight','loadedFonts')} for r in layouts],
        limitations=browser['limits'])
    output['ok'] = True
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run()
