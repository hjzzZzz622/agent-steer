"""Trusted fixture executed by Claude, not a real database."""
import argparse
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', required=True)
    parser.add_argument('selection')
    parser.add_argument('--receipt', default=None)
    args = parser.parse_args()
    fixture = json.loads(Path(args.fixture).read_text())
    if args.selection not in fixture['values']:
        parser.error('unknown selection')
    row = {'selection': args.selection, 'value': fixture['values'][args.selection],
           'completed_at_ns': time.time_ns(),
           'after_guidance': Path(fixture['emissions']).exists(),
           'steering_receipt': args.receipt}
    with open(fixture['trace'], 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(row) + '\n')
    print(json.dumps({'selection': row['selection'], 'value': row['value']}))


if __name__ == '__main__':
    main()
