"""Verifier and transformation contracts for ordered ordinary-memory IR."""
from copy import deepcopy
import unittest
from lang.dongc import ssa

I,B,T,F=ssa.Instruction,ssa.Block,ssa.Terminator,ssa.Function


class SSAEffectTests(unittest.TestCase):
    def test_loads_stores_and_read_faults_are_observable_roots(self):
        f=F('effects',(0,1),{0:'u64',1:'u64',2:'u64',3:'u64',4:'u64',5:'u64'},[
            B('entry',[I(2,'load','u64',(0,)),I(3,'store','u64',(1,2)),
                       I(4,'load','u64',(0,)),I(5,'store','u64',(0,4))],T('return'))],return_type='void')
        before=deepcopy(f);out=ssa.optimize(f)
        self.assertEqual(f,before)
        self.assertEqual([i.op for i in out.blocks[0].instructions],['load','store','load','store'])

    def test_never_fold_a_load_across_an_aliasing_store(self):
        f=F('alias',(0,1),{0:'u64',1:'u64',2:'u64',3:'u64',4:'u64',5:'u64'},[
            B('entry',[I(2,'const','u64',(),8),I(3,'addr','u64',(0,1),(8,1)),
                       I(4,'load','u64',(3,)),I(5,'store','u64',(3,2))],T('return',(4,)))])
        out=ssa.optimize(f)
        memory=[i for i in out.blocks[0].instructions if i.op in ssa.MEMORY]
        self.assertEqual([i.op for i in memory],['load_index','store_index'])
        self.assertEqual(memory[0].args,(0,1))
        self.assertEqual(memory[1].args,(0,1,2))

    def test_only_adjacent_single_use_loads_fold_into_arithmetic(self):
        f=F('sum',(0,1,2),{0:'u64',1:'u64',2:'u64',3:'u64',4:'u64',5:'u64'},[
            B('entry',[I(3,'addr','u64',(0,1),(8,1)),I(4,'load','u64',(3,)),
                       I(5,'add','u64',(2,4))],T('return',(5,)))])
        out=ssa.optimize(f)
        self.assertEqual([(i.op,i.args)for i in out.blocks[0].instructions],[('add_load',(2,0,1))])
        g=deepcopy(f);g.value_types[6]='u64'
        g.blocks[0].instructions.insert(2,I(6,'store','u64',(0,2)))
        self.assertNotIn('add_load',[i.op for i in ssa.optimize(g).blocks[0].instructions])

    def test_memory_operand_types_and_address_metadata_are_verified(self):
        bad=[I(2,'load','u64',(0,),8),I(2,'store','u64',(0,1),8),
             I(2,'addr','u64',(0,1),(-1,1)),I(2,'addr','u64',(0,1),(8,0)),
             I(2,'load_index','u64',(0,),(8,1))]
        for ins in bad:
            f=F('invalid',(0,1),{0:'u64',1:'u64',2:ins.typ},[B('entry',[ins],T('return',(2,)))])
            with self.subTest(ins=ins),self.assertRaises(ssa.SSAError):ssa.verify(f)
        f=F('booladdr',(0,),{0:'bool',1:'u64'},[B('entry',[I(1,'load','u64',(0,))],T('return',(1,)))])
        with self.assertRaisesRegex(ssa.SSAError,'address must be u64'):ssa.verify(f)

    def test_rematerialization_is_explicit_and_only_constants_qualify(self):
        f=F('constant',(0,),{0:'u64',1:'u64',2:'u64'},[
            B('entry',[I(1,'const','u64',(),3),I(2,'add','u64',(0,1))],T('return',(2,)))])
        with self.assertRaisesRegex(ssa.SSAError,'only constants'):ssa.allocate(f,('r8',),rematerialize=(0,))
        places=ssa.allocate(f,('r8',),rematerialize=(1,))
        self.assertEqual(places[0],places[2])


if __name__=='__main__':unittest.main()
