#!/usr/bin/env python3
"""Public read-only audit of C1; no account/signing calls or source mutations."""
import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import run_case
from chain_receipts import fetch_receipt, status_of, execution_of, consensus_result_of, successful

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=False)
    address = '0x45F610cefF1ed367d684A1839b1801Af12Cfb038'
    rpc = 'https://rpc-bradbury.genlayer.com'
    manifest = ROOT / 'runs/bradbury-v2-live.jsonl'
    original = manifest.read_bytes()
    rows = [json.loads(line) for line in original.splitlines() if line.strip()]
    if any(row.get('address', '').lower() != address.lower() for row in rows):
        raise ValueError('manifest address mismatch')
    begin = datetime.datetime.now(datetime.timezone.utc).isoformat()
    raw = []
    def save(kind, key, value):
        record = {'at': time.time(), 'kind': kind, 'key': key, 'value': value}
        raw.append(record)
        with (folder / 'raw.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
    def read(method, *call_args):
        value = run_case.tool.chain_call(address, method, list(call_args), rpc, 30)
        save('read', [method, list(call_args)], value)
        return value
    claim = run_case.load_claim(str(ROOT / 'calibration/claim-court24-v2.json'))
    rewrites = run_case.load_rewrites(claim)
    frozen = digest(json.dumps([claim, rewrites], sort_keys=True, ensure_ascii=False).encode())
    identity = json.loads(Path(str(manifest) + '.complete/identity.json').read_text())
    if frozen != identity['input_sha256']:
        raise ValueError('claim/rewrite fingerprint changed')
    clock = read('clock')
    counts = read('counts')
    challenge = read('get_challenge', 1)
    chain_claim = read('get_claim', 1)
    if (challenge.get('claim_id') != 1 or challenge.get('challenge_id') != 1
            or challenge.get('status') != 'TRIAL' or sorted(challenge.get('subset', [])) != list(range(24))
            or chain_claim.get('claim_id') != 1 or chain_claim.get('active_challenge') != 1
            or chain_claim.get('status') != 'TRIAL'):
        raise ValueError('audit is only for the unchanged pre-rule C1/H1 TRIAL')
    expected = {key: claim[key] for key in ('subject', 'endpoint', 'score_milli', 'scoring_rule',
        'classes', 'delta_threshold', 'recall_threshold', 'min_items')}
    expected.update(item_hashes=[run_case.tool.item_commitment(item['prompt'], item['answer'], item['salt'])
        for item in claim['_items']], stake=int(claim['stake']), bond_sworn=int(claim['bond']))
    expected.update(claim['extras'])
    for key, value in expected.items():
        if chain_claim.get(key) != value:
            raise ValueError('frozen on-chain claim mismatch: ' + key)
    for key in ('prompt_template', 'decode_params'):
        value = chain_claim.get(key)
        if isinstance(value, str):
            value = json.loads(value)
        if value != claim[key]:
            raise ValueError('frozen on-chain claim mismatch: ' + key)
    if set(challenge.get('classes', [])) != set(claim['classes']):
        raise ValueError('challenge classes mismatch')
    certificate = read('certificate', 1)
    solvency = read('solvency')
    states = [read('get_probe', 1, index) for index in range(24)]
    for index, state in enumerate(states):
        if state.get('challenge_id') != 1 or state.get('item_index') != index:
            raise ValueError('probe identity mismatch')
        env = rewrites[index]
        if state.get('rewrite_class') and any(state.get(k) != v for k, v in {
                'rewrite_class': env['class'], 'rewrite_prompt': env['prompt'],
                'rewrite_answer': env['answer'], 'rewrite_hash': run_case.tool.rewrite_hash(
                    env['class'], env['prompt'], env['answer'])}.items()):
            raise ValueError('applied rewrite differs from frozen input')
    receipts = {}
    classifications = []
    for index, row in enumerate(rows):
        tx = row['tx']
        if tx not in receipts:
            receipts[tx] = fetch_receipt(tx, rpc, 30)
            save('receipt', tx, receipts[tx])
        receipt = receipts[tx]
        classifications.append({'tx': tx, 'key': row['key'], 'method': row.get('method'),
            'previous_tx': row.get('previous_tx'), 'status': status_of(receipt),
            'execution': execution_of(receipt), 'consensus_result': consensus_result_of(receipt),
            'receipt_successful': successful(receipt)})
        if index % 20 == 0:
            print('read receipts', index + 1, '/', len(rows), flush=True)
    if manifest.read_bytes() != original:
        raise ValueError('manifest changed during audit; raw reads retained, rerun when writer is idle')
    totals = {k: dict(collections.Counter(s.get(k, '') for s in states))
              for k in ['pinned', 'recall', 'stage_c1', 'stage_c2', 'rewrite']}
    result = {'format': 'impeach-native-audit/1', 'began_at': begin,
        'ended_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'address': address, 'claim_id': 1, 'challenge_id': 1,
        'manifest_sha256': digest(original), 'input_sha256': frozen,
        'source_sha256': digest((ROOT / 'build/impeach.py').read_bytes()),
        'frozen_onchain_claim_matches': True,
        'clock': clock, 'counts': counts, 'claim': chain_claim, 'challenge': challenge,
        'certificate': certificate, 'solvency': solvency, 'states': states, 'totals': totals,
        'all_24_admitted': all(s.get('stage_c1') == s.get('stage_c2') == 'ADMISSIBLE' for s in states),
        'all_24_pinned_right': totals['pinned'] == {'RIGHT': 24},
        'all_24_recall_miss': totals['recall'] == {'MISS': 24},
        'manifest_rows': len(rows), 'unique_hashes': len(receipts),
        'recovery_rows': sum(bool(r.get('previous_tx')) for r in rows),
        'statuses': dict(collections.Counter(x['status'] for x in classifications)),
        'all_manifest_finalized': all(x['status'] == 'FINALIZED' for x in classifications),
        'transactions': classifications,
        'raw_sha256': digest((folder / 'raw.jsonl').read_bytes()),
        'caution': 'Native FINALIZED alone is not application success; original failed attempts remain in history.'}
    (folder / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['totals', 'all_24_admitted', 'statuses',
        'all_manifest_finalized', 'manifest_rows', 'recovery_rows']}), flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
