#!/usr/bin/env python3
"""Build a smaller deployment source without changing the contract's logic.

Only comments and docstrings are omitted. The resulting AST is checked against
the original with docstrings removed, then stored in a standard-library
zlib/base85 loader. Public names, storage types, and executable statements stay
unchanged. The readable source remains contracts/impeach.py.
"""

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[1]


class WithoutDocstrings(ast.NodeTransformer):
    def visit_body(self, node):
        self.generic_visit(node)
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            node.body.pop(0)
        return node

    visit_Module = visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = visit_body


def build(source):
    header = source.splitlines()[0]
    if not header.startswith('# { "Depends":'):
        raise ValueError("source must start with its pinned GenVM dependency header")
    tree = WithoutDocstrings().visit(ast.parse(source))
    compact = ast.unparse(tree) + "\n"
    if ast.dump(tree, include_attributes=False) != ast.dump(ast.parse(compact), include_attributes=False):
        raise ValueError("compact source changed the executable AST")
    compact_bytes = compact.encode("utf-8")
    compact_sha = hashlib.sha256(compact_bytes).hexdigest()
    original_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    packed = base64.b85encode(zlib.compress(compact_bytes, 9)).decode("ascii")
    loader = (
        header + "\n"
        "import base64 as _deploy_b64, zlib as _deploy_zlib, hashlib as _deploy_hash\n"
        "_deploy_source = _deploy_zlib.decompress(_deploy_b64.b85decode(" + repr(packed) + "))\n"
        "assert _deploy_hash.sha256(_deploy_source).hexdigest() == " + repr(compact_sha) + "\n"
        "exec(compile(_deploy_source, '<impeach>', 'exec'), globals())\n"
        "del _deploy_source, _deploy_b64, _deploy_zlib, _deploy_hash\n"
    )
    return loader, compact, {"source_sha256": original_sha, "compact_sha256": compact_sha,
                             "artifact_sha256": hashlib.sha256(loader.encode()).hexdigest(),
                             "source_bytes": len(source.encode()), "compact_bytes": len(compact_bytes),
                             "artifact_bytes": len(loader.encode()),
                             "transformation": "remove comments/docstrings; AST equivalence checked; zlib + base85"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "contracts" / "impeach.py")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "impeach.py")
    args = parser.parse_args()
    loader, compact, manifest = build(args.source.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(loader, encoding="utf-8")
    args.out.with_suffix(".readable.py").write_text(compact, encoding="utf-8")
    args.out.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("%d source bytes -> %d deployment bytes: %s" %
          (manifest["source_bytes"], manifest["artifact_bytes"], args.out))


if __name__ == "__main__":
    main()
