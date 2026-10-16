"""Offline completion scheduling: every chain read and broadcast is mocked."""
import contextlib
import copy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import complete_case as complete
import run_case
import retry_finalized_probe as recovery
from proof_fixture import make_bundle

SUCCESS = {'status': 5, 'result': 1, 'txExecutionResult': 1}
FAILED = {'status': 7, 'result': 5, 'txExecutionResult': 1, 'rounds': [{'votes': ['TIMEOUT', 'DISAGREE']}]}


class CompletionTests(unittest.TestCase):
    def test_legacy_leader_revealing_is_pending_even_with_a_proposed_return(self):
        for receipt in ({'status':14,'result':0,'txExecutionResult':0},
                        {'status':14,'statusName':'LEADER_REVEALING','result':1,'txExecutionResult':1}):
            self.assertEqual(complete.classify(receipt),'PENDING')
            self.assertFalse(complete.successful(receipt))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.args = SimpleNamespace(address='0x'+'1'*40, account='challenger', rpc='https://rpc.example',
            manifest=os.path.join(self.tmp.name, 'case.jsonl'), claim=str(ROOT/'calibration/claim-gsm8k.json'),
            challenge_id=0, wait_timeout=.01, poll_interval=.001, max_runtime=30,
            deadline_margin=1, dry_run=False, delay=0, acknowledge_failed=[])
        self.claim = run_case.load_claim(self.args.claim)
        self.rewrites = run_case.load_rewrites(self.claim)
        self.chain_claim = {k: copy.deepcopy(v) for k,v in self.claim.items() if not k.startswith('_')}
        self.chain_claim.update(self.claim['extras'])
        self.chain_claim.update(claim_id=0, status='TRIAL', active_challenge=0,
            item_hashes=[run_case.tool.item_commitment(i['prompt'], i['answer'], i['salt']) for i in self.claim['_items']],
            stake=int(self.claim['stake']), bond_sworn=int(self.claim['bond']))
        self.challenge = {'challenge_id':0,'claim_id':0,'status':'TRIAL','subset':list(range(24)),
                          'classes':self.claim['classes'],'trial_started_at':100}
        self.clock = 110
        self.states = {i: {'challenge_id':0,'item_index':i,'touched':False} for i in range(24)}
        self.receipts, self.calls, self.behavior = {}, [], {}
        self.c1, self.c2 = {}, {}
        self.next_hash = 1
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(patch.object(run_case.Runner, 'read', side_effect=self.read))
        for module in (complete, recovery, run_case):
            self.enterContext(patch.object(module, 'fetch_receipt', side_effect=self.fetch))
        self.write = self.enterContext(patch.object(run_case.subprocess, 'run', side_effect=self.submit))

    def read(self, method, *args):
        if method=='get_challenge': return copy.deepcopy(self.challenge)
        if method=='get_claim': return copy.deepcopy(self.chain_claim)
        if method=='clock': return self.clock
        if method=='get_probe': return copy.deepcopy(self.states[args[1]])
        self.fail('unexpected chain read: '+method)

    def fetch(self, tx, *args, **kwargs):
        value=self.receipts[tx]
        if isinstance(value,Exception): raise value
        return copy.deepcopy(value)

    def apply(self, index, mode):
        s=self.states[index]
        if not s['touched']:
            s.update(touched=True,pinned='',pinned_answer='',recall='',rewrite_class='',rewrite_prompt='',
                     rewrite_answer='',rewrite_hash='',stage_c1='PENDING',stage_c2='PENDING',rewrite='',
                     rewrite_reply='',stale=False,slice_settled=False)
        if mode=='PINNED': s.update(pinned='RIGHT',pinned_answer=self.claim['_items'][index]['answer'])
        elif mode=='RECALL': s['recall']='MISS'
        elif mode=='REWRITE':
            env=self.rewrites[index]
            s.update(rewrite_class=env['class'],rewrite_prompt=env['prompt'],rewrite_answer=env['answer'],
                     rewrite_hash=run_case.tool.rewrite_hash(env['class'],env['prompt'],env['answer']),
                     stage_c1=self.c1.get(index,'ADMISSIBLE'))
            if s['stage_c1']=='ADMISSIBLE': s.update(rewrite='RIGHT',rewrite_reply=env['answer'])
        elif mode=='ADMIT':
            self.assertEqual(s['stage_c1'],'ADMISSIBLE')
            s['stage_c2']=self.c2.get(index,'ADMISSIBLE')
        else: self.fail('forbidden mode '+mode)

    def submit(self, command, **kwargs):
        self.assertEqual(command[3], 'probe')
        self.assertEqual(command[command.index('--value')+1], '0')
        h,index,mode,payload=json.loads(command[command.index('--args-json')+1])
        index=int(index)
        self.assertEqual(h,'0')
        expected=run_case.tool.canonical_envelope(self.rewrites[index]) if mode=='REWRITE' else ''
        self.assertEqual(payload,expected)
        attempt=sum(i==index and m==mode for i,m in self.calls)
        self.calls.append((index,mode))
        outcome=self.behavior.get((index,mode,attempt),SUCCESS)
        if isinstance(outcome,Exception): raise outcome
        tx='0x'+format(self.next_hash,'064x'); self.next_hash+=1
        self.receipts[tx]=outcome
        if complete.successful(outcome): self.apply(index,mode)
        return subprocess.CompletedProcess(command,0,'Transaction Hash: '+tx+'\n','')

    def report(self):
        return json.loads(Path(self.args.manifest+'.complete/progress.json').read_text())

    def rows(self):
        path=Path(self.args.manifest)
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def add_row(self, index, mode, receipt):
        payload=run_case.tool.canonical_envelope(self.rewrites[index]) if mode=='REWRITE' else ''
        tx='0x'+format(self.next_hash,'064x'); self.next_hash+=1
        row={'key':f'probe:0:{index}:{mode}','tx':tx,'address':self.args.address,'method':'probe','step':'probe',
             'challenge_id':0,'item_index':index,'mode':mode,
             'signature':complete.signature(['0',str(index),mode,payload]),'at':1}
        with open(self.args.manifest,'a') as stream: stream.write(json.dumps(row)+'\n')
        self.receipts[tx]=receipt
        return row

    def test_all_24_slots_complete_without_rule_or_duplicate_on_resume(self):
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(len(self.calls),96)
        self.assertEqual(self.calls,[(index,mode) for index in range(24) for mode in complete.MODES])
        self.assertNotIn('subject_first',self.report())
        self.assertTrue(self.report()['all_slots_complete'])
        self.assertTrue(self.report()['all_24_admitted'])
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(len(self.calls),96)
        self.assertEqual(len(self.rows()),96)

    def prepare_ready_pairs(self):
        self.args.subject_first = True
        self.args.subject_deadline = 1  # Expired API must not block unpaid C2.
        self.args.admit_ready_only = True
        for index in range(24):
            self.apply(index, 'PINNED')
            self.apply(index, 'RECALL')
            if index != 14:
                self.apply(index, 'REWRITE')

    def test_ready_c2_pass_never_calls_subject_or_claims_whole_case_completion(self):
        self.prepare_ready_pairs()
        self.assertEqual(complete.complete(self.args), 0)
        self.assertEqual(self.calls, [(i, 'ADMIT') for i in range(24) if i != 14])
        report = self.report()
        self.assertEqual(report['phase'], 'READY_ADMISSIONS_COMPLETE')
        self.assertFalse(report['all_slots_complete'])
        self.assertFalse(report['all_24_admitted'])
        self.assertEqual(report['totals']['admitted'], 23)
        self.assertEqual(report['subjects_incomplete'][0]['item_index'], 14)
        identity = Path(self.args.manifest+'.complete/identity.json').read_bytes()
        # Once the subject recovery is actually saved, normal completion uses
        # the same identity and only sends the missing C2.
        self.apply(14, 'REWRITE')
        self.args.admit_ready_only = False
        self.assertEqual(complete.complete(self.args), 0)
        self.assertEqual(self.calls[-1], (14, 'ADMIT'))
        self.assertEqual(len(self.calls), 24)
        self.assertTrue(self.report()['all_24_admitted'])
        self.assertEqual(Path(self.args.manifest+'.complete/identity.json').read_bytes(), identity)

    def test_ready_c2_pass_retains_finalized_failure_and_uses_guarded_recovery(self):
        self.prepare_ready_pairs()
        self.behavior[(3, 'ADMIT', 0)] = FAILED
        self.assertEqual(complete.complete(self.args), 0)
        rows = [r for r in self.rows() if r['item_index'] == 3]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['previous_tx'], rows[0]['tx'])
        self.assertEqual(rows[1]['recovery_ordinal'], 1)
        self.assertTrue(all(mode == 'ADMIT' for _, mode in self.calls))
        self.assertFalse(self.report()['all_slots_complete'])
        self.assertEqual(self.report()['totals']['admitted'], 23)

    def test_ready_c2_option_cannot_dispatch_all_modes_without_subject_first(self):
        self.args.admit_ready_only = True
        self.assertEqual(complete.complete(self.args), 2)
        self.assertEqual(self.calls, [])

    def subject_first(self, deadline=None):
        self.args.subject_first=True
        self.args.subject_deadline=deadline
        self.wall_clock=[1000.0]
        self.enterContext(patch.object(complete.time,'time',side_effect=lambda:self.wall_clock[0]))

    def apply_all_subjects(self):
        for index in range(24):
            for mode in recovery.SUBJECT_MODES:
                self.apply(index,mode)

    def test_subject_first_all_72_apply_before_any_admit(self):
        self.subject_first(3000)
        def submit(command,**kwargs):
            args=json.loads(command[command.index('--args-json')+1])
            if args[2]=='ADMIT':
                self.assertTrue(all(complete.subjects_completed(s) for s in self.states.values()))
            return self.submit(command,**kwargs)
        self.write.side_effect=submit
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(self.calls[:72],[(i,m) for i in range(24) for m in recovery.SUBJECT_MODES])
        self.assertEqual(self.calls[72:],[(i,'ADMIT') for i in range(24)])
        self.assertTrue(self.report()['all_subjects_applied'])
        self.assertEqual(self.report()['subject_dispatch_cutoff'],2880)
        before=Path(self.args.manifest).read_bytes()
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(Path(self.args.manifest).read_bytes(),before)

    def test_subject_recoveries_precede_all_admits_and_preserve_history(self):
        self.subject_first(3000);self.args.max_recoveries=3
        for attempt in range(3):self.behavior[(0,'REWRITE',attempt)]=FAILED
        self.behavior[(1,'PINNED',0)]=FAILED
        self.assertEqual(complete.complete(self.args),0)
        first_admit=next(i for i,(_,mode) in enumerate(self.calls) if mode=='ADMIT')
        self.assertEqual(first_admit,76)
        self.assertTrue(all(mode in recovery.SUBJECT_MODES for _,mode in self.calls[:first_admit]))
        self.assertEqual(self.calls.count((0,'REWRITE')),4)
        rows=[r for r in self.rows() if r['key']=='probe:0:0:REWRITE']
        self.assertEqual([r.get('recovery_ordinal',0) for r in rows],[0,1,2,3])
        for prior,row in zip(rows,rows[1:]):
            self.assertEqual(row['previous_row'],prior)
            self.assertEqual(json.loads((Path(self.tmp.name)/row['previous_receipt']).read_text()),FAILED)

    def test_subject_failure_nonfinal_releases_lock_then_recovers_before_admit(self):
        self.subject_first(3000)
        self.behavior[(0,'REWRITE',0)]={**FAILED,'status':13}
        with patch.object(complete.time,'sleep') as sleep:
            self.assertEqual(complete.complete(self.args),2)
        sleep.assert_not_called()
        self.assertEqual(len(self.calls),72)
        self.assertNotIn('ADMIT',[mode for _,mode in self.calls])
        waiting=self.report()['awaiting_finalization']
        self.assertEqual(len(waiting),1)
        with open(self.args.manifest+'.complete.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.receipts[waiting[0]['tx']]=FAILED
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(self.calls[72],(0,'REWRITE'))
        self.assertEqual(self.calls[73:],[(i,'ADMIT') for i in range(24)])

    def test_subject_pending_recovery_resumes_same_hash_before_c2(self):
        self.subject_first(3000)
        self.behavior[(0,'PINNED',0)]=FAILED
        self.behavior[(0,'PINNED',1)]={'status':14,'result':1,'txExecutionResult':1}
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(len(self.calls),73)
        self.assertNotIn('ADMIT',[mode for _,mode in self.calls])
        row=run_case.manifest_rows(self.args.manifest)['probe:0:0:PINNED']
        self.receipts[row['tx']]=SUCCESS;self.apply(0,'PINNED')
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(self.calls.count((0,'PINNED')),2)
        self.assertEqual(self.calls[73:],[(i,'ADMIT') for i in range(24)])

    def test_subject_dead_and_c1_rejection_block_c2_without_duplicate(self):
        self.subject_first(3000)
        self.apply(0,'PINNED');self.states[0]['pinned']='DEAD'
        self.c1[1]='INADMISSIBLE'
        self.assertEqual(complete.complete(self.args),2)
        before=list(self.calls)
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls,before)
        self.assertNotIn((0,'PINNED'),self.calls)
        self.assertEqual(self.calls.count((1,'REWRITE')),1)
        self.assertNotIn('ADMIT',[mode for _,mode in self.calls])
        self.assertFalse(self.report()['all_subjects_applied'])
        self.assertEqual([s['item_index'] for s in self.report()['subjects_incomplete']],[0,1])

    def test_subject_deadline_exact_margin_blocks_initial_before_marker(self):
        self.subject_first(1120)
        self.assertEqual(complete.complete(self.args),2)
        self.write.assert_not_called()
        self.assertEqual(self.rows(),[])
        self.assertEqual(list(Path(self.args.manifest+'.complete/dispatch').glob('*.json')),[])
        self.assertIn('subject deadline',self.report()['message'])

    def test_subject_chain_clock_ahead_blocks_even_when_wall_time_allows(self):
        self.subject_first(3000);self.clock=2880
        self.assertEqual(complete.complete(self.args),2)
        self.write.assert_not_called()
        self.assertIn('subject deadline',self.report()['message'])

    def test_subject_deadline_does_not_block_ready_admits_or_admit_recovery(self):
        self.subject_first(1120);self.apply_all_subjects()
        self.behavior[(0,'ADMIT',0)]=FAILED
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(len(self.calls),25)
        self.assertTrue(all(mode=='ADMIT' for _,mode in self.calls))
        self.assertEqual(self.calls.count((0,'ADMIT')),2)
        self.assertTrue(self.report()['all_subjects_applied'])

    def test_subject_positive_receipt_with_empty_slot_is_not_retried(self):
        self.subject_first(3000)
        row=self.add_row(0,'PINNED',{**SUCCESS,'status':7})
        self.assertEqual(complete.complete(self.args),2)
        self.assertNotIn((0,'PINNED'),self.calls)
        self.assertNotIn('ADMIT',[mode for _,mode in self.calls])
        self.assertEqual(run_case.manifest_rows(self.args.manifest)[row['key']],row)

    def test_subject_policy_cannot_be_removed_or_deadline_extended_on_resume(self):
        self.subject_first(3000);self.apply_all_subjects()
        self.assertEqual(complete.complete(self.args),0)
        self.write.reset_mock()
        self.args.subject_deadline=4000
        self.assertEqual(complete.complete(self.args),2)
        self.args.subject_deadline=None;self.args.subject_first=False
        self.assertEqual(complete.complete(self.args),2)
        self.write.assert_not_called()

    def test_subject_recovery_checks_fresh_deadline_after_proof_lookup(self):
        self.subject_first(3000);self.enable_proof_rpc_fixture()
        self.behavior[(0,'PINNED',0)]={'status':7,'result':0,'txExecutionResult':1}
        base_submit=self.write.side_effect
        proof_calls=[]
        def command(args,**kwargs):
            result=base_submit(args,**kwargs)
            if args[1]=='scripts/native_finality_proof.mjs':
                proof_calls.append(args)
                if len(proof_calls)==2:
                    # Chain time deliberately remains 110: expiry must also use UTC.
                    self.wall_clock[0]=2880
            return result
        self.write.side_effect=command
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(len(proof_calls),2)
        self.assertEqual(len(self.calls),72)
        self.assertNotIn('ADMIT',[mode for _,mode in self.calls])
        row=run_case.manifest_rows(self.args.manifest)['probe:0:0:PINNED']
        self.assertFalse(Path(recovery.dispatch_path(self.args.manifest,row['tx'])).exists())
        self.assertEqual(self.report()['recoveries_eligible'],[])
        self.assertIn('subject deadline',self.report()['message'])

    def test_subject_first_cli_is_explicit_and_deadline_is_positive_epoch(self):
        options=[v for n in ('address','account','rpc','manifest','claim')
                 for v in ('--'+n,getattr(self.args,n))]+['--challenge-id','0']
        args=complete.parse_args(options)
        self.assertFalse(args.subject_first);self.assertIsNone(args.subject_deadline)
        args=complete.parse_args(options+['--subject-first','--subject-deadline','1791720000'])
        self.assertTrue(args.subject_first);self.assertEqual(args.subject_deadline,1791720000)
        for tail in (['--subject-deadline','1791720000'],
                     ['--subject-first','--subject-deadline','0'],
                     ['--subject-first','--subject-deadline','-1'],
                     ['--subject-first','--subject-deadline','1.5']):
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                complete.parse_args(options+tail)

    def enable_proof_rpc_fixture(self):
        self.args.allow_proven_no_messages=True
        self.args.source=str(ROOT/'build/impeach.py')
        def command(args, **kwargs):
            if args[1]=='scripts/native_finality_proof.mjs':
                tx=args[args.index('--tx')+1]
                row=next(r for r in self.rows() if r['tx']==tx)
                receipt=self.receipts[tx]
                bundle=make_bundle(row,recovery.original_call(row,self.args.claim),
                    source_sha=hashlib.sha256(Path(self.args.source).read_bytes()).hexdigest(),
                    claim_sha=complete.proof.claim_hash(self.args.claim),
                    outcome=(receipt['txExecutionResult'],receipt['result']))
                return subprocess.CompletedProcess(args,0,json.dumps(bundle),'')
            return self.submit(args,**kwargs)
        self.write.side_effect=command

    def test_proof_path_three_recoveries_preserve_proof_history_and_resume(self):
        self.enable_proof_rpc_fixture();self.args.max_recoveries=3
        ambiguous={'status':7,'result':0,'txExecutionResult':1}
        for attempt in range(3):self.behavior[(0,'REWRITE',attempt)]=ambiguous
        self.assertFalse(recovery.retryable_receipt(ambiguous))
        with self.assertRaises(complete.Pause):complete.classify(ambiguous)
        self.assertEqual(complete.complete(self.args),0)
        rows=[r for r in self.rows() if r['key']=='probe:0:0:REWRITE']
        self.assertEqual(len(rows),4)
        for ordinal,row in enumerate(rows[1:],1):
            self.assertEqual(row['recovery_ordinal'],ordinal)
            self.assertEqual(row['previous_failure_basis'],complete.proof.BASIS)
            path=Path(self.tmp.name)/row['previous_finalization_proof']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),row['previous_finalization_proof_sha256'])
            marker=json.loads(Path(recovery.dispatch_path(self.args.manifest,row['previous_tx'])).read_text())
            self.assertEqual(marker['previous_finalization_proof_sha256'],row['previous_finalization_proof_sha256'])
            self.assertEqual(recovery.validate_history(row,self.args.manifest,
                {row['key']:rows[:ordinal+1]},self.args.claim,self.args.source),ordinal)
        calls=len(self.calls)
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(len(self.calls),calls)
        proof_path=Path(self.tmp.name)/rows[1]['previous_finalization_proof']
        proof_path.write_text(proof_path.read_text()+' ')
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(len(self.calls),calls)

    def test_proven_no_messages_fourth_recovery_remains_blocked(self):
        self.enable_proof_rpc_fixture();self.args.max_recoveries=3
        for attempt in range(4):self.behavior[(0,'RECALL',attempt)]={'status':7,'result':1,'txExecutionResult':0}
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls.count((0,'RECALL')),4)
        self.assertEqual(self.report()['recoveries_exhausted'][0]['recovery_ordinal'],3)
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls.count((0,'RECALL')),4)

    def test_opt_in_without_available_proof_pauses_before_new_probes(self):
        self.args.allow_proven_no_messages=True
        self.add_row(0,'REWRITE',{'status':7,'result':0,'txExecutionResult':1})
        self.write.side_effect=lambda *a,**kw:subprocess.CompletedProcess([],2,'','bounded lookup unavailable')
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls,[])
        self.assertEqual(len(self.rows()),1)

    def test_proof_cannot_resend_applied_rejected_dead_or_changed_slot(self):
        self.enable_proof_rpc_fixture()
        self.add_row(0,'REWRITE',{'status':7,'result':0,'txExecutionResult':1})
        self.apply(0,'PINNED');self.apply(0,'RECALL');self.apply(0,'REWRITE')
        self.states[0].update(stage_c1='INADMISSIBLE',rewrite='')
        self.assertEqual(complete.complete(self.args),0)
        self.assertNotIn((0,'REWRITE'),self.calls)

    def test_inadmissible_c1_is_complete_and_does_not_run_admit_or_retry(self):
        self.c1[3]='INADMISSIBLE'
        self.assertEqual(complete.complete(self.args),0)
        self.assertNotIn((3,'ADMIT'),self.calls)
        self.assertEqual(len(self.calls),95)
        self.assertEqual(self.report()['totals']['inadmissible'],1)
        self.assertFalse(self.report()['all_24_admitted'])

    def test_known_failure_progresses_all_initial_slots_before_one_recovery(self):
        self.behavior[(0,'PINNED',0)]=FAILED
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(self.calls[-1],(0,'PINNED'))
        self.assertEqual(len(self.calls),97)
        rows=[r for r in self.rows() if r['key']=='probe:0:0:PINNED']
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1]['previous_tx'],rows[0]['tx'])
        report=self.report(); self.assertEqual(len(report['acknowledged_failures']),1)
        record=report['acknowledged_failures'][0]
        self.assertFalse(record['assumed_success'])
        with open(Path(self.args.manifest).parent/record['receipt']) as stream:
            self.assertEqual(json.load(stream),FAILED)

    def test_two_identical_failure_receipts_are_logged_for_both_hashes(self):
        self.behavior[(0,'PINNED',0)]=FAILED
        self.behavior[(1,'PINNED',0)]=FAILED
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(len(self.report()['acknowledged_failures']),2)

    def test_nonfinal_failure_waits_after_all_independent_initial_slots(self):
        self.behavior[(0,'PINNED',0)]={**FAILED,'status':6}
        with patch.object(complete.time,'sleep',side_effect=complete.Pause('bounded test stop')):
            self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(len(self.calls),96)
        self.assertEqual(self.calls.count((0,'PINNED')),1)
        self.assertEqual(len(self.report()['awaiting_finalization']),1)
        self.assertEqual(self.report()['recoveries_eligible'],[])

    def test_recovered_rewrite_then_allows_its_single_admit_call(self):
        self.behavior[(0,'REWRITE',0)]=FAILED
        self.assertEqual(complete.complete(self.args),0)
        calls=[mode for index,mode in self.calls if index==0]
        self.assertEqual(calls,['PINNED','RECALL','REWRITE','REWRITE','ADMIT'])

    def test_pending_recovery_is_retained_and_never_repeated(self):
        self.behavior[(0,'PINNED',0)]=FAILED
        self.behavior[(0,'PINNED',1)]={'status':1,'result':0,'txExecutionResult':0}
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls.count((0,'PINNED')),2)
        row=run_case.manifest_rows(self.args.manifest)['probe:0:0:PINNED']
        self.receipts[row['tx']]=SUCCESS; self.apply(0,'PINNED')
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(self.calls.count((0,'PINNED')),2)

    def test_deadline_closing_before_recovery_prevents_its_broadcast(self):
        self.behavior[(0,'PINNED',0)]=FAILED
        def fetch(tx,*args,**kwargs):
            value=self.fetch(tx,*args,**kwargs)
            if len(self.calls)==96 and tx=='0x'+format(1,'064x'):
                self.clock=100+self.chain_claim['trial_window_s']
            return value
        with patch.object(complete,'fetch_receipt',side_effect=fetch):
            self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(len(self.calls),96)
        self.assertEqual(self.report()['recoveries_eligible'],[])
        self.assertEqual(self.report()['deadline_distance_s'],0)

    def test_recovery_exhausted_and_no_third_attempt(self):
        self.behavior[(0,'PINNED',0)]=FAILED
        self.behavior[(0,'PINNED',1)]=FAILED
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls.count((0,'PINNED')),2)
        self.assertEqual(len(self.report()['recoveries_exhausted']),1)
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls.count((0,'PINNED')),2)

    def test_finalized_idle_not_voted_is_retryable_only_when_empty(self):
        self.behavior[(0,'RECALL',0)]={'status':7,'result':0,'txExecutionResult':0}
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(self.calls.count((0,'RECALL')),2)

    def test_unknown_malformed_and_unavailable_receipts_stop_without_writes(self):
        for receipt in ({},None,{'status':7,'txExecutionResult':1},
                        {'status':7,'result':5,'resultName':'AGREE','txExecutionResult':1},
                        RuntimeError('RPC unavailable')):
            with self.subTest(receipt=receipt):
                if Path(self.args.manifest).exists(): Path(self.args.manifest).unlink()
                self.add_row(0,'PINNED',receipt)
                self.assertEqual(complete.complete(self.args),2)
                self.write.assert_not_called()

    def test_pending_hash_is_retained_and_never_resent(self):
        row=self.add_row(0,'PINNED',{'status':1,'result':0,'txExecutionResult':0})
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.rows(),[row])
        self.write.assert_not_called()
        self.receipts[row['tx']]=SUCCESS; self.apply(0,'PINNED')
        self.assertEqual(complete.complete(self.args),0)
        self.assertNotIn((0,'PINNED'),self.calls)

    def test_applied_slots_without_local_rows_are_not_repeated(self):
        for mode in complete.MODES: self.apply(0,mode)
        self.assertEqual(complete.complete(self.args),0)
        self.assertFalse(any(index==0 for index,mode in self.calls))

    def test_dead_applied_outcome_is_reported_without_retry_or_success(self):
        for index in range(24):
            for mode in complete.MODES: self.apply(index,mode)
        self.states[0]['pinned']='DEAD'
        self.assertEqual(complete.complete(self.args),2)
        self.write.assert_not_called()
        self.assertEqual(self.report()['totals']['dead_slots'],1)
        self.assertFalse(self.report()['all_slots_complete'])

    def test_dispatch_crash_is_durable_and_second_run_refuses(self):
        self.behavior[(0,'PINNED',0)]=RuntimeError('lost response before hash')
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.rows(),[])
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(len(list(Path(self.args.manifest+'.complete/dispatch').glob('*.json'))),1)

    def test_claim_mismatch_signature_mismatch_and_closed_trial_refuse(self):
        self.chain_claim['score_milli']+=1
        self.assertEqual(complete.complete(self.args),2)
        self.chain_claim['score_milli']-=1
        self.challenge['status']='RULED'
        self.assertEqual(complete.complete(self.args),2)
        self.challenge['status']='TRIAL'
        self.clock=100+self.chain_claim['trial_window_s']
        self.assertEqual(complete.complete(self.args),2)
        self.clock=110
        row=self.add_row(0,'PINNED',SUCCESS); row['signature']='changed'
        Path(self.args.manifest).write_text(json.dumps(row)+'\n')
        self.assertEqual(complete.complete(self.args),2)
        self.write.assert_not_called()

    def test_malformed_probe_state_does_not_imply_empty(self):
        self.states[0]={'challenge_id':0,'item_index':0,'touched':False,'pinned':'RIGHT'}
        self.assertEqual(complete.complete(self.args),2)
        self.write.assert_not_called()

    def test_second_signing_process_cannot_acquire_lock(self):
        with open(self.args.manifest+'.complete.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(complete.complete(self.args),2)
        self.write.assert_not_called()

    def test_explicit_three_recoveries_complete_with_every_prior_receipt_and_hash(self):
        self.args.max_recoveries = 3
        for attempt in range(3):
            self.behavior[(0,'REWRITE',attempt)] = FAILED
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(self.calls.count((0,'REWRITE')),4)
        self.assertEqual(self.calls.count((0,'ADMIT')),1)
        rows=[r for r in self.rows() if r['key']=='probe:0:0:REWRITE']
        self.assertEqual([r.get('recovery_ordinal',0) for r in rows],[0,1,2,3])
        self.assertEqual(len({r['tx'] for r in rows}),4)
        for ordinal,row in enumerate(rows[1:],1):
            self.assertEqual(row['previous_row'],rows[ordinal-1])
            self.assertEqual(row['previous_tx'],rows[ordinal-1]['tx'])
            self.assertEqual(json.loads((Path(self.tmp.name)/row['previous_receipt']).read_text()),FAILED)
        report=self.report()
        self.assertEqual(report['max_recoveries'],3)
        self.assertEqual(sorted(r['recovery_ordinal'] for r in report['acknowledged_failures']),[0,1,2])
        self.assertEqual({r['tx'] for r in report['acknowledged_failures']},{r['tx'] for r in rows[:-1]})
        self.assertTrue(report['all_slots_complete'])
        before=Path(self.args.manifest).read_bytes()
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(Path(self.args.manifest).read_bytes(),before)

    def test_fourth_recovery_is_blocked_across_resume(self):
        self.args.max_recoveries = 3
        for attempt in range(4):
            self.behavior[(0,'PINNED',attempt)] = FAILED
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls.count((0,'PINNED')),4)
        exhausted=self.report()['recoveries_exhausted']
        self.assertEqual(len(exhausted),1)
        self.assertEqual(exhausted[0]['recovery_ordinal'],3)
        self.assertEqual(self.report()['recoveries_eligible'],[])
        before=Path(self.args.manifest).read_bytes()
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(Path(self.args.manifest).read_bytes(),before)
        self.assertEqual(self.calls.count((0,'PINNED')),4)

    def test_explicit_larger_bound_resumes_exhausted_history_without_resetting_it(self):
        self.args.max_recoveries = 3
        for attempt in range(6):
            self.behavior[(0,'PINNED',attempt)] = FAILED
        self.assertEqual(complete.complete(self.args),2)
        before=Path(self.args.manifest).read_bytes()
        identity=Path(self.args.manifest+'.complete/identity.json').read_bytes()
        self.args.max_recoveries = 6
        self.assertEqual(complete.complete(self.args),0)
        self.assertTrue(Path(self.args.manifest).read_bytes().startswith(before))
        self.assertEqual(Path(self.args.manifest+'.complete/identity.json').read_bytes(),identity)
        rows=[r for r in self.rows() if r['key']=='probe:0:0:PINNED']
        self.assertEqual([r.get('recovery_ordinal',0) for r in rows],list(range(7)))
        self.assertEqual(recovery.validate_history(rows[-1],self.args.manifest),6)
        calls=len(self.calls)
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(len(self.calls),calls)

    def test_seventh_recovery_is_blocked_by_absolute_ceiling(self):
        self.args.max_recoveries = 6
        for attempt in range(7):
            self.behavior[(0,'PINNED',attempt)] = FAILED
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls.count((0,'PINNED')),7)
        self.assertEqual(self.report()['recoveries_exhausted'][0]['recovery_ordinal'],6)
        before=Path(self.args.manifest).read_bytes()
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(Path(self.args.manifest).read_bytes(),before)

    def test_pending_second_recovery_never_consumes_third_allowance(self):
        self.args.max_recoveries = 3
        self.behavior[(0,'PINNED',0)] = FAILED
        self.behavior[(0,'PINNED',1)] = FAILED
        self.behavior[(0,'PINNED',2)] = {'status':14,'result':1,'txExecutionResult':1}
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls.count((0,'PINNED')),3)
        row=run_case.manifest_rows(self.args.manifest)['probe:0:0:PINNED']
        self.assertEqual(row['recovery_ordinal'],2)
        self.receipts[row['tx']] = SUCCESS
        self.apply(0,'PINNED')
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(self.calls.count((0,'PINNED')),3)

    def test_second_recovery_must_wait_for_its_own_finality(self):
        self.args.max_recoveries = 3
        self.behavior[(0,'PINNED',0)] = FAILED
        self.behavior[(0,'PINNED',1)] = {**FAILED,'status':12}
        with patch.object(complete.time,'sleep',side_effect=complete.Pause('bounded test stop')):
            self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.calls.count((0,'PINNED')),2)
        waiting=self.report()['awaiting_finalization']
        self.assertEqual(len(waiting),1)
        self.assertEqual(waiting[0]['recovery_ordinal'],1)
        self.assertEqual(self.report()['recoveries_eligible'],[])
        self.receipts[waiting[0]['tx']] = FAILED
        self.assertEqual(complete.complete(self.args),0)
        self.assertEqual(self.calls.count((0,'PINNED')),3)

    def test_later_recovery_refuses_missing_history_before_any_submission(self):
        self.behavior[(0,'PINNED',0)] = FAILED
        self.behavior[(0,'PINNED',1)] = FAILED
        self.assertEqual(complete.complete(self.args),2)
        self.args.max_recoveries = 3
        rows=self.rows()
        original=next(r for r in rows if r['key']=='probe:0:0:PINNED' and 'previous_tx' not in r)
        Path(self.args.manifest).write_text(''.join(json.dumps(r)+'\n' for r in rows if r != original))
        self.write.reset_mock()
        self.assertEqual(complete.complete(self.args),2)
        self.write.assert_not_called()
        error=json.loads(Path(self.args.manifest+'.complete/startup-error.json').read_text())
        self.assertIn('original manifest rows are missing or changed',error['reason'])

    def test_larger_limit_does_not_retry_finalized_return_idle(self):
        self.args.max_recoveries = 3
        row=self.add_row(0,'PINNED',{'status':7,'result':0,'txExecutionResult':1})
        self.assertEqual(complete.complete(self.args),2)
        self.assertEqual(self.rows(),[row])
        self.write.assert_not_called()

    def test_cli_recovery_policy_is_explicit_and_bounded(self):
        options=[value for name in ('address','account','rpc','manifest','claim')
                 for value in ('--'+name,getattr(self.args,name))]+['--challenge-id','0']
        self.assertEqual(complete.parse_args(options).max_recoveries,1)
        self.assertEqual(complete.parse_args(options+['--max-recoveries','3']).max_recoveries,3)
        self.assertEqual(complete.parse_args(options+['--max-recoveries','6']).max_recoveries,6)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            complete.parse_args(options+['--max-recoveries','7'])


if __name__=='__main__': unittest.main()
