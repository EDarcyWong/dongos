"""Independent review sensitivity probe; never edits worker source or tests."""
import hashlib
import importlib.util
import json
from pathlib import Path

w = Path(__file__).resolve().parents[1]
p = w / 'deepseek-works/tests/test_nasm_byte_truth_load.py'
spec = importlib.util.spec_from_file_location('d22_review', p)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
cls = mod.NasmByteTruthLoadTests
cls.setUpClass()
t = cls('test_dong_assemble_and_native_byte_truth')
source = mod.SOURCE.read_text(encoding='utf-8')
old = '*written=total;return OK;'
assert source.count(old) == 1
new = ('let extra="mov r11, 61453\\n";var e:usize=0;'
       'while e<extra.len{out[total+e]=extra[e];e+=1;}'
       '*written=total+extra.len;return OK;')
bad = source.replace('module bootstrap.nasm_byte_truth_load;',
                     'module bootstrap.nasm_byte_truth_load_bad_r11;').replace(old, new)
executables = cls.bad_build('review-r11', bad, 'nasm_byte_truth_load_bad_r11', 'dong_r11_emit')
records = []
for mode, exe in executables.items():
    c = mod.item(6, 0, cap=128)
    good = t._emit_text(cls.executables[mode], c, 'review-good-'+mode)
    t._probe(mode, 950, 6, 0, 255, good)
    text = t._emit_text(exe, c, 'review-bad-'+mode)
    assert text == good + b'mov r11, 61453\n'
    captured = t._probe(mode, 951, 6, 0, 255, text)
    assert captured[0] == 1 and 11 not in captured
    records.append(dict(mode=mode, good_native_passed=True, bad_native_returned=True,
                        bad_r11_clobber_escaped_assertions=True, observed=sorted(captured)))
report = dict(records=records, work=str(cls.work), source_sha256=hashlib.sha256(mod.SOURCE.read_bytes()).hexdigest(),
              test_sha256=hashlib.sha256(p.read_bytes()).hexdigest(), worker_files_modified=False)
(w/'reviews/2026-10-19-D22-r11-sensitivity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
