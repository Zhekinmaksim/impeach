"""Local GenLayer stub. Enough surface to run contracts/impeach.py offline.

Same approach as the Jastrow and Suborn stubs: this is not a simulator of
consensus. It exercises the state machine, the money, the registry and the
windows without waiting on Bradbury. The subject model, the marking judge and
the referee are scripted in test/population.py and driven on purpose.

test/run_sdk.py runs the same scenarios against the real pinned SDK.
"""

from dataclasses import dataclass as _dataclass
import typing

__all__ = [
    "gl",
    "Address",
    "TreeMap",
    "DynArray",
    "u256",
    "bigint",
    "allow_storage",
]


def allow_storage(cls):
    return cls


def u256(v):
    v = int(v)
    if v < 0:
        raise OverflowError("u256 underflow")
    return v


bigint = int


class Address:
    def __init__(self, value):
        if isinstance(value, Address):
            value = value._v
        self._v = str(value).lower()

    @property
    def as_hex(self):
        return self._v

    def __eq__(self, other):
        return isinstance(other, Address) and other._v == self._v

    def __hash__(self):
        return hash(self._v)

    def __repr__(self):
        return "Address(%s)" % self._v


class TreeMap(dict):
    """Strict map: a missing key raises, as typed storage does."""


class DynArray(list):
    pass


class _UserError(Exception):
    pass


class _Vm:
    UserError = _UserError


class _Message:
    def __init__(self):
        self.sender_address = Address("0x" + "00" * 20)
        self.value = 0


@_dataclass
class _Response:
    status: int
    headers: dict
    body: typing.Optional[bytes]


class _Web:
    def __init__(self):
        self.handler = None
        self.calls = []

    def post(self, url, body=None, headers=None, sign=False):
        self.calls.append((url, body))
        if self.handler is None:
            raise RuntimeError("no endpoint handler installed in the stub")
        status, payload = self.handler(url, body)
        return _Response(status=status, headers={}, body=payload)

    def render(self, url, mode="text"):
        raise RuntimeError("page rendering is not used in impeach/1")


class _Nondet:
    def __init__(self):
        self.handler = None
        self.calls = []
        self.web = _Web()

    def exec_prompt(self, prompt, response_format=None):
        self.calls.append(prompt)
        if self.handler is None:
            raise RuntimeError("no model handler installed in the stub")
        return self.handler(prompt)


class _EqPrinciple:
    @staticmethod
    def prompt_comparative(fn, principle):
        return fn()

    @staticmethod
    def prompt_non_comparative(fn, task=None, criteria=None):
        return fn()

    @staticmethod
    def strict_eq(fn):
        return fn()


class _Advanced:
    def __init__(self):
        self.transfers = []

    def emit_transfer(self, to, amount):
        self.transfers.append((to, int(amount)))


class _PublicWrite:
    def __call__(self, fn):
        fn._gl_public = "write"
        return fn

    def payable(self, fn):
        fn._gl_public = "write.payable"
        return fn


class _Public:
    write = _PublicWrite()

    @staticmethod
    def view(fn):
        fn._gl_public = "view"
        return fn


class _StorageMeta(type):
    """Instantiate declared storage slots from their annotations."""

    def __call__(cls, *args, **kwargs):
        obj = cls.__new__(cls)
        for klass in reversed(cls.__mro__):
            for name, ann in getattr(klass, "__annotations__", {}).items():
                origin = typing.get_origin(ann) or ann
                if origin is TreeMap:
                    setattr(obj, name, TreeMap())
                elif origin is DynArray:
                    setattr(obj, name, DynArray())
        obj.__init__(*args, **kwargs)
        return obj


class Contract(metaclass=_StorageMeta):
    pass


class _Gl:
    Contract = Contract
    vm = _Vm()
    public = _Public()
    eq_principle = _EqPrinciple()

    def __init__(self):
        self.message = _Message()
        self.message_raw = {"datetime": "2026-10-03T12:00:00+00:00"}
        self.nondet = _Nondet()
        self.advanced = _Advanced()


gl = _Gl()
