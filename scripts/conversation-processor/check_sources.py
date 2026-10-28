"""Read-only source diagnostics. No cursor store, extraction, network or bodies."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from conversation_processor import adapters
from conversation_processor.adapters import dsh
from conversation_processor.common import complete_lines, now
from conversation_processor.config import load


def inspect(config):
    results = []
    stamp = now()
    for source in config.sources:
        counts = {'kind': source['kind'], 'files': 0, 'scanned': 0, 'records': 0,
                  'frames': 0, 'incomplete_tail_files': 0, 'incomplete_tail_bytes': 0,
                  'max_declared_window_bytes': 0, 'errors': []}
        initial_presets, selections = Counter(), Counter()
        try:
            paths = adapters.files(config, source)
        except Exception as exc:
            counts['errors'].append({'code': type(exc).__name__})
            paths = []
        for path in paths:
            counts['files'] += 1
            try:
                raw = adapters.read_bytes(path, source)  # Retains the normal file size cap.
                if source['kind'] == 'dsh':
                    stats = {}
                    rows, offset = dsh.frames(raw, max_window_size=source.get('max_window_size', dsh.DEFAULT_MAX_WINDOW_SIZE), statistics=stats)
                    counts['records'] += stats['records']
                    counts['frames'] += stats['frames']
                    counts['max_declared_window_bytes'] = max(counts['max_declared_window_bytes'], stats['max_declared_window_bytes'])
                    tail = len(raw) - offset
                    preset = rows[0].get('agentPreset') if rows else None
                    initial_presets[preset if isinstance(preset, str) else '(unset)'] += 1
                    for row in rows[1:]:
                        if row.get('type') == 'agent-preset/selected':
                            preset = row.get('data', {}).get('agentPreset')
                            selections[preset if isinstance(preset, str) else '(unset)'] += 1
                elif source['kind'] == 'lmstudio':
                    document = json.loads(raw.decode('utf-8-sig'))
                    counts['records'] += len(document.get('messages', []))
                    preset = document.get('preset')
                    initial_presets[preset if isinstance(preset, str) else '(unset)'] += 1
                    tail = 0
                else:
                    rows, offset = complete_lines(raw)
                    counts['records'] += len(rows)
                    tail = len(raw) - offset
                counts['incomplete_tail_files'] += bool(tail)
                counts['incomplete_tail_bytes'] += tail
                # Exercise both adapter paths, but keep the temporary cursor
                # entirely in memory. No pipeline.baseline or Store is imported.
                snapshot = adapters.scan(source['kind'], path, source, baseline=True, enabled_at=stamp)
                adapters.scan(source['kind'], path, source, cursor=snapshot.cursor, enabled_at=stamp)
                counts['scanned'] += 1
            except Exception as exc:
                # No exception message, filename, source text, or model output.
                counts['errors'].append({'file_id': hashlib.sha256(str(path).encode()).hexdigest()[:12],
                                         'code': type(exc).__name__})
        counts['initial_preset_distribution'] = dict(sorted(initial_presets.items()))
        counts['preset_selection_events'] = dict(sorted(selections.items()))
        results.append(counts)
    return {'read_only': True, 'sources': results, 'errors': sum(len(r['errors']) for r in results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = inspect(load(args.config))
    except Exception as exc:
        result = {'read_only': True, 'errors': 1, 'code': type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
