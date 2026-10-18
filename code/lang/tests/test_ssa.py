"""Independent typed-SSA verifier, optimizer and allocator regressions."""
from __future__ import annotations

from copy import deepcopy
import random
import unittest

from lang.dongc import ssa

I = ssa.Instruction
T = ssa.Terminator
B = ssa.Block
F = ssa.Function
MASK = (1 << 64) - 1


def canonical(value, typ):
    if typ == 'bool':
        return int(bool(value))
    value &= MASK
    if typ == 'i64' and value >= 1 << 63:
        value -= 1 << 64
    return value


def execute(function, *arguments):
    """Small independent interpreter: phi inputs are parallel edge copies."""
    values = dict(zip(function.params, arguments))
    blocks = {block.name: block for block in function.blocks}
    current, previous = function.entry, None
    for _ in range(2000):
        block = blocks[current]
        incoming = {}
        for ins in block.instructions:
            if ins.op == 'phi':
                source = dict(ins.imm)[previous]
                incoming[ins.result] = values[source]
        values.update(incoming)
        for ins in block.instructions:
            if ins.op in ('phi', 'param'):
                continue
            args = [values[v] for v in ins.args]
            if ins.op == 'const': value = ins.imm
            elif ins.op in ('copy', 'cast'): value = args[0]
            elif ins.op == 'neg': value = -args[0]
            elif ins.op == 'not': value = ~args[0]
            elif ins.op == 'add': value = args[0] + args[1]
            elif ins.op == 'sub': value = args[0] - args[1]
            elif ins.op == 'mul': value = args[0] * args[1]
            elif ins.op == 'and': value = args[0] & args[1]
            elif ins.op == 'or': value = args[0] | args[1]
            elif ins.op == 'xor': value = args[0] ^ args[1]
            elif ins.op == 'cmp':
                a, b = args
                value = {'==': a == b, '!=': a != b, '<': a < b,
                         '<=': a <= b, '>': a > b, '>=': a >= b}[ins.imm]
            else: raise AssertionError(ins.op)
            values[ins.result] = canonical(value, ins.typ)
        term = block.terminator
        if term.op == 'return':
            return values[term.args[0]] if term.args else None
        target = term.targets[0 if term.op == 'jump' or values[term.args[0]] else 1]
        previous, current = current, target
    raise AssertionError('interpreter exceeded bounded test loop')


def diamond():
    return F('diamond', (0, 1, 2), {0: 'bool', 1: 'u64', 2: 'u64',
                                   3: 'u64', 4: 'u64', 5: 'u64'}, [
        B('entry', [], T('branch', (0,), ('yes', 'no'))),
        B('yes', [I(3, 'add', 'u64', (1, 2))], T('jump', (), ('join',))),
        B('no', [I(4, 'sub', 'u64', (1, 2))], T('jump', (), ('join',))),
        B('join', [I(5, 'phi', 'u64', (), (('yes', 3), ('no', 4)))],
          T('return', (5,))),
    ])


def constant_phi_loop():
    # A constant phi precedes a varying phi. The constant must remain live
    # after replacement, exposing a phi-prefix ordering regression.
    return F('constant_phi_loop', (0,), {0: 'u64', 1: 'u64', 2: 'u64',
                                          3: 'u64', 4: 'u64', 5: 'bool', 6: 'u64'}, [
        B('entry', [I(1, 'const', 'u64', (), 5), I(2, 'const', 'u64', (), 0)],
          T('jump', (), ('loop',))),
        B('loop', [I(3, 'phi', 'u64', (), (('entry', 1), ('loop', 1))),
                   I(4, 'phi', 'u64', (), (('entry', 2), ('loop', 6))),
                   I(5, 'cmp', 'bool', (4, 0), '<'),
                   I(6, 'add', 'u64', (4, 3))],
          T('branch', (5,), ('loop', 'end'))),
        B('end', [], T('return', (4,))),
    ])


