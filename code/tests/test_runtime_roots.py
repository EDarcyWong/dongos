"""Execute production forest/paging code against an independent C raw oracle."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "tests"


def closure():
    result = {"runtime_roots_probe.dg": HERE / "runtime_roots_probe.dg"}
    pending = list(result.values())
    while pending:
        source = pending.pop()
        for module in re.findall(r"(?m)^\s*import\s+([\w.]+)", source.read_text(encoding="utf-8")):
            relative = module.replace(".", "/") + ".dg"
            if relative in result:
                continue
            matches = [p / relative for p in (ROOT / "kernel", ROOT / "lang/std")
                       if (p / relative).is_file()]
            if len(matches) != 1:
                raise AssertionError((module, matches))
            result[relative] = matches[0]
            pending.append(matches[0])
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RuntimeRootsTests(unittest.TestCase):
    def test_production_forest_and_five_real_wrong_implementations_both_modes(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        self.assertTrue(nasm and cc, "native tools are required; no skip")
        sources = closure()
        inputs = sorted(set(sources.values()) | {
            Path(__file__), HERE / "runtime_roots_probe.c", ROOT / "docs/runtime-roots.md",
            ROOT / "lang/tests/test_dongc.py",
            *list((ROOT / "lang/dongc").rglob("*.py")),
        })
        hashes = lambda: {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs}
        before = hashes()
        tool_paths = {"nasm": Path(nasm).resolve(), "cc": Path(cc).resolve()}
        tool_hashes = {name: dict(path=str(path), sha256=sha(path)) for name, path in tool_paths.items()}
        state = ROOT / "build/test/runtime-roots" / ("run-" + uuid.uuid4().hex[:12])
        state.mkdir(parents=True)
        (state / "source-before.json").write_text(json.dumps(before, indent=2) + "\n")
        (state / "tools.json").write_text(json.dumps(tool_hashes, indent=2) + "\n")
        original = (ROOT / "kernel/mm/runtime_roots.dg").read_text(encoding="utf-8")
        mutants = {
            "ignore-shared": (
                "if ((actual^expected)&~(32 as u64))!=0{return SHARED_MISMATCH;}",
                "if false&&((actual^expected)&~(32 as u64))!=0{return SHARED_MISMATCH;}",
                "shared", "shared-slot1"),
            "accept-private-foreign": (
                "if pa<(*v).physical||pa-(*v).physical>=pool_bytes{return FOREIGN;}",
                "if pa<(*v).physical||pa-(*v).physical>=pool_bytes{return OK;}",
                "foreign", "foreign-private"),
            "omit-hidden-alias": (
                "if !overlap(pa,size,physical,bytes){return OK;}",
                "if flags==0||!overlap(pa,size,physical,bytes){return OK;}",
                "hidden", "hidden-alias"),
            "ignore-hardware-width": (
                "if hardware!=0&&hardware<mask{mask=hardware;}",
                "if false&&hardware!=0&&hardware<mask{mask=hardware;}",
                "hardware-width", "hardware-leaf-width"),
            "ignore-private-width": (
                "if hardware!=0&&hardware<mask{mask=hardware;}",
                "if hardware!=0{mask=hardware;}",
                "private-width", "private-leaf-width"),
        }
        expected_cases = 2 * (1 + len(mutants))
        cases = []
        commands = []

        def run(command, directory, label, expected=0):
            command = list(map(str, command))
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
            receipt = dict(command=command, returncode=result.returncode,
                           stdout=result.stdout, stderr=result.stderr)
            (directory / (label + ".json")).write_text(json.dumps(receipt, indent=2) + "\n")
            commands.append(dict(directory=directory.relative_to(state).as_posix(), label=label, **receipt))
            self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
            return result

        try:
            for mode in ("debug", "release"):
                for mutation in (None, *mutants):
                    with self.subTest(mode=mode, mutation=mutation):
                        directory = state / mode / (mutation or "production")
                        staged = directory / "src"
                        staged.mkdir(parents=True)
                        for relative, source in sources.items():
                            target = staged / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source, target)
                        source = original
                        if mutation:
                            old, new, scenario, diagnostic = mutants[mutation]
                            self.assertEqual(1, source.count(old), "mutant must change one actual semantic boundary")
                            source = source.replace(old, new)
                            (staged / "mm/runtime_roots.dg").write_text(source, encoding="utf-8")
                            (directory / "mutation.json").write_text(json.dumps(dict(
                                source="mm/runtime_roots.dg", old=old, new=new,
                                production_sha256=hashlib.sha256(original.encode()).hexdigest(),
                                mutant_sha256=sha(staged / "mm/runtime_roots.dg")), indent=2) + "\n")
                        compiled = compile_file(staged / "runtime_roots_probe.dg", roots=[staged], mode=mode)
                        layouts = {item["full_name"]: item for item in compiled.layout_manifest["types"]}
                        workspace = layouts["mm.runtime_roots.Scratch"]
                        self.assertEqual((5056, 64), (workspace["size"], workspace["alignment"]))
                        self.assertEqual([(0, 4096), (4096, 952)],
                                         [(field["offset"], field["size"]) for field in workspace["fields"]])
                        (directory / "compilation.json").write_text(json.dumps(dict(
                            api="lang.dongc.compile_file", source=str(staged / "runtime_roots_probe.dg"),
                            roots=[str(staged)], mode=mode,
                            caller_owned_scratch=workspace,
                            staged_inputs={relative: sha(staged / relative) for relative in sorted(sources)},
                            production_inputs=before), indent=2) + "\n")
                        (directory / "layout.json").write_text(json.dumps(compiled.layout_manifest, indent=2) + "\n")
                        assembly = directory / "probe.asm"
                        assembly.write_text(compiled.assembly)
                        objects = {}
                        for fmt in ("elf64", "win64"):
                            obj = directory / (fmt + ".o")
                            run([nasm, "-f", fmt, *nasm_flags(nasm), assembly, "-o", obj], directory, fmt)
                            objects[fmt] = obj
                        executable = directory / ("probe.exe" if os.name == "nt" else "probe")
                        run([cc, "-std=c11", "-O2", "-D__USE_MINGW_ANSI_STDIO=1", "-Wall", "-Wextra", "-Werror",
                             *(["-mno-sse"] if os.name == "nt" else ["-no-pie"]),
                             HERE / "runtime_roots_probe.c", objects["win64" if os.name == "nt" else "elf64"],
                             "-o", executable], directory, "link")
                        result = run([executable, scenario if mutation else "all"], directory, "execute", 1 if mutation else 0)
                        if mutation:
                            self.assertIn("roots oracle: " + diagnostic, result.stderr)
                            self.assertIn("normally", result.stderr)
                        else:
                            self.assertIn("runtime roots raw oracle checks=", result.stdout)
                            self.assertIn("privileged instructions not executed", result.stdout)
                            self.assertIn("widths=36,40,46,52 private48; canonical52 shared-high passed", result.stdout)
                        cases.append(dict(mode=mode, mutation=mutation,
                                          actual_source_sha256=sha(staged / "mm/runtime_roots.dg"),
                                          scratch_bytes=workspace["size"], scratch_alignment=workspace["alignment"],
                                          hardware_widths=[36, 40, 46, 52] if mutation is None else [],
                                          private_width=48, canonical_high_shared=mutation is None,
                                          elf_sha256=sha(objects["elf64"]), coff_sha256=sha(objects["win64"]),
                                          executable_sha256=sha(executable), normally_exited=True))
                        self.assertEqual(before, hashes(), "production inputs must remain frozen")
        finally:
            after = hashes()
            tools_stable = all(sha(path) == tool_hashes[name]["sha256"] for name, path in tool_paths.items())
            (state / "source-after.json").write_text(json.dumps(after, indent=2) + "\n")
            (state / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
            (state / "result.json").write_text(json.dumps(dict(
                passed=len(cases) == expected_cases and before == after and tools_stable,
                expected_cases=expected_cases, cases=cases,
                source_stable=before == after, source_before=before, source_after=after,
                tools_stable=tools_stable, tools=tool_hashes, guest_started=False), indent=2) + "\n")
        self.assertEqual(expected_cases, len(cases))
        self.assertEqual(before, hashes())
        self.assertTrue(tools_stable)
        print("runtime roots native evidence", state)


if __name__ == "__main__":
    unittest.main()
