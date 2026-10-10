#!/usr/bin/env python3
"""Combine independently collected cases from the same court, in input order."""
import argparse
import copy
import json
from pathlib import Path

from chain_receipts import TERMINAL


def receipt_totals(cases):
    """Count each retained hash once, including original failed attempts."""
    transactions = {}
    for case in cases:
        case_hashes = {row['tx'] for row in case.get('txs', {}).values()}
        for name, row in case.get('txs', {}).items():
            if row.get('previous_tx') and row['previous_tx'] not in case_hashes:
                raise ValueError('recovery is missing its original transaction evidence')
            key = name.split('@', 1)[0].split(':')
            mode = key[-1] if key[0] in ('probe', 'retry') else None
            record = (row.get('status', 'PENDING'), row.get('execution', 'UNKNOWN'),
                      row.get('consensus_result', 'UNKNOWN'), mode)
            if row['tx'] in transactions and transactions[row['tx']] != record:
                raise ValueError('conflicting receipt for the same transaction')
            transactions[row['tx']] = record
    totals = {'total': len(transactions), 'pending': 0, 'by_status': {},
              'by_execution': {}, 'by_consensus_result': {}, 'by_mode': {}}
    for status, execution, result, mode in transactions.values():
        totals['pending'] += status not in TERMINAL
        for field, value in (('by_status', status), ('by_execution', execution),
                             ('by_consensus_result', result)):
            totals[field][value] = totals[field].get(value, 0) + 1
        if mode:
            counts = totals['by_mode'].setdefault(mode, {})
            counts[status] = counts.get(status, 0) + 1
    return totals


def merge(snapshots):
    if not snapshots:
        raise ValueError('at least one snapshot required')
    first=snapshots[0]
    if not isinstance(first.get('contract'), str) or not first['contract']:
        raise ValueError('only chain snapshots from the same court may be combined')
    for snap in snapshots:
        if (snap.get('format')!='impeach-case/1' or snap.get('provenance')!='bradbury'
                or not snap.get('contract') or snap['contract'].lower()!=first['contract'].lower()):
            raise ValueError('only chain snapshots from the same court may be combined')
    out=copy.deepcopy(first)
    out['cases']=[]
    out['generated_at']=max(s['generated_at'] for s in snapshots)
    seen=set(); registry={}
    for snap in snapshots:
        # Aggregate-only receipts cannot be attached to an auditable hash. Do
        # not claim that a merged publication retained evidence it never had.
        if receipt_totals(snap['cases']) != snap['receipts']:
            raise ValueError('receipt summary does not match retained transaction evidence')
        for case in snap['cases']:
            cid=case['certificate']['claim_id']
            if case['claim'].get('claim_id') != cid:
                raise ValueError('claim and certificate ids differ')
            if cid in seen:
                raise ValueError('duplicate claim evidence')
            if not case['certificate'].get('contested') or not case['certificate'].get('ruled_at'):
                raise ValueError('only ruled cases can be published')
            seen.add(cid);out['cases'].append(copy.deepcopy(case))
        for row in snap['registry']:
            key=row['content_hash']
            if key not in registry:
                registry[key]=copy.deepcopy(row)
                continue
            prior=registry[key]
            for field,value in row.items():
                if field in ('preview','item_hash'):
                    if value and prior.get(field) and value!=prior[field]:
                        raise ValueError('conflicting registry annotation')
                    if value:prior[field]=value
                elif field in prior and prior[field]!=value:
                    raise ValueError('conflicting immutable registry row')
                else:prior[field]=value
    out['registry']=list(registry.values())
    out['receipts']=receipt_totals(out['cases'])
    out['note']='Separately collected ruled claims from one Bradbury court; originals and failed attempts retained.'
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshots',nargs='+',type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    result=merge([json.loads(path.read_text()) for path in a.snapshots])
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=1)+'\n')
    print('%d cases, %d registry entries, %d submitted transactions' %
          (len(result['cases']),len(result['registry']),result['receipts']['total']))


if __name__=='__main__':main()
