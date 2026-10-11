import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_failure_proof as proof
from proof_fixture import make_bundle

class ProofTests(unittest.TestCase):
    def setUp(self):
        self.call=['1','3','REWRITE','frozen envelope']
        self.row={'tx':'0x'+'a'*64,'address':'0x'+'1'*40,'signature':proof.digest(['probe',self.call,'0'])}
        self.receipt={'status':7,'result':0,'txExecutionResult':1}

    def test_all_three_failed_phases_and_two_ambiguous_outcomes_with_both_origins(self):
        for previous in (6,12,13):
            for outcome in ((1,0),(0,1)):
                for service in (False,True):
                    with self.subTest(previous=previous,outcome=outcome,service=service):
                        b=make_bundle(self.row,self.call,previous=previous,outcome=outcome,service=service)
                        receipt={**self.receipt,'result':outcome[1],'txExecutionResult':outcome[0]}
                        self.assertTrue(proof.validate(b,self.row,receipt,self.call))

    def test_unknown_positive_pending_and_conflicting_receipts_are_not_candidates(self):
        for fields in ({'status':13},{'result':1},{'result':6},{'txExecutionResult':5},
                       {'resultName':'MAJORITY_AGREE'},{'statusName':'ACCEPTED'}):
            self.assertFalse(proof.candidate(self.receipt|fields))

    def test_event_and_identity_mutations_fail_closed(self):
        changes=[lambda b:b['event'].update(previousStatus=5),lambda b:b['event'].update(shouldProcessMessages=True),
          lambda b:b['event']['log'].update(removed=True),lambda b:b['event']['log'].update(address=proof.MAIN),
          lambda b:b['event']['log']['topics'].__setitem__(1,'0x'+'c'*64),
          lambda b:b['event']['log'].update(data='0x'+'0'*128),
          lambda b:b['evm']['receipt'].update(status='reverted'),
          lambda b:b['evm']['receipt']['logs'].append(copy.deepcopy(b['event']['log'])),
          lambda b:b['evm']['block'].update(hash='wrong'),lambda b:b['evm']['transaction'].update(value='1'),
          lambda b:b['snapshot']['protocol']['implementations'].update(ConsensusMain='wrong'),
          lambda b:b['eventProtocol']['implementations'].update(FinalizationPhase='wrong'),
          lambda b:b['snapshot'].update(sourceSha256='changed'),
          lambda b:b['snapshot']['transactions'][0]['stored'].update(status=13),
          lambda b:b['snapshot']['transactions'][0]['decoded']['callData'].update(args=['other']),
          lambda b:b['snapshot']['transactions'][0]['stored'].update(value='1'),
          lambda b:b['snapshot']['transactions'][0]['stored'].update(recipient='wrong'),
          lambda b:b.update(service={})]
        for change in changes:
            b=make_bundle(self.row,self.call);change(b)
            with self.subTest(change=change), self.assertRaises((ValueError,KeyError)):
                proof.validate(b,self.row,self.receipt,self.call)

    def test_explicit_service_requires_consistent_journal_and_actual_finalize_input(self):
        for change in [lambda b:b['service']['done'].update(resolved=False),
            lambda b:b['service']['before']['protocol']['transactions'][0]['stored'].update(status=5),
            lambda b:b['service']['dispatch'].update(operation='process-idleness'),
            lambda b:b['service']['evm_hash'].update(evm_tx='wrong'),
            lambda b:b['evm']['transaction'].update(input='0x00')]:
            b=make_bundle(self.row,self.call,service=True);change(b)
            with self.assertRaises(ValueError):proof.validate(b,self.row,self.receipt,self.call)

    def test_service_timeout_can_materialize_undetermined_before_phase_event(self):
        for old in (12,13):
            b=make_bundle(self.row,self.call,previous=6,service=True)
            b['service']['before']['protocol']['transactions'][0]['stored']['status']=old
            self.assertTrue(proof.validate(b,self.row,self.receipt,self.call))
        b=make_bundle(self.row,self.call,previous=13,service=True)
        b['service']['before']['protocol']['transactions'][0]['stored']['status']=6
        with self.assertRaises(ValueError):proof.validate(b,self.row,self.receipt,self.call)

    def test_claim_source_manager_and_transaction_block_are_bound(self):
        b=make_bundle(self.row,self.call)
        with self.assertRaises(ValueError):proof.validate(b,self.row,self.receipt,self.call,expected_source='changed')
        with self.assertRaises(ValueError):proof.validate(b,self.row,self.receipt,self.call,expected_claim='changed')
        for change in (lambda b:b['snapshot']['protocol'].update(manager='wrong'),
                       lambda b:b['evm']['transaction'].update(blockHash='wrong'),
                       lambda b:b['evm']['transaction'].update(blockNumber='41')):
            b=make_bundle(self.row,self.call);change(b)
            with self.assertRaises(ValueError):proof.validate(b,self.row,self.receipt,self.call)

    def test_history_bundle_digest_and_path_are_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest=str(Path(tmp)/'case.jsonl');folder=Path(manifest+'.receipts');folder.mkdir()
            path=folder/'proof.json';path.write_text(json.dumps(make_bundle(self.row,self.call)))
            entry={'previous_failure_basis':proof.BASIS,'previous_finalization_proof':'case.jsonl.receipts/proof.json',
                   'previous_finalization_proof_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertTrue(proof.verify_reference(entry,manifest,self.row,self.receipt,self.call))
            path.write_text(path.read_text()+' ')
            with self.assertRaisesRegex(ValueError,'digest'):proof.verify_reference(entry,manifest,self.row,self.receipt,self.call)
            entry['previous_finalization_proof']=str(path)
            with self.assertRaisesRegex(ValueError,'unsafe'):proof.verify_reference(entry,manifest,self.row,self.receipt,self.call)

if __name__=='__main__':unittest.main()
