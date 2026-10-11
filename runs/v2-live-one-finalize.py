"""One authorized native finalization only; never repeat uncertain dispatch."""
import fcntl, hashlib, json, os, pathlib, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / 'scripts'))
import complete_case, run_case
TX = '0xcedffa69c57e1b3b42dc91ec2f4921b5d43de2a0ca05841382df34aa2f752a54'
COURT = '0x45F610cefF1ed367d684A1839b1801Af12Cfb038'
RPC = 'https://rpc-bradbury.genlayer.com'
MANIFEST = ROOT / 'runs/bradbury-v2-live.jsonl'
FOLDER = ROOT / 'runs/v2-live-item23-finalize01'
FOLDER.mkdir(exist_ok=True)
def save(name, value):
    complete_case.json_write(FOLDER / name, value, exclusive=True)
with open(str(MANIFEST) + '.complete.lock', 'a+') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (FOLDER / 'dispatch.json').exists():
        raise RuntimeError('dispatch attempted; reconcile, never resend')
    rows = [json.loads(line) for line in MANIFEST.read_text().splitlines() if line.strip()]
    row = [row for row in rows if row['key'] == 'probe:1:23:ADMIT'][-1]
    if row['tx'] != TX or row['address'].lower() != COURT.lower():
        raise RuntimeError('latest manifest transaction changed')
    result = subprocess.run(['node', 'scripts/inspect_queue.mjs', '--address', COURT,
        '--rpc', RPC, '--source', 'build/impeach.py', '--tx', TX],
        capture_output=True, text=True, timeout=50, check=True)
    before = json.loads(result.stdout)
    native = next(t for t in before['transactions'] if t['tx'] == TX)
    state = run_case.tool.chain_call(COURT, 'get_probe', [1, 23], RPC, 30)
    refs = ['build/impeach.py', 'calibration/claim-court24-v2.json',
            'runs/v2-live-item23-finalize-simulation.log',
            'runs/v2-live-record-finalize-evm.mjs', 'runs/v2-live-one-finalize.py']
    save('before.json', {'at': time.time(), 'native': before, 'row': row, 'state23': state,
        'refs_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in refs}})
    if native['stored']['status'] == 7:
        save('result.json', {'at': time.time(), 'already_finalized': True, 'broadcast': False})
        raise SystemExit(0)
    if (native['stored']['status'] != 5 or not native['atFinalizedHead']
            or not native['canFinalize'][0] or native['stored']['txExecutionResult'] != 1
            or native['receipt']['result'] != 1 or native['stored']['value'] != '0'
            or native['decoded']['callData'] != {'method': 'probe', 'args': ['1', '23', 'ADMIT', '']}
            or state.get('stage_c1') != 'ADMISSIBLE' or state.get('stage_c2') != 'ADMISSIBLE'):
        raise RuntimeError('reviewed native/state finalization conditions changed')
    save('dispatch.json', {'at': time.time(), 'tx': TX, 'account': 'recuse-deployer',
        'value': '0', 'status': 'DISPATCHING', 'authorized_finalizations': 1})
    env = dict(os.environ, IMPEACH_EVM_RECEIPT_FILE=str(FOLDER / 'evm-hash.json'))
    command = ['node', '--import', str(ROOT / 'runs/v2-live-record-finalize-evm.mjs'),
        'scripts/genlayer_write.mjs', '--finalize', TX, '--account', 'recuse-deployer',
        '--value', '0', '--rpc', RPC]
    with (FOLDER / 'bridge.log').open('a', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env, pass_fds=(lock.fileno(),))
        for line in process.stdout:
            log.write(line); log.flush(); os.fsync(log.fileno()); print(line, end='', flush=True)
        code = process.wait()
    save('result.json', {'at': time.time(), 'returncode': code,
        'evm_hash_recorded': (FOLDER / 'evm-hash.json').exists()})
    if code or not (FOLDER / 'evm-hash.json').exists():
        raise RuntimeError('reconcile outcome, never resend; before/dispatch retained')
