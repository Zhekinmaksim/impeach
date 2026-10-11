#!/usr/bin/env python3
"""Complete a revealed 24-item TRIAL without adjudicating or withdrawing.

One process holds <manifest>.complete.lock. Stop other signing tools for this
manifest/account before starting. State and immutable failure receipts live in
<manifest>.complete/; progress.json and events.jsonl are safe to inspect while
running. Exit 0 means all answers/recall outcomes and required referee stages
are recorded, not that 24 rewrites were admitted. Exit 2 means resume is needed.
DEAD outcomes are reported, never automatically resubmitted.

Initial calls have durable dispatch markers. An unknown submission outcome
requires manual reconciliation; deleting a marker to guess-and-resend is unsafe.
After progressing all independent initial slots, the existing guarded recovery
helper may retry each finalized, untouched failed slot once by default, or up
to three times with --max-recoveries 3. Every retry requires a new finalized
failure and preserves the earlier hashes and receipts. No appeal,
finalization, rule, retire or withdrawal is performed here.
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
import tempfile
import time

import run_case
import retry_finalized_probe as recovery
import native_failure_proof as proof
from chain_receipts import (EXECUTION_CODES, RESULT_CODES, STATUS_CODES,
                            consensus_result_of, execution_of, fetch_receipt,
                            finalized_failure, status_of, successful)

MODES = ('PINNED', 'RECALL', 'REWRITE', 'ADMIT')
DECIDED_FAILURES = {'UNDETERMINED', 'LEADER_TIMEOUT', 'VALIDATORS_TIMEOUT', 'CANCELED'}
TX = re.compile(r'^0x[0-9a-fA-F]{64}$')


class Pause(RuntimeError):
    """Stop without assuming the outcome or submitting another transaction."""


def signature(call_args):
    return hashlib.sha256(json.dumps(['probe', call_args, '0'], ensure_ascii=False,
                                    sort_keys=True).encode()).hexdigest()


def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def json_write(path, value, exclusive=False):
    """Publish complete JSON durably; exclusive markers are never overwritten."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     prefix='.complete-', delete=False) as stream:
        temporary = stream.name
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    try:
        if exclusive:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        fsync_dir(path.parent)
        fsync_dir(path.parent.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def classify(receipt):
    if not isinstance(receipt, dict) or not any(
            receipt.get(k) not in (None, '') for k in ('status', 'statusName', 'status_name', 'consensus_status')):
        raise Pause('malformed receipt: missing status; resume without another broadcast')
    status, execution, result = status_of(receipt), execution_of(receipt), consensus_result_of(receipt)
    if status not in STATUS_CODES.values():
        raise Pause('unknown or inconsistent receipt status: ' + status)
    if execution not in EXECUTION_CODES.values() and execution != 'UNKNOWN':
        raise Pause('unknown or inconsistent execution result: ' + execution)
    if result not in RESULT_CODES.values() and result != 'UNKNOWN':
        raise Pause('unknown or inconsistent consensus result: ' + result)
    if successful(receipt):
        return 'SUCCESS'
    if status in DECIDED_FAILURES | {'ACCEPTED', 'FINALIZED'}:
        if execution not in EXECUTION_CODES.values() or result not in RESULT_CODES.values():
            raise Pause('decided receipt has unknown execution/consensus; inspect before resuming')
        if (status in DECIDED_FAILURES or finalized_failure(receipt) or
                (status == 'ACCEPTED' and execution != 'FINISHED_WITH_RETURN')):
            return 'FAILURE'
        raise Pause('contradictory or undecided terminal receipt; inspect before resuming')
    return 'PENDING'


def completed(state):
    return (state.get('pinned') in {'RIGHT', 'WRONG'} and
            state.get('recall') in {'MATCH', 'MISS', 'NA'} and
            (state.get('stage_c1') == 'INADMISSIBLE' or
             (state.get('stage_c1') == 'ADMISSIBLE' and
              state.get('stage_c2') in {'ADMISSIBLE', 'INADMISSIBLE'} and
              state.get('rewrite') in {'RIGHT', 'WRONG'})))


class Completer(run_case.Runner):
    def __init__(self, args, completion_lock=None):
        super().__init__(args)
        self.max_recoveries = recovery.max_recoveries(args)
        self.completion_lock = completion_lock
        self.folder = Path(os.path.abspath(args.manifest) + '.complete')
        self.folder.mkdir(parents=True, exist_ok=True)
        self.claim = run_case.load_claim(args.claim)
        self.rewrites = run_case.load_rewrites(self.claim)
        if len(self.claim['_items']) != 24 or set(self.rewrites) != set(range(24)):
            raise Pause('complete_case requires exactly 24 items and one valid rewrite per item')
        self.input_hash = self.fingerprint()
        self.states, self.outcomes, self.receipts = {}, {}, {}
        self.finality_proofs = {}
        self.failure_records = {}
        self.claim_id = None
        self.deadline = self.chain_time = None
        self.phase = 'STARTING'
        self.message = ''
        self.started = time.monotonic()
        self.new_transactions = 0
        self.restore_events()
        self.validate_rows()
        self.check_markers()

    def fingerprint(self):
        claim = run_case.load_claim(self.args.claim)
        rewrites = run_case.load_rewrites(claim)
        return hashlib.sha256(json.dumps([claim, rewrites], sort_keys=True,
                                        ensure_ascii=False).encode()).hexdigest()

    def event(self, event, **fields):
        value = {'event': event, 'at': int(time.time()), **fields}
        with open(self.folder / 'events.jsonl', 'a', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        fsync_dir(self.folder)
        print(json.dumps(value, ensure_ascii=False), flush=True)

    def restore_events(self):
        path = self.folder / 'events.jsonl'
        if path.exists():
            try:
                for line in path.read_text().splitlines():
                    row = json.loads(line)
                    if row.get('event') == 'ACKNOWLEDGED_FAILURE':
                        self.failure_records[row['tx'].lower() + '-' + row['receipt_sha256']] = row
            except (ValueError, KeyError) as exc:
                raise Pause('malformed completion log; reconcile before resuming') from exc
        identity = self.folder / 'identity.json'
        expected = {'address': self.args.address.lower(), 'challenge_id': self.args.challenge_id,
                    'input_sha256': self.input_hash}
        if identity.exists():
            if json.loads(identity.read_text()) != expected:
                raise Pause('completion identity/claim changed; use the original inputs and manifest')
        else:
            json_write(identity, expected, exclusive=True)

    def call(self, index, mode):
        payload = run_case.tool.canonical_envelope(self.rewrites[index]) if mode == 'REWRITE' else ''
        return [str(self.args.challenge_id), str(index), mode, payload]

    def key(self, index, mode):
        return 'probe:%d:%d:%s' % (self.args.challenge_id, index, mode)

    def validate_rows(self):
        history = recovery.manifest_history(self.args.manifest)
        for key, row in self.rows.items():
            if row.get('address', '').lower() != self.args.address.lower():
                raise Pause('manifest belongs to a different contract: ' + key)
            if not TX.fullmatch(str(row.get('tx', ''))):
                raise Pause('manifest transaction hash is malformed: ' + key)
            if row.get('method') == 'probe' or key.startswith(('probe:', 'retry:')):
                index, mode = row.get('item_index'), row.get('mode')
                if (type(index) is not int or index not in range(24) or mode not in MODES or
                        row.get('challenge_id') != self.args.challenge_id or key != self.key(index, mode) or
                        row.get('step') != 'probe' or row.get('method') != 'probe' or
                        str(row.get('value', '0')) != '0' or row.get('signature') != signature(self.call(index, mode))):
                    raise Pause('manifest probe inputs/signature do not match the current claim: ' + key)
                recovery.validate_history(row, self.args.manifest, history, self.args.claim,
                                          getattr(self.args, 'source', str(Path(run_case.ROOT)/'build/impeach.py')))

    def marker(self, key):
        return self.folder / 'dispatch' / (hashlib.sha256(key.encode()).hexdigest() + '.json')

    def check_markers(self):
        for path in (self.folder / 'dispatch').glob('*.json'):
            marker = json.loads(path.read_text())
            row = self.rows.get(marker.get('key'))
            if not row or row.get('signature') != marker.get('signature') or row.get('address', '').lower() != marker.get('address'):
                raise Pause('unresolved dispatch; reconcile bridge/chain outcome into the manifest before resuming: ' + str(path))
        # The recovery helper keeps its own pre-broadcast markers.
        for row in self.rows.values():
            path = recovery.dispatch_path(self.args.manifest, row['tx'])
            if row.get('method') == 'probe' and os.path.exists(path):
                raise Pause('unresolved recovery dispatch; reconcile its new hash before resuming: ' + path)

    def guard(self):
        if self.fingerprint() != self.input_hash:
            raise Pause('claim or rewrite inputs changed during completion')
        challenge = self.read('get_challenge', self.args.challenge_id)
        if (not isinstance(challenge, dict) or challenge.get('status') != 'TRIAL' or
                challenge.get('challenge_id') != self.args.challenge_id or
                sorted(challenge.get('subset', [])) != list(range(24))):
            raise Pause('challenge must be an active revealed TRIAL containing exactly all 24 items')
        claim_id = challenge.get('claim_id')
        if type(claim_id) is not int or claim_id < 0:
            raise Pause('challenge has no valid claim id')
        chain = self.read('get_claim', claim_id)
        if (chain.get('claim_id') != claim_id or chain.get('status') != 'TRIAL' or
                chain.get('active_challenge') != self.args.challenge_id):
            raise Pause('on-chain claim is not in this active TRIAL')
        expected = {key: self.claim[key] for key in ('subject', 'endpoint', 'score_milli', 'scoring_rule',
                    'classes', 'delta_threshold', 'recall_threshold', 'min_items')}
        expected.update(item_hashes=[run_case.tool.item_commitment(item['prompt'], item['answer'], item['salt'])
                                    for item in self.claim['_items']],
                        stake=int(self.claim['stake']), bond_sworn=int(self.claim['bond']))
        expected.update(self.claim['extras'])
        for key, value in expected.items():
            if chain.get(key) != value:
                raise Pause('on-chain frozen claim differs from local claim: ' + key)
        for key in ('prompt_template', 'decode_params'):
            actual = chain.get(key)
            if isinstance(actual, str):
                actual = json.loads(actual)
            if actual != self.claim[key]:
                raise Pause('on-chain frozen claim differs from local claim: ' + key)
        if set(challenge.get('classes', [])) != set(self.claim['classes']):
            raise Pause('challenge classes differ from the local claim')
        self.claim_id = claim_id
        started, window, now = challenge.get('trial_started_at'), chain.get('trial_window_s'), self.read('clock')
        if any(type(value) is not int for value in (started, window, now)) or started <= 0 or window <= 0:
            raise Pause('invalid trial clock or deadline')
        self.deadline, self.chain_time = started + window, now
        if now + self.args.deadline_margin >= self.deadline:
            raise Pause('trial deadline reached or too close; no further probe will be submitted')
        if time.monotonic() - self.started >= self.args.max_runtime:
            raise Pause('runtime limit reached; resume using the same manifest')

    def state(self, index):
        state = self.read('get_probe', self.args.challenge_id, index)
        if (not isinstance(state, dict) or state.get('challenge_id') != self.args.challenge_id or
                state.get('item_index') != index or type(state.get('touched')) is not bool):
            raise Pause('malformed probe state for item ' + str(index))
        if state['touched']:
            allowed = {'pinned': {'', 'RIGHT', 'WRONG', 'DEAD'}, 'recall': {'', 'MATCH', 'MISS', 'DEAD', 'NA'},
                       'rewrite': {'', 'RIGHT', 'WRONG', 'DEAD'},
                       'stage_c1': {'PENDING', 'ADMISSIBLE', 'INADMISSIBLE'},
                       'stage_c2': {'PENDING', 'ADMISSIBLE', 'INADMISSIBLE'}}
            if any(state.get(key) not in values for key, values in allowed.items()):
                raise Pause('unknown or missing probe outcome for item ' + str(index))
            if state.get('rewrite_class'):
                env = self.rewrites[index]
                if (state.get('rewrite_class') != env['class'] or state.get('rewrite_prompt') != env['prompt'] or
                        state.get('rewrite_answer') != env['answer'] or state.get('rewrite_hash') !=
                        run_case.tool.rewrite_hash(env['class'], env['prompt'], env['answer'])):
                    raise Pause('applied rewrite differs from the current input for item ' + str(index))
                if state['stage_c1'] == 'PENDING':
                    raise Pause('applied rewrite has no C1 decision for item ' + str(index))
            elif (state.get('rewrite_class') != '' or state['rewrite'] or
                  state['stage_c1'] != 'PENDING' or state['stage_c2'] != 'PENDING'):
                raise Pause('inconsistent empty rewrite state for item ' + str(index))
        elif (any(state.get(key, '') != '' for key in ('pinned', 'recall', 'rewrite', 'rewrite_class')) or
              any(state.get(key, 'PENDING') != 'PENDING' for key in ('stage_c1', 'stage_c2'))):
            raise Pause('untouched probe contains applied fields for item ' + str(index))
        self.states[index] = state
        return state

    def save_failure(self, row, receipt):
        raw = json.dumps(receipt, sort_keys=True, ensure_ascii=False).encode()
        digest = hashlib.sha256(raw).hexdigest()
        path = self.folder / 'receipts' / (row['tx'].lower() + '-' + digest + '.json')
        if not path.exists():
            json_write(path, receipt, exclusive=True)
        record_key = row['tx'].lower() + '-' + digest
        if record_key not in self.failure_records:
            record = {'key': row['key'], 'tx': row['tx'], 'status': status_of(receipt),
                      'execution': execution_of(receipt), 'consensus_result': consensus_result_of(receipt),
                      'receipt': os.path.relpath(path, Path(self.args.manifest).resolve().parent),
                      'receipt_sha256': digest, 'assumed_success': False, 'resubmitted': False}
            if row.get('method') == 'probe':
                record['recovery_ordinal'] = recovery.recovery_ordinal(row)
            record.update(self.finality_proofs.get(row['tx'], {}))
            self.event('ACKNOWLEDGED_FAILURE', **record)
            self.failure_records[record_key] = record
        self.acknowledged.add(row['tx'])

    def wait(self, row):
        deadline = time.monotonic() + self.args.wait_timeout
        last_pending = None
        while True:
            try:
                receipt = fetch_receipt(row['tx'], self.args.rpc,
                                        timeout=max(1, min(30, deadline-time.monotonic())))
            except (RuntimeError, ValueError, subprocess.TimeoutExpired, OSError) as exc:
                raise Pause('receipt unavailable for %s; resume without rebroadcast: %s' % (row['tx'], exc)) from exc
            if (row.get('method') == 'probe' and getattr(self.args, 'allow_proven_no_messages', False)
                    and proof.candidate(receipt)):
                if row['tx'] not in self.finality_proofs:
                    self.finality_proofs[row['tx']] = proof.obtain(self.args, row, receipt,
                        self.call(row['item_index'], row['mode']))
                else:
                    proof.verify_reference(self.finality_proofs[row['tx']], self.args.manifest, row, receipt,
                        self.call(row['item_index'], row['mode']), self.args.claim,
                        getattr(self.args, 'source', str(Path(run_case.ROOT)/'build/impeach.py')))
                outcome = 'FAILURE'
            else:
                outcome = classify(receipt)
            self.outcomes[row['tx']], self.receipts[row['tx']] = outcome, receipt
            if outcome == 'SUCCESS':
                self.confirmed.add(row['tx'])
                return
            if outcome == 'FAILURE':
                self.save_failure(row, receipt)
                return
            pending = (status_of(receipt), execution_of(receipt), consensus_result_of(receipt))
            if pending != last_pending:
                self.report('WAITING_RECEIPT', row['key'] + ' ' + row['tx'])
                last_pending = pending
            if time.monotonic() >= deadline:
                raise Pause('still pending %s; resume tracking the same hash' % row['tx'])
            time.sleep(min(self.args.poll_interval, max(0, deadline-time.monotonic())))

    def initial(self, index, mode):
        key = self.key(index, mode)
        if key in self.rows:
            return False
        state = self.state(index)
        if not recovery.slot_untouched(state, mode):
            return False
        self.guard()
        if run_case.manifest_rows(self.args.manifest) != self.rows:
            raise Pause('manifest changed outside this completion process')
        marker = self.marker(key)
        value = {'key': key, 'address': self.args.address.lower(), 'signature': signature(self.call(index, mode)),
                 'input_sha256': self.input_hash, 'at': int(time.time()), 'status': 'DISPATCHING',
                 'recovery_ordinal': 0}
        try:
            json_write(marker, value, exclusive=True)
        except FileExistsError as exc:
            raise Pause('unresolved dispatch; manual reconciliation required: ' + str(marker)) from exc
        extra = {'step': 'probe', 'challenge_id': self.args.challenge_id, 'item_index': index,
                 'mode': mode, 'recovery_ordinal': 0}
        if mode == 'REWRITE':
            env = self.rewrites[index]
            extra['rewrite_hash'] = run_case.tool.rewrite_hash(env['class'], env['prompt'], env['answer'])
        self.event('DISPATCH', key=key, signature=value['signature'])
        # Runner retains the bridge gas guard, appends+fsyncs the hash, then calls
        # this class's wait. The marker survives every exception/crash path.
        super().send(key, 'probe', self.call(index, mode), value=0, extra=extra)
        self.new_transactions += 1
        self.event('SUBMITTED', key=key, tx=self.rows[key]['tx'])
        self.state(index)
        self.report('RUNNING')
        return True

    def recover(self, row):
        self.guard()
        state = self.state(row['item_index'])
        receipt = self.receipts[row['tx']]
        ordinal = recovery.recovery_ordinal(row)
        if (ordinal >= self.max_recoveries or not recovery.slot_untouched(state, row['mode']) or
                not (recovery.retryable_receipt(receipt) or row['tx'] in self.finality_proofs)):
            return False
        args = copy.copy(self.args)
        args.tx = row['tx']
        args.delay = 0
        self.event('RECOVERY_REQUEST', key=row['key'], previous_tx=row['tx'],
                   recovery_ordinal=ordinal + 1, max_recoveries=self.max_recoveries)
        error = None
        try:
            recovery.retry(args, completion_lock=self.completion_lock)
        except (SystemExit, RuntimeError, ValueError, subprocess.TimeoutExpired, OSError) as exc:
            error = exc
        self.rows = run_case.manifest_rows(self.args.manifest)
        self.validate_rows()
        new = self.rows.get(row['key'])
        if not new or new['tx'] == row['tx']:
            raise Pause('guarded recovery did not record a new hash; reconcile before resume: ' + str(error))
        if new.get('previous_tx') != row['tx'] or new.get('recovery_ordinal') != ordinal + 1:
            raise Pause('unexpected recovery provenance; reconcile manifest')
        self.new_transactions += 1
        self.wait(new)
        self.state(row['item_index'])
        self.report('RUNNING')
        return True

    def report(self, phase, message=''):
        self.phase, self.message = phase, message
        states = list(self.states.values())
        eligible, awaiting, exhausted = [], [], []
        window_open = (self.deadline is not None and
                       self.chain_time + self.args.deadline_margin < self.deadline)
        for row in self.rows.values():
            if row.get('method') != 'probe' or self.outcomes.get(row['tx']) != 'FAILURE':
                continue
            state = self.states.get(row['item_index'], {})
            if not recovery.slot_untouched(state, row['mode']):
                continue
            receipt = self.receipts[row['tx']]
            ordinal = recovery.recovery_ordinal(row)
            entry = {'key': row['key'], 'tx': row['tx'], 'status': status_of(receipt),
                     'recovery_ordinal': ordinal, 'max_recoveries': self.max_recoveries}
            if ordinal >= self.max_recoveries:
                exhausted.append(entry)
            elif window_open and (recovery.retryable_receipt(receipt) or row['tx'] in self.finality_proofs):
                eligible.append(entry)
            elif window_open and status_of(receipt) != 'FINALIZED':
                awaiting.append(entry)
        admitted = sum(s.get('stage_c1') == s.get('stage_c2') == 'ADMISSIBLE' for s in states)
        totals = {'items': 24, 'states_read': len(states), 'complete_items': sum(completed(s) for s in states),
                  'pinned_answers': sum(s.get('pinned') in {'RIGHT', 'WRONG'} for s in states),
                  'recall_results': sum(s.get('recall') in {'MATCH', 'MISS', 'NA'} for s in states),
                  'admitted': admitted,
                  'inadmissible': sum('INADMISSIBLE' in (s.get('stage_c1'), s.get('stage_c2')) for s in states),
                  'dead_slots': sum(s.get(k) == 'DEAD' for s in states for k in ('pinned', 'recall', 'rewrite')),
                  'new_transactions_this_process': self.new_transactions}
        data = {'format': 'impeach-completion/1', 'at': int(time.time()), 'phase': phase, 'message': message,
                'address': self.args.address, 'challenge_id': self.args.challenge_id, 'claim_id': self.claim_id,
                'max_recoveries': self.max_recoveries,
                'input_sha256': self.input_hash, 'deadline': self.deadline, 'chain_time': self.chain_time,
                'deadline_distance_s': None if self.deadline is None else self.deadline-self.chain_time,
                'totals': totals, 'all_slots_complete': totals['complete_items'] == 24,
                'all_24_admitted': admitted == 24, 'recoveries_eligible': eligible,
                'awaiting_finalization': awaiting, 'recoveries_exhausted': exhausted,
                'acknowledged_failures': list(self.failure_records.values()),
                'transactions': [{'key': row['key'], 'tx': row['tx'],
                                  'recovery_ordinal': recovery.recovery_ordinal(row) if row.get('method') == 'probe' else None,
                                  'previous_tx': row.get('previous_tx'),
                                  'outcome': self.outcomes.get(row['tx'], 'UNREAD'),
                                  'status': status_of(self.receipts[row['tx']]) if row['tx'] in self.receipts else None,
                                  'execution': execution_of(self.receipts[row['tx']]) if row['tx'] in self.receipts else None,
                                  'consensus_result': consensus_result_of(self.receipts[row['tx']]) if row['tx'] in self.receipts else None}
                                 for row in self.rows.values()],
                'items': [{'item_index': i, 'complete': completed(s), 'state': s} for i, s in sorted(self.states.items())]}
        json_write(self.folder / 'progress.json', data)
        return data

    def run(self):
        self.guard()
        # Even applied slots do not justify silently ignoring an unknown hash.
        for row in self.rows.values():
            self.wait(row)
        while True:
            self.guard()
            for index in range(24):
                for mode in MODES:
                    self.initial(index, mode)
                self.state(index)
            progress = self.report('RUNNING')
            if progress['all_slots_complete']:
                self.report('COMPLETE')
                return 0
            # Progress all initially available slots before any recovery attempt.
            recovered = became_successful = False
            for row in list(self.rows.values()):
                if row.get('method') != 'probe':
                    continue
                before = self.outcomes.get(row['tx'])
                self.wait(row)
                if self.outcomes[row['tx']] == 'FAILURE':
                    recovered = self.recover(row) or recovered
                elif before != 'SUCCESS':
                    became_successful = True
            if recovered or became_successful:
                continue
            progress = self.report('WAITING_FINALITY')
            if not progress['awaiting_finalization']:
                raise Pause('incomplete applied/DEAD slots or exhausted recovery; inspect progress.json')
            self.guard()
            time.sleep(self.args.poll_interval)


def complete(args):
    os.makedirs(os.path.dirname(os.path.abspath(args.manifest)), exist_ok=True)
    lock_path = args.manifest + '.complete.lock'
    with open(lock_path, 'a+', encoding='utf-8') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'phase': 'PAUSED', 'reason': 'another completion process holds this manifest lock',
                              'exit_code': 2}), flush=True)
            return 2
        lock.seek(0)
        lock.truncate()
        lock.write(json.dumps({'pid': os.getpid(), 'at': int(time.time()), 'address': args.address,
                               'challenge_id': args.challenge_id}) + '\n')
        lock.flush()
        os.fsync(lock.fileno())
        fsync_dir(Path(lock_path).resolve().parent)
        runner = None
        try:
            runner = Completer(args, completion_lock=lock)
            return runner.run()
        except (Pause, RuntimeError, ValueError, KeyError, TypeError, OSError, SystemExit, subprocess.TimeoutExpired) as exc:
            if runner:
                runner.event('PAUSED', reason=str(exc))
                runner.report('PAUSED', str(exc))
            else:
                json_write(Path(os.path.abspath(args.manifest) + '.complete') / 'startup-error.json',
                           {'phase': 'PAUSED', 'at': int(time.time()), 'reason': str(exc), 'exit_code': 2})
            print(json.dumps({'phase': 'PAUSED', 'reason': str(exc), 'exit_code': 2}), flush=True)
            return 2


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('address', 'claim', 'manifest', 'account', 'rpc'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--challenge-id', type=int, required=True)
    parser.add_argument('--wait-timeout', type=float, default=120)
    parser.add_argument('--poll-interval', type=float, default=5)
    parser.add_argument('--max-runtime', type=float, default=3600)
    parser.add_argument('--deadline-margin', type=int, default=120)
    parser.add_argument('--allow-proven-no-messages', action='store_true',
                        help='opt in to exact finalized ambiguous outcomes with a verified Phase event proof')
    parser.add_argument('--source', default=str(Path(run_case.ROOT)/'build/impeach.py'))
    parser.add_argument('--max-recoveries', type=int, choices=range(1, 4), default=1,
                        help='maximum new recovery transactions per slot, excluding the original (default: 1)')
    args = parser.parse_args(argv)
    if (not re.fullmatch(r'0x[0-9a-fA-F]{40}', args.address) or not args.account.strip() or
            args.challenge_id < 0 or args.wait_timeout <= 0 or not 0 < args.poll_interval <= 10 or
            args.max_runtime <= 0 or args.deadline_margin < 0 or
            not all(math.isfinite(value) for value in (args.wait_timeout, args.poll_interval, args.max_runtime))):
        parser.error('invalid address/account/timing options; poll interval must be in (0, 10] seconds')
    args.dry_run, args.delay, args.acknowledge_failed = False, 0, []
    return args


if __name__ == '__main__':
    raise SystemExit(complete(parse_args()))
