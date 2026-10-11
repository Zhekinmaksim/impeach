"""Authorized V3 open/challenge/reveal using the official Runner, never C1 writes."""
import fcntl,hashlib,json,os,pathlib,sys,time
from types import SimpleNamespace
ROOT=pathlib.Path(__file__).resolve().parent.parent
os.chdir(ROOT);sys.path.insert(0,str(ROOT/'scripts'))
import complete_case,run_case
from chain_receipts import fetch_receipt,successful
ADDRESS='0x45F610cefF1ed367d684A1839b1801Af12Cfb038'
RPC='https://rpc-bradbury.genlayer.com'
MANIFEST=ROOT/'runs/bradbury-v3-live.jsonl'
FOLDER=ROOT/'runs/v3-native-setup'
FOLDER.mkdir(exist_ok=True)
def load(path):return json.loads(pathlib.Path(path).read_text())
def digest(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def save(name,value):complete_case.json_write(FOLDER/name,value,exclusive=True)
def read(method,*args):return run_case.tool.chain_call(ADDRESS,method,list(args),RPC,30)
def same_claim(value):
    expected={k:claim[k] for k in ['subject','endpoint','score_milli','scoring_rule','classes','delta_threshold','recall_threshold','min_items']}
    expected.update(claim['extras']);expected.update(stake=int(claim['stake']),bond_sworn=int(claim['bond']),
      item_hashes=[run_case.tool.item_commitment(i['prompt'],i['answer'],i['salt']) for i in claim['_items']])
    for key,v in expected.items():
        if value.get(key)!=v:raise RuntimeError('frozen chain claim mismatch '+key)
    for key in ['prompt_template','decode_params']:
        v=value[key];v=json.loads(v) if isinstance(v,str) else v
        if v!=claim[key]:raise RuntimeError('frozen chain claim mismatch '+key)
    if value['publisher'].lower()!='0x771388495f34d21c5574fefc04cd1d5811e00ada':raise RuntimeError('wrong publisher')
class DurableSetup(run_case.Runner):
    def send(self,key,method,call_args,value=0,extra=None):
        marker=FOLDER/(key.replace(':','-')+'.dispatch.json')
        if marker.exists() and key not in self.rows:raise RuntimeError('unknown setup dispatch; reconcile without resending '+key)
        if key not in self.rows:
            complete_case.json_write(marker,{'at':time.time(),'key':key,'method':method,'args':call_args,
                'value':str(value),'account':self.args.account,'status':'DISPATCHING'},exclusive=True)
        return super().send(key,method,call_args,value,extra)
    def wait(self,row):
        try:return super().wait(row)
        finally:
            receipt=fetch_receipt(row['tx'],RPC,30)
            suffix=hashlib.sha256(json.dumps(receipt,sort_keys=True).encode()).hexdigest()
            path=FOLDER/(row['key'].replace(':','-')+'-'+suffix+'.receipt.json')
            if not path.exists():complete_case.json_write(path,receipt,exclusive=True)
with open(str(MANIFEST)+'.complete.lock','a+') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if digest('calibration/claim-court24-v3.json')!='17577cd188fa66c5735bc1e1228c335ee51743631ab9981b01f371d1653fbe61':raise RuntimeError('claim changed')
    if digest('build/impeach.py')!='6336e9c160b53839497adb4652c0cf8d7c1f5b76bcf7ed99d3f5553da53f3c89':raise RuntimeError('source changed')
    pre=load('runs/v3-native-start-preflight.json');activation=load('runs/v3-live-activation-verified.json')
    model=load('runs/v3-llama-verified-audit.json');ref=load('runs/v3-referee-verified.json')
    if (not pre['all_24_unspent'] or not pre['native_queues_empty'] or pre['counts']!=pre['counts_after']
        or not model['gate_passed'] or model['unique_actual_new_requests']!=72 or not ref['gate_passed']
        or ref['honest_admitted']!=24 or ref['controls_rejected_both']!=4 or activation['epoch']!=1791730289
        or not activation['v3_enabled'] or time.time()+120>=activation['epoch']):raise RuntimeError('V3 gates not ready')
    claim=run_case.load_claim('calibration/claim-court24-v3.json')
    args=SimpleNamespace(address=ADDRESS,claim='calibration/claim-court24-v3.json',manifest=str(MANIFEST),rpc=RPC,
        account='recuse-deployer',dry_run=False,delay=0,wait_timeout=240,poll_interval=5,acknowledge_failed=[],subset='')
    before_path=FOLDER/'before.json'
    if not before_path.exists():
        counts=read('counts')
        if counts!=pre['counts_after']:raise RuntimeError('counts changed since fresh preflight')
        save('before.json',{'at':time.time(),'counts':counts,'preflight_sha256':digest('runs/v3-native-start-preflight.json'),
            'activation_sha256':digest('runs/v3-live-activation-verified.json'),'wrapper_sha256':digest(__file__)})
    before=load(before_path);cid=before['counts']['claims'];hid=before['counts']['challenges']
    args.claim_id=cid;args.challenge_id=hid
    runner=DurableSetup(args)
    run_case.step_open(runner)
    chain_claim=read('get_claim',cid);counts=read('counts');same_claim(chain_claim)
    if counts['claims']!=cid+1:raise RuntimeError('unexpected actual claim counter')
    if not (FOLDER/'open.actual.json').exists():save('open.actual.json',{'at':time.time(),'actual_claim_id':chain_claim['claim_id'],'claim':chain_claim,'counts':counts,'row':runner.rows['open']})
    print(json.dumps({'actual_claim_id':chain_claim['claim_id'],'open_tx':runner.rows['open']['tx']}),flush=True)
    args.account='impeach-challenger';runner=DurableSetup(args)
    run_case.step_challenge(runner)
    challenge=read('get_challenge',hid);counts=read('counts')
    if (challenge['claim_id']!=cid or challenge['challenge_id']!=hid or challenge['subset']!=list(range(24))
       or counts['challenges']!=hid+1):raise RuntimeError('unexpected actual challenge identity')
    if not (FOLDER/'challenge.actual.json').exists():save('challenge.actual.json',{'at':time.time(),'actual_challenge_id':challenge['challenge_id'],'challenge':challenge,'counts':counts,'row':runner.rows['challenge:'+str(cid)]})
    print(json.dumps({'actual_challenge_id':hid,'challenge_tx':runner.rows['challenge:'+str(cid)]['tx']}),flush=True)
    args.account='recuse-deployer';runner=DurableSetup(args)
    run_case.step_reveal(runner)
    challenge=read('get_challenge',hid);chain_claim=read('get_claim',cid);same_claim(chain_claim)
    if challenge['status']!='TRIAL' or chain_claim['status']!='TRIAL' or chain_claim['active_challenge']!=hid:raise RuntimeError('reveal did not create matching TRIAL')
    result={'at':time.time(),'actual_claim_id':cid,'actual_challenge_id':hid,'challenge':challenge,'claim':chain_claim,
      'counts':read('counts'),'solvency':read('solvency'),'trial_deadline':challenge['trial_started_at']+21600,
      'gateway_expires_at':1791730289,'subject_dispatch_cutoff':1791730169,'rows':list(runner.rows.values())}
    if not (FOLDER/'result.json').exists():save('result.json',result)
    print(json.dumps({'setup_complete':True,'claim_id':cid,'challenge_id':hid,'trial_started_at':challenge['trial_started_at'],
      'trial_deadline':result['trial_deadline'],'gateway_expires_at':1791730289}),flush=True)
