"""Machine-readable summaries only; exception values and dialogue are never printed."""
import argparse
import json
import sqlite3
import re
import yaml
import zstandard
from .extract import Invalid
from .config import load
from . import pipeline


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check-config')
    baseline = sub.add_parser('baseline')
    baseline.add_argument('--confirm', required=True, action='store_true', help='explicitly register T0')
    sub.add_parser('collect')
    sub.add_parser('status')
    for name in ('extract', 'run'):
        command = sub.add_parser(name)
        command.add_argument('--limit', type=int)
    args = parser.parse_args(argv)
    try:
        config = load(args.config)
        if args.command == 'check-config':
            result = {'valid': True, 'enabled_sources': len(config.sources)}
        elif args.command == 'baseline':
            result = pipeline.baseline(config)
        elif args.command == 'collect':
            result = pipeline.collect(config)
        elif args.command == 'status':
            result = pipeline.status(config)
        else:
            if args.limit is not None and args.limit < 1:
                raise ValueError('positive_limit_required')
            result = {}
            if args.command == 'run':
                result['collect'] = pipeline.collect(config)
            result['extract'] = pipeline.extract_pending(config, args.limit)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        return 2 if result.get('extract', {}).get('pending') or result.get('collect', {}).get('source_errors') else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError,
            sqlite3.Error, yaml.YAMLError, re.error, zstandard.ZstdError, Invalid):
        print(json.dumps({'error': 'configuration_or_state_invalid'}))
        return 1
