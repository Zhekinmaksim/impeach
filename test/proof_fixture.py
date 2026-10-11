import copy
import native_failure_proof as proof

def make_bundle(row, call_args, *, source_sha='a'*64, claim_sha='b'*64, previous=13, outcome=(1,0), service=False):
    tx=row['tx']; evm='0x'+'e'*64; blockhash='0x'+'f'*64
    proto={'chainId':4221,'main':proof.MAIN,'version':'2.0.0','manager':'0x8ace036c8c3c5d603db546b031302fcf149648e8',
           'sourceCommit':'9c686087963551277fc2dce0354c2b1a7050b4b2','implementations':dict(proof.PINS)}
    receipt={'txId':tx,'recipient':row['address'],'status':7,'result':outcome[1],'txExecutionResult':outcome[0]}
    native={'tx':tx,'stored':{'id':tx,'recipient':row['address'],'status':7,'value':'0','result':outcome[1],'txExecutionResult':outcome[0]},
            'receipt':receipt,'decoded':{'type':'call','leaderOnly':False,'callData':{'method':'probe','args':call_args}},
            'atFinalizedHead':False}
    snapshot={'protocol':copy.deepcopy(proto),'address':row['address'],'sourceSha256':source_sha,
              'blockNumber':'42','transactions':[native]}
    log={'address':proof.PHASE,'topics':[proof.TOPIC,tx],'data':'0x'+format(previous,'064x')+'0'*64,
         'removed':False,'transactionHash':evm,'blockHash':blockhash,'blockNumber':'40','logIndex':1}
    r={'status':'success','transactionHash':evm,'blockHash':blockhash,'blockNumber':'40','to':proof.MAIN,'logs':[log]}
    t={'to':proof.MAIN,'hash':evm,'blockHash':blockhash,'blockNumber':'40','value':'0','from':'0x'+'9'*40,'input':'0xb2efda83'+tx[2:]}
    b={'format':'impeach-native-no-messages/1','tx':tx,'address':row['address'],'snapshot':snapshot,
       'eventProtocol':copy.deepcopy(proto),'event':{'txId':tx,'previousStatus':previous,'shouldProcessMessages':False,'log':log},
       'evm':{'receipt':r,'transaction':t,'block':{'hash':blockhash,'number':'40'}},
       'call':{'method':'probe','args':call_args,'value':'0'},'source_sha256':source_sha,'claim_sha256':claim_sha,
       'origin':'chain_observation'}
    if service:
        before=copy.deepcopy(snapshot);before['transactions'][0]['stored']['status']=previous
        before['transactions'][0]['atFinalizedHead']=True
        b.update(origin='service_queue',service={'before':{'protocol':before,'row':copy.deepcopy(row)},
            'dispatch':{'operation':'finalize','tx':tx,'value':0,'from':t['from']},
            'done':{'resolved':True,'native_status':'FINALIZED','evm_tx':evm},
            'evm_hash':{'evm_tx':evm},'evm_receipt':{'receipt':copy.deepcopy(r),'transaction':copy.deepcopy(t)},
            'after':copy.deepcopy(snapshot)})
    return b
