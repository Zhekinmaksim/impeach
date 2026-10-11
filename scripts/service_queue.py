#!/usr/bin/env python3
"""Inspect/service known Bradbury queue heads between complete_case runs.

Read-only by default. --execute permits only zero-value Main finalize or
processIdleness calls after exact gas simulation. Never appeals or resubmits an
application call. Shares <manifest>.complete.lock; stop other account writers.
Evidence lives in <manifest>.queue/. An uncertain dispatch requires manual
reconciliation, never deleting markers and guessing a resend.
Use --from with the public address of --account; --source is the exact deployed
artifact. A bounded run exits 2 when waiting, exhausted or needing attention.
"""
import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from types import SimpleNamespace

import complete_case
import retry_finalized_probe as recovery
import run_case
from chain_receipts import (EXECUTION_CODES, NEGATIVE_RESULTS, RESULT_CODES, STATUS_CODES,
                            consensus_result_of, execution_of, status_of)

ROOT = Path(run_case.ROOT)
ZERO = '0x' + '0' * 64
MAIN = '0x0112bf6e83497965a5fdd6dad1e447a6e004271d'
IMPL = '0x0a2c393975da79505ed930efc55ae4aeb88b0d62'
HASH = re.compile(r'^0x[0-9a-fA-F]{64}$')
ADDRESS = re.compile(r'^0x[0-9a-fA-F]{40}$')
PROJECTED = {'UNDETERMINED', 'LEADER_TIMEOUT', 'VALIDATORS_TIMEOUT', 'READY_TO_FINALIZE'}
DEFERRED = {1, 2, 3, 4, 9, 10, 14}
HEADS = ('getFinalizedHeadTxId', 'getPendingHeadTxId', 'getAcceptedHeadTxId', 'getUndeterminedHeadTxId')
Pause = complete_case.Pause


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def applied(state, mode):
    return {'PINNED': state.get('pinned') in {'RIGHT', 'WRONG', 'DEAD'},
            'RECALL': state.get('recall') in {'MATCH', 'MISS', 'NA', 'DEAD'},
            'REWRITE': bool(state.get('rewrite_class')) and state.get('stage_c1') in {'ADMISSIBLE', 'INADMISSIBLE'},
            'ADMIT': state.get('stage_c1') == 'ADMISSIBLE' and
                     state.get('stage_c2') in {'ADMISSIBLE', 'INADMISSIBLE'}}[mode]


def phase_fingerprint(candidate):
    # Wall clock/block number are excluded: waiting alone must not permit a
    # duplicate idleness call. Phase/round/timer progress must be observed.
    return digest({'tx': candidate['tx'].lower(), 'status': candidate['stored']['status'],
                   'round': candidate['receipt'].get('numOfRounds'),
                   'timestamps': candidate['mainTimestamps']})


def state_fingerprint(candidate):
    return digest({key: candidate[key] for key in ('stored', 'decoded', 'mainTimestamps', 'queueType',
                                                  'queueModification', 'atFinalizedHead')} |
                  {'round': candidate['receipt'].get('lastRound'),
                   'status': status_of(candidate['receipt']), 'result': consensus_result_of(candidate['receipt']),
                   'execution': execution_of(candidate['receipt'])})


def mature(candidate, snapshot):
    return (candidate['stored']['status'] in DEFERRED and
            status_of(candidate['receipt']) in PROJECTED and candidate['firstSlotElapsed'] is True and
            any(int(value) > 0 for value in candidate['mainTimestamps'].values()) and
            any(int(value) > 0 for value in snapshot['mainTimeouts'].values()))


def outcome_evidence(candidate):
    # These verified failed phases remain failed native executions even if
    # stale result/execution fields resemble success after queue finalization.
    undetermined = candidate['stored']['status'] == 6
    failed_phase = candidate['stored']['status'] in {6, 12, 13}
    return {'beforeStoredUND': undetermined,
            **({'beforeStoredFailurePhase': candidate['stored']['status'], 'native_success': False}
               if failed_phase else {})}


