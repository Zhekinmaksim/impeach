"""Explicit user-approved retirement of C1 bond only; no wallet withdrawal."""
import fcntl,hashlib,json,os,pathlib,sys,time
from types import SimpleNamespace
ROOT=pathlib.Path(__file__).resolve().parent.parent
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'scripts'))
import complete_case,run_case
from chain_receipts import fetch_receipt,successful
ADDRESS='0x45F610cefF1ed367d684A1839b1801Af12Cfb038'
RPC='https://rpc-bradbury.genlayer.com';MANIFEST=ROOT/'runs/bradbury-v2-live.jsonl'
FOLDER=ROOT/'runs/v2-live-retire01';FOLDER.mkdir(exist_ok=True)
def save(name,value):complete_case.json_write(FOLDER/name,value,exclusive=True)
def read(method,*args):return run_case.tool.chain_call(ADDRESS,method,list(args),RPC,30)
with open(str(MANIFEST)+'.complete.lock','a+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if (FOLDER/'dispatch.json').exists():raise RuntimeError('retirement attempted; reconcile same hash')
    ruled=json.loads((ROOT/'runs/v2-live-rule01/result.json').read_text())
    receipt=fetch_receipt(ruled['tx'],RPC,30)
    if not successful(receipt) or not ruled['certificate_matches_recompute']:raise RuntimeError('rule not confirmed')
    certificate,claim,solvency=read('certificate',1),read('get_claim',1),read('solvency')
    credit=read('balance_of','0x771388495F34d21C5574FeFc04cd1D5811E00aDa')
    if (certificate['verdict'] not in ['CLEAN','INCONCLUSIVE'] or certificate['admissible_probes']!=23
        or claim['status']!='STANDING' or claim['claim_id']!=1 or claim['bond']!=100000000000000000):
        raise RuntimeError('reviewed C1 retirement state differs')
    args=SimpleNamespace(address=ADDRESS,manifest=str(MANIFEST),account='recuse-deployer',rpc=RPC,
        dry_run=False,delay=0,wait_timeout=240,poll_interval=5,acknowledge_failed=[])
    runner=run_case.Runner(args)
    if 'retire:1' in runner.rows:raise RuntimeError('retirement already journaled')
    save('before.json',{'at':time.time(),'certificate':certificate,'claim':claim,'solvency':solvency,
        'publisher_credit':credit,'rule_receipt':receipt,'user_approval':'Да, закрыть неполную попытку и снять бонд',
        'question_id':'call_999544e1c61f4adf813a7c2c58e0ab4e',
        'wrapper_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()})
    save('dispatch.json',{'at':time.time(),'method':'retire_claim','args':['1'],'value':'0','account':args.account,'status':'DISPATCHING'})
    runner.send('retire:1','retire_claim',['1'],value=0,extra={'step':'retire','claim_id':1})
    row=runner.rows['retire:1'];save('submitted.json',row)
    after={'at':time.time(),'receipt':fetch_receipt(row['tx'],RPC,30),'certificate':read('certificate',1),
      'claim':read('get_claim',1),'solvency':read('solvency'),'publisher_credit':read('balance_of','0x771388495F34d21C5574FeFc04cd1D5811E00aDa')}
    save('after.json',after)
    if (not successful(after['receipt']) or after['claim']['status']!='RETIRED'
        or after['claim']['bond']!=0 or after['publisher_credit']!=credit+100000000000000000
        or not after['solvency']['balanced']):raise RuntimeError('retirement accounting differs')
    save('result.json',{'at':time.time(),'tx':row['tx'],'native_accepted':True,'bond_credited_wei':100000000000000000,'wallet_withdrawal_sent':False})
