"""Run the local memory/evolution pipeline once; --dry-run has no side effects."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / 'scripts/personality-engine'), str(ROOT / 'scripts/conversation-processor')]
from personality_engine.policy import Config
from personality_engine.daily import run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'config/engine.yaml'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = run(Config(args.config), args.dry_run)
        if sys.stdout:
            print(json.dumps(result, ensure_ascii=False))
        return 0 if result['code'] in ('ok', 'preview') else 1
    except Exception:
        if sys.stderr:
            print('{"code":"daily_configuration_or_lock_failed"}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
