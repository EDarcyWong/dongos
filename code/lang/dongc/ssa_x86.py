"""Instruction selection and cycle-safe parallel copies for the verified SSA IR."""
from collections import Counter
from . import ssa

REGISTERS=("rdi","rsi","rdx","rcx","r8","r9")


def assembly(function, *, registers=REGISTERS):
    from .ssa_lower import Unsupported
    ssa.verify(function)
    if not set(registers)<=set(REGISTERS):
        raise ValueError('backend registers must be SysV volatile and exclude scratch registers')
    constants={i.result:int(i.imm)for b in function.blocks for i in b.instructions if i.op=='const'}
    immediate={v for v,n in constants.items()if -(1<<31)<=n<(1<<31)}
    locations=ssa.allocate(function,registers,rematerialize=immediate)
    spills=max((n for v,n in locations.items()if v not in immediate and type(n)is int),default=-1)+1
    frame=(8*(spills+len(function.params))+15)&~15
    if frame+16>4096:raise Unsupported('optimized frame exceeds 4096 bytes')
    def slot(index):return f'qword [rbp-{8*(index+1)}]'
    def loc(v):return slot(locations[v])if type(locations[v])is int else locations[v]
    def src(v):return str(constants[v])if v in immediate else loc(v)
    def label(name):return '.S_'+name
    lines=['','align 16','$'+function.name+':','    push rbp','    mov rbp, rsp','    cld']
    if frame:lines.append(f'    sub rsp, {frame}')
    def move(dst,value):
        if dst==value:return
        if dst.startswith('qword ')and(value.startswith('qword ')or
                (value.lstrip('-').isdigit()and not -(1<<31)<=int(value)<(1<<31))):
            lines.extend((f'    mov rax, {value}',f'    mov {dst}, rax'))
        else:lines.append(f'    mov {dst}, {value}')
    def copies(pairs):
        pending={d:s for d,s in pairs if d!=s}
        while pending:
            sources=set(pending.values())
            ready=next((d for d in pending if d not in sources),None)
            if ready is not None:
                move(ready,pending.pop(ready));continue
            # Preserve one old location and break its cycle. R11 is never
            # allocated; RAX handles memory-to-memory moves independently.
            dest=next(iter(pending));move('r11',dest)
            pending={d:('r11'if s==dest else s)for d,s in pending.items()}
    args=('rdi','rsi','rdx','rcx','r8','r9')
    uses=Counter(v for b in function.blocks for i in b.instructions for v in i.args)
    uses.update(v for b in function.blocks for i in b.instructions if i.op=='phi'for _,v in i.imm)
    uses.update(v for b in function.blocks for v in b.terminator.args)
    # Home first so stack parameters and register cycles cannot overwrite any
    # incoming argument before it is captured. Entry cost stays outside loops.
    for index,v in enumerate(function.params):
        if uses[v]:move(slot(spills+index),args[index]if index<6 else f'qword [rbp+{16+8*(index-6)}]')
    for index,v in enumerate(function.params):
        if uses[v]:
            move(loc(v),slot(spills+index))
            if function.value_types[v]=='bool':
                move('rax',loc(v));lines.append('    movzx eax, al');move(loc(v),'rax')
    blocks={b.name:b for b in function.blocks}
    def edge_pairs(a,b):return [(loc(i.result),src(dict(i.imm)[a]))for i in blocks[b].instructions if i.op=='phi']
    deferred=[]
    def target(a,b):
        pairs=[(d,s)for d,s in edge_pairs(a,b)if d!=s]
        if not pairs:return label(b)
        name=f'.E_{a}_{b}'
        deferred.append((name,pairs,b));return name
    def comparison(i):
        signed=function.value_types[i.args[0]]=='i64'
        return {'==':'e','!=':'ne','<':'l'if signed else'b','<=':'le'if signed else'be',
                '>':'g'if signed else'a','>=':'ge'if signed else'ae'}[i.imm]
    inverse={'e':'ne','ne':'e','l':'ge','le':'g','g':'le','ge':'l','b':'ae','be':'a','a':'be','ae':'b'}
    def emit_cmp(i):
        left,right=src(i.args[0]),src(i.args[1])
        if left.lstrip('-').isdigit():move('rax',left);left='rax'
        if left.startswith('qword ')and right.startswith('qword '):move('r10',right);right='r10'
        lines.append(f'    cmp {left}, {right}')
    def address(arguments,indexed=None):
        base=src(arguments[0])
        if not(type(locations[arguments[0]])is str and arguments[0]not in immediate):
            move('r11',base);base='r11'
        if indexed is None:return f'[{base}]'
        scale,sign=indexed;index=src(arguments[1])
        if sign==1 and scale in(1,2,4,8)and type(locations[arguments[1]])is str and arguments[1]not in immediate:
            return f'[{base}+{index}*{scale}]'
        move('r10',index)
        if scale!=1:
            if scale<(1<<31):lines.append(f'    imul r10, {scale}')
            else:move('rax',str(scale));lines.append('    imul r10, rax')
        move('r11',base)
        lines.append(f"    {'add'if sign==1 else'sub'} r11, r10")
        return '[r11]'
    if function.blocks[0].name!=function.entry:lines.append(f'    jmp {label(function.entry)}')
    for index,b in enumerate(function.blocks):
        next_name=function.blocks[index+1].name if index+1<len(function.blocks)else None
        lines.append(label(b.name)+':')
        term=b.terminator
        real=[i for i in b.instructions if i.op not in {'phi','const','param'}]
        fused=real[-1]if real and term.op=='branch'and real[-1].op=='cmp'and real[-1].result==term.args[0]and uses[term.args[0]]==1 else None
        mask=None
        if fused and fused.imm in {'==','!='}and fused.args[1]in constants and constants[fused.args[1]]==0 and len(real)>1:
            prior=real[-2]
            if prior.op=='and'and prior.result==fused.args[0]and uses[prior.result]==1 and any(v in immediate for v in prior.args):
                mask=prior
        for i in b.instructions:
            if i.op in {'phi','param'}or i.result in immediate or i is fused or i is mask:continue
            if i.token:lines.append(f'    ; line {i.token.line}')
            destination=loc(i.result)
            if i.op=='const':move(destination,str(constants[i.result]));continue
            if i.op=='addr':
                operand=address(i.args,i.imm)
                accumulator=destination if type(locations[i.result])is str else'rax'
                lines.append(f'    lea {accumulator}, {operand}');move(destination,accumulator);continue
            if i.op in ssa.MEMORY:
                indexed=i.op in {'load_index','store_index','add_load'}
                operands=i.args[1:]if i.op=='add_load'else i.args
                operand=address(operands,i.imm if indexed else None)
                if i.op.startswith('load'):
                    accumulator=destination if type(locations[i.result])is str and i.typ!='bool'else'rax'
                    lines.append(f'    movzx eax, byte {operand}'if i.typ=='bool'else f'    mov {accumulator}, qword {operand}')
                    move(destination,accumulator)
                elif i.op.startswith('store'):
                    # Capture the address before using RAX for the stored value.
                    # Address components only use allocated registers/R10/R11.
                    move('rax',src(i.args[-1]))
                    lines.append(f"    mov {'byte'if i.typ=='bool'else'qword'} {operand}, {'al'if i.typ=='bool'else'rax'}")
                    if uses[i.result]:move(destination,'rax')
                else:
                    left=src(i.args[0])
                    accumulator=destination if type(locations[i.result])is str and not(destination in operand and destination!=left)else'rax'
                    move(accumulator,left);lines.append(f'    add {accumulator}, qword {operand}');move(destination,accumulator)
                continue
            if i.op=='cmp':
                emit_cmp(i);lines.extend((f'    set{comparison(i)} al','    movzx eax, al'));move(destination,'rax');continue
            left=src(i.args[0]);right=src(i.args[1])if len(i.args)>1 else None
            if destination==right and i.op in {'add','mul','and','or','xor'}:left,right=right,left
            direct=type(locations[i.result])is str and not(right==destination and left!=destination)
            accumulator=destination if direct else'rax';move(accumulator,left)
            if i.op in {'neg','not'}:lines.append(f'    {i.op} {accumulator}')
            elif i.op not in {'copy','cast'}:lines.append(f"    {'imul'if i.op=='mul'else i.op} {accumulator}, {right}")
            move(destination,accumulator)
        if term.op=='return':
            move('rax',src(term.args[0]))if term.args else lines.append('    xor eax, eax')
            lines.extend(('    cld','    mov rsp, rbp','    pop rbp','    ret'))
        elif term.op=='jump':
            copies(edge_pairs(b.name,term.targets[0]))
            if term.targets[0]!=next_name:lines.append(f'    jmp {label(term.targets[0])}')
        else:
            condition='ne'
            if mask:
                left,right=mask.args
                if left in immediate:left,right=right,left
                left=src(left)
                if left.lstrip('-').isdigit():move('rax',left);left='rax'
                lines.append(f'    test {left}, {src(right)}');condition=comparison(fused)
            elif fused:emit_cmp(fused);condition=comparison(fused)
            else:
                operand=src(term.args[0])
                if operand.lstrip('-').isdigit():move('rax',operand);operand='rax'
                if operand.startswith('qword '):lines.append(f'    cmp {operand}, 0')
                else:lines.append(f'    test {operand}, {operand}')
            fall=1 if term.targets[1]==next_name else 0
            other=1-fall
            code=condition if other==0 else inverse[condition]
            lines.append(f'    j{code} {target(b.name,term.targets[other])}')
            copies(edge_pairs(b.name,term.targets[fall]))
            if term.targets[fall]!=next_name:lines.append(f'    jmp {label(term.targets[fall])}')
    for name,pairs,to in deferred:
        lines.append(name+':');copies(pairs);lines.append(f'    jmp {label(to)}')
    return lines,{'registers':list(registers),'spills':spills,'frame_bytes':frame+16,
                  'locations':{str(k):v for k,v in locations.items()},'parallel_copy_scratch':'r11'}