class VerifierTests(unittest.TestCase):
    def rejects(self, function, text=None):
        with self.assertRaises(ssa.SSAError) as caught:
            ssa.verify(function)
        if text: self.assertIn(text, str(caught.exception))

    def test_implicit_entry_params_and_phi_edge_dominance(self):
        self.assertIs(ssa.verify(diamond()).return_type, 'u64')
        self.assertIs(ssa.verify(constant_phi_loop()).return_type, 'u64')

    def test_parameter_markers_are_optional_unique_entry_prefix(self):
        f = diamond()
        f.blocks[0].instructions = [I(0, 'param', 'bool', (), 0), I(1, 'param', 'u64', (), 1)]
        ssa.verify(f)
        f.blocks[0].instructions.append(I(1, 'param', 'u64', (), 1))
        self.rejects(f, 'parameter marker')

    def test_unique_definition_and_complete_type_table(self):
        f = diamond(); f.blocks[1].instructions.append(I(3, 'const', 'u64', (), 0))
        self.rejects(f, 'defined more than once')
        f = diamond(); f.value_types[99] = 'u64'
        self.rejects(f, 'undefined or missing')
        f = diamond(); del f.value_types[3]
        self.rejects(f, 'declared type')

    def test_bool_value_ids_rejected_in_all_positions(self):
        f = diamond(); f.params = (False, 1, 2)
        self.rejects(f, 'parameters')
        f = diamond(); f.blocks[0].terminator = T('branch', (False,), ('yes', 'no'))
        self.rejects(f, 'undefined value')
        f = diamond(); f.blocks[1].instructions[0] = I(True, 'const', 'u64', (), 0)
        self.rejects(f, 'declared type')

    def test_same_block_use_before_definition(self):
        f = F('forward', (), {0: 'u64', 1: 'u64'}, [
            B('entry', [I(0, 'copy', 'u64', (1,)), I(1, 'const', 'u64', (), 3)],
              T('return', (0,)))])
        self.rejects(f, 'dominate')

    def test_non_dominating_normal_and_phi_use_rejected(self):
        f = diamond(); f.blocks[2].instructions[0] = I(4, 'add', 'u64', (3, 2))
        self.rejects(f, 'dominate')
        f = diamond(); f.blocks[3].instructions[0] = I(5, 'phi', 'u64', (), (('yes', 3), ('no', 3)))
        self.rejects(f, 'dominate')

    def test_phi_exact_predecessors_and_prefix(self):
        for incoming in ((('yes', 3),), (('yes', 3), ('yes', 3)),
                         (('yes', 3), ('no', 4), ('entry', 1))):
            f = diamond(); f.blocks[3].instructions[0] = I(5, 'phi', 'u64', (), incoming)
            self.rejects(f, 'exactly all predecessors')
        f = constant_phi_loop(); f.blocks[1].instructions[0] = I(3, 'const', 'u64', (), 5)
        self.rejects(f, 'prefix')
        f = F('entryphi', (), {0: 'u64'}, [B('entry', [I(0, 'phi', 'u64', (), ())], T('return', (0,)))])
        self.rejects(f, 'non-entry')

    def test_type_safety(self):
        f = diamond(); f.blocks[1].instructions[0] = I(3, 'add', 'u64', (0, 2))
        self.rejects(f, 'operand type')
        f = diamond(); f.blocks[0].terminator = T('branch', (1,), ('yes', 'no'))
        self.rejects(f, 'condition must be bool')
        f = diamond(); f.value_types[5] = 'i64'; f.blocks[3].instructions[0] = I(5, 'phi', 'i64', (), (('yes', 3), ('no', 4)))
        self.rejects(f, 'phi incoming type')
        f = F('castbool', (0,), {0: 'bool', 1: 'u64'}, [B('entry', [I(1, 'cast', 'u64', (0,))], T('return', (1,)))])
        self.rejects(f, '64-bit integer casts')

    def test_canonical_constants_and_unsupported_ops(self):
        for typ, imm in [('u64', -1), ('i64', 1 << 63), ('bool', 2)]:
            f = F('badconst', (), {0: typ}, [B('entry', [I(0, 'const', typ, (), imm)], T('return', (0,)))], return_type=typ)
            self.rejects(f, 'canonical')
        f = diamond(); f.blocks[1].instructions[0] = I(3, 'div', 'u64', (1, 2))
        self.rejects(f, 'unsupported SSA')

    def test_cfg_requires_reachable_blocks_and_valid_terminators(self):
        f = diamond(); f.blocks.append(B('dead', [], T('return', (1,))))
        self.rejects(f, 'unreachable')
        f = diamond(); f.blocks[1].terminator = None
        self.rejects(f, 'lacks terminator')
        f = diamond(); f.blocks[1].terminator = T('jump', (), ('missing',))
        self.rejects(f, 'unknown branch target')
        f = diamond(); f.blocks[1].terminator = T('jump', (1,), ('join',))
        self.rejects(f, 'invalid terminator')
        f = F('cycleentry', (), {}, [B('entry', [], T('jump', (), ('entry',)))], return_type='void')
        self.rejects(f, 'entry block has predecessors')


