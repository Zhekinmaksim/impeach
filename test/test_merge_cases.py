import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from merge_cases import merge, receipt_totals


class MergeTests(unittest.TestCase):
    def setUp(self):
        # Fixed unit evidence; publishing a second live case must not change
        # the scenarios exercised by this merger regression.
        self.a={'format':'impeach-case/1','provenance':'bradbury','contract':'0x'+'9'*40,
                'generated_at':100,'cases':[{'claim':{'claim_id':0},
                'certificate':{'claim_id':0,'contested':True,'ruled_at':99},
                'txs':{'rule':{'tx':'0x'+'2'*64,'status':'FINALIZED',
                               'execution':'FINISHED_WITH_RETURN','consensus_result':'AGREE'}}}],
                'registry':[{'content_hash':'a'*64,'claim_id':0,'preview':'Known item text'}],
                'receipts':{'total':1,'pending':0,'by_status':{'FINALIZED':1},
                'by_execution':{'FINISHED_WITH_RETURN':1},'by_consensus_result':{'AGREE':1},'by_mode':{}}}
        self.b=copy.deepcopy(self.a)
        self.b['cases'][0]['certificate']['claim_id']=1
        self.b['cases'][0]['claim']['claim_id']=1
        self.b['cases'][0]['txs']['rule']['tx']='0x'+'3'*64

    def test_preserves_case_order_and_receipt_outcomes(self):
        merged=merge([self.b,self.a])
        self.assertEqual([c['certificate']['claim_id'] for c in merged['cases']],[1,0])
        self.assertEqual(merged['receipts']['total'],2*self.a['receipts']['total'])
        self.assertEqual(merged['cases'][1]['txs'],self.a['cases'][0]['txs'])

    def test_combines_registry_annotations_without_erasing_known_text(self):
        self.a['registry'][0]['preview']=''
        merged=merge([self.a,self.b])
        self.assertEqual(merged['registry'][0]['preview'],self.b['registry'][0]['preview'])
        self.assertEqual(len(merged['registry']),len(self.a['registry']))

    def test_refuses_mixed_courts_duplicate_cases_or_conflicting_registry(self):
        for mutate in [lambda b:b.update(contract='0x'+'1'*40),
                       lambda b:b['cases'][0]['certificate'].update(claim_id=0),
                       lambda b:b['registry'][0].update(claim_id=99)]:
            b=copy.deepcopy(self.b);mutate(b)
            with self.assertRaises(ValueError):merge([self.a,b])

    def test_two_24_item_cases_keep_all_registry_previews_and_recovery_hashes(self):
        # Synthetic unit evidence only: no outcome is attributed to a real court.
        rows=[{'content_hash':format(i,'064x'),'claim_id':int(i>=24),
               'preview':'','burned_at':10+i} for i in range(48)]
        self.a['registry']=copy.deepcopy(rows)
        self.b['registry']=copy.deepcopy(rows)
        for i in range(24):self.a['registry'][i]['preview']='control fixture '+str(i)
        for i in range(24,48):self.b['registry'][i]['preview']='real fixture '+str(i)
        old={'tx':'0x'+'4'*64,'status':'FINALIZED',
             'execution':'FINISHED_WITH_RETURN','consensus_result':'NO_MAJORITY'}
        new=dict(old,tx='0x'+'5'*64,consensus_result='AGREE',previous_tx=old['tx'])
        self.a['cases'][0]['txs'].update({'probe:0:2:REWRITE':old,
                                       'probe:0:2:REWRITE@'+new['tx']:new})
        self.a['receipts']=receipt_totals(self.a['cases'])
        result=merge([self.b,self.a])
        self.assertEqual([c['certificate']['claim_id'] for c in result['cases']],[1,0])
        self.assertEqual(len(result['registry']),48)
        self.assertTrue(all(row['preview'] for row in result['registry']))
        self.assertEqual(result['receipts']['total'],4)
        self.assertEqual(result['receipts']['by_consensus_result'],{'AGREE':3,'NO_MAJORITY':1})
        self.assertEqual(result['receipts']['by_mode'],{'REWRITE':{'FINALIZED':2}})
        self.assertEqual(result['cases'][1]['txs']['probe:0:2:REWRITE'],old)
        self.assertEqual(result['cases'][1]['txs']['probe:0:2:REWRITE@'+new['tx']],new)

    def test_shared_receipt_is_counted_once_without_removing_case_links(self):
        self.b['cases'][0]['txs']['rule']=copy.deepcopy(self.a['cases'][0]['txs']['rule'])
        result=merge([self.b,self.a])
        self.assertEqual(result['receipts']['total'],1)
        self.assertEqual(len(result['cases'][0]['txs']),1)
        self.assertEqual(len(result['cases'][1]['txs']),1)

    def test_refuses_unruled_mismatched_or_incomplete_evidence(self):
        for mutate in [lambda b:b['cases'][0]['certificate'].update(ruled_at=0),
                       lambda b:b['cases'][0]['certificate'].update(contested=False),
                       lambda b:b['cases'][0]['claim'].update(claim_id=77),
                       lambda b:b['receipts'].update(total=99),
                       lambda b:b['cases'][0]['txs']['rule'].update(previous_tx='0xmissing')]:
            b=copy.deepcopy(self.b);mutate(b)
            with self.assertRaises(ValueError):merge([self.a,b])

    def test_refuses_conflicting_versions_of_a_shared_receipt(self):
        tx=self.a['cases'][0]['txs']['rule']['tx']
        self.b['cases'][0]['txs']['rule'].update(tx=tx,consensus_result='NO_MAJORITY')
        self.b['receipts']=receipt_totals(self.b['cases'])
        with self.assertRaisesRegex(ValueError,'conflicting receipt'):merge([self.a,self.b])


if __name__=='__main__':unittest.main()
