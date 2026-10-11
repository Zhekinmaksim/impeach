"""One explicitly authorized same-hash, zero-bond appeal; never retry this script."""
import fcntl, hashlib, json, os, pathlib, subprocess, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / 'scripts'))
import complete_case, retry_finalized_probe
FOLDER = ROOT / 'runs/v2-live-item14-appeal01'
FOLDER.mkdir(exist_ok=True)
TX = '0xa264c36846db3a8a567d3e493ceadfd3ff30d1582aa6f573fe7d42d701ccb40c'
ADDRESS = '0x45F610cefF1ed367d684A1839b1801Af12Cfb038'
RPC = 'https://rpc-bradbury.genlayer.com'
MANIFEST = 'runs/bradbury-v2-live.jsonl'
def save(name, value):
    complete_case.json_write(FOLDER / name, value, exclusive=True)
args = complete_case.parse_args(['--address', ADDRESS, '--claim', 'calibration/claim-court24-v2.json',
    '--manifest', MANIFEST, '--account', 'impeach-challenger', '--rpc', RPC, '--challenge-id', '1',
    '--max-recoveries', '3', '--deadline-margin', '120'])
with open(MANIFEST + '.complete.lock', 'a+') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (FOLDER / 'dispatch.json').exists():
        raise RuntimeError('appeal dispatch already attempted; reconcile, never resend')
    runner = complete_case.Completer(args, completion_lock=lock)
    runner.guard()
    row = runner.rows['probe:1:14:ADMIT']
    if row['tx'] != TX or not retry_finalized_probe.slot_untouched(runner.state(14), 'ADMIT'):
        raise RuntimeError('latest transaction/slot changed')
    inspection = subprocess.run(['node', 'scripts/inspect_queue.mjs', '--address', ADDRESS,
        '--rpc', RPC, '--source', 'build/impeach.py', '--tx', TX], capture_output=True, text=True,
        timeout=45, check=True)
    before = json.loads(inspection.stdout)
    native = next(t for t in before['transactions'] if t['tx'] == TX)
    if native['stored']['status'] != 13 or native['stored']['result'] != 0 or native['stored']['txExecutionResult'] != 0:
        raise RuntimeError('reviewed no-execution phase changed; do not appeal')
    refs = ['build/impeach.py', 'calibration/claim-court24-v2.json',
        'runs/v2-live-item14-early-appeal-simulation.log', 'runs/v2-live-before-appeal-state-0928.json',
        'runs/v2-live-item14-recovery01-appeal-capacity.json',
        'runs/v2-live-record-appeal-evm.mjs', 'runs/v2-live-one-appeal.py']
    save('before.json', {'at': time.time(), 'native': before, 'original_row': row,
        'input_sha256': runner.input_hash, 'state14': runner.state(14), 'state23': runner.state(23),
        'refs_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in refs}})
    runner.guard()
    if not retry_finalized_probe.slot_untouched(runner.state(14), 'ADMIT'):
        raise RuntimeError('C2 changed before dispatch')
    save('dispatch.json', {'at': time.time(), 'tx': TX, 'account': args.account, 'bond': '0',
        'status': 'DISPATCHING', 'authorized_appeals': 1, 'unchanged_payload': True})
    env = dict(os.environ, IMPEACH_EVM_RECEIPT_FILE=str(FOLDER / 'evm-hash.json'))
    command = ['node', '--import', str(ROOT / 'runs/v2-live-record-appeal-evm.mjs'),
        'scripts/genlayer_write.mjs', '--appeal', TX, '--account', args.account, '--value', '0', '--rpc', RPC]
    with (FOLDER / 'bridge.log').open('a', encoding='utf-8') as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        for line in process.stdout:
            log.write(line); log.flush(); os.fsync(log.fileno()); print(line, end='', flush=True)
        code = process.wait()
    save('result.json', {'at': time.time(), 'returncode': code, 'evm_hash_recorded': (FOLDER / 'evm-hash.json').exists()})
    if code or not (FOLDER / 'evm-hash.json').exists():
        raise RuntimeError('appeal outcome requires reconciliation; never resend')
