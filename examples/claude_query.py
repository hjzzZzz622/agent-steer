"""Fake date-partition query for manual Claude Code acceptance testing."""
import argparse
import json
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('date', choices=('0907', '0906'))
    parser.add_argument('--delay', type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.delay <= 60:
        parser.error('--delay must be between 0 and 60 seconds')
    time.sleep(args.delay)
    print(json.dumps({'date': args.date, 'rows': [] if args.date == '0907'
                      else [{'revenue': 120}]}))


if __name__ == '__main__':
    main()
