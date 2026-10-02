"""Read-only SL-signature evidence from immutable trade snapshots.

Only writes JSON review artifacts beside this script. No project modules,
network, database writes, terminal or LLM calls.
"""
from __future__ import annotations
import csv
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import statistics

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
IDS = [2349227, 2375480, 2362868, 2048285, 2059368]


def number(v):
    text = (v or '').replace(' ', '').replace('\xa0', '').replace(',', '.')
    return Decimal(text) if text else Decimal(0)


def load(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream, delimiter=';'))
    orderbook = len(rows[0]) == 13
    items = []
    for line, row in enumerate(rows[1:], 2):
        if len(row) < 2 or row[1] not in ('Buy', 'Sell'):
            continue
        close_i, exit_i, profit_i = (7, 8, 11) if orderbook else (6, 7, 10)
        profit = number(row[profit_i])
        comm = number(row[profit_i - 2]); swap = number(row[profit_i - 1])
        direction = row[1]
        entry, exit_price = number(row[4]), number(row[exit_i])
        items.append({'line': line, 'open': datetime.strptime(row[0], '%Y.%m.%d %H:%M:%S'),
            'close': datetime.strptime(row[close_i], '%Y.%m.%d %H:%M:%S'),
            'symbol': row[3].strip().upper(), 'side': direction, 'volume': number(row[2]),
            'entry': entry, 'exit': exit_price, 'profit': profit,
            'net': profit + comm + swap,
            'sl': number(row[5]) if orderbook else None,
            'tp': number(row[6]) if orderbook else None,
            'comment': row[12].strip() if orderbook else '',
            'adverse_price_distance': (entry-exit_price) * (1 if direction == 'Buy' else -1)})
    return items, 'mt4_orderbook' if orderbook else 'positions'


def brief_stats(values):
    return {'min': min(values), 'median': statistics.median(values), 'max': max(values)} if values else None


def classify(items):
    negative = sum(t['net'] < 0 for t in items)
    positive = sum(t['net'] > 0 for t in items)
    if negative == len(items):
        return 'all_negative'
    if positive == len(items):
        return 'all_positive'
    if negative and positive:
        return 'mixed_net_' + ('negative' if sum(t['net'] for t in items) < 0 else 'positive'
                             if sum(t['net'] for t in items) > 0 else 'zero')
    return 'with_breakeven_net_' + ('negative' if negative else 'positive' if positive else 'zero')


def group_stats(trades, max_span):
    by_symbol = defaultdict(list)
    for trade in trades:
        by_symbol[trade['symbol']].append(trade)
    results = []
    for symbol, book in sorted(by_symbol.items()):
        groups = []
        for trade in sorted(book, key=lambda t: (t['close'], t['open'], t['line'])):
            if not groups or (trade['close'] - groups[-1][0]['close']).total_seconds() > max_span:
                groups.append([])
            groups[-1].append(trade)
        for group in groups:
            first = group[0]['close']; last = group[-1]['close']
            active = [t for t in book if t['open'] <= first <= t['close']]
            lines = {t['line'] for t in active}
            side = group[0]['side'] if len({t['side'] for t in group}) == 1 else None
            active_side = [t for t in active if t['side'] == side] if side else []
            loss_dist = [float(t['adverse_price_distance']) for t in group if t['net'] < 0]
            results.append({'symbol': symbol, 'close_first': str(first), 'close_last': str(last),
                'span_seconds': (last-first).total_seconds(), 'n': len(group),
                'kind': classify(group), 'net_usd': float(sum(t['net'] for t in group)),
                'profit_usd': float(sum(t['profit'] for t in group)),
                'n_negative_net': sum(t['net'] < 0 for t in group),
                'n_negative_gross': sum(t['profit'] < 0 for t in group),
                'positive_net_usd': float(sum(t['net'] for t in group if t['net'] > 0)),
                'negative_net_usd': float(sum(t['net'] for t in group if t['net'] < 0)),
                'side': side or 'mixed', 'active_symbol_before_first_close': len(active),
                'closed_from_active_symbol': sum(t['line'] in lines for t in group),
                'coverage_symbol_pct': round(100 * sum(t['line'] in lines for t in group) / len(active), 6) if active else None,
                'active_side_before_first_close': len(active_side) if side else None,
                'coverage_side_pct': round(100 * sum(t['line'] in lines for t in group) / len(active_side), 6) if active_side else None,
                'adverse_price_distance': brief_stats(loss_dist),
                'exit_price_span': float(max(t['exit'] for t in group) - min(t['exit'] for t in group)),
                'holding_hours': brief_stats([(t['close'] - t['open']).total_seconds()/3600 for t in group]),
                'sl_fields': sum(t['sl'] is not None and t['sl'] > 0 for t in group),
                'sl_markers': sum(bool(re.fullmatch(r'\[sl\](?:\s+(?:ticket\s*)?#?\d+)?', t['comment'], re.I)) for t in group),
                'tp_markers': sum(bool(re.fullmatch(r'\[tp\](?:\s+(?:ticket\s*)?#?\d+)?', t['comment'], re.I)) for t in group),
                'trade_lines': [t['line'] for t in group]})
    return sorted(results, key=lambda g: (g['close_first'], g['symbol']))