class QueueService:
    def __init__(self, args, lock):
        self.args, self.lock = args, lock
        self.started = time.monotonic()
        self.folder = Path(os.path.abspath(args.manifest) + '.queue')
        self.folder.mkdir(parents=True, exist_ok=True)
        self.operations = 0
        self.local = self.local_identity()
        self.rows = self.load_rows()
        identity = {'address': args.address.lower(), 'claim_id': args.claim_id,
                    'challenge_id': args.challenge_id, 'claim_sha256': self.local['claim_sha256'],
                    'source_sha256': self.local['source_sha256'], 'rpc': args.rpc}
        path = self.folder / 'identity.json'
        if path.exists():
            if json.loads(path.read_text()) != identity:
                raise Pause('queue service identity/source/claim changed')
        else:
            self.save(path, identity)
        self.check_dispatches()

    def save(self, path, data):
        complete_case.json_write(path, data, exclusive=True)

    def event(self, action, **fields):
        value = {'at': int(time.time()), 'action': action, **fields}
        with open(self.folder / 'events.jsonl', 'a') as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps(value, ensure_ascii=False), flush=True)

    def local_identity(self):
        claim = run_case.load_claim(self.args.claim)
        rewrites = run_case.load_rewrites(claim)
        if len(claim['_items']) != 24 or set(rewrites) != set(range(24)):
            raise Pause('queue service requires the frozen 24-item claim/rewrites')
        return {'claim_sha256': digest([claim, rewrites]),
                'source_sha256': hashlib.sha256(Path(self.args.source).read_bytes()).hexdigest(),
                'manifest_sha256': hashlib.sha256(Path(self.args.manifest).read_bytes()).hexdigest()}

    def guard(self):
        if self.local_identity() != self.local:
            raise Pause('local claim/source/manifest changed during queue service')
        if time.monotonic() - self.started >= self.args.max_runtime:
            raise Pause('queue service runtime limit reached')

    def load_rows(self):
        history = recovery.manifest_history(self.args.manifest)
        expected = {}
        def capture(key, method, call_args, value=0, extra=None):
            expected[key] = (method, call_args, str(value))
        plan = SimpleNamespace(args=SimpleNamespace(claim=self.args.claim, claim_id=self.args.claim_id,
                                                   challenge_id=self.args.challenge_id, subset=''), send=capture)
        for step in (run_case.step_open, run_case.step_challenge, run_case.step_reveal, run_case.step_rule):
            step(plan)
        bytx = {}
        for key, chain in history.items():
            if chain[-1].get('method') == 'probe':
                recovery.validate_history(chain[-1], self.args.manifest, history, self.args.claim, self.args.source)
            for row in chain:
                tx = row.get('tx', '')
                if not HASH.fullmatch(tx) or tx.lower() in bytx or row.get('address', '').lower() != self.args.address.lower():
                    raise Pause('manifest hash/address is malformed, duplicated or belongs to another court')
                if row.get('method') == 'probe':
                    if row.get('challenge_id') != self.args.challenge_id:
                        raise Pause('manifest probe belongs to another challenge')
                    args = recovery.original_call(row, self.args.claim)
                    call = ('probe', args, '0')
                else:
                    call = expected.get(key)
                    if not call or call[0] != row.get('method') or digest(list(call)) != row.get('signature'):
                        # run_case uses default JSON separators, as digest does.
                        raise Pause('manifest contains an unrecognized application call/signature')
                    if row['method'] == 'rule' and (row.get('step') != 'rule' or
                            row.get('challenge_id') != self.args.challenge_id or str(row.get('value', '0')) != '0'):
                        raise Pause('manifest rule must match the challenge, step and zero value')
                row = copy.deepcopy(row)
                row['_expected_call'] = {'method': call[0], 'args': call[1], 'value': call[2]}
                bytx[tx.lower()] = row
        if not bytx:
            raise Pause('manifest is empty')
        return bytx

    def read(self, method, *args):
        return run_case.tool.chain_call(self.args.address, method, list(args), self.args.rpc, 30)

    def claim_guard(self):
        claim = run_case.load_claim(self.args.claim)
        chain = self.read('get_claim', self.args.claim_id)
        challenge = self.read('get_challenge', self.args.challenge_id)
        if (chain.get('claim_id') != self.args.claim_id or challenge.get('claim_id') != self.args.claim_id or
                challenge.get('challenge_id') != self.args.challenge_id or
                sorted(challenge.get('subset', [])) != list(range(24)) or
                set(challenge.get('classes', [])) != set(claim['classes'])):
            raise Pause('claim/challenge identity or full corpus does not match')
        expected = {k: claim[k] for k in ('subject', 'endpoint', 'score_milli', 'scoring_rule',
                                        'classes', 'delta_threshold', 'recall_threshold', 'min_items')}
        expected.update(claim['extras'])
        expected.update(item_hashes=[run_case.tool.item_commitment(i['prompt'], i['answer'], i['salt']) for i in claim['_items']],
                        stake=int(claim['stake']), bond_sworn=int(claim['bond']))
        if any(chain.get(k) != v for k, v in expected.items()):
            raise Pause('on-chain frozen claim differs from local inputs')
        for key in ('decode_params', 'prompt_template'):
            actual = chain.get(key)
            if isinstance(actual, str):
                actual = json.loads(actual)
            if actual != claim[key]:
                raise Pause('on-chain frozen claim differs: ' + key)
        # Queue cleanup does not submit probes and remains valid after TRIAL
        # expires. The application runner owns its stricter trial deadline.
        return {'claim': chain, 'challenge': challenge}

    def inspect(self, tx=None):
        command = ['node', 'scripts/inspect_queue.mjs', '--address', self.args.address,
                   '--rpc', self.args.rpc, '--source', self.args.source]
        if tx:
            command += ['--tx', tx]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise Pause('read-only protocol inspection failed: ' + result.stderr[-1500:])
        return json.loads(result.stdout)

    def validate(self, data):
        p = data['protocol']
        if (p['chainId'] != 4221 or p['main'].lower() != MAIN or p['version'] != '2.0.0' or
                p['implementations']['ConsensusMain'].lower() != IMPL or
                data['address'].lower() != self.args.address.lower() or data['sourceSha256'] != self.local['source_sha256']):
            raise Pause('unverified network, implementation or court source')
        heads = data['heads']
        if set(heads) != set(HEADS):
            raise Pause('incomplete court queue heads')
        bytx = {d['tx'].lower(): d for d in data['transactions']}
        if len(bytx) != len(data['transactions']):
            raise Pause('duplicate protocol transaction records')
        for tx in heads.values():
            if not HASH.fullmatch(tx) or (tx != ZERO and (tx.lower() not in bytx or tx.lower() not in self.rows)):
                raise Pause('unknown queue head is outside the authorized manifest')
        for tx, candidate in bytx.items():
            row = self.rows.get(tx)
            if not row:
                raise Pause('protocol transaction is outside the authorized manifest')
            stored, receipt = candidate['stored'], candidate['receipt']
            if (stored['id'].lower() != tx or stored['recipient'].lower() != self.args.address.lower() or
                    receipt['recipient'].lower() != self.args.address.lower() or
                    stored['status'] not in STATUS_CODES or stored['result'] not in RESULT_CODES or
                    stored['txExecutionResult'] not in EXECUTION_CODES or
                    status_of(receipt) not in STATUS_CODES.values() or execution_of(receipt) not in EXECUTION_CODES.values() or
                    consensus_result_of(receipt) not in RESULT_CODES.values()):
                raise Pause('unknown/conflicting native status or transaction recipient')
            decoded, expected = candidate['decoded'], row['_expected_call']
            if (decoded.get('type') != 'call' or decoded.get('leaderOnly') is not False or
                    decoded.get('callData') != {'method': expected['method'], 'args': expected['args']} or
                    str(stored['value']) != expected['value']):
                raise Pause('native calldata/value does not match the original manifest call')
            if (type(candidate['firstSlotElapsed']) is not bool or type(candidate['atFinalizedHead']) is not bool or
                    not isinstance(candidate['mainTimestamps'], dict) or not isinstance(data['mainTimeouts'], dict)):
                raise Pause('missing Main timer/queue evidence')
            if (set(candidate['mainTimestamps']) != {'created', 'pending', 'activated', 'proposed', 'committed',
                                                     'lastVote', 'appealSubmitted', 'leaderRevealed'} or
                    set(data['mainTimeouts']) != {'activate', 'propose', 'commit', 'reveal', 'accept', 'leaderReveal'} or
                    not str(receipt.get('numOfRounds', '')).isdigit()):
                raise Pause('incomplete Main timestamps/timeouts or round evidence')
            for value in [data['blockTimestamp'], *candidate['mainTimestamps'].values(), *data['mainTimeouts'].values()]:
                if not str(value).isdigit():
                    raise Pause('invalid Main timer value')
        return bytx

    def check_dispatches(self):
        for path in self.folder.glob('*.dispatch.json'):
            done = path.with_name(path.name.replace('.dispatch.json', '.done.json'))
            if not done.exists() or json.loads(done.read_text()).get('resolved') is not True:
                raise Pause('unresolved protocol dispatch; reconcile its EVM/native outcome: ' + str(path))

    def stem(self, candidate, operation):
        suffix = 'finalize' if operation == 'finalize' else 'process-idleness-' + phase_fingerprint(candidate)
        return self.folder / (candidate['tx'].lower() + '.' + suffix)

    def preflight(self, candidate, operation):
        command = ['node', 'scripts/genlayer_write.mjs', '--' + operation, candidate['tx'],
                   '--value', '0', '--dry-run', '--from', self.args.from_address, '--rpc', self.args.rpc]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.save(self.folder / ('simulation-' + str(time.time_ns()) + '.json'),
                  {'operation': operation, 'tx': candidate['tx'], 'returncode': result.returncode,
                   'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode == 0:
            return True
        # Only an explicit EVM revert permits the idleness fallback. Transport,
        # gas-cap, parsing or signing-wrapper failures are not eligibility data.
        message = (result.stdout + result.stderr).lower()
        if 'revert' not in message:
            raise Pause('protocol simulation failed without an explicit EVM revert')
        return False

    def dispatch(self, candidate, operation, before, identity):
        stem = self.stem(candidate, operation)
        if Path(str(stem) + '.dispatch.json').exists():
            raise Pause('protocol operation already attempted for this hash/phase; no repeat')
        outcome = outcome_evidence(candidate)
        self.save(str(stem) + '.before.json', {'protocol': before, 'identity': identity,
                                              'row': self.rows[candidate['tx'].lower()], **outcome})
        self.guard()
        marker = {'at': int(time.time()), 'operation': operation, 'tx': candidate['tx'],
                  'phase_fingerprint': phase_fingerprint(candidate), 'account': self.args.account,
                  'from': self.args.from_address, 'value': 0, 'status': 'DISPATCHING', **outcome}
        self.save(str(stem) + '.dispatch.json', marker)
        command = ['node', 'scripts/genlayer_write.mjs', '--' + operation, candidate['tx'],
                   '--value', '0', '--account', self.args.account, '--rpc', self.args.rpc]
        evm = self.broadcast(command, stem)
        result = subprocess.run(['node', 'scripts/inspect_queue.mjs', '--rpc', self.args.rpc,
                                 '--evm-receipt', evm], cwd=ROOT, capture_output=True, text=True, timeout=55)
        if result.returncode:
            raise Pause('EVM receipt unavailable; dispatch remains unresolved')
        evidence = json.loads(result.stdout)
        self.save(str(stem) + '.evm-receipt.json', evidence)
        if (evidence['receipt']['status'] != 'success' or
                evidence['transaction']['from'].lower() != self.args.from_address.lower()):
            raise Pause('EVM operation reverted or used an unexpected signer; no repeat')
        after = self.inspect(candidate['tx'])
        self.save(str(stem) + '.after.json', after)
        current = self.validate(after)[candidate['tx'].lower()]
        if operation == 'finalize':
            resolved = status_of(current['receipt']) == 'FINALIZED' and current['stored']['status'] == 7
        else:
            resolved = phase_fingerprint(candidate) != phase_fingerprint(current)
        self.save(str(stem) + '.done.json', {'at': int(time.time()), 'resolved': resolved,
                                            'evm_tx': evm, 'native_status': status_of(current['receipt']), **outcome})
        self.operations += 1
        self.event('PROTOCOL_OPERATION_DONE', operation=operation, tx=candidate['tx'], evm_tx=evm,
                   native_status=status_of(current['receipt']), resolved=resolved, **outcome)
        if not resolved:
            raise Pause('EVM success without expected native progress; no repeat')

    def broadcast(self, command, stem):
        # The bridge inherits the lock until it exits even if the supervisor
        # reaches its runtime bound. Its file log remains writable without us.
        path = Path(str(stem) + '.command.log')
        with open(path, 'x') as out:
            proc = subprocess.Popen(command, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                    text=True, pass_fds=(self.lock.fileno(),))
        evm = None
        while True:
            # Poll before reading: once exit is observed, the final log bytes
            # are present; a hash written just before exit cannot be missed.
            rc = proc.poll()
            raw = path.read_text()
            hashes = re.findall(r'(?:Idleness|Finalization) EVM transaction: (0x[0-9a-fA-F]{64})', raw)
            if len(set(hashes)) > 1:
                raise Pause('multiple EVM hashes for one dispatch; reconcile before proceeding')
            if hashes and evm is None:
                evm = hashes[0]
                self.save(str(stem) + '.evm-hash.json', {'at': int(time.time()), 'evm_tx': evm})
                self.event('EVM_HASH', evm_tx=evm)
            if rc is not None:
                self.save(str(stem) + '.result.json', {'at': int(time.time()), 'returncode': rc, 'evm_tx': evm})
                if rc or not evm:
                    raise Pause('dispatch outcome uncertain; no resend, reconcile command log')
                return evm
            if time.monotonic() - self.started >= self.args.max_runtime:
                self.save(str(stem) + '.pending-process.json', {'pid': proc.pid, 'evm_tx': evm, 'lock_inherited': True})
                raise Pause('dispatch still running; hash may be unknown, inherited lock remains held')
            time.sleep(.1)

    def run(self):
        while self.operations < self.args.max_operations:
            self.guard()
            identity = self.claim_guard()
            data = self.inspect()
            bytx = self.validate(data)
            self.save(self.folder / ('snapshot-' + str(time.time_ns()) + '.json'), data)
            heads = data['heads']
            if all(tx == ZERO for tx in heads.values()):
                self.event('QUEUE_EMPTY')
                return 0
            candidates = []
            final = heads['getFinalizedHeadTxId'].lower()
            if final != ZERO:
                c = bytx[final]
                result, execution = consensus_result_of(c['receipt']), execution_of(c['receipt'])
                stored_failed = c['stored']['status'] in {6, 12, 13}
                positive = execution == 'FINISHED_WITH_RETURN' and result == 'MAJORITY_AGREE'
                negative = result in NEGATIVE_RESULTS or (execution == 'NOT_VOTED' and result == 'IDLE')
                state_ok = True
                row = self.rows[final]
                if positive and not stored_failed and row['method'] == 'probe':
                    state = self.read('get_probe', self.args.challenge_id, row['item_index'])
                    state_ok = (state.get('challenge_id') == self.args.challenge_id and
                                state.get('item_index') == row['item_index'] and applied(state, row['mode']))
                    if state_ok and row['mode'] in {'REWRITE', 'ADMIT'}:
                        env = run_case.load_rewrites(run_case.load_claim(self.args.claim))[row['item_index']]
                        state_ok = (state.get('rewrite_class') == env['class'] and
                                    state.get('rewrite_prompt') == env['prompt'] and state.get('rewrite_answer') == env['answer'] and
                                    state.get('rewrite_hash') == run_case.tool.rewrite_hash(env['class'], env['prompt'], env['answer']))
                if (stored_failed or positive or negative) and state_ok and c['atFinalizedHead'] and (
                        c['stored']['status'] in {5, 6, 12, 13} or mature(c, data)):
                    # CD.canFinalize is advisory: exact Main simulation below
                    # covers valid paths which the older view reports false.
                    # Stored phases 6/12/13 skip message processing in Main;
                    # its stale outcome fields need no application-state proof.
                    candidates.append((c, 'finalize'))
            for tx in dict.fromkeys((heads['getPendingHeadTxId'].lower(), final)):
                if tx != ZERO and mature(bytx[tx], data):
                    candidates.append((bytx[tx], 'process-idleness'))
            for candidate, operation in candidates:
                stem = self.stem(candidate, operation)
                if Path(str(stem) + '.dispatch.json').exists():
                    raise Pause('protocol operation already consumed for this hash/phase; no repeat')
                if not self.preflight(candidate, operation):
                    continue
                self.event('PLAN', operation=operation, tx=candidate['tx'], execute=self.args.execute,
                           consensus_data_can_finalize=candidate['canFinalize'], **outcome_evidence(candidate))
                if not self.args.execute:
                    return 0
                self.guard()
                current_identity = self.claim_guard()
                fresh = self.inspect()
                current = self.validate(fresh).get(candidate['tx'].lower())
                if (current is None or state_fingerprint(current) != state_fingerprint(candidate) or
                        fresh['heads'] != data['heads'] or current_identity != identity):
                    raise Pause('native state/heads changed during simulation; re-inspect before signing')
                self.dispatch(current, operation, fresh, identity)
                break
            else:
                self.event('WAITING_PROTOCOL', heads=heads)
                return 2
        self.event('OPERATION_BOUND', operations=self.operations)
        return 2


def service(args):
    runner = None
    os.makedirs(os.path.dirname(os.path.abspath(args.manifest)), exist_ok=True)
    try:
        with open(args.manifest + '.complete.lock', 'a+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Pause('another writer holds the completion lock')
            runner = QueueService(args, lock)
            return runner.run()
    except (Pause, SystemExit, RuntimeError, ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
        if runner:
            runner.event('PAUSED', reason=str(exc))
        print(json.dumps({'phase': 'PAUSED', 'reason': str(exc), 'exit_code': 2}), flush=True)
        return 2


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('address', 'manifest', 'claim', 'account', 'rpc'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--from', dest='from_address', required=True, help='public address of --account; never a private key')
    parser.add_argument('--claim-id', type=int, required=True)
    parser.add_argument('--challenge-id', type=int, required=True)
    parser.add_argument('--source', default=str(ROOT / 'build/impeach.py'))
    parser.add_argument('--max-runtime', type=float, default=300)
    parser.add_argument('--max-operations', type=int, default=8)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if (not ADDRESS.fullmatch(args.address) or not ADDRESS.fullmatch(args.from_address) or
            args.claim_id < 0 or args.challenge_id < 0 or not args.account.strip() or
            not 0 < args.max_runtime <= 3600 or not math.isfinite(args.max_runtime) or
            not 1 <= args.max_operations <= 128 or not re.match(r'^https?://', args.rpc)):
        parser.error('invalid court/signer/identity/timing options')
    return args


if __name__ == '__main__':
    raise SystemExit(service(parse_args()))
