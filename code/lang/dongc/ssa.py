"""Typed SSA CFG, verifier, SCCP/DCE, ordered memory, and register coloring.

Ordinary loads/stores are observable roots, never speculated, cached or reordered.
Calls, volatile/atomic accesses and checked operators still use the L1 backend.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

TYPES=frozenset({'u64','i64','bool'})
BINARY=frozenset({'add','sub','mul','and','or','xor'})
UNARY=frozenset({'neg','not','copy','cast'})
COMPARE=frozenset({'==','!=','<','<=','>','>='})
MASK=(1<<64)-1
MEMORY=frozenset({'load','store','load_index','store_index','add_load'})

class SSAError(ValueError):pass

def need(condition,message):
    if not condition:raise SSAError(message)

@dataclass(frozen=True)
class Instruction:
    result:int
    op:str
    typ:str
    args:tuple[int,...]=()
    imm:Any=None
    token:Any=None

@dataclass(frozen=True)
class Terminator:
    op:str
    args:tuple[int,...]=()
    targets:tuple[str,...]=()
    token:Any=None

@dataclass
class Block:
    name:str
    instructions:list[Instruction]=field(default_factory=list)
    terminator:Terminator|None=None

@dataclass
class Function:
    name:str
    params:tuple[int,...]
    value_types:dict[int,str]
    blocks:list[Block]
    entry:str='entry'
    return_type:str='u64'


def _cfg(f):
    names={b.name:b for b in f.blocks}
    predecessors={name:set()for name in names}
    for b in f.blocks:
        for target in b.terminator.targets:predecessors[target].add(b.name)
    reachable=set();pending=[f.entry]
    while pending:
        name=pending.pop()
        if name in reachable:continue
        reachable.add(name);pending.extend(names[name].terminator.targets)
    return names,predecessors,reachable


def verify(f:Function):
    need(isinstance(f,Function),'expected Function')
    need(isinstance(f.return_type,str)and f.return_type in TYPES|{'void'},'unsupported return type')
    need(bool(f.blocks),'function has no entry block')
    need(all(isinstance(b,Block)and isinstance(b.name,str)and b.name for b in f.blocks),'invalid block')
    need(len({b.name for b in f.blocks})==len(f.blocks),'duplicate block name')
    names={b.name for b in f.blocks};need(f.entry in names,'missing entry block')
    need(type(f.params)is tuple and all(type(v)is int and v>=0 for v in f.params)and len(set(f.params))==len(f.params),'duplicate/invalid entry parameters')
    need(isinstance(f.value_types,dict),'invalid value/type table')
    need(all(type(v)is int and v>=0 and isinstance(t,str)and t in TYPES for v,t in f.value_types.items()),'invalid value/type table')
    need(all(v in f.value_types for v in f.params),'parameter has no type')
    definitions={v:(f.entry,-1)for v in f.params};markers=set()
    for block in f.blocks:
        term=block.terminator
        need(isinstance(term,Terminator),'block lacks terminator: '+block.name)
        need(type(term.args)is tuple and type(term.targets)is tuple,'terminator operands/targets must be tuples')
        need(isinstance(term.op,str)and all(isinstance(target,str)and target in names for target in term.targets),'unknown branch target')
        need(isinstance(block.instructions,(list,tuple)),'invalid instruction list')
        need((term.op=='jump'and len(term.targets)==1 and not term.args)
             or(term.op=='branch'and len(term.targets)==2 and len(term.args)==1)
             or(term.op=='return'and not term.targets and len(term.args)==(0 if f.return_type=='void'else 1)), 'invalid terminator')
        non_phi=False;non_param=False
        for index,ins in enumerate(block.instructions):
            need(isinstance(ins,Instruction),'non-SSA instruction')
            need(type(ins.result)is int and ins.result>=0 and ins.result in f.value_types,'result has no declared type')
            need(isinstance(ins.op,str)and isinstance(ins.typ,str)and ins.typ in TYPES and f.value_types[ins.result]==ins.typ,'result type mismatch')
            need(type(ins.args)is tuple and all(type(v)is int for v in ins.args),'instruction operands must be value IDs')
            if ins.op=='param':
                need(block.name==f.entry and not non_param and ins.result in f.params and ins.result not in markers,'invalid/duplicate entry parameter marker')
                need(not ins.args and ins.imm in(None,f.params.index(ins.result)),'invalid parameter marker operands')
                markers.add(ins.result);continue
            non_param=True
            need(ins.result not in definitions,'value defined more than once')
            definitions[ins.result]=(block.name,index)
            if ins.op=='phi':
                need(block.name!=f.entry and not non_phi and not ins.args,'phis must be a non-entry operand-free block prefix')
                need(type(ins.imm)is tuple and all(type(e)is tuple and len(e)==2 and isinstance(e[0],str)and type(e[1])is int for e in ins.imm),'malformed phi incoming edges')
            else:non_phi=True
            need(ins.op in BINARY|UNARY|MEMORY|{'const','cmp','phi','addr'},'unsupported SSA operation: '+ins.op)
            if ins.op=='const':
                need(not ins.args and isinstance(ins.imm,int),'invalid constant')
                low,high=(0,1)if ins.typ=='bool'else(-(1<<63),(1<<63)-1)if ins.typ=='i64'else(0,MASK)
                need(low<=ins.imm<=high,'constant outside canonical type range')
            elif ins.op in BINARY:
                need(ins.typ in {'u64','i64'}and len(ins.args)==2 and ins.imm is None,'invalid integer binary operation')
            elif ins.op in UNARY:
                need(len(ins.args)==1 and ins.imm is None,'invalid unary/copy/cast operation')
                if ins.op in{'neg','not','cast'}:need(ins.typ in{'u64','i64'},'integer operation on bool')
            elif ins.op=='cmp':need(ins.typ=='bool'and len(ins.args)==2 and isinstance(ins.imm,str)and ins.imm in COMPARE,'invalid comparison')
            elif ins.op=='addr' or ins.op in {'load_index','store_index','add_load'}:
                need(type(ins.imm)is tuple and len(ins.imm)==2 and type(ins.imm[0])is int and
                     0<=ins.imm[0]<=MASK and type(ins.imm[1])is int and ins.imm[1]in(-1,1),'invalid address scale/sign')
                count=3 if ins.op in {'store_index','add_load'} else 2
                need(len(ins.args)==count and (ins.op!='addr' or ins.typ=='u64'),'invalid indexed operands')
                if ins.op=='add_load':need(ins.typ in {'u64','i64'},'invalid memory arithmetic type')
            elif ins.op in {'load','store'}:
                need(ins.imm is None and len(ins.args)==(1 if ins.op=='load'else 2),'invalid memory operands')
    need(set(definitions)==set(f.value_types),'value table has undefined or missing definitions')
    by_name,pred,reachable=_cfg(f)
    need(not pred[f.entry],'entry block has predecessors')
    need(reachable==set(by_name),'block is unreachable from entry')
    dominators={name:({name}if name==f.entry else set(reachable))for name in reachable}
    changed=True
    while changed:
        changed=False
        for block in f.blocks:
            name=block.name
            if name==f.entry:continue
            common=set.intersection(*(dominators[p]for p in pred[name]))
            value=common|{name}
            if value!=dominators[name]:dominators[name]=value;changed=True
    def use(value,block,index):
        need(type(value)is int and value in definitions,'use of undefined value')
        owner,position=definitions[value]
        need(owner in dominators[block]and(owner!=block or position<index),'value definition does not dominate use')
    for block in f.blocks:
        for index,ins in enumerate(block.instructions):
            if ins.op=='param':continue
            if ins.op=='phi':
                incoming=[name for name,value in ins.imm]
                need(len(incoming)==len(set(incoming))and set(incoming)==pred[block.name],'phi must have exactly all predecessors')
                for source,value in ins.imm:
                    use(value,source,len(by_name[source].instructions))
                    need(f.value_types[value]==ins.typ,'phi incoming type mismatch')
                continue
            for value in ins.args:use(value,block.name,index)
            if ins.op in BINARY|{'neg','not','copy'}:need(all(f.value_types[v]==ins.typ for v in ins.args),'operand type mismatch')
            if ins.op=='cast':need(f.value_types[ins.args[0]]in{'u64','i64'},'only 64-bit integer casts are supported')
            if ins.op=='cmp':
                need(f.value_types[ins.args[0]]==f.value_types[ins.args[1]],'comparison operand type mismatch')
                need(f.value_types[ins.args[0]]!='bool'or ins.imm in{'==','!='},'ordered bool comparison')
            if ins.op in MEMORY|{'addr'}:
                address_args=ins.args[1:] if ins.op=='add_load' else ins.args[:2]if ins.op in {'addr','load_index','store_index'}else ins.args[:1]
                need(all(f.value_types[v]=='u64'for v in address_args),'memory address must be u64')
                if ins.op in {'store','store_index','add_load'}:
                    value=ins.args[0]if ins.op=='add_load'else ins.args[-1]
                    need(f.value_types[value]==ins.typ,'memory value type mismatch')
        term=block.terminator
        for value in term.args:use(value,block.name,len(block.instructions))
        if term.op=='branch':need(f.value_types[term.args[0]]=='bool','branch condition must be bool')
        if term.op=='return'and term.args:need(f.value_types[term.args[0]]==f.return_type,'return type mismatch')
    return f


def _normal(value,typ):
    if typ=='bool':return int(bool(value))
    value=int(value)&MASK
    return value-(1<<64)if typ=='i64'and value&(1<<63)else value


def _evaluate(ins,operands):
    if ins.op=='const':return int(ins.imm)
    if ins.op=='addr':return (operands[0]+ins.imm[0]*ins.imm[1]*operands[1])&MASK
    if ins.op in{'copy','cast'}:return _normal(operands[0],ins.typ)
    if ins.op=='neg':return _normal(-operands[0],ins.typ)
    if ins.op=='not':return _normal(~operands[0],ins.typ)
    a,b=operands
    if ins.op=='cmp':return int({'==':a==b,'!=':a!=b,'<':a<b,'<=':a<=b,'>':a>b,'>=':a>=b}[ins.imm])
    if ins.op=='add':value=a+b
    elif ins.op=='sub':value=a-b
    elif ins.op=='mul':value=a*b
    elif ins.op=='and':value=a&b
    elif ins.op=='or':value=a|b
    elif ins.op=='xor':value=a^b
    else:raise SSAError('operation cannot be evaluated')
    return _normal(value,ins.typ)


def optimize(f:Function)->Function:
    """Sparse conditional constant propagation followed by copy/phi DCE.

    Input is verified before transformation; output is newly allocated and
    verified again. All supported instructions are pure modulo-64 operations.
    """
    verify(f)
    undefined,over=object(),object()
    values={v:over if v in f.params else undefined for v in f.value_types}
    executable={f.entry};edges=set();changed=True
    def merge(old,new):
        if old is over or new is undefined:return old
        if old is undefined:return new
        return old if new is not over and old==new else over
    while changed:
        changed=False
        for block in f.blocks:
            if block.name not in executable:continue
            for ins in block.instructions:
                if ins.op=='param':continue
                if ins.op in MEMORY:new=over
                elif ins.op=='phi':
                    known=[values[v]for p,v in ins.imm if(p,block.name)in edges and values[v]is not undefined]
                    new=undefined if not known else known[0]
                    for value in known[1:]:new=merge(new,value)
                else:
                    operands=[values[v]for v in ins.args]
                    new=over if any(v is over for v in operands)else undefined if any(v is undefined for v in operands)else _evaluate(ins,operands)
                new=merge(values[ins.result],new)
                if new is not values[ins.result]and new!=values[ins.result]:values[ins.result]=new;changed=True
            term=block.terminator;targets=term.targets
            if term.op=='branch':
                condition=values[term.args[0]]
                targets=()if condition is undefined else targets if condition is over else(targets[0 if condition else 1],)
            for target in targets:
                if(block.name,target)not in edges:edges.add((block.name,target));changed=True
                if target not in executable:executable.add(target);changed=True
    blocks=[]
    for block in f.blocks:
        if block.name not in executable:continue
        term=block.terminator
        if term.op=='branch'and values[term.args[0]]is not over and values[term.args[0]]is not undefined:
            term=Terminator('jump',(),(term.targets[0 if values[term.args[0]]else 1],),term.token)
        elif term.op=='branch'and term.targets[0]==term.targets[1]:term=Terminator('jump',(),(term.targets[0],),term.token)
        instructions=[]
        for ins in block.instructions:
            value=values[ins.result]
            if ins.op!='param'and value is not over and value is not undefined:
                instructions.append(Instruction(ins.result,'const',ins.typ,(),value,ins.token))
            elif ins.op=='phi':instructions.append(Instruction(ins.result,'phi',ins.typ,(),tuple((p,v)for p,v in ins.imm if p in executable and(block.name in [t for t in next(b for b in f.blocks if b.name==p).terminator.targets])),ins.token))
            else:instructions.append(ins)
        # Replacing an early phi by a constant must not put that definition
        # ahead of the still-varying phis. Phi edge uses occur at predecessor
        # exits, so moving those constants immediately after the phi prefix
        # preserves dominance, including self-loop incoming values.
        instructions=[i for i in instructions if i.op=='phi']+[i for i in instructions if i.op!='phi']
        blocks.append(Block(block.name,instructions,term))
    result=Function(f.name,f.params,dict(f.value_types),blocks,f.entry,f.return_type)
    by_name,pred,reachable=_cfg(result)
    # Branch folding can remove edges between still-executable blocks.
    result.blocks=[b for b in result.blocks if b.name in reachable]
    by_name,pred,_=_cfg(result)
    for b in result.blocks:
        b.instructions=[Instruction(i.result,i.op,i.typ,i.args,tuple((p,v)for p,v in i.imm if p in pred[b.name]),i.token)if i.op=='phi'else i for i in b.instructions]
    aliases={}
    def resolved(value):
        visited=set()
        while value in aliases:
            need(value not in visited,'cyclic copy aliases');visited.add(value);value=aliases[value]
        return value
    changed=True
    while changed:
        changed=False
        for b in result.blocks:
            for ins in b.instructions:
                if ins.result in aliases:continue
                operands={resolved(v)for p,v in ins.imm if resolved(v)!=ins.result}if ins.op=='phi'else{resolved(ins.args[0])}if ins.op=='copy'else set()
                if len(operands)==1:
                    target=next(iter(operands))
                    if target!=ins.result:aliases[ins.result]=target;changed=True
    for b in result.blocks:
        b.instructions=[Instruction(i.result,i.op,i.typ,tuple(resolved(v)for v in i.args),tuple((p,resolved(v))for p,v in i.imm)if i.op=='phi'else i.imm,i.token)for i in b.instructions if i.result not in aliases]
        t=b.terminator;b.terminator=Terminator(t.op,tuple(resolved(v)for v in t.args),t.targets,t.token)
    # Form x86-compatible addresses in the IR, BEFORE liveness/allocation, so
    # original base/index values stay live across evaluation of a store RHS.
    definitions={i.result:i for b in result.blocks for i in b.instructions}
    for b in result.blocks:
        selected=[]
        for i in b.instructions:
            address=definitions.get(i.args[0])if i.op in {'load','store'}else None
            if address and address.op=='addr':
                i=Instruction(i.result,i.op+'_index',i.typ,address.args+(i.args[1:]if i.op=='store'else()),address.imm,i.token)
            if i.op=='add'and selected:
                previous=selected[-1]
                uses=sum(j.args.count(previous.result)for block in result.blocks for j in block.instructions)
                uses+=sum(t.args.count(previous.result)for t in [block.terminator for block in result.blocks])
                uses+=sum(sum(v==previous.result for p,v in j.imm)for block in result.blocks for j in block.instructions if j.op=='phi')
                if previous.op=='load_index'and uses==1 and previous.result in i.args and previous.typ==i.typ:
                    left=i.args[1]if i.args[0]==previous.result else i.args[0]
                    selected.pop()
                    i=Instruction(i.result,'add_load',i.typ,(left,)+previous.args,previous.imm,i.token)
            selected.append(i)
        b.instructions=selected
    definitions={i.result:i for b in result.blocks for i in b.instructions};needed=set()
    pending=[v for b in result.blocks for v in b.terminator.args]
    pending.extend(i.result for b in result.blocks for i in b.instructions if i.op in MEMORY)
    while pending:
        value=pending.pop()
        if value in needed:continue
        needed.add(value);ins=definitions.get(value)
        if ins is not None:pending.extend(v for p,v in ins.imm)if ins.op=='phi'else pending.extend(ins.args)
    for b in result.blocks:b.instructions=[i for i in b.instructions if i.result in needed]
    # Constants do not read memory or trap. Intern and hoist them to entry;
    # the machine backend may keep costly 64-bit immediates in registers.
    canonical={};constant_aliases={};hoisted=[]
    for b in result.blocks:
        for i in b.instructions:
            if i.op=='const':
                key=(i.typ,i.imm)
                if key in canonical:constant_aliases[i.result]=canonical[key]
                else:canonical[key]=i.result;hoisted.append(i)
        b.instructions=[i for i in b.instructions if i.op!='const']
    for b in result.blocks:
        b.instructions=[Instruction(i.result,i.op,i.typ,tuple(constant_aliases.get(v,v)for v in i.args),
            tuple((p,constant_aliases.get(v,v))for p,v in i.imm)if i.op=='phi'else i.imm,i.token)for i in b.instructions]
        t=b.terminator;b.terminator=Terminator(t.op,tuple(constant_aliases.get(v,v)for v in t.args),t.targets,t.token)
    entry=next(b for b in result.blocks if b.name==result.entry)
    markers=[i for i in entry.instructions if i.op=='param']
    entry.instructions=markers+hoisted+[i for i in entry.instructions if i.op!='param']
    present=set(f.params)|{i.result for b in result.blocks for i in b.instructions}
    result.value_types={v:f.value_types[v]for v in f.value_types if v in present}
    return verify(result)


def liveness(f:Function):
    verify(f);by_name,pred,_=_cfg(f)
    definitions={};uses={};phi_defs={};edge_uses={}
    for b in f.blocks:
        seen=set(f.params)if b.name==f.entry else set();use=set();phis=set()
        for i in b.instructions:
            if i.op=='phi':
                phis.add(i.result)
                for p,v in i.imm:edge_uses.setdefault((p,b.name),set()).add(v)
            elif i.op!='param':use.update(v for v in i.args if v not in seen)
            seen.add(i.result)
        use.update(v for v in b.terminator.args if v not in seen)
        definitions[b.name]=seen;uses[b.name]=use;phi_defs[b.name]=phis
    live_in={b.name:set()for b in f.blocks};live_out={b.name:set()for b in f.blocks};changed=True
    while changed:
        changed=False
        for b in reversed(f.blocks):
            outgoing=set()
            for target in b.terminator.targets:outgoing.update(live_in[target]-phi_defs[target]);outgoing.update(edge_uses.get((b.name,target),()))
            incoming=uses[b.name]|(outgoing-definitions[b.name])
            if incoming!=live_in[b.name]or outgoing!=live_out[b.name]:live_in[b.name]=incoming;live_out[b.name]=outgoing;changed=True
    return live_in,live_out


def interference(f:Function):
    live_in,live_out=liveness(f);graph={v:set()for v in f.value_types}
    def edge(a,b):
        if a!=b:graph[a].add(b);graph[b].add(a)
    def clique(values):
        values=sorted(set(values))
        for index,a in enumerate(values):
            for b in values[index+1:]:edge(a,b)
    clique(f.params)
    for block in f.blocks:
        live=set(live_out[block.name])|set(block.terminator.args)
        for i in reversed(block.instructions):
            if i.op in{'phi','param'}:continue
            for value in live:edge(i.result,value)
            live.discard(i.result);live.update(i.args)
        phis=[i for i in block.instructions if i.op=='phi']
        for i in phis:
            for value in live:edge(i.result,value)
        # Phi results exist together on entry. Incoming values exist at their
        # own predecessor exits; different predecessor edges are exclusive.
        # Parallel edge copies handle cycles, so result/input pairs need not
        # interfere merely because they participate in the same phi.
        clique([i.result for i in phis])
        clique(live_out[block.name])
    return graph


def allocate(f:Function,registers, *, rematerialize=()):
    """Deterministic global interference coloring; integers name spill slots."""
    need(isinstance(registers,(list,tuple))and all(isinstance(r,str)and r for r in registers)and len(set(registers))==len(registers),'invalid register set')
    graph=interference(f)
    rematerialize=set(rematerialize)
    constants={i.result for b in f.blocks for i in b.instructions if i.op=='const'}
    need(rematerialize<=constants,'only constants may be rematerialized')
    graph={v:ns-rematerialize for v,ns in graph.items() if v not in rematerialize}
    parent={v:v for v in graph};members={v:{v} for v in graph}
    def group(v):
        while parent[v]!=v:
            parent[v]=parent[parent[v]];v=parent[v]
        return v
    preferences=[]
    for b in f.blocks:
        for i in b.instructions:
            if i.op=='phi':preferences.extend((i.result,v)for p,v in i.imm)
            elif i.op in BINARY|{'copy','cast','neg','not','add_load'}:
                preferences.append((i.result,i.args[0]))
    for a,b in preferences:
        if a not in graph or b not in graph:continue
        a,b=group(a),group(b)
        if a==b or any(graph[v]&members[b]for v in members[a]):continue
        if a>b:a,b=b,a
        parent[b]=a;members[a].update(members.pop(b))
    groups={g:{group(n)for v in vs for n in graph[v]}-{g}for g,vs in members.items()}
    colors={};locations={};next_spill=0
    for g in sorted(groups,key=lambda v:(-len(groups[v]),v)):
        unavailable={colors[n]for n in groups[g]if n in colors}
        register=next((r for r in registers if r not in unavailable),None)
        if register is None:colors[g]=next_spill;next_spill+=1
        else:colors[g]=register
    for v in graph:locations[v]=colors[group(v)]
    # These IDs are never read from a location by the requesting backend.
    for v in rematerialize:locations[v]=registers[0] if registers else 0
    return locations
