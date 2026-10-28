"""CLI entry point. --dry-run performs no writes, subprocesses or HTTP calls."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import sqlite3
import subprocess
import yaml

# Dependency boundary: private engine may depend on the generic sibling processor.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'conversation-processor'))
from personality_engine.policy import Config, EngineError, exclusive
from personality_engine.engine import run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(Path(__file__).resolve().parents[2] / 'config/engine.yaml'))
    parser.add_argument('--dry-run', action='store_true')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('collect', 'extract', 'reflect', 'apply', 'rollback', 'status', 'approve', 'reject', 'sync'):
        command = commands.add_parser(name)
        command.add_argument('--dry-run', action='store_true', default=argparse.SUPPRESS)
        command.add_argument('--config', default=argparse.SUPPRESS)
        if name in ('apply', 'rollback', 'approve', 'reject'):
            command.add_argument('proposal_id', nargs='?' if name == 'apply' else None)
        if name in ('approve', 'reject'):
            command.add_argument('--owner-approved', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command in ('approve', 'reject') and not args.owner_approved:
            raise EngineError('owner_approval_flag_required')
        config = Config(args.config)
        with exclusive(config, args.dry_run or args.command == 'status'):
            value = run(config, args.command, getattr(args, 'proposal_id', None), args.dry_run,
                        getattr(args, 'owner_approved', False))
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return 0
    except EngineError as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError,
            sqlite3.Error, subprocess.SubprocessError, yaml.YAMLError):
        print('{"error":"invalid_config_or_input"}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
