"""Authorized one deterministic rule of expired C1 with 23 paired results.

This is a historical partial case, not completion of the full24 user goal.
No probes, appeals, retirements, withdrawals or new claims are sent here.
"""
import fcntl, hashlib, json, os, pathlib, subprocess, sys, time
from types import SimpleNamespace
ROOT=pathlib.Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0,str(ROOT/'scripts'))
import complete_case, run_case
from chain_receipts import fetch_receipt, successful
ADDRESS='0x45F610cefF1ed367d684A1839b1801Af12Cfb038'
RPC='https://rpc-bradbury.genlayer.com'
MANIFEST=ROOT/'runs/bradbury-v2-live.jsonl'
FOLDER=ROOT/'runs/v2-live-rule01'
FOLDER.mkdir(exist_ok=True)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name,value): complete_case.json_write(FOLDER/name,value,exclusive=True)
def read(method,*args): return run_case.tool.chain_call(ADDRESS,method,list(args),RPC,30)
with open(str(MANIFEST)+'.complete.lock','a+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (FOLDER/'dispatch.json').exists(): raise RuntimeError('rule dispatch already attempted; reconcile same hash')
    audit_path=ROOT/'runs/v2-live-human-approved-audit/audit.json'
    audit=json.loads(audit_path.read_text())
    if (not audit['all_manifest_finalized'] or not audit['frozen_onchain_claim_matches']
        or audit['manifest_rows']!=107 or audit['manifest_sha256']!=digest(MANIFEST)
        or audit['source_sha256']!=digest(ROOT/'build/impeach.py')):
        raise RuntimeError('full frozen 107-receipt final audit required')
    claim=run_case.load_claim('calibration/claim-court24-v2.json')
    rewrites=run_case.load_rewrites(claim)
    if hashlib.sha256(json.dumps([claim,rewrites],sort_keys=True,ensure_ascii=False).encode()).hexdigest()!=audit['input_sha256']:
        raise RuntimeError('frozen claim inputs changed')
    states=audit['states']
    forecast=run_case.tool.rule_offline(claim,states)
    if forecast['verdict']!='CLEAN' or forecast['admissible_probes']!=23:
        raise RuntimeError('reviewed partial-case arithmetic changed')
    inspection=subprocess.run(['node','scripts/inspect_queue.mjs','--address',ADDRESS,'--rpc',RPC,
        '--source','build/impeach.py'],capture_output=True,text=True,timeout=50,check=True)
    native=json.loads(inspection.stdout)
    # The user subsequently explicitly approved C1's partial closure. V3 setup
    # is already accepted, so only these exact three verified positive calls
    # may precede rule1. Pending/unknown/failed queue heads remain forbidden.
    v3_manifest=ROOT/'runs/bradbury-v3-live.jsonl'
    v3_rows=[json.loads(line) for line in v3_manifest.read_text().splitlines() if line.strip()]
    allowed={'open':'0x6d496d483c03edb59c0386fabbaa19edd606f81fe47012c58dac6b9dffb00083',
      'challenge:2':'0x5d3bcf0eea8260351d1573145fd18368224ada050cd8f298ec812c66aff16aca',
      'reveal:2':'0x521dabe386c85626b4dd02295403fd6d169b5293804c80951a15fdae4ec2ba5c'}
    if len(v3_rows)!=3 or {r['key']:r['tx'] for r in v3_rows}!=allowed:raise RuntimeError('unexpected V3 manifest frontier')
    v3_setup=json.loads((ROOT/'runs/v3-native-setup/result.json').read_text())
    if read('get_claim',2)!=v3_setup['claim'] or read('get_challenge',2)!=v3_setup['challenge']:
        raise RuntimeError('V3 frozen revealed TRIAL state changed')
    capture_args=SimpleNamespace(claim='calibration/claim-court24-v3.json',claim_id=2,challenge_id=2,subset='')
    class Capture:
        args=capture_args
        def send(self,key,method,call_args,value=0,extra=None):self.expected=(key,method,call_args,value)
    frontier=[]
    for row,step,account in zip(v3_rows,[run_case.step_open,run_case.step_challenge,run_case.step_reveal],
        ['0x771388495F34d21C5574FeFc04cd1D5811E00aDa','0x4988285D5a05da3a1827f21330fdf14d9F81d4C9','0x771388495F34d21C5574FeFc04cd1D5811E00aDa']):
        capture=Capture();step(capture);key,method,call_args,value=capture.expected
        signature=hashlib.sha256(json.dumps([method,call_args,str(value)],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if row['key']!=key or row['method']!=method or row['signature']!=signature or row['address'].lower()!=ADDRESS.lower():
            raise RuntimeError('V3 frontier signature changed')
        snapshot=json.loads(subprocess.run(['node','scripts/inspect_queue.mjs','--address',ADDRESS,'--rpc',RPC,
            '--source','build/impeach.py','--tx',row['tx']],capture_output=True,text=True,timeout=50,check=True).stdout)
        if (int(snapshot['heads']['getPendingHeadTxId'],16) or int(snapshot['heads']['getUndeterminedHeadTxId'],16)
            or any(int(v,16) and v not in allowed.values() for v in snapshot['heads'].values())):
            raise RuntimeError('unapproved native queue frontier')
        item=next(t for t in snapshot['transactions'] if t['tx']==row['tx'])
        if (item['stored']['status'] not in (5,7) or not successful(item['receipt'])
            or int(item['stored']['value'])!=value or item['stored']['sender'].lower()!=account.lower()
            or item['decoded']['callData']!={'method':method,'args':call_args}):
            raise RuntimeError('V3 frontier is not exact positive accepted setup')
        frontier.append(snapshot)
    challenge,chain_claim,clock=read('get_challenge',1),read('get_claim',1),read('clock')
    p14,p23=read('get_probe',1,14),read('get_probe',1,23)
    if (challenge!=audit['challenge'] or chain_claim!=audit['claim'] or p14!=states[14] or p23!=states[23]
        or clock<=challenge['trial_started_at']+chain_claim['trial_window_s']):
        raise RuntimeError('audited expired TRIAL/state changed')
    args=SimpleNamespace(address=ADDRESS,manifest=str(MANIFEST),account='impeach-challenger',rpc=RPC,
        dry_run=False,wait_timeout=240,poll_interval=5,delay=0,acknowledge_failed=[],challenge_id=1)
    runner=run_case.Runner(args)
    if 'rule:1' in runner.rows: raise RuntimeError('rule already journaled; reconcile only')
    save('before.json',{'at':time.time(),'audit_sha256':digest(audit_path),'native':native,
        'challenge':challenge,'claim':chain_claim,'clock':clock,'states':states,'forecast':forecast,
        'full24_paired_goal_completed':False,'pending_C2_items':[14],
        'wrapper_sha256':digest(pathlib.Path(__file__)), 'v3_frontier':frontier,
        'policy_exception':'Only the three exact accepted V3 setup transactions may precede deterministic rule1; no pending/unknown/failed heads.',
        'human_approval':{'relay':'/root directly received user answer',
          'question_id':'call_999544e1c61f4adf813a7c2c58e0ab4e',
          'answer':'Да, закрыть неполную попытку и снять бонд',
          'scope':'Close C1/H1 with its actual23 pairs and retire its bond; no withdrawal here.'}})
    save('dispatch.json',{'at':time.time(),'method':'rule','args':['1'],'value':'0',
        'account':args.account,'status':'DISPATCHING','authorized_calls':1})
    run_case.step_rule(runner)
    row=runner.rows['rule:1']
    save('submitted.json',row)
    receipt=fetch_receipt(row['tx'],RPC,30)
    save('receipt.json',receipt)
    if not successful(receipt): raise RuntimeError('rule receipt not confirmed; poll same hash only')
    certificate=read('certificate',1)
    save('after.json',{'at':time.time(),'certificate':certificate,'claim':read('get_claim',1),
        'challenge':read('get_challenge',1),'solvency':read('solvency'),'counts':read('counts'),
        'state14':read('get_probe',1,14),'state23':read('get_probe',1,23),'forecast':forecast})
    for key,value in forecast.items():
        if certificate.get(key)!=value: raise RuntimeError('certificate arithmetic differs: '+key)
    save('result.json',{'at':time.time(),'tx':row['tx'],'native_accepted':True,
        'certificate_matches_recompute':True,'full24_paired_goal_completed':False})
