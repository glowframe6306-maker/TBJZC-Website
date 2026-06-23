"""
save_feedback.py

Standalone utility to reliably append feedback entries to a Feedback.txt file.
Drop this file into your project root (TBJZC-Website) and run it or call
`append_feedback()` from your server code.

Usage (CLI):
  python save_feedback.py --name "Name" --email "you@example.com" --message "Your message"

You can also pipe JSON on stdin: echo '{"name":"A","email":"b@c","message":"Hi"}' | python save_feedback.py

The script writes entries in a safe, retried append with flush+fsync.
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path

DEFAULT_FILENAME = 'Feedback.txt'
RETRY_COUNT = 3
RETRY_DELAY = 0.15


def format_entry(name: str, email: str, message: str) -> str:
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    entry = (
        f"Name - {name}\n"
        f"Email - {email}\n"
        f"Submitted - {timestamp}\n"
        "________________________________\n"
        "Message:\n"
        f"{message}\n\n"
    )
    return entry


def append_feedback(directory: str, filename: str, name: str, email: str, message: str) -> None:
    """Append the formatted entry to directory/filename with retries.

    Raises an exception on permanent failure.
    """
    dirpath = Path(directory)
    dirpath.mkdir(parents=True, exist_ok=True)
    file_path = dirpath / filename
    entry = format_entry(name, email, message)

    last_exc = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            # Open in append+binary to ensure we flush bytes and fsync
            with open(file_path, 'ab') as f:
                data = entry.encode('utf-8')
                f.write(data)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    # fsync may not be available in some environments; ignore safely
                    pass
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(RETRY_DELAY)
    raise RuntimeError(f'Failed to write feedback after {RETRY_COUNT} attempts') from last_exc


def _from_stdin_or_args():
    # Try to read JSON from stdin first
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read().strip()
            if raw:
                payload = json.loads(raw)
                return payload.get('name'), payload.get('email'), payload.get('message')
    except Exception:
        pass

    parser = argparse.ArgumentParser(description='Append feedback to a file')
    parser.add_argument('--name', required=True)
    parser.add_argument('--email', required=True)
    parser.add_argument('--message', required=True)
    parser.add_argument('--dir', default='Feedback', help='Directory to save Feedback.txt into')
    parser.add_argument('--file', default=DEFAULT_FILENAME, help='Feedback filename')
    args = parser.parse_args()
    return args.name, args.email, args.message, args.dir, args.file


if __name__ == '__main__':
    # Support both stdin JSON and CLI args
    try:
        # If stdin JSON returned values, it returns 3 items; otherwise argparse returns 5
        res = _from_stdin_or_args()
        if isinstance(res, tuple) and len(res) == 3:
            name, email, message = res
            directory = 'Feedback'
            filename = DEFAULT_FILENAME
        else:
            name, email, message, directory, filename = res

        if not (name and email and message):
            print('Missing name/email/message', file=sys.stderr)
            sys.exit(2)

        append_feedback(directory, filename, name, email, message)
        print('Feedback saved')
    except SystemExit:
        raise
    except Exception as e:
        print('Error saving feedback:', str(e), file=sys.stderr)
        sys.exit(1)
