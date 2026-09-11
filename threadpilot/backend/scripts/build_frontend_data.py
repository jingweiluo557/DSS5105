"""Rebuild the frontend snapshot from the shared source CSV files."""
import csv
import json
from pathlib import Path

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    data = {'today': '2026-04-01'}
    for name in ('orders', 'production_log', 'workshops'):
        with (root / 'data' / f'{name}.csv').open(encoding='utf-8-sig', newline='') as source:
            data[name] = list(csv.DictReader(source))
    (root / 'frontend' / 'data.js').write_text('window.TRACK1_DATA = ' + json.dumps(data, ensure_ascii=False) + ';\n', encoding='utf-8')
    print({name: len(rows) for name, rows in data.items() if isinstance(rows, list)})
