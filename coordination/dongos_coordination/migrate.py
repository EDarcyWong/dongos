"""Import existing task books without rewriting delivery/review history."""
import re
from pathlib import Path
from .store import Conflict, digest, now, resolve

MODULES = {
    'C1': 'bigint_div', 'C2': 'bigint_bits', 'C3': 'constant_arithmetic',
    'C4': 'type_layout', 'C5': 'diagnostic_format', 'C6': 'source_position',
}
DEEP = {
    'D1': ('原始字节内存模块', 'core/mem', 'mem'),
    'D2': ('usize检查算术与对齐', 'core/int', 'int'),
    'D3': ('字节切片辅助模块', 'core/slice', 'slice'),
    'D4': ('原子自旋锁', 'sync/spin', 'spin'),
    'D5': ('缓冲区与回调格式化', 'core/fmt', 'fmt'),
    'D6': ('x86-64外部汇编包装器', 'arch/x86_64', 'arch'),
    'D7': ('特权级硬件探针', 'arch/x86_64', None),
    'D8': ('物理伙伴分配器', 'mm/buddy', None),
    'D9': ('内存区间归一化', 'mm/memory_map', None),
    'D10': ('固定对象缓存', 'mm/cache', None),
    'D11': ('位集合', 'core/bitset', 'bitset'),
    'D12': ('线性arena', 'core/arena', 'arena'),
    'D13': ('严格UTF-8', 'core/utf8', 'utf8'),
}


def document_status(text):
    # Only the current header, never a historical paragraph further down the book.
    match = re.search(r'状态[：:]\s*([^。\n]+)', text[:1400])
    value = match[1] if match else ''
    if '已集成' in value:
        return 'accepted'  # A book alone is not evidence of integration.
    if any(word in value for word in ('已验收', '验收通过', '正式验收')):
        return 'accepted'
    if '待复验' in value or '待验收' in value:
        return 'submitted'
    if '返修' in value or '修复' in value:
        return 'rework'
    if '进行中' in value or '已领取' in value:
        return 'in_progress'
    return 'todo'


