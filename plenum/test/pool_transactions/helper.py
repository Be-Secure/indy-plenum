from plenum.client.client import Client
from plenum.client.wallet import Wallet
from plenum.common.txn import STEWARD, TXN_TYPE, NYM, ROLE, TARGET_NYM, ALIAS, \
    NODE_PORT, CLIENT_IP, NODE_IP, DATA, NEW_NODE, CLIENT_PORT, CHANGE_HA, \
    CHANGE_KEYS, VERKEY

from plenum.client.signer import SimpleSigner
from plenum.common.raet import initLocalKeep
from plenum.common.util import randomString, hexToCryptonym
from plenum.test.eventually import eventually
from plenum.test.helper import checkSufficientRepliesRecvd, genHa, TestNode, \
    TestClient, genTestClient
from plenum.test.helper import TestRequestIdStore

def addNewClient(role, looper, creatorClient: Client, creatorWallet: Wallet,
                 name: str):
    wallet = Wallet(name, requestIdStore=TestRequestIdStore())
    wallet.addSigner()
    verstr = wallet.idsToSigners[wallet.defaultId].verstr

    op = {
        TXN_TYPE: NYM,
        ROLE: role,
        TARGET_NYM: verstr,
        ALIAS: name
    }

    req = creatorWallet.signOp(op)
    creatorClient.submitReqs(req)

    nodeCount = len(creatorClient.nodeReg)
    looper.run(eventually(checkSufficientRepliesRecvd, creatorClient.inBox,
                          req.reqId, 1,
                          retryWait=1, timeout=3*nodeCount))
    return wallet


def addNewNode(looper, stewardClient, stewardWallet, newNodeName, tdir, tconf,
               allPluginsPath=None, autoStart=True):
    sigseed = randomString(32).encode()
    nodeSigner = SimpleSigner(seed=sigseed)

    (nodeIp, nodePort), (clientIp, clientPort) = genHa(2)

    op = {
        TXN_TYPE: NEW_NODE,
        TARGET_NYM: nodeSigner.verstr,
        DATA: {
            NODE_IP: nodeIp,
            NODE_PORT: nodePort,
            CLIENT_IP: clientIp,
            CLIENT_PORT: clientPort,
            ALIAS: newNodeName
        }
    }

    req = stewardWallet.signOp(op)
    stewardClient.submitReqs(req)

    nodeCount = len(stewardClient.nodeReg)
    looper.run(eventually(checkSufficientRepliesRecvd, stewardClient.inBox,
                          req.reqId, 1,
                          retryWait=1, timeout=3*nodeCount))
    initLocalKeep(newNodeName, tdir, sigseed, override=True)
    node = TestNode(newNodeName, basedirpath=tdir, config=tconf,
                    ha=(nodeIp, nodePort), cliha=(clientIp, clientPort),
                    pluginPaths=allPluginsPath)
    if autoStart:
        looper.add(node)
    return node


def addNewStewardAndNode(looper, creatorClient, creatorWallet, stewardName,
                         newNodeName, tdir, tconf,
                         allPluginsPath=None, autoStart=True):
    newStewardWallet = addNewClient(STEWARD, looper, creatorClient,
                                    creatorWallet, stewardName)
    newSteward = TestClient(name=stewardName,
                            nodeReg=None, ha=genHa(),
                            # DEPR
                            # signer=newStewardSigner,
                            basedirpath=tdir)

    looper.add(newSteward)
    looper.run(newSteward.ensureConnectedToNodes())
    newNode = addNewNode(looper, newSteward, newStewardWallet, newNodeName,
                         tdir, tconf, allPluginsPath, autoStart=autoStart)
    return newSteward, newStewardWallet, newNode


def changeNodeHa(looper, stewardClient, stewardWallet, node, nodeHa, clientHa):
    nodeNym = hexToCryptonym(node.nodestack.local.signer.verhex)
    (nodeIp, nodePort), (clientIp, clientPort) = nodeHa, clientHa
    op = {
        TXN_TYPE: CHANGE_HA,
        TARGET_NYM: nodeNym,
        DATA: {
            NODE_IP: nodeIp,
            NODE_PORT: nodePort,
            CLIENT_IP: clientIp,
            CLIENT_PORT: clientPort,
            ALIAS: node.name
        }
    }

    req = stewardWallet.signOp(op)
    stewardClient.submitReqs(req)
    looper.run(eventually(checkSufficientRepliesRecvd, stewardClient.inBox,
                          req.reqId, 1,
                          retryWait=1, timeout=5))
    node.nodestack.clearLocalKeep()
    node.nodestack.clearRemoteKeeps()
    node.clientstack.clearLocalKeep()
    node.clientstack.clearRemoteKeeps()


def changeNodeKeys(looper, stewardClient, stewardWallet, node, verkey):
    nodeNym = hexToCryptonym(node.nodestack.local.signer.verhex)

    op = {
        TXN_TYPE: CHANGE_KEYS,
        TARGET_NYM: nodeNym,
        DATA: {
            VERKEY: verkey,
            ALIAS: node.name
        }
    }
    req = stewardWallet.signOp(op)
    stewardClient.submitReqs(req)

    looper.run(eventually(checkSufficientRepliesRecvd, stewardClient.inBox,
                          req.reqId, 1,
                          retryWait=1, timeout=5))
    node.nodestack.clearLocalRoleKeep()
    node.nodestack.clearRemoteRoleKeeps()
    node.nodestack.clearAllDir()
    node.clientstack.clearLocalRoleKeep()
    node.clientstack.clearRemoteRoleKeeps()
    node.clientstack.clearAllDir()


def buildPoolClientAndWallet(clientData, tempDir, clientClass=None,
                             walletClass=None):
    walletClass = walletClass or Wallet
    clientClass = clientClass or TestClient
    name, sigseed = clientData
    w = walletClass(name)
    w.addSigner(seed=sigseed)
    client, _ = genTestClient(name=name, identifier=w.defaultId,
                              tmpdir=tempDir, usePoolLedger=True,
                              testClientClass=clientClass)
    return client, w
