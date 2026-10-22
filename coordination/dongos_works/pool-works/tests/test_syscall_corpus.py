"""Strict tests for the deterministic syscall/IPC corpus tool (P9CORPUS1).

The tool is driven both as a library and as a real CLI subprocess. The oracle
implementation below is an independent restatement of the dispatcher checks in
`code/` (it does not call the tool's classifier), so a wrong boundary rule in
the tool fails here instead of agreeing with itself.

No test skips: every check either passes or fails.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import uuid

WORKS = Path(__file__).resolve().parents[2]
TOOL = WORKS / "pool-works/p9-corpus/tools/syscall_corpus.py"


def _source_root(works):
    """Locate the DongOS sources in the works root and in the verifier copy.

    The verifier copy flattens the `code/` tree at the copy root next to the
    mounted `pool-works/` and has no `project.json`; the real works root has no
    top-level `lang/`+`kernel/` pair and resolves `source_root` from the
    project configuration.
    """
    if (works / "lang").is_dir() and (works / "kernel").is_dir():
        return works
    project = works / "project.json"
    if project.is_file():
        data = json.loads(project.read_text(encoding="utf-8-sig"))
        root = Path(data["source_root"])
        return (root if root.is_absolute() else (works / root)).resolve()
    fallback = works / "code/kernel"
    if fallback.is_dir():
        return (works / "code").resolve()
    raise RuntimeError("cannot locate the DongOS sources from %s" % works)


SOURCE = _source_root(WORKS)
PYTHON = sys.executable
TEMP_ROOT = Path(tempfile.gettempdir())


def unique_file(name="corpus.jsonl"):
    """A fresh file directly under the platform temp root (no subdirectories)."""
    return TEMP_ROOT / ("p9corpus-" + uuid.uuid4().hex + "-" + name)

_spec = importlib.util.spec_from_file_location("syscall_corpus_under_test", TOOL)
corpus = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(corpus)

# Independent constants, read from the kernel sources by hand.
USER_MIN = 0x1_0000
USER_LIMIT = 0x0000_0080_0000_0000
MESSAGE_BYTES = 64
LOG_MAX = 4096
MAX_GENERATION = 0x00ff_ffff_ffff_ffff
CODE_INVALID_CALL = 0x050b0001
CODE_PROTOCOL = 0x050b0002
CODE_INVALID_ADDRESS = 0x04060003
CODE_INVALID_HANDLE = 0x04010002


def dumps(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def independent_oracle(operation, registers, requires):
    """Independent model of the documented argument-shape contract.

    `accepted_shape` deliberately does not claim a successful syscall: it means
    the shape checks pass under the declared mapping/peer preconditions.
    """
    if operation == "syscall.unknown":
        return "invalid_call", CODE_INVALID_CALL
    if operation == "syscall.log":
        address, length = registers["rdi"], registers["rsi"]
        if length > LOG_MAX:  # services.dg:1058
            return "protocol", CODE_PROTOCOL
        if (address < USER_MIN or address >= USER_LIMIT
                or length > USER_LIMIT - address):  # memory.dg:704-707
            return "invalid_address", CODE_INVALID_ADDRESS
        if length == 0:  # copy_in no-op + services_write_bytes(ptr,0)==0
            return "ok", None
        raise AssertionError("in-range non-empty log copy is not decidable")
    handle = registers["rdi"]
    slot, generation = handle & 0xFF, handle >> 8
    if (slot == 0 or slot > 32 or generation == 0
            or generation == MAX_GENERATION):  # handles.dg:22,56-82
        return "invalid_handle", CODE_INVALID_HANDLE
    if requires == "absent_handle_entry":
        return "invalid_handle", CODE_INVALID_HANDLE
    assert operation == "syscall.call"
    assert requires in ("live_endpoint", "live_endpoint_write", "live_endpoint_rw")

    def span_in_range(address):
        return (USER_MIN <= address < USER_LIMIT
                and MESSAGE_BYTES <= USER_LIMIT - address)

    response, request = registers["rdx"], registers["rsi"]
    if not span_in_range(response):  # services.dg:885, before copy_in(rsi)
        assert requires == "live_endpoint"
        return "invalid_address", CODE_INVALID_ADDRESS
    assert requires in ("live_endpoint_write", "live_endpoint_rw")
    if not span_in_range(request):
        assert requires == "live_endpoint_write"
        return "invalid_address", CODE_INVALID_ADDRESS
    assert requires == "live_endpoint_rw"
    return "accepted_shape", None


def regs(rax, rdi=0, rsi=0, rdx=0, r10=0, r8=0, r9=0):
    return {"rax": rax, "rdi": rdi, "rsi": rsi, "rdx": rdx,
            "r10": r10, "r8": r8, "r9": r9}


def lines_of(data):
    return data.decode("ascii").split("\n")[:-1]


def payload(lines):
    return ("\n".join(lines) + "\n").encode("ascii")


def load_case(lines, offset):
    return json.loads(lines[offset])


def find_offset(lines, predicate):
    for offset in range(1, len(lines)):
        if predicate(load_case(lines, offset)):
            return offset
    raise AssertionError("no case matched the predicate")


class CorpusCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed = 7
        cls.count = 48
        cls.data = corpus.generate(cls.seed, cls.count)
        cls.header, cls.records = corpus.verify_bytes(cls.data)

    def edited(self, mutate):
        lines = lines_of(self.data)
        mutate(lines, self)
        return payload(lines)

    def assert_rejected(self, data, fragment):
        with self.assertRaises(corpus.CorpusError) as caught:
            corpus.verify_bytes(data)
        self.assertIn(fragment, str(caught.exception))


class DeterminismTests(CorpusCase):
    def test_in_process_prefix_and_roundtrip(self):
        seeds = [0, 1, 0x2A, 0xDEADBEEF, corpus.MASK64]
        counts = [0, 1, 5, 31, 200]
        for seed in seeds:
            produced = {}
            for count in counts:
                data = corpus.generate(seed, count)
                header, records = corpus.verify_bytes(data)
                self.assertEqual(len(records), count)
                self.assertEqual(header["seed"], str(seed))
                self.assertEqual(header["origin"], "generated")
                self.assertEqual(data, corpus.generate(seed, count))
                produced[count] = lines_of(data)[1:]
            for small, large in zip(counts, counts[1:]):
                self.assertEqual(produced[small], produced[large][:len(produced[small])],
                                 "case lines must be prefix-stable in count")

    def test_cli_runs_are_byte_identical(self):
        first = unique_file("a.jsonl")
        second = unique_file("b.jsonl")
        self.addCleanup(first.unlink, missing_ok=True)
        self.addCleanup(second.unlink, missing_ok=True)
        for target in (first, second):
            run = subprocess.run(
                [PYTHON, str(TOOL), "generate", "--seed", "0x2a",
                 "--count", "64", "--out", str(target)],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("sha256=", run.stdout)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first.read_bytes(), corpus.generate(0x2A, 64))
        self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(),
                         hashlib.sha256(second.read_bytes()).hexdigest())

    def test_cli_generate_verify_regenerate(self):
        path = unique_file("c.jsonl")
        self.addCleanup(path.unlink, missing_ok=True)
        gen = subprocess.run(
            [PYTHON, str(TOOL), "generate", "--seed", "123456789",
             "--count", "96", "--out", str(path)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(gen.returncode, 0, gen.stderr)
        verify = subprocess.run([PYTHON, str(TOOL), "verify", str(path)],
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertIn("verified cases=96", verify.stdout)
        first_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertIn(first_sha, verify.stdout)
        regen = subprocess.run(
            [PYTHON, str(TOOL), "generate", "--seed", "123456789",
             "--count", "96", "--out", str(path)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(regen.returncode, 0, regen.stderr)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), first_sha)


class StrictParserTests(CorpusCase):
    def test_reject_empty_or_truncated(self):
        self.assert_rejected(b"", "empty")
        self.assert_rejected(self.data[:-1], "end with a newline")
        self.assert_rejected(self.data + b"\n", "blank line")
        self.assert_rejected(self.data[:-1] + b"x\n", "invalid JSON")

    def test_reject_bom_and_crlf(self):
        self.assert_rejected(b"\xef\xbb\xbf" + self.data, "BOM")
        self.assert_rejected(self.data.replace(b"\n", b"\r\n"), "LF line endings")

    def test_reject_header_drift(self):
        for key, value, fragment in (
                ("format", "other-format", "header format"),
                ("version", 2, "header version"),
                ("kind", "row", "must be the header"),
                ("origin", "copied", "header origin")):
            def mutate(lines, owner, key=key, value=value):
                header = json.loads(lines[0])
                header[key] = value
                lines[0] = dumps(header)
            self.assert_rejected(self.edited(mutate), fragment)
        def count_high(lines, owner):
            header = json.loads(lines[0])
            header["count"] = str(corpus.MAX_COUNT + 1)
            lines[0] = dumps(header)
        self.assert_rejected(self.edited(count_high), "header count exceeds")
        def count_short(lines, owner):
            header = json.loads(lines[0])
            header["count"] = str(int(header["count"]) - 1)
            lines[0] = dumps(header)
        self.assert_rejected(self.edited(count_short), "declares")
        def minimized_without_source(lines, owner):
            header = json.loads(lines[0])
            header["origin"] = "minimized"
            header.pop("minimized_from", None)
            lines[0] = dumps(header)
        self.assert_rejected(self.edited(minimized_without_source), "header fields mismatch")
        def two_headers(lines, owner):
            lines.insert(1, lines[0])
        self.assert_rejected(self.edited(two_headers), "declares")
        def header_last(lines, owner):
            lines.insert(len(lines), lines.pop(0))
        self.assert_rejected(self.edited(header_last), "must be the header")

    def test_reject_duplicate_fields(self):
        def duplicate_kind(lines, owner):
            lines[1] = lines[1].replace('{"kind":"case",',
                                        '{"kind":"case","kind":"case",', 1)
            owner.assertIn('"kind":"case","kind":"case"', lines[1])
        self.assert_rejected(self.edited(duplicate_kind), "duplicate field")

    def test_reject_case_field_errors(self):
        def missing(lines, owner):
            case = json.loads(lines[1])
            del case["requires"]
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(missing), "missing=['requires']")
        def extra(lines, owner):
            case = json.loads(lines[1])
            case["note"] = "x"
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(extra), "extra=['note']")
        def wrong_kind(lines, owner):
            case = json.loads(lines[1])
            case["kind"] = "row"
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(wrong_kind), "not a case")
        def bad_version(lines, owner):
            case = json.loads(lines[1])
            case["version"] = 2
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(bad_version), "case version")
        def bad_seed(lines, owner):
            case = json.loads(lines[1])
            case["seed"] = str(int(case["seed"]) + 1)
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(bad_seed), "case seed")
        def bad_index(lines, owner):
            case = json.loads(lines[1])
            case["index"] = "999"
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(bad_index), "case index")
        def bad_operation(lines, owner):
            case = json.loads(lines[1])
            case["operation"] = "syscall.nope"
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(bad_operation), "unknown operation")
        def bad_oracle_class(lines, owner):
            case = json.loads(lines[1])
            case["oracle"]["class"] = "maybe"
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(bad_oracle_class), "unknown oracle class")
        def bad_oracle_code(lines, owner):
            case = json.loads(lines[1])
            case["oracle"]["code"] = "0x12"
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(bad_oracle_code), "oracle code")
        def bad_requires(lines, owner):
            case = json.loads(lines[1])
            case["requires"] = "sometimes"
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(bad_requires), "unknown requires")

    def test_reject_number_spelling(self):
        for value, fragment in (
                (112, "canonical decimal u64 string"),
                ("-1", "canonical decimal u64 string"),
                ("0112", "canonical decimal u64 string"),
                ("1.5", "canonical decimal u64 string"),
                (str(2 ** 64), "exceeds 2^64-1")):
            def mutate(lines, owner, value=value):
                case = json.loads(lines[1])
                case["registers"]["rax"] = value
                lines[1] = dumps(case)
            self.assert_rejected(self.edited(mutate), fragment)

    def test_reject_non_finite_number(self):
        def mutate(lines, owner):
            case = json.loads(lines[1])
            case["requires"] = float("nan")
            lines[1] = dumps(case)
            owner.assertIn("NaN", lines[1])
        self.assert_rejected(self.edited(mutate), "non-finite number")

    def test_reject_oversized_line(self):
        def mutate(lines, owner):
            case = json.loads(lines[1])
            case["abi"]["source"] = "x" * (corpus.MAX_LINE + 8)
            lines[1] = dumps(case)
        self.assert_rejected(self.edited(mutate), "line exceeds")

    def test_reject_non_object_record(self):
        lines = lines_of(self.data)
        lines[1] = "[]"
        self.assert_rejected(payload(lines), "not a JSON object")

    def test_reject_recognised_number_in_unknown_probe(self):
        def mutate(lines, owner):
            offset = find_offset(lines, lambda case: case["operation"] == "syscall.unknown")
            case = json.loads(lines[offset])
            case["syscall"] = "34"
            case["registers"]["rax"] = "34"
            lines[offset] = dumps(case)
        self.assert_rejected(self.edited(mutate), "recognised number")

    def test_reject_inconsistent_requires(self):
        def mutate(lines, owner):
            offset = find_offset(lines, lambda case: case["operation"] == "syscall.log")
            case = json.loads(lines[offset])
            case["requires"] = "live_endpoint"
            lines[offset] = dumps(case)
        self.assert_rejected(self.edited(mutate), "not valid for syscall.log")

    def test_reject_message_shape(self):
        def short_message(lines, owner):
            offset = find_offset(lines, lambda case: case["message"] is not None)
            case = json.loads(lines[offset])
            case["message"] = case["message"][:7]
            lines[offset] = dumps(case)
        self.assert_rejected(self.edited(short_message), "8 u64 words")
        def message_on_log(lines, owner):
            offset = find_offset(lines, lambda case: case["operation"] == "syscall.log")
            case = json.loads(lines[offset])
            case["message"] = ["0"] * 8
            lines[offset] = dumps(case)
        self.assert_rejected(self.edited(message_on_log), "only valid for CALL")

    def test_reject_oracle_and_abi_drift(self):
        def oracle(lines, owner):
            offset = find_offset(lines, lambda case: case["oracle"]["class"] != "protocol")
            case = json.loads(lines[offset])
            case["oracle"]["class"] = "protocol"
            case["oracle"]["code"] = "0x050b0002"
            lines[offset] = dumps(case)
        self.assert_rejected(self.edited(oracle), "oracle class")
        def abi(lines, owner):
            offset = find_offset(lines, lambda case: case["operation"] != "syscall.unknown")
            case = json.loads(lines[offset])
            case["abi"]["source"] = "invented:1-2"
            lines[offset] = dumps(case)
        self.assert_rejected(self.edited(abi), "abi summary drift")
        def duplicate_index(lines, owner):
            case = json.loads(lines[2])
            case["index"] = json.loads(lines[1])["index"]
            lines[2] = dumps(case)
        self.assert_rejected(self.edited(duplicate_index), "case index")

    def test_reject_syscall_register_mismatch(self):
        def known(lines, owner):
            offset = find_offset(lines, lambda case: case["operation"] == "syscall.log")
            case = json.loads(lines[offset])
            case["registers"]["rax"] = str(int(case["registers"]["rax"]) + 1)
            lines[offset] = dumps(case)
        self.assert_rejected(self.edited(known), "registers.rax must equal")
        def unknown(lines, owner):
            offset = find_offset(lines, lambda case: case["operation"] == "syscall.unknown")
            case = json.loads(lines[offset])
            original = int(case["registers"]["rax"])
            case["syscall"] = "0" if original != 0 else "63"
            lines[offset] = dumps(case)
        self.assert_rejected(self.edited(unknown), "registers.rax must equal")

    def test_reject_boolean_or_float_version(self):
        for value in (True, 1.0):
            def header(lines, owner, value=value):
                record = json.loads(lines[0])
                record["version"] = value
                lines[0] = dumps(record)
            self.assert_rejected(self.edited(header), "header version must be the integer")
        for value in (True, 1.0):
            def case(lines, owner, value=value):
                record = json.loads(lines[1])
                record["version"] = value
                lines[1] = dumps(record)
            self.assert_rejected(self.edited(case), "case version must be the integer")

    def test_reject_deep_json_as_corpus_error(self):
        nested = "[" * 995 + "]" * 995
        self.assertLessEqual(len(nested), corpus.MAX_LINE)
        header = lines_of(corpus.generate(1, 1))[0]
        with self.assertRaises(corpus.CorpusError) as caught:
            corpus.verify_bytes(payload([header, nested]))
        self.assertIn("nesting depth exceeds", str(caught.exception))

    def test_cli_deep_json_has_no_traceback(self):
        nested = "[" * 995 + "]" * 995
        header = lines_of(corpus.generate(1, 1))[0]
        path = unique_file("deep.jsonl")
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_bytes(payload([header, nested]))
        run = subprocess.run([PYTHON, str(TOOL), "verify", str(path)],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
        self.assertIn("error:", run.stderr)
        self.assertIn("nesting depth exceeds", run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        self.assertNotIn("Traceback", run.stdout)


class IndependentOracleTests(CorpusCase):
    def test_log_boundary_matrix(self):
        matrix = [
            (0, 0), (0, 1), (USER_MIN - 1, 0), (USER_MIN - 1, 1),
            (USER_MIN, 0), (USER_MIN, LOG_MAX + 1), (USER_LIMIT - 1, 0),
            (USER_LIMIT - 1, 2), (USER_LIMIT, 0), (USER_LIMIT, 1),
            (0x0000_8000_0000_0000, 0), (0xFFFF_0000_0000_0000, 0),
            (0x7FFF_FFFF_FFFF_FFFF, 0), (0, LOG_MAX + 1), (corpus.MASK64, 0),
            (USER_LIMIT - 1, LOG_MAX),
        ]
        for address, length in matrix:
            registers = regs(0x70, address, length)
            expected = independent_oracle("syscall.log", registers, "none")
            self.assertEqual(corpus.classify("syscall.log", registers, None, "none"),
                             expected, (address, length))
        for address, length in ((USER_MIN, 1), (USER_LIMIT - 1, 1),
                                (USER_MIN + 0x1000, LOG_MAX)):
            with self.assertRaises(ValueError):
                corpus.classify("syscall.log", regs(0x70, address, length), None, "none")

    def test_unknown_numbers(self):
        for number in (0, 0x3F, 0x8B, 0x9A, 0xBF, 0x100, 0xFFFF,
                       0x7FFF_FFFF_FFFF_FFFF, corpus.MASK64):
            self.assertEqual(
                corpus.classify("syscall.unknown", regs(number), None, "none"),
                independent_oracle("syscall.unknown", regs(number), "none"))
            self.assertEqual(corpus.abi_summary("syscall.unknown", number)["name"],
                             "unknown")

    def test_unknown_probes_are_unambiguous(self):
        for number in corpus.UNKNOWN_FIXED:
            self.assertNotIn(number, corpus.DISPATCH)
            self.assertNotIn(number, corpus.LEGACY)
        for number in (0x30, 0x31, 0x40):
            self.assertNotIn(number, corpus.DISPATCH)
            self.assertIn(number, corpus.LEGACY)

    def test_handle_matrix(self):
        samples = [
            ("syscall.close", 0x00, "none"),
            ("syscall.close", 0x01, "none"),
            ("syscall.duplicate", 0x0100, "none"),
            ("syscall.receive", 0x21, "none"),
            ("syscall.take_call", 0x2021, "none"),
            ("syscall.reply", 0xFFFF, "none"),
            ("syscall.reply_wait", 0xFFFF_FFFF_FFFF_FF01, "none"),
            ("syscall.call", 0xFFFF_FFFF_FFFF_FF20, "none"),
            ("syscall.close", 0x0101, "absent_handle_entry"),
            ("syscall.call", 0x0102, "absent_handle_entry"),
            ("syscall.call", 0xFFFF_FFFF_FFFF_FE01, "absent_handle_entry"),
        ]
        for operation, handle, requires in samples:
            registers = regs(corpus.OPERATIONS[operation], handle)
            self.assertEqual(corpus.classify(operation, registers, None, requires),
                             independent_oracle(operation, registers, requires),
                             (operation, hex(handle), requires))
        with self.assertRaises(ValueError):
            corpus.classify("syscall.close", regs(0x10, 0x0101), None, "none")

    def test_call_pointer_matrix(self):
        cases = [
            # response out of range: decided before any mapping is touched
            (0, USER_MIN, "live_endpoint", "invalid_address", CODE_INVALID_ADDRESS),
            (USER_LIMIT, USER_MIN, "live_endpoint", "invalid_address", CODE_INVALID_ADDRESS),
            (USER_LIMIT - 63, USER_MIN, "live_endpoint", "invalid_address",
             CODE_INVALID_ADDRESS),
            # response mapped writable precondition: request range is decidable
            (USER_MIN, 0, "live_endpoint_write", "invalid_address", CODE_INVALID_ADDRESS),
            (USER_MIN, USER_LIMIT, "live_endpoint_write", "invalid_address",
             CODE_INVALID_ADDRESS),
            # both spans in range and mapped: only shape-pass is asserted
            (USER_MIN, USER_MIN, "live_endpoint_rw", "accepted_shape", None),
            (USER_LIMIT - 64, USER_LIMIT - 64, "live_endpoint_rw", "accepted_shape", None),
        ]
        for response, request, requires, expected_class, expected_code in cases:
            registers = regs(0x22, 0x0101, request, response)
            self.assertEqual(corpus.classify("syscall.call", registers, None, requires),
                             (expected_class, expected_code),
                             (hex(request), hex(response), requires))
            self.assertEqual(corpus.classify("syscall.call", registers, None, requires),
                             independent_oracle("syscall.call", registers, requires))
        # An undeclared mapping precondition must never be guessed.
        both_valid = regs(0x22, 0x0101, USER_MIN, USER_MIN)
        with self.assertRaises(ValueError):
            corpus.classify("syscall.call", both_valid, None, "live_endpoint")
        with self.assertRaises(ValueError):
            corpus.classify("syscall.call", both_valid, None, "live_endpoint_write")
        # Declared preconditions that are physically impossible are rejected.
        with self.assertRaises(ValueError):
            corpus.classify("syscall.call", regs(0x22, 0x0101, 0, USER_MIN),
                            None, "live_endpoint_rw")
        with self.assertRaises(ValueError):
            corpus.classify("syscall.call", regs(0x22, 0x0101, USER_MIN, 0),
                            None, "live_endpoint_write")

    def test_generated_records_match_independent_oracle(self):
        for seed in (0, 3, 0x2A, 0xDEADBEEF):
            _, records = corpus.verify_bytes(corpus.generate(seed, 300))
            for record in records:
                values = {name: int(record["registers"][name])
                          for name in corpus.REGISTERS}
                message = record["message"]
                message_values = None if message is None else [int(w) for w in message]
                expected = independent_oracle(record["operation"], values,
                                              record["requires"])
                expected_text = None if expected[1] is None else "0x%08x" % expected[1]
                self.assertEqual(record["oracle"],
                                 {"class": expected[0], "code": expected_text},
                                 record["index"])

    def test_corpus_covers_every_oracle_class(self):
        classes = set()
        for seed in (0, 1, 0x2A):
            _, records = corpus.verify_bytes(corpus.generate(seed, 300))
            classes.update(record["oracle"]["class"] for record in records)
        self.assertEqual(classes, {"invalid_call", "protocol", "invalid_address",
                                   "invalid_handle", "accepted_shape", "ok"})

    def test_shape_pass_is_never_reported_as_success(self):
        _, records = corpus.verify_bytes(corpus.generate(0, 400))
        for record in records:
            if record["operation"] != "syscall.call":
                continue
            self.assertIn(record["oracle"]["class"],
                          {"invalid_handle", "invalid_address", "accepted_shape"},
                          record["index"])
            if record["requires"] == "live_endpoint_rw":
                self.assertEqual(record["oracle"]["class"], "accepted_shape")
                self.assertIsNone(record["oracle"]["code"])


class MessageTests(CorpusCase):
    def test_message_matrix_boundaries(self):
        matrix = set(corpus.MESSAGE_MATRIX)
        self.assertIn((0,) * 8, matrix)
        self.assertIn((corpus.MASK64,) * 8, matrix)
        self.assertIn((0x400, 1, 2, 3, 4, 5, 6, 7), matrix)
        self.assertEqual(corpus.DISPATCH[0x22].message_bytes, MESSAGE_BYTES)

    def test_generated_message_records_are_exact(self):
        _, records = corpus.verify_bytes(corpus.generate(0, 400))
        messages = [tuple(int(word) for word in record["message"])
                    for record in records if record["message"] is not None]
        self.assertGreaterEqual(len(messages), 20)
        matrix = set(corpus.MESSAGE_MATRIX)
        self.assertGreaterEqual(sum(1 for message in messages if message in matrix), 3)
        self.assertGreater(len(set(messages)), 4)
        for record in records:
            if record["message"] is None:
                continue
            self.assertEqual(record["operation"], "syscall.call")
            self.assertEqual(record["requires"], "live_endpoint_rw")
            self.assertEqual(record["oracle"]["class"], "accepted_shape")
            self.assertIsNone(record["oracle"]["code"])
            self.assertEqual(record["abi"]["message_bytes"], "64")
            self.assertEqual(json.loads(dumps(record)), record)

    def test_message_round_trip_is_byte_exact(self):
        data = corpus.generate(11, 120)
        header, records = corpus.verify_bytes(data)
        rebuilt = payload([dumps(header)] + [dumps(record) for record in records])
        self.assertEqual(rebuilt, data)


class MinimizeTests(CorpusCase):
    def test_minimize_bounded_and_same_operation(self):
        source = unique_file("src.jsonl")
        self.addCleanup(source.unlink, missing_ok=True)
        source.write_bytes(corpus.generate(5, 64))
        _, records = corpus.verify_bytes(source.read_bytes())
        target = next(record for record in records
                      if any(int(value) for value in
                             list(record["registers"].values())[1:]))
        produced = corpus.minimize(target, 4)
        header, candidates = corpus.verify_bytes(produced)
        self.assertEqual(header["origin"], "minimized")
        self.assertEqual(header["minimized_from"], target["index"])
        self.assertLessEqual(len(candidates), 4)
        self.assertGreaterEqual(len(candidates), 1)
        for candidate in candidates:
            self.assertEqual(candidate["operation"], target["operation"])
            self.assertEqual(candidate["syscall"], target["syscall"])

    def test_minimize_preserves_operation_and_reduces_values(self):
        def candidate_oracle(candidate):
            values = {name: int(candidate["registers"][name])
                      for name in corpus.REGISTERS}
            oracle_class, code = independent_oracle(candidate["operation"], values,
                                                    candidate["requires"])
            return {"class": oracle_class,
                    "code": None if code is None else "0x%08x" % code}

        _, records = corpus.verify_bytes(corpus.generate(9, 200))
        tested = 0
        for record in records:
            values = [int(record["registers"][name]) for name in corpus.REGISTERS]
            if not any(values[1:]):
                continue
            produced = corpus.minimize(record, 8)
            header, candidates = corpus.verify_bytes(produced)
            self.assertLessEqual(len(candidates), 8)
            self.assertEqual(header["seed"], record["seed"])
            for candidate in candidates:
                self.assertEqual(candidate["operation"], record["operation"])
                self.assertEqual(candidate["syscall"], record["syscall"])
                for name in corpus.REGISTERS:
                    self.assertLessEqual(int(candidate["registers"][name]),
                                         int(record["registers"][name]))
                self.assertEqual(candidate["oracle"], candidate_oracle(candidate))
            tested += 1
            if tested == 12:
                break
        self.assertEqual(tested, 12)

    def test_minimize_header_and_cli(self):
        source = unique_file("src.jsonl")
        out = unique_file("min.jsonl")
        self.addCleanup(source.unlink, missing_ok=True)
        self.addCleanup(out.unlink, missing_ok=True)
        source.write_bytes(corpus.generate(21, 32))
        run = subprocess.run(
            [PYTHON, str(TOOL), "minimize", str(source), "--index", "2",
             "--limit", "5", "--out", str(out)],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("candidates=", run.stdout)
        header, candidates = corpus.verify_bytes(out.read_bytes())
        self.assertEqual(header["origin"], "minimized")
        self.assertEqual(header["minimized_from"], "2")
        self.assertLessEqual(len(candidates), 5)
        source_before = source.read_bytes()
        corpus.verify_bytes(source_before)
        self.assertEqual(source.read_bytes(), source_before)

    def test_minimize_rejects_tampered_or_invalid_input(self):
        with self.assertRaises(corpus.CorpusError):
            corpus.minimize({"kind": "case"}, 4)
        _, records = corpus.verify_bytes(corpus.generate(4, 16))
        broken = dict(records[0])
        if broken["oracle"]["class"] == "protocol":
            broken["oracle"] = {"class": "invalid_call", "code": "0x050b0001"}
        else:
            broken["oracle"] = {"class": "protocol", "code": "0x050b0002"}
        with self.assertRaises(corpus.CorpusError):
            corpus.minimize(broken, 4)
        bad_rax = dict(records[0])
        bad_rax["registers"] = dict(records[0]["registers"])
        bad_rax["registers"]["rax"] = str(int(records[0]["registers"]["rax"]) + 1)
        with self.assertRaises(corpus.CorpusError):
            corpus.minimize(bad_rax, 4)
        with self.assertRaises(corpus.CorpusError):
            corpus.minimize(records[0], 0)
        with self.assertRaises(corpus.CorpusError):
            corpus.minimize(records[0], corpus.MAX_MINIMIZE + 1)


class LimitTests(unittest.TestCase):
    def test_bounded_read_preflight(self):
        path = unique_file("bounded.bin")
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_bytes(b"x" * 100)
        with self.assertRaises(corpus.CorpusError) as caught:
            corpus.read_bounded(path, 16)
        self.assertIn("exceeds the bounded size", str(caught.exception))
        self.assertEqual(corpus.read_bounded(path, 100), b"x" * 100)
        with self.assertRaises(corpus.CorpusError):
            corpus.read_bounded(path, 99)
        with self.assertRaises(corpus.CorpusError):
            corpus.read_bounded(path, -1)

    def test_generate_argument_bounds(self):
        for seed in (-1, corpus.MASK64 + 1, 1.5, "1"):
            with self.assertRaises(corpus.CorpusError):
                corpus.generate(seed, 4)
        for count in (-1, corpus.MAX_COUNT + 1, 1.5, "4"):
            with self.assertRaises(corpus.CorpusError):
                corpus.generate(1, count)
        self.assertEqual(corpus.generate(0, 0),
                         corpus.generate(0, 0))

    def test_cli_rejects_bad_arguments(self):
        path = unique_file("x.jsonl")
        self.addCleanup(path.unlink, missing_ok=True)
        for argv, fragment in (
                (["generate", "--seed", "not-a-number", "--count", "4",
                  "--out", str(path)], "seed must be"),
                (["generate", "--seed", "1", "--count", "-1",
                  "--out", str(path)], "count must be"),
                (["generate", "--seed", "1", "--count", "100001",
                  "--out", str(path)], "count must be")):
            run = subprocess.run([PYTHON, str(TOOL)] + argv,
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
            self.assertIn("error:", run.stderr)
            self.assertIn(fragment, run.stderr)

    def test_cli_verify_reports_line(self):
        path = unique_file("bad.jsonl")
        self.addCleanup(path.unlink, missing_ok=True)
        lines = lines_of(corpus.generate(2, 8))
        offset = find_offset(lines, lambda case: case["requires"] == "none")
        case = json.loads(lines[offset])
        case["requires"] = "sometimes"
        lines[offset] = dumps(case)
        path.write_bytes(payload(lines))
        run = subprocess.run([PYTHON, str(TOOL), "verify", str(path)],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 3)
        self.assertIn("line %d:" % (offset + 1), run.stderr)
        self.assertIn("unknown requires", run.stderr)


class SourceIntegrityTests(unittest.TestCase):
    def test_source_root_matches_the_active_layout(self):
        layout = Path(__file__).resolve().parents[2]
        self.assertTrue((layout / "pool-works").is_dir())
        self.assertTrue(TOOL.is_file())
        self.assertTrue((SOURCE / "kernel/user/services.dg").is_file())
        # Flattened verifier copy: lang/ and kernel/ live beside pool-works/
        # and SOURCE is the copy root itself. Real works root: no top-level
        # lang/+kernel/, so SOURCE comes from project.json's source_root.
        flat = (layout / "lang").is_dir() and (layout / "kernel").is_dir()
        self.assertEqual(flat, SOURCE == layout.resolve())
        if not flat:
            self.assertTrue((layout / "project.json").is_file())

    def compact(self, relative):
        text = (SOURCE / relative).read_text(encoding="utf-8")
        return re.sub(r"\s+", "", text)

    def constants(self, relative):
        text = (SOURCE / relative).read_text(encoding="utf-8")
        found = {}
        for match in re.finditer(
                r"pub\s+const\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*u64\s*=\s*"
                r"(0x[0-9a-fA-F_]+)\s*;", text):
            found[match.group(1)] = int(match.group(2).replace("_", ""), 16)
        return found

    def test_frozen_abi_matches_source_constants(self):
        expected = {
            "services/lib/process_abi.dg": {
                "CONFIG": 0x80, "SPAWN": 0x81, "WAIT": 0x82, "KILL": 0x83,
                "MARK_READY": 0x84, "EXEC": 0x85, "INCARNATION": 0x86,
                "RUNTIME": 0x87, "RESTART_SERVICE": 0x88},
            "services/lib/device_abi.dg": {
                "ENUMERATE": 0x90, "BIND": 0x91, "IRQ_BIND": 0x92,
                "IRQ_WAIT": 0x93, "IRQ_ACK": 0x94, "REVOKE": 0x95,
                "PCI_IRQ_BIND": 0x96},
            "services/lib/cap_notify_abi.dg": {
                "CREATE": 0xB0, "SIGNAL": 0xB1, "TAKE": 0xB2,
                "CALL_CAP": 0xB3, "CLAIM": 0xB4, "EXPORT_ENDPOINT": 0xB5},
            "services/lib/shared_abi.dg": {
                "CREATE": 0xB6, "MAP": 0xB7, "UNMAP": 0xB8, "INFO": 0xB9},
            "services/lib/window_broker_abi.dg": {
                "ALLOCATE": 0xA0, "REVOKE": 0xA1, "FONT": 0xA2, "PEER": 0xA3},
            "services/lib/pci_inventory_abi.dg": {"ENUMERATE": 0x97},
        }
        for relative, wanted in expected.items():
            constants = self.constants(relative)
            for name, number in wanted.items():
                self.assertEqual(constants.get(name), number, (relative, name))
                self.assertIn(number, corpus.DISPATCH, (relative, name))
        elf = self.constants("kernel/exec/elf.dg")
        self.assertEqual(elf.get("USER_MIN"), corpus.USER_MIN)
        self.assertEqual(elf.get("USER_LIMIT"), corpus.USER_LIMIT)
        handles = self.constants("kernel/ipc/handles.dg")
        self.assertEqual(handles.get("MAX_GENERATION"), corpus.MAX_GENERATION)
        self.assertIn("bytes:[64]u8", self.compact("kernel/ipc/core.dg"))
        self.assertIn("words:[8]u64", self.compact("services/lib/abi.dg"))
        self.assertIn("rsi>4096", self.compact("kernel/user/services.dg"))

    def test_every_dispatch_token_exists_in_the_dispatcher(self):
        text = self.compact("kernel/user/services.dg")
        for number, entry in corpus.DISPATCH.items():
            self.assertTrue(entry.token in text, hex(number))
        for number in corpus.UNKNOWN_FIXED:
            pattern = re.compile(r"code==0x%x(?![0-9a-fA-F])" % number)
            self.assertIsNone(pattern.search(text), hex(number))
        for number in (0x30, 0x31, 0x40):
            pattern = re.compile(r"code==0x%x(?![0-9a-fA-F])" % number)
            self.assertIsNone(pattern.search(text), hex(number))

    def test_tool_is_offline_and_self_contained(self):
        text = TOOL.read_text(encoding="utf-8")
        for forbidden in ("import subprocess", "import ctypes", "import socket",
                          "import shutil", "os.system", "os.popen", "urllib",
                          "requests", "random.", "import random"):
            self.assertNotIn(forbidden, text, forbidden)
        compiled = compile(text, str(TOOL), "exec")
        self.assertIsInstance(compiled, object)

    def test_no_test_skips(self):
        text = Path(__file__).read_text(encoding="utf-8")
        needles = ["self." + "skip" + "Test(", "unittest." + "skip("]
        for needle in needles:
            self.assertNotIn(needle, text)


class ImmutabilityTests(unittest.TestCase):
    def test_operations_do_not_modify_inputs_or_tool(self):
        data = corpus.generate(13, 40)
        source = unique_file("corpus.jsonl")
        self.addCleanup(source.unlink, missing_ok=True)
        source.write_bytes(data)
        tool_hash = hashlib.sha256(TOOL.read_bytes()).hexdigest()
        input_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        corpus.verify_bytes(source.read_bytes())
        _, records = corpus.verify_bytes(data)
        for record in records[:5]:
            corpus.minimize(record, 4)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), input_hash)
        self.assertEqual(hashlib.sha256(TOOL.read_bytes()).hexdigest(), tool_hash)

    def test_cli_writes_only_the_requested_path(self):
        watched = [TOOL, TOOL.parent.parent / "docs", Path(__file__)]
        before = {}
        for path in watched:
            if path.is_file():
                before[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            elif path.is_dir():
                before[str(path)] = sorted(
                    p.name for p in path.iterdir() if p.is_file())
        out = unique_file("out.jsonl")
        self.addCleanup(out.unlink, missing_ok=True)
        run = subprocess.run(
            [PYTHON, str(TOOL), "generate", "--seed", "1", "--count", "8",
             "--out", str(out)], capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(out.is_file())
        for path in watched:
            if path.is_file():
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(), before[str(path)])
            elif path.is_dir():
                self.assertEqual(
                    sorted(p.name for p in path.iterdir() if p.is_file()),
                    before[str(path)])


if __name__ == "__main__":
    unittest.main()
