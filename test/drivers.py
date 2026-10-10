"""Two ways to run the same contract.

StubDriver   the local stub in test/stub. No downloads, no dependencies. This is
             what `make check` and CI run.
SdkDriver    the real GenLayer Python SDK, at the exact runner hash pinned in
             the contract header, through genlayer-test's direct mode. Storage,
             calldata and the eq-principle wrappers are the real ones; only the
             network (endpoint, LLM) is scripted. This is `make check-sdk`.

Scenarios in test/scenarios.py are written against the small interface both
drivers share, so every assertion is made twice.
"""

import datetime
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(ROOT, "contracts", "impeach.py")
EPOCH = 1_790_000_000  # arbitrary fixed start, late 2026


def _iso(seconds: int) -> str:
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).isoformat()


class Reverted(Exception):
    pass


class _Base:
    name = "?"

    def __init__(self, world):
        self.world = world
        self.now = EPOCH
        self.paid_in = 0
        self.paid_out = 0
        self.broken = []     # solvency violations, by call

    # subclasses: _invoke(sender, value, method, args), _set_time(), addr(n), hex(a)

    def call(self, sender, method, *args, value=0):
        result = self._invoke(sender, value, method, args)
        self.paid_in += value
        if method == "withdraw":
            self.paid_out += int(result)
        s = self._invoke(sender, 0, "solvency", ())
        if not s["balanced"] or s["held"] != self.paid_in - self.paid_out:
            self.broken.append((method, dict(s), self.paid_in, self.paid_out))
        return result

    def view(self, method, *args):
        return self._invoke(self.addr(0), 0, method, args)

    def reverts(self, sender, method, *args, value=0, match=""):
        """True when the call is refused, and refused for the expected reason."""
        try:
            self._invoke(sender, value, method, args)
        except Exception as exc:  # noqa: BLE001
            return match in str(exc) if match else True
        return False

    def warp(self, seconds: int):
        self.now += seconds
        self._set_time()

    def close(self):
        pass

    def sent(self) -> list:
        """Native value that actually left the contract, in order."""
        raise NotImplementedError


class StubDriver(_Base):
    name = "stub"

    def __init__(self, world):
        super().__init__(world)
        stub = os.path.join(ROOT, "test", "stub")
        if stub not in sys.path:
            sys.path.insert(0, stub)
        import genlayer as glmod

        self.glmod = glmod
        self.gl = glmod.gl
        spec = importlib.util.spec_from_file_location("impeach_contract", CONTRACT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.gl.nondet.handler = world.llm
        self.gl.nondet.web.handler = world.http
        self.gl.nondet.web.calls = []
        self.gl.advanced.transfers = []
        self._set_time()
        self.contract = self.module.Impeach()

    def addr(self, n: int):
        return self.glmod.Address("0x" + ("%02x" % (0x11 * (n + 1) % 256)) * 20)

    def hex(self, a) -> str:
        return a.as_hex

    def _set_time(self):
        self.gl.message_raw["datetime"] = _iso(self.now)

    def sent(self) -> list:
        return [amount for _, amount in self.gl.advanced.transfers]

    def _invoke(self, sender, value, method, args):
        self.gl.message.sender_address = sender
        self.gl.message.value = value
        return getattr(self.contract, method)(*args)


class SdkDriver(_Base):
    name = "sdk"
    SDK_VERSION = os.environ.get("IMPEACH_GENVM", "v0.2.16")

    def __init__(self, world):
        super().__init__(world)
        from gltest.direct import VMContext, deploy_contract, create_address

        self._create_address = create_address
        self.vm = VMContext()
        self.vm._datetime = _iso(self.now)
        self.vm.sender = None
        self._cm = self.vm.activate()
        self._cm.__enter__()
        self.vm._live_web_handler = self._web
        self.vm._live_llm_handler = self._llm
        self.vm._gl_call_hook = self._hook
        # Closures handed to the eq-principles are pickled and re-run by every
        # validator. Have the harness prove that they can be.
        self.vm.check_pickling = True
        self.transfers = []
        self._addrs = {}
        # deploy needs a sender before the module is loaded
        self.vm._sender = bytes(20)
        self.contract = deploy_contract(CONTRACT, self.vm, sdk_version=self.SDK_VERSION)
        self._set_time()

    def addr(self, n: int):
        if n not in self._addrs:
            self._addrs[n] = self._create_address("impeach-test-%d" % n)
        return self._addrs[n]

    def hex(self, a) -> str:
        return a.as_hex

    def _web(self, data):
        body = data.get("body")
        status, payload = self.world.http(data.get("url", ""), body)
        return {"ok": {"response": {"status": status, "headers": {}, "body": payload}}}

    def _llm(self, data):
        result = self.world.llm(data.get("prompt", ""))
        if data.get("response_format") == "json" and isinstance(result, str):
            result = json.loads(result)
        return {"ok": result}

    def _hook(self, vm, request):
        # native value leaving the contract on withdraw
        for kind in ("EthSend", "PostMessage", "EthCall"):
            if kind in request:
                self.transfers.append((kind, request[kind]))
                return {"ok": None}
        return None

    def _set_time(self):
        self.vm.warp(_iso(self.now))
        gl = sys.modules.get("genlayer.gl")
        if gl is not None and getattr(gl, "message_raw", None) is not None:
            gl.message_raw["datetime"] = _iso(self.now)

    def _invoke(self, sender, value, method, args):
        self.vm.sender = sender
        self.vm.value = value
        return getattr(self.contract, method)(*args)

    def sent(self) -> list:
        return [int(req.get("value", 0)) for kind, req in self.transfers if kind == "EthSend"]

    def close(self):
        self._cm.__exit__(None, None, None)