def synchronize(store):
    added, changed = [], []
    books = []
    for owner in ('claude', 'cursor', 'deepseek', 'codex', 'lmstudio', 'pool'):
        for path in sorted((store.works_root / (owner + '-works/tasks')).glob('*.md')):
            match = re.match(r'([A-Z]+\d+)[-\.]', path.name)
            if match:
                books.append((owner, match[1], path))
    # D1-D4 predate the per-task directory and remain in the original list.
    old = store.works_root / 'deepseek-works/deepseek-work-list.md'
    if old.exists():
        for number in ('D1', 'D2', 'D3', 'D4'):
            books.append(('deepseek', number, old))
    for owner, number, path in books:
        text = path.read_text(encoding='utf-8-sig')
        status = document_status(text)
        if number in ('D1', 'D2', 'D3', 'D4'):
            status = 'accepted' if re.search(r'\| ' + number + r' \|[^\n]*已验收', text) else 'todo'
        key = owner + ':' + number
        title = re.sub(r'^#\s*' + number + r'\s*[—–-]?\s*', '', text.splitlines()[0]).strip()
        patterns, tests = [], []
        if owner == 'claude' and number in MODULES:
            module = MODULES[number]
            patterns = [f'lang/bootstrap/{module}.dg', f'lang/bootstrap/{module}.md',
                        f'lang/tests/test_bootstrap_{module}.py', f'lang/tests/bootstrap_{module}_probe.*']
            tests = ['module:lang.tests.test_bootstrap_' + module]
        elif owner == 'cursor' and number == 'CR1':
            patterns = ['cursor-works/src/bootstrap/nasm_bytes.dg', 'cursor-works/src/bootstrap/nasm_bytes.md',
                        'cursor-works/tests/test_nasm_bytes.py', 'cursor-works/tests/nasm_bytes_probe*']
            tests = ['discover:cursor-works/tests:test_nasm_bytes.py']
        elif owner == 'deepseek' and number in DEEP:
            title, module, test = DEEP[number]
            patterns = [f'lang/std/{module}.dg', f'lang/std/{module}.md']
            if test:
                patterns += [f'lang/tests/test_std_{test}.py', f'lang/tests/std_{test}_probe*']
                tests = ['module:lang.tests.test_std_' + test]
            if number == 'D5':
                patterns.append('lang/std/core/errors.dg')
            if number == 'D6':
                patterns.append('lang/std/arch/x86_64.asm')
            if number == 'D7':
                patterns = ['lang/tests/std_arch_ring0.dg', 'lang/tests/std_arch_ring0.asm',
                            'tests/run_std_arch_qemu.py', 'tests/test_std_arch_qemu_result.py',
                            'tests/test_std_arch_qemu_negative.py', 'docs/std-arch-ring0.md']
                # Hardware runs are never auto-dispatched by importing a historical book.
                tests = []
            if number in ('D8', 'D9', 'D10'):
                module = {'D8': 'phys_buddy', 'D9': 'memory_map', 'D10': 'fixed_cache'}[number]
                patterns = [f'kernel/mm/{module}.dg', f'kernel/mm/{module}.md',
                            f'tests/test_{module}.py', f'tests/{module}_probe*']
                if number == 'D8':
                    patterns.append('kernel/mm/errors.dg')
                tests = ['module:tests.test_' + module]
        # Console-generated books declare exact scopes; retain them on a fresh
        # database rather than replacing them with broad legacy wildcards.
        scope = re.search(r'^## 可修改文件\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
        if scope:
            declared = re.findall(r'^- `([^`]+)`\s*$', scope[1], re.M)
            if declared:
                patterns = declared
        check_section = re.search(r'^## 定向验收\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
        if check_section:
            tests = re.findall(r'^- `([^`]+)`\s*$', check_section[1], re.M)
        if not patterns:
            patterns = [owner + '-works/src/**', owner + '-works/tests/**']
        patterns += [f'{owner}-works/deliveries/{number}.md']
        # Only the fixed pre-console baseline has independent acceptance evidence.
        baseline = baseline_accepted(store.works_root, owner, number)
        if status == 'accepted' and not baseline:
            status = 'submitted' if store.path(f'{owner}-works/deliveries/{number}.md').is_file() else 'todo'
        data = dict(id=number, owner=None if owner == 'pool' else owner, title=title[:180], description='从现有任务书导入，历史内容保留。',
                    status=status, write_paths=patterns, checks=tests,
                    historical=status == 'accepted', document=path.relative_to(store.works_root).as_posix(),
                    delivery=f'{owner}-works/deliveries/{number}.md', legacy_hash=digest(path),
                    evidence=[f'{owner}-works/README.md'])
        try:
            current = store.get(key)
        except ValueError:
            store.create(data, imported=True)
            added.append(key)
            continue
        if current.get('archived'):
            continue  # Retained task books must not revive archived handoffs.
        if baseline and current.get('legacy_hash') and current.get('legacy_schema') != 2:
            with store.transaction() as c:
                current = store.get(key, c)
                current['write_paths'], current['checks'] = patterns, tests
                current['legacy_schema'] = 2
                # Metadata migration never promotes an existing task's acceptance.
                store.save(c, current, 'legacy_metadata_reconciled')
            changed.append(key)
        if current.get('legacy_hash') == data['legacy_hash']:
            continue
        with store.transaction() as c:
            current = store.get(key, c)
            current['legacy_hash'] = data['legacy_hash']
            current['document_status'] = status
            # Import progress and deliveries, never a new self-declared acceptance.
            if not store.active_for(c, key) and current['status'] in ('todo', 'in_progress', 'rework'):
                if status == 'in_progress' and current['status'] == 'todo':
                    current['status'] = status
                if status == 'submitted' and store.path(current['delivery']).is_file():
                    current['status'] = 'submitted'
                    current['candidate'], current['verification'] = None, None
            store.save(c, current, 'document_changed')
        changed.append(key)
    return dict(added=added, changed=changed, at=now())


def baseline_accepted(root, owner, number):
    if owner == 'claude' and number in MODULES:
        marker, review = 'C1～C6均已验收', '2026-10-18-C6-acceptance.md'
    elif owner == 'deepseek' and number in DEEP:
        marker, review = 'D1～D13 均已验收', '2026-10-18-D12-acceptance.md'
    else:
        return False
    readme = root / (owner + '-works/README.md')
    return (readme.is_file() and marker in readme.read_text(encoding='utf-8-sig')[:1200] and
            (root / f'{owner}-works/reviews/{review}').is_file())
