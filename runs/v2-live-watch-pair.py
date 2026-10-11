"""Read-only bounded watcher of the two existing hashes after one appeal."""
import json, pathlib, sys, time, datetime
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import run_case
from chain_receipts import fetch_receipt, status_of, execution_of, consensus_result_of
folder = ROOT / 'runs/v2-live-item14-appeal01'
rpc = 'https://rpc-bradbury.genlayer.com'
address = '0x45F610cefF1ed367d684A1839b1801Af12Cfb038'
begin = time.monotonic()
while time.monotonic() - begin < 1200:
    result = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'items': {}}
    compact = []
    for index, tx in [(14, '0xa264c36846db3a8a567d3e493ceadfd3ff30d1582aa6f573fe7d42d701ccb40c'),
                      (23, '0xcedffa69c57e1b3b42dc91ec2f4921b5d43de2a0ca05841382df34aa2f752a54')]:
        receipt = fetch_receipt(tx, rpc, 30)
        state = run_case.tool.chain_call(address, 'get_probe', [1, index], rpc, 30)
        result['items'][str(index)] = {'tx': tx, 'receipt': receipt, 'state': state}
        compact.append({'item': index, 'status': status_of(receipt), 'execution': execution_of(receipt),
            'result': consensus_result_of(receipt), 'rounds': receipt.get('numOfRounds'), 'C2': state.get('stage_c2')})
    (folder / ('paired-observation-' + str(time.time_ns()) + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'at': result['at'], 'items': compact}), flush=True)
    if all(x['status'] == 'FINALIZED' for x in compact):
        break
    time.sleep(40)