def summary(groups):
    multi = [g for g in groups if g['n'] >= 2]
    neg = [g for g in multi if g['kind'] == 'all_negative']
    full = [g for g in neg if g['coverage_symbol_pct'] == 100.0]
    full_side = [g for g in neg if g['coverage_side_pct'] == 100.0]
    mixed = [g for g in multi if g['kind'].startswith('mixed')]
    return {'all_groups': len(groups), 'multi_groups': len(multi),
        'multi_kind_counts': dict(Counter(g['kind'] for g in multi)),
        'multi_negative': len(neg), 'negative_independent_dates': len({g['close_first'][:10] for g in neg}),
        'negative_by_month': dict(sorted(Counter(g['close_first'][:7] for g in neg).items())),
        'negative_full_symbol_book': len(full),
        'negative_full_symbol_book_dates': len({g['close_first'][:10] for g in full}),
        'negative_full_side_book': len(full_side),
        'negative_group_sizes': brief_stats([g['n'] for g in neg]),
        'negative_group_net': brief_stats([g['net_usd'] for g in neg]),
        'negative_coverage_pct': brief_stats([g['coverage_symbol_pct'] for g in neg]),
        'mixed_negative_legs_usd': round(sum(g['negative_net_usd'] for g in mixed), 2),
        'mixed_positive_legs_usd': round(sum(g['positive_net_usd'] for g in mixed), 2),
        'negative_sl_markers': sum(g['sl_markers'] for g in neg),
        'negative_tp_markers': sum(g['tp_markers'] for g in neg),
        'largest_complete_negative_group': max((g['n'] for g in full), default=0),
        'complete_negative_group_within_distance_range': brief_stats([
            round(g['adverse_price_distance']['max'] - g['adverse_price_distance']['min'], 8)
            for g in full]),
        'negative_examples_full_book': sorted(full, key=lambda g: g['net_usd'])[:8],
        'mixed_examples': sorted(mixed, key=lambda g: g['negative_net_usd'])[:5]}


def main():
    connection = sqlite3.connect((ROOT/'data/mqlkiscanner.db').as_uri()+'?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    marks = ','.join('?' for _ in IDS)
    rows = connection.execute(f'SELECT s.signal_id,s.name,s.platform,t.path,t.sha256 FROM signals s '
        f'JOIN trade_files t ON t.signal_id=s.signal_id WHERE s.signal_id IN ({marks})', IDS).fetchall()
    connection.close()
    result = {'group_definition': 'same raw uppercase symbol; anchored maximum close-time span 0/2/5 seconds; no transitive window extension',
        'coverage_definition': 'same-symbol closed members already open at first close / all observed positions with open<=first_close<=close; not current unexported positions',
        'caveat': 'Repeated complete negative closes indicate observed loss-exit discipline; no causal proof of broker SL or guaranteed future cap. Mixed/net-positive closes do not prove stops. Timestamp order inside a second unavailable.',
        'signals': []}
    all_groups = {}
    for row in rows:
        actual_hash = hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()
        assert actual_hash == row['sha256'], row['signal_id']
        trades, fmt = load(row['path'])
        item = {'id': row['signal_id'], 'name': row['name'], 'platform': row['platform'],
            'path': row['path'], 'sha256': actual_hash, 'format': fmt, 'trades': len(trades),
            'first_open': str(min(t['open'] for t in trades)), 'last_close': str(max(t['close'] for t in trades)),
            'negative_net_trades': sum(t['net'] < 0 for t in trades),
            'negative_gross_trades': sum(t['profit'] < 0 for t in trades),
            'negative_net_price_distances': brief_stats([
                float(t['adverse_price_distance']) for t in trades if t['net'] < 0]),
            'negative_net_sl_markers': sum(t['net'] < 0 and t['comment'].lower() == '[sl]' for t in trades),
            'historical_peak_open_positions': max(sum(t['open'] <= when <= t['close'] for t in trades)
                for when in sorted({t['open'] for t in trades} | {t['close'] for t in trades})),
            'close_second_zero_pct': round(100 * sum(t['close'].second == 0 for t in trades)/len(trades), 2),
            'sl_fields': sum(t['sl'] is not None and t['sl'] > 0 for t in trades),
            'sl_markers': sum(t['comment'].lower() == '[sl]' for t in trades),
            'tp_markers': sum(t['comment'].lower() == '[tp]' for t in trades)}
        item['windows'] = {}
        for window in (0, 2, 5):
            groups = group_stats(trades, window)
            all_groups[f'{row["signal_id"]}:{window}'] = groups
            item['windows'][str(window)] = summary(groups)
        result['signals'].append(item)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'close_groups_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT/'close_groups_all.json').write_text(json.dumps(all_groups, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in result['signals']:
        print(item['id'],item['name'],'trades',item['trades'],'SL',item['sl_fields'],'markers',item['sl_markers'])
        for window, stats in item['windows'].items():
            print(' window',window,'counts',stats['multi_kind_counts'],'full negative',stats['negative_full_symbol_book'],
                  'dates',stats['negative_full_symbol_book_dates'])


if __name__ == '__main__':
    main()
