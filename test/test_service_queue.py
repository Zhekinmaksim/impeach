"""Offline native queue service tests: all chain reads and broadcasts mocked."""
import contextlib
import copy
import fcntl
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import service_queue as queue
import run_case
import complete_case

TX = '0x' + 'a' * 64
EVM = '0x' + 'b' * 64


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        source = folder / 'source.py'
        source.write_text('frozen contract artifact\n')
        self.args = SimpleNamespace(address='0x'+'1'*40, account='timer-signer', from_address='0x'+'2'*40,
            manifest=str(folder/'case.jsonl'), claim=str(ROOT/'calibration/claim-gsm8k.json'),
            claim_id=0, challenge_id=0, source=str(source), rpc='https://rpc.example',
            max_runtime=300, max_operations=8, execute=False)
        self.row = {'key':'probe:0:0:PINNED', 'tx':TX, 'address':self.args.address, 'at':1,
                    'method':'probe', 'step':'probe', 'challenge_id':0, 'item_index':0, 'mode':'PINNED',
                    'signature':complete_case.signature(['0','0','PINNED',''])}
        Path(self.args.manifest).write_text(json.dumps(self.row)+'\n')
        self.claim = run_case.load_claim(self.args.claim)
        self.chain_claim = {k:copy.deepcopy(v) for k,v in self.claim.items() if not k.startswith('_')}
        self.chain_claim.update(self.claim['extras'])
        self.chain_claim.update(claim_id=0, status='TRIAL', active_challenge=0,
            item_hashes=[run_case.tool.item_commitment(i['prompt'], i['answer'], i['salt']) for i in self.claim['_items']],
            stake=int(self.claim['stake']), bond_sworn=int(self.claim['bond']))
        self.challenge = {'claim_id':0, 'challenge_id':0, 'status':'TRIAL', 'subset':list(range(24)),
                          'classes':self.claim['classes']}
        self.probe = {'challenge_id':0,'item_index':0,'touched':True,'pinned':'RIGHT'}
        self.candidate = {
            'tx':TX, 'stored':{'id':TX,'recipient':self.args.address,'status':5,'result':0,'txExecutionResult':1,'value':'0'},
            'receipt':{'recipient':self.args.address,'status':11,'result':1,'txExecutionResult':1,
                       'numOfRounds':'0','lastRound':{'round':'0','votesRevealed':'5'}},
            'decoded':{'type':'call','leaderOnly':False,'callData':{'method':'probe','args':['0','0','PINNED','']}},
            'mainTimestamps':{k:'10' for k in ('created','pending','activated','proposed','committed','lastVote','appealSubmitted','leaderRevealed')},
            'firstSlotElapsed':False, 'queueType':2, 'queueModification':{'lastQueueType':2,'lastQueueTimestamp':'10'},
            'atFinalizedHead':True, 'canFinalize':[False,'100','0'],
        }
        self.data = {'address':self.args.address,'blockTimestamp':'100','blockNumber':'10',
            'protocol':{'chainId':4221,'main':queue.MAIN,'version':'2.0.0','implementations':{'ConsensusMain':queue.IMPL}},
            'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'mainTimeouts':{k:'1' for k in ('activate','propose','commit','reveal','accept','leaderReveal')},
            'heads':{k:(TX if k in ('getFinalizedHeadTxId','getAcceptedHeadTxId') else queue.ZERO) for k in queue.HEADS},
            'transactions':[self.candidate]}
        self.calls = []
        self.broadcast_error = None
        self.broadcast_progress = True
        self.dry_results = {}
        self.output = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.inspector = self.enterContext(patch.object(queue.QueueService,'inspect',side_effect=lambda tx=None: copy.deepcopy(self.data)))
        self.enterContext(patch.object(queue.QueueService,'read',side_effect=self.read))
        self.command = self.enterContext(patch.object(queue.subprocess,'run',side_effect=self.run_command))
        self.sender = self.enterContext(patch.object(queue.QueueService,'broadcast',side_effect=self.broadcast))

    def read(self, method, *args):
        return copy.deepcopy({'get_claim':self.chain_claim,'get_challenge':self.challenge,'get_probe':self.probe}[method])

    def run_command(self, command, **kwargs):
        self.calls.append(command)
        if '--dry-run' in command:
            self.assertIn('--value',command)
            self.assertEqual(command[command.index('--value')+1],'0')
            action = 'finalize' if '--finalize' in command else 'process-idleness'
            rc, err = self.dry_results.get(action,(0,''))
            return subprocess.CompletedProcess(command,rc,'{}',err)
        self.assertIn('--evm-receipt',command)
        return subprocess.CompletedProcess(command,0,json.dumps({'receipt':{'status':'success'},
            'transaction':{'from':self.args.from_address,'to':queue.MAIN,'value':'0'}}),'')

    def broadcast(self, command, stem):
        self.calls.append(command)
        self.assertTrue(Path(str(stem)+'.dispatch.json').exists())
        self.assertTrue(Path(str(stem)+'.before.json').exists())
        self.assertNotIn('--dry-run',command)
        if self.broadcast_error:
            raise self.broadcast_error
        complete_case.json_write(str(stem)+'.evm-hash.json',{'evm_tx':EVM},exclusive=True)
        if self.broadcast_progress:
            if '--finalize' in command:
                self.candidate['stored']['status']=7
                self.candidate['receipt']['status']=7
                self.data['heads']={key:queue.ZERO for key in queue.HEADS}
                self.candidate['atFinalizedHead']=False
            else:
                self.candidate['stored']['status']=12
                self.candidate['receipt']['status']=12
                self.candidate['firstSlotElapsed']=False
        return EVM

    def records(self, suffix):
        return list(Path(self.args.manifest+'.queue').glob('*'+suffix))

    def test_default_only_simulates_main_even_when_can_finalize_is_false(self):
        self.assertEqual(queue.service(self.args),0)
        self.sender.assert_not_called()
        self.assertTrue(all('--dry-run' in command for command in self.calls))
        self.assertIn('--finalize',self.calls[0])
        self.assertFalse(self.records('.dispatch.json'))

    def test_execute_finalizes_known_head_preserving_native_and_evm_evidence(self):
        self.args.execute=True
        self.assertEqual(queue.service(self.args),0)
        self.assertEqual(self.sender.call_count,1)
        for suffix in ('.before.json','.dispatch.json','.evm-hash.json','.evm-receipt.json','.after.json','.done.json'):
            self.assertEqual(len(self.records(suffix)),1)
        self.assertTrue(json.loads(self.records('.done.json')[0].read_text())['resolved'])
        self.assertEqual(queue.service(self.args),0)
        self.assertEqual(self.sender.call_count,1)
        self.assertFalse(any('--appeal' in command or 'probe' in command for command in self.calls))

    def test_main_revert_falls_back_to_mature_deferred_idleness_once(self):
        self.args.execute=True; self.args.max_operations=1
        self.candidate['stored']['status']=4
        self.candidate['firstSlotElapsed']=True
        self.dry_results['finalize']=(2,'execution reverted: FinalizationNotAllowed')
        self.assertEqual(queue.service(self.args),2)
        actions=[next(x for x in command if x in ('--finalize','--process-idleness')) for command in self.calls if '--evm-receipt' not in command]
        self.assertEqual(actions,['--finalize','--process-idleness','--process-idleness'])
        self.assertTrue(json.loads(self.records('.done.json')[0].read_text())['resolved'])

    def test_immature_deferred_phase_and_unknown_return_idle_cannot_dispatch(self):
        self.args.execute=True
        self.candidate['stored']['status']=2
        self.candidate['firstSlotElapsed']=False
        self.assertEqual(queue.service(self.args),2)
        self.sender.assert_not_called(); self.command.assert_not_called()
        self.candidate['stored']['status']=5
        self.candidate['receipt']['result']=0
        self.assertEqual(queue.service(self.args),2)
        self.sender.assert_not_called()

    def assert_undetermined_cleanup(self, result, execution):
        self.args.execute=True
        self.candidate['stored'].update(status=6,result=result,txExecutionResult=execution)
        self.candidate['receipt'].update(status=6,result=result,txExecutionResult=execution)
        self.probe={'challenge_id':0,'item_index':0,'touched':False}
        def without_application_proof(method, *args):
            self.assertNotEqual(method,'get_probe')
            return self.read(method,*args)
        with patch.object(queue.QueueService,'read',side_effect=without_application_proof):
            self.assertEqual(queue.service(self.args),0)
        self.assertEqual(self.sender.call_count,1)
        self.assertIn('--finalize',self.sender.call_args.args[0])
        for suffix in ('.before.json','.dispatch.json','.done.json'):
            evidence=json.loads(self.records(suffix)[0].read_text())
            self.assertIs(evidence['beforeStoredUND'],True)
            self.assertIs(evidence['native_success'],False)
        done=json.loads(self.records('.done.json')[0].read_text())
        self.assertTrue(done['resolved'])
        self.assertEqual(done['native_status'],'FINALIZED')
        events=[json.loads(line) for line in self.records('events.jsonl')[0].read_text().splitlines()]
        for event in events:
            if event['action'] in {'PLAN','PROTOCOL_OPERATION_DONE'}:
                self.assertIs(event['beforeStoredUND'],True)
                self.assertIs(event['native_success'],False)
        # Closing the native queue must not expand application recovery policy.
        self.assertFalse(queue.recovery.retryable_receipt(self.candidate['receipt']))

    def test_stored_undetermined_with_stale_agree_not_voted_finalizes_as_failure(self):
        self.assert_undetermined_cleanup(result=1,execution=0)

    def test_stored_undetermined_return_idle_finalizes_without_claiming_success(self):
        self.assert_undetermined_cleanup(result=0,execution=1)

    def test_stored_undetermined_stale_positive_needs_no_applied_slot_proof(self):
        self.assert_undetermined_cleanup(result=1,execution=1)

    def test_stored_undetermined_still_requires_actual_head_and_exact_simulation(self):
        self.args.execute=True
        self.candidate['stored'].update(status=6,result=1,txExecutionResult=0)
        self.candidate['receipt'].update(status=6,result=1,txExecutionResult=0)
        self.candidate['atFinalizedHead']=False
        self.assertEqual(queue.service(self.args),2)
        self.command.assert_not_called(); self.sender.assert_not_called()
        self.candidate['atFinalizedHead']=True
        self.dry_results['finalize']=(2,'execution reverted: FinalizationNotAllowed')
        self.assertEqual(queue.service(self.args),2)
        self.assertEqual(len(self.calls),1)
        self.assertIn('--finalize',self.calls[0])
        self.sender.assert_not_called()

    def recorded_rule(self):
        self.row={'key':'rule:0','tx':TX,'address':self.args.address,'at':1,
                  'method':'rule','step':'rule','challenge_id':0,
                  'signature':queue.digest(['rule',['0'],'0'])}
        Path(self.args.manifest).write_text(json.dumps(self.row)+'\n')
        self.candidate['decoded']['callData']={'method':'rule','args':['0']}

    def test_recorded_rule_is_finalized_without_creating_an_application_call(self):
        self.recorded_rule()
        self.chain_claim['status']='RULED'; self.challenge['status']='RULED'
        self.args.execute=True
        self.assertEqual(queue.service(self.args),0)
        self.assertEqual(self.sender.call_count,1)
        self.assertIn('--finalize',self.sender.call_args.args[0])
        self.assertFalse(any('rule' in command or '--method' in command for command in self.calls))
        before=json.loads(self.records('.before.json')[0].read_text())
        self.assertEqual(before['row']['_expected_call'],{'method':'rule','args':['0'],'value':'0'})

    def test_recorded_rule_wrong_identity_step_signature_or_value_is_rejected(self):
        self.recorded_rule()
        original=copy.deepcopy(self.row)
        changes=[{'key':'rule:1'}, {'challenge_id':1}, {'step':'probe'}, {'value':1},
                 {'signature':queue.digest(['rule',['1'],'0'])},
                 {'signature':queue.digest(['rule',['0'],'1'])},
                 {'key':'retire:0','method':'retire','step':'retire',
                  'signature':queue.digest(['retire',['0'],'0'])},
                 {'key':'withdraw','method':'withdraw','step':'withdraw',
                  'signature':queue.digest(['withdraw',[],'0'])}]
        self.args.execute=True
        for change in changes:
            with self.subTest(change=change):
                row=original|change
                Path(self.args.manifest).write_text(json.dumps(row)+'\n')
                self.assertEqual(queue.service(self.args),2)
                self.inspector.assert_not_called(); self.command.assert_not_called(); self.sender.assert_not_called()

    def test_recorded_rule_native_wrong_calldata_or_value_is_rejected(self):
        self.recorded_rule()
        self.args.execute=True
        self.candidate['decoded']['callData']['args']=['1']
        self.assertEqual(queue.service(self.args),2)
        self.command.assert_not_called(); self.sender.assert_not_called()
        self.candidate['decoded']['callData']['args']=['0']
        self.candidate['stored']['value']='1'
        self.assertEqual(queue.service(self.args),2)
        self.command.assert_not_called(); self.sender.assert_not_called()

    def test_finalized_no_execution_may_be_closed_but_does_not_create_a_probe(self):
        self.candidate['stored'].update(status=13,txExecutionResult=0)
        self.candidate['receipt'].update(status=13,result=0,txExecutionResult=0)
        self.args.execute=True
        self.assertEqual(queue.service(self.args),0)
        self.assertEqual(self.sender.call_count,1)
        self.assertIn('--finalize',self.sender.call_args.args[0])

    def test_unknown_heads_network_source_calldata_and_outcomes_refuse(self):
        original=copy.deepcopy(self.data)
        changes=[lambda d:d['heads'].update(getPendingHeadTxId='0x'+'c'*64),
                 lambda d:d['protocol'].update(chainId=1), lambda d:d.update(sourceSha256='wrong'),
                 lambda d:d['protocol']['implementations'].update(ConsensusMain='0x'+'f'*40),
                 lambda d:d['transactions'][0]['stored'].update(recipient='0x'+'3'*40),
                 lambda d:d['transactions'][0]['decoded']['callData'].update(method='rule'),
                 lambda d:d['transactions'][0]['receipt'].update(resultName='NO_MAJORITY'),
                 lambda d:d['transactions'][0]['receipt'].update(result=7),
                 lambda d:d['transactions'][0]['mainTimestamps'].pop('lastVote')]
        self.args.execute=True
        for change in changes:
            self.data=copy.deepcopy(original); change(self.data)
            with self.subTest(change=change):
                self.assertEqual(queue.service(self.args),2)
                self.sender.assert_not_called(); self.command.assert_not_called()

    def test_unknown_dispatch_or_noop_remains_blocked_on_resume(self):
        self.args.execute=True
        self.broadcast_error=queue.Pause('lost bridge output before hash')
        self.assertEqual(queue.service(self.args),2)
        self.broadcast_error=None
        self.assertEqual(queue.service(self.args),2)
        self.assertEqual(self.sender.call_count,1)
        self.assertFalse(self.records('.done.json'))

    def test_evm_success_without_native_progress_is_not_resolved(self):
        self.args.execute=True; self.broadcast_progress=False
        self.assertEqual(queue.service(self.args),2)
        self.assertFalse(json.loads(self.records('.done.json')[0].read_text())['resolved'])
        self.assertEqual(queue.service(self.args),2)
        self.assertEqual(self.sender.call_count,1)

    def test_idleness_fingerprint_does_not_reset_for_wall_clock_or_vote_count(self):
        before=queue.phase_fingerprint(self.candidate)
        self.candidate['receipt']['currentTimestamp']='99999'
        self.candidate['receipt']['lastRound']['votesRevealed']='6'
        self.assertEqual(queue.phase_fingerprint(self.candidate),before)
        self.candidate['mainTimestamps']['lastVote']='11'
        self.assertNotEqual(queue.phase_fingerprint(self.candidate),before)

    def test_transport_failure_does_not_authorize_idleness_fallback(self):
        self.args.execute=True
        self.candidate['stored']['status']=4; self.candidate['firstSlotElapsed']=True
        self.dry_results['finalize']=(2,'RPC timeout')
        self.assertEqual(queue.service(self.args),2)
        self.assertEqual(len(self.calls),1)
        self.sender.assert_not_called()

    def test_claim_and_manifest_identity_changes_stop_before_any_simulation(self):
        self.chain_claim['score_milli']+=1
        self.assertEqual(queue.service(self.args),2)
        self.command.assert_not_called()
        self.chain_claim['score_milli']-=1
        self.row['address']='0x'+'9'*40
        Path(self.args.manifest).write_text(json.dumps(self.row)+'\n')
        self.assertEqual(queue.service(self.args),2)
        self.command.assert_not_called()

    def test_state_change_during_simulation_stops_before_marker(self):
        self.args.execute=True
        original=self.run_command
        def change(command, **kwargs):
            response=original(command,**kwargs)
            self.candidate['mainTimestamps']['lastVote']='90'
            return response
        self.command.side_effect=change
        self.assertEqual(queue.service(self.args),2)
        self.sender.assert_not_called()
        self.assertFalse(self.records('.dispatch.json'))

    def test_same_completion_lock_excludes_writer(self):
        with open(self.args.manifest+'.complete.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(queue.service(self.args),2)
        self.inspector.assert_not_called(); self.sender.assert_not_called()

    def test_frozen_claim_can_be_cleaned_after_trial_expiry_without_new_probes(self):
        self.chain_claim['status']='RULED'; self.challenge['status']='RULED'
        self.assertEqual(queue.service(self.args),0)
        self.sender.assert_not_called()

    def test_runtime_and_operation_limits_stop_additional_operations(self):
        self.args.max_runtime=1e-12
        self.assertEqual(queue.service(self.args),2)
        self.command.assert_not_called()
        self.args.max_runtime=300; self.args.execute=True; self.args.max_operations=1
        self.assertEqual(queue.service(self.args),2)
        self.assertEqual(self.sender.call_count,1)

    def test_broadcast_records_hash_even_if_bridge_then_fails_and_passes_lock_fd(self):
        # Exercise the actual streaming/log monitor without starting a process.
        original_broadcast=ORIGINAL_BROADCAST
        with open(self.args.manifest+'.complete.lock','a') as lock:
            runner=queue.QueueService(self.args,lock)
            stem=runner.folder/'fake-operation'
            def popen(command, **kwargs):
                self.assertEqual(kwargs['pass_fds'],(lock.fileno(),))
                kwargs['stdout'].write('Finalization EVM transaction: '+EVM+'\n')
                kwargs['stdout'].flush()
                return SimpleNamespace(poll=lambda:2,pid=123)
            with patch.object(queue.subprocess,'Popen',side_effect=popen), self.assertRaisesRegex(queue.Pause,'outcome uncertain'):
                original_broadcast(runner,['mock'],stem)
            self.assertEqual(json.loads(Path(str(stem)+'.evm-hash.json').read_text())['evm_tx'],EVM)

    def test_cli_defaults_to_read_only(self):
        options=[value for name in ('address','manifest','claim','account','rpc') for value in ('--'+name,getattr(self.args,name))]
        options+=['--from',self.args.from_address,'--claim-id','0','--challenge-id','0']
        self.assertFalse(queue.parse_args(options).execute)
        self.assertTrue(queue.parse_args(options+['--execute']).execute)


ORIGINAL_BROADCAST=queue.QueueService.broadcast
if __name__=='__main__':
    unittest.main()
