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
    audit_path=ROOT/'runs/v2-live-final-native-audit/audit.json'
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
    if any(int(v,16) for v in native['heads'].values()): raise RuntimeError('native queue not empty')
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
        'wrapper_sha256':digest(pathlib.Path(__file__))})
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