class OptimizerTests(unittest.TestCase):
    def test_constant_phi_stays_after_remaining_phi_prefix(self):
        f = constant_phi_loop(); original = deepcopy(f)
        out = ssa.optimize(f)
        self.assertEqual(f, original)
        loop = next(b for b in out.blocks if b.name == 'loop')
        self.assertEqual(loop.instructions[0].op, 'phi')
        self.assertTrue(any(i.op == 'const' and i.imm == 5 for i in out.blocks[0].instructions))
        for n in range(45):
            self.assertEqual(execute(f, n), ((n + 4) // 5) * 5)
            self.assertEqual(execute(out, n), execute(f, n))

    def test_branch_fold_unreachable_phi_repair_and_dce(self):
        f = F('fold', (), {0: 'bool', 1: 'u64', 2: 'u64', 3: 'u64', 4: 'u64'}, [
            B('entry', [I(0, 'const', 'bool', (), 1), I(4, 'const', 'u64', (), 99)], T('branch', (0,), ('yes', 'no'))),
            B('yes', [I(1, 'const', 'u64', (), 41)], T('jump', (), ('join',))),
            B('no', [I(2, 'const', 'u64', (), 91)], T('jump', (), ('join',))),
            B('join', [I(3, 'phi', 'u64', (), (('yes', 1), ('no', 2)))], T('return', (3,)))])
        out = ssa.optimize(f)
        self.assertEqual(execute(out), 41)
        self.assertEqual([b.name for b in out.blocks], ['entry', 'yes', 'join'])
        self.assertEqual(out.blocks[0].terminator.op, 'jump')
        self.assertNotIn(4, out.value_types)
        self.assertFalse(any(i.op == 'phi' for b in out.blocks for i in b.instructions))

    def test_constant_branch_removes_edge_between_live_blocks(self):
        f = F('edge', (0, 1, 2), {0: 'bool', 1: 'u64', 2: 'u64', 3: 'bool', 4: 'u64'}, [
            B('entry', [], T('branch', (0,), ('left', 'right'))),
            B('left', [I(3, 'const', 'bool', (), 0)], T('branch', (3,), ('right', 'join'))),
            B('right', [], T('jump', (), ('join',))),
            B('join', [I(4, 'phi', 'u64', (), (('left', 1), ('right', 2)))], T('return', (4,)))])
        out = ssa.optimize(f)
        for choose in (0, 1): self.assertEqual(execute(out, choose, 17, 29), execute(f, choose, 17, 29))
        self.assertEqual(next(b for b in out.blocks if b.name == 'left').terminator.targets, ('join',))

    def test_self_phi_and_copy_simplification(self):
        f = F('same', (0, 1), {0: 'u64', 1: 'bool', 2: 'u64', 3: 'u64'}, [
            B('entry', [], T('jump', (), ('loop',))),
            B('loop', [I(2, 'phi', 'u64', (), (('entry', 0), ('loop', 2))), I(3, 'copy', 'u64', (2,))],
              T('branch', (1,), ('end', 'loop'))),
            B('end', [], T('return', (3,)))])
        out = ssa.optimize(f)
        self.assertEqual(execute(out, 57, 1), 57)
        self.assertFalse(any(i.op in ('phi', 'copy') for b in out.blocks for i in b.instructions))
        self.assertEqual(out.params, (0, 1))

    def test_signed_unsigned_constant_evaluation_and_wrap(self):
        examples = [('u64', 'add', MASK, 1, 0), ('u64', 'sub', 0, 1, MASK),
                    ('i64', 'add', (1 << 63)-1, 1, -(1 << 63)),
                    ('i64', 'mul', -(1 << 63), -1, -(1 << 63)),
                    ('i64', 'and', -1, 31, 31), ('u64', 'xor', 99, 123, 24)]
        for typ, op, a, b, expected in examples:
            f = F('wrap', (), {0: typ, 1: typ, 2: typ}, [B('entry', [I(0, 'const', typ, (), a), I(1, 'const', typ, (), b), I(2, op, typ, (0, 1))], T('return', (2,)))], return_type=typ)
            out = ssa.optimize(f)
            self.assertEqual(execute(out), expected)
            self.assertEqual(out.blocks[0].instructions[-1].imm, expected)
        for typ, a, expected in [('i64', -1, 1), ('u64', MASK, 0)]:
            f = F('compare', (), {0: typ, 1: typ, 2: 'bool'}, [B('entry', [I(0, 'const', typ, (), a), I(1, 'const', typ, (), 0), I(2, 'cmp', 'bool', (0, 1), '<')], T('return', (2,)))], return_type='bool')
            self.assertEqual(execute(ssa.optimize(f)), expected)

    def test_cast_neg_not_and_void_dce(self):
        f = F('casts', (), {0:'u64',1:'i64',2:'i64',3:'i64'}, [B('entry', [I(0,'const','u64',(),MASK),I(1,'cast','i64',(0,)),I(2,'neg','i64',(1,)),I(3,'not','i64',(2,))], T('return',(3,)))], return_type='i64')
        self.assertEqual(execute(ssa.optimize(f)), -2)
        f.return_type='void';f.blocks[0].terminator=T('return')
        self.assertEqual(ssa.optimize(f).blocks[0].instructions, [])

    def test_deterministic_random_pure_programs(self):
        rng = random.Random(0x535341)
        for case in range(80):
            typ = 'i64' if case % 2 else 'u64'
            instructions = [I(2, 'const', typ, (), canonical(rng.getrandbits(64), typ))]
            types = {0:typ,1:typ,2:typ}
            for value in range(3, 25):
                op = rng.choice(sorted(ssa.BINARY))
                a,b = rng.randrange(value),rng.randrange(value)
                instructions.append(I(value,op,typ,(a,b)));types[value]=typ
            f = F('random', (0,1), types, [B('entry', instructions,T('return',(24,)))],return_type=typ)
            out = ssa.optimize(f)
            for _ in range(12):
                args = [canonical(rng.getrandbits(64),typ) for _ in range(2)]
                self.assertEqual(execute(out,*args),execute(f,*args))


class AllocatorTests(unittest.TestCase):
    def test_phi_uses_live_on_predecessor_edges(self):
        f = diamond(); incoming,outgoing = ssa.liveness(f)
        self.assertEqual(outgoing['yes'], {3})
        self.assertEqual(outgoing['no'], {4})
        self.assertEqual(incoming['join'], set())
        self.assertEqual(incoming['yes'], {1,2})
        self.assertEqual(incoming['no'], {1,2})
        graph = ssa.interference(f)
        # Mutually exclusive predecessors do not require simultaneous storage.
        self.assertNotIn(4, graph[3]);self.assertNotIn(3,graph[5])

    def test_global_loop_liveness_reaches_fixed_point(self):
        f = constant_phi_loop(); incoming,outgoing = ssa.liveness(f)
        self.assertIn(0, incoming['loop'])
        self.assertIn(6, outgoing['loop'])
        self.assertIn(1, outgoing['entry'])
        self.assertIn(2, outgoing['entry'])
        self.assertNotIn(6, incoming['entry'])

    def test_coloring_edges_and_spills_are_safe_and_deterministic(self):
        for f in (diamond(), constant_phi_loop()):
            graph = ssa.interference(f)
            for registers in ((), ('r8',), ('r8','r9'), ('r8','r9','rsi','rdi','rdx','rcx')):
                locations = ssa.allocate(f,registers)
                self.assertEqual(set(locations),set(f.value_types))
                self.assertEqual(locations,ssa.allocate(f,registers))
                spills = [loc for loc in locations.values() if type(loc) is int]
                self.assertEqual(sorted(set(spills)),list(range(len(set(spills)))))
                for value, adjacent in graph.items():
                    for other in adjacent:
                        self.assertNotEqual(locations[value],locations[other])
                        self.assertIn(value,graph[other])
                if not registers:self.assertTrue(all(type(v) is int for v in locations.values()))

    def test_unused_parameters_keep_distinct_locations(self):
        f = F('params', (0,1,2), {0:'u64',1:'u64',2:'u64'}, [B('entry',[],T('return',(1,)))])
        out = ssa.optimize(f)
        locations = ssa.allocate(out,('r8',))
        self.assertEqual(set(locations),{0,1,2})
        self.assertEqual(len(set(locations.values())),3)

    def test_bad_register_sets_rejected(self):
        for registers in (('r8','r8'), ('',), 'r8', (1,), None):
            with self.assertRaises(ssa.SSAError): ssa.allocate(diamond(), registers)


if __name__ == '__main__':
    unittest.main()
