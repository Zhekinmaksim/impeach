"""Narrow, opt-in no-messages proof. Receipt-only success/failure rules stay strict.

Bundles are immutable local evidence; new dispatches always obtain a fresh
read-only RPC proof. Historical bundles are revalidated, never silently repaired.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import run_case
from chain_receipts import status_of, execution_of, consensus_result_of

ROOT = Path(run_case.ROOT)
BASIS = 'verified_finalized_no_messages'
MAIN = '0x0112bf6e83497965a5fdd6dad1e447a6e004271d'
PHASE = '0x7de0ff58b401f2d800470e4390e24ff2baa02aae'
TOPIC = '0xfcc739ca8e51c67e4fd127179070d26ae8ed5ed6dcbc26bcd88ff81c50f346a6'
PINS = {
    'ConsensusMain': '0x0a2c393975da79505ed930efc55ae4aeb88b0d62',
    'FinalizationPhase': '0x3ab63c1fc784682ef72276a76e2ad8fc1c5813b2',
    'ConsensusData': '0x7ee629530e70e2a3a772f8522d8835060abf0755',
    'IdlenessPhase': '0x2cf61473cafcf47adc0ddd861290a7e848881446',
    'Idleness': '0x4e696416634012119187d8dda6a56e66ac7cb23d',
    'TransactionManager': '0xeee45073f7eeb3b80d1973f8398f8e508f893f9c',
    'Queues': '0x7559ebdbc6f59e5dd2a048a1a1539ac14bf93db0',
    'AddressManager': '0xf63f3a95fbf2e97618a5e3ea0fff63024915f3e6',
}


def require(condition, message):
    if not condition:
        raise ValueError('native failure proof: ' + message)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def candidate(receipt):
    return status_of(receipt) == 'FINALIZED' and (execution_of(receipt), consensus_result_of(receipt)) in {
        ('FINISHED_WITH_RETURN', 'IDLE'), ('NOT_VOTED', 'MAJORITY_AGREE')}


def claim_hash(path):
    claim = run_case.load_claim(path)
    return digest([claim, run_case.load_rewrites(claim)])


def protocol(p):
    require(p['chainId'] == 4221 and p['main'].lower() == MAIN and p['version'] == '2.0.0' and
            p['manager'].lower() == '0x8ace036c8c3c5d603db546b031302fcf149648e8' and
            p['sourceCommit'] == '9c686087963551277fc2dce0354c2b1a7050b4b2' and
            {k: v.lower() for k, v in p['implementations'].items()} == PINS, 'unreviewed protocol')


def native(snapshot, row, call_args, source_sha):
    protocol(snapshot['protocol'])
    require(snapshot['address'].lower() == row['address'].lower() and snapshot['sourceSha256'] == source_sha,
            'court/source mismatch')
    matches = [t for t in snapshot['transactions'] if t['tx'].lower() == row['tx'].lower()]
    require(len(matches) == 1, 'missing/duplicate native hash')
    c = matches[0]
    require(c['stored']['id'].lower() == row['tx'].lower() and
            c['stored']['recipient'].lower() == row['address'].lower() and
            c['receipt']['recipient'].lower() == row['address'].lower() and
            c['receipt']['txId'].lower() == row['tx'].lower() and str(c['stored']['value']) == '0',
            'native identity/value mismatch')
    require(type(c['stored']['result']) is int and c['stored']['result'] in range(6) and
            type(c['stored']['txExecutionResult']) is int and c['stored']['txExecutionResult'] in range(5),
            'unknown stored outcome')
    require(c['decoded'] == {'type': 'call', 'leaderOnly': False,
                            'callData': {'method': 'probe', 'args': call_args}}, 'native calldata mismatch')
    return c


def validate(bundle, row, receipt, call_args, *, expected_claim=None, expected_source=None):
    require(candidate(receipt), 'receipt is outside the two explicit ambiguous outcomes')
    require(bundle['format'] == 'impeach-native-no-messages/1' and bundle['tx'].lower() == row['tx'].lower()
            and bundle['address'].lower() == row['address'].lower(), 'bundle identity mismatch')
    require(bundle['call'] == {'method': 'probe', 'args': call_args, 'value': '0'} and
            digest(['probe', call_args, '0']) == row['signature'], 'original call mismatch')
    source_sha = bundle['source_sha256']
    require(isinstance(source_sha, str) and len(source_sha) == 64 and
            (expected_source is None or source_sha == expected_source) and
            (expected_claim is None or bundle['claim_sha256'] == expected_claim), 'frozen inputs changed')
    snapshot = bundle['snapshot']
    c = native(snapshot, row, call_args, source_sha)
    require(c['stored']['status'] == 7 and candidate(c['receipt']) and
            (execution_of(c['receipt']), consensus_result_of(c['receipt'])) ==
            (execution_of(receipt), consensus_result_of(receipt)), 'fresh native outcome differs')
    protocol(bundle['eventProtocol'])
    event, evm = bundle['event'], bundle['evm']
    r, t, block = evm['receipt'], evm['transaction'], evm['block']
    require(r['status'] == 'success' and r['to'].lower() == MAIN and t['to'].lower() == MAIN and
            str(t['value']) == '0' and t['hash'].lower() == r['transactionHash'].lower() and
            t['blockHash'].lower() == r['blockHash'].lower() and int(t['blockNumber']) == int(r['blockNumber']) and
            block['hash'].lower() == r['blockHash'].lower() and
            int(block['number']) == int(r['blockNumber']) <= int(snapshot['blockNumber']), 'EVM receipt mismatch')
    logs = [log for log in r['logs'] if log['address'].lower() == PHASE and
            len(log.get('topics', [])) >= 2 and log['topics'][0].lower() == TOPIC and
            log['topics'][1].lower() == row['tx'].lower()]
    require(len(logs) == 1 and event['log'] == logs[0], 'missing/competing Phase event')
    log = logs[0]
    previous = event['previousStatus']
    require(type(previous) is int and previous in {6, 12, 13} and event['shouldProcessMessages'] is False and
            event['txId'].lower() == row['tx'].lower() and log['removed'] is False and len(log['topics']) == 2 and
            log['data'].lower() == '0x' + format(previous, '064x') + '0' * 64 and
            log['transactionHash'].lower() == r['transactionHash'].lower() and
            log['blockHash'].lower() == r['blockHash'].lower() and int(log['blockNumber']) == int(r['blockNumber']),
            'event does not prove finalization without messages')
    require(bundle['origin'] in {'chain_observation', 'service_queue'}, 'unknown proof origin')
    if bundle['origin'] == 'service_queue':
        service = bundle['service']
        before = service['before']
        old = native(before['protocol'], row, call_args, source_sha)
        old_phase = old['stored']['status']
        require((old_phase == previous or (old_phase in {12, 13} and previous == 6)) and
                old_phase in {6, 12, 13} and old['atFinalizedHead'] is True and
                before['row']['tx'].lower() == row['tx'].lower() and before['row']['signature'] == row['signature'],
                'service before evidence mismatch')
        dispatch, done = service['dispatch'], service['done']
        require(dispatch['operation'] == 'finalize' and dispatch['tx'].lower() == row['tx'].lower() and
                dispatch['value'] == 0 and dispatch['from'].lower() == t['from'].lower() and
                done['resolved'] is True and done['native_status'] == 'FINALIZED' and
                done['evm_tx'].lower() == r['transactionHash'].lower() and
                service['evm_hash']['evm_tx'].lower() == r['transactionHash'].lower() and
                service['evm_receipt']['receipt'] == r and service['evm_receipt']['transaction'] == t and
                t['input'].lower() == '0xb2efda83' + row['tx'][2:].lower(), 'service dispatch mismatch')
        closed = native(service['after'], row, call_args, source_sha)
        require(closed['stored']['status'] == 7 and status_of(closed['receipt']) == 'FINALIZED', 'service not closed')
    else:
        require('service' not in bundle, 'chain observation contains fabricated dispatch')
    return True


def service_evidence(manifest, row, bundle):
    stem = Path(os.path.abspath(manifest) + '.queue') / (row['tx'].lower() + '.finalize')
    if not Path(str(stem) + '.dispatch.json').exists():
        return
    names = {'before': 'before', 'dispatch': 'dispatch', 'evm_hash': 'evm-hash',
             'evm_receipt': 'evm-receipt', 'after': 'after', 'done': 'done'}
    evidence = {}
    for key, suffix in names.items():
        path = Path(str(stem) + '.' + suffix + '.json')
        require(not path.is_symlink(), 'symlinked service evidence')
        evidence[key] = json.loads(path.read_text())
    bundle.update(origin='service_queue', service=evidence)


def obtain(args, row, receipt, call_args):
    require(getattr(args, 'allow_proven_no_messages', False) and candidate(receipt), 'proof path is not enabled/eligible')
    source = Path(getattr(args, 'source', ROOT / 'build/impeach.py'))
    source_sha, claim_sha = hashlib.sha256(source.read_bytes()).hexdigest(), claim_hash(args.claim)
    command = ['node', 'scripts/native_finality_proof.mjs', '--rpc', args.rpc,
               '--address', row['address'], '--tx', row['tx'], '--source', str(source)]
    stem = Path(os.path.abspath(args.manifest) + '.queue') / (row['tx'].lower() + '.finalize')
    if Path(str(stem) + '.dispatch.json').exists():
        recorded = Path(str(stem) + '.evm-hash.json')
        require(not recorded.is_symlink(), 'symlinked service hash')
        command += ['--evm-hash', json.loads(recorded.read_text())['evm_tx']]
    result = subprocess.run(command,
        cwd=ROOT, capture_output=True, text=True, timeout=90)
    require(result.returncode == 0, 'read-only lookup failed: ' + result.stderr[-500:])
    bundle = json.loads(result.stdout)
    bundle.update(call={'method': 'probe', 'args': call_args, 'value': '0'},
                  source_sha256=source_sha, claim_sha256=claim_sha)
    service_evidence(args.manifest, row, bundle)
    validate(bundle, row, receipt, call_args, expected_claim=claim_sha, expected_source=source_sha)
    require(hashlib.sha256(source.read_bytes()).hexdigest() == source_sha and claim_hash(args.claim) == claim_sha,
            'inputs changed during proof lookup')
    folder = Path(os.path.abspath(args.manifest) + '.receipts')
    folder.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(bundle, ensure_ascii=False, indent=2) + '\n').encode()
    sha = hashlib.sha256(raw).hexdigest()
    path = folder / ('native-proof-' + row['tx'].lower() + '-' + sha + '.json')
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as out:
            temporary = out.name; out.write(raw); out.flush(); os.fsync(out.fileno())
        try:
            os.link(temporary, path)
            fd = os.open(folder, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
        finally: os.unlink(temporary)
    require(path.read_bytes() == raw and not path.is_symlink(), 'existing bundle changed')
    return {'previous_failure_basis': BASIS,
            'previous_finalization_proof': os.path.relpath(path, Path(args.manifest).resolve().parent),
            'previous_finalization_proof_sha256': sha}


def verify_reference(entry, manifest, row, receipt, call_args, claim_path=None, source_path=None):
    require(entry.get('previous_failure_basis') == BASIS, 'unknown failure basis')
    relative = entry['previous_finalization_proof']
    base = Path(manifest).resolve().parent
    path = base / relative
    require(not os.path.isabs(relative) and not path.is_symlink() and not Path(os.path.abspath(manifest) + '.receipts').is_symlink() and
            path.resolve().parent == Path(os.path.abspath(manifest) + '.receipts').resolve(), 'unsafe proof path')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == entry['previous_finalization_proof_sha256'], 'proof digest changed')
    bundle = json.loads(raw)
    return validate(bundle, row, receipt, call_args if call_args is not None else bundle['call']['args'],
                    expected_claim=claim_hash(claim_path) if claim_path else None,
                    expected_source=hashlib.sha256(Path(source_path).read_bytes()).hexdigest() if source_path else None)


def frozen_claim(chain, claim_path):
    local = run_case.load_claim(claim_path)
    expected = {k: local[k] for k in ('subject', 'endpoint', 'score_milli', 'scoring_rule',
                                      'classes', 'delta_threshold', 'recall_threshold', 'min_items')}
    expected.update(local['extras'])
    expected.update(item_hashes=[run_case.tool.item_commitment(i['prompt'], i['answer'], i['salt']) for i in local['_items']],
                    stake=int(local['stake']), bond_sworn=int(local['bond']))
    require(all(chain.get(k) == v for k, v in expected.items()), 'on-chain frozen claim differs')
    for key in ('decode_params', 'prompt_template'):
        value = chain.get(key)
        if isinstance(value, str): value = json.loads(value)
        require(value == local[key], 'on-chain frozen ' + key + ' differs')
