"""Static checks on a built Shortcut: every action output and variable is
defined before it's read, and every If/Repeat block is closed.

Usage: python3 test/verify.py build/unsigned.shortcut
"""
import plistlib, sys
d = plistlib.load(open(sys.argv[1], 'rb'))
A = d['WFWorkflowActions']
uuids = {}
problems = []
stack = []
setvars = set(['Repeat Item', 'Repeat Index'])
def walk(v, i, path=''):
    if isinstance(v, dict):
        if v.get('Type') == 'ActionOutput':
            u = v.get('OutputUUID')
            if u not in uuids: problems.append(f'{i}: output {v.get("OutputName")} not defined before use')
            elif uuids[u] >= i: problems.append(f'{i}: output used before produced')
        if v.get('Type') == 'Variable' and 'Variable' not in v:
            n = v.get('VariableName')
            if n not in setvars: problems.append(f'{i}: variable {n} read before set')
        for k, x in v.items(): walk(x, i, path + '/' + str(k))
    elif isinstance(v, list):
        for x in v: walk(x, i, path)
for i, a in enumerate(A):
    p = a['WFWorkflowActionParameters']
    walk(p, i)
    ident = a['WFWorkflowActionIdentifier']
    if ident == 'is.workflow.actions.setvariable': setvars.add(p['WFVariableName'])
    if 'UUID' in p and 'WFControlFlowMode' not in p: uuids[p['UUID']] = i
    if 'WFControlFlowMode' in p:
        m = p['WFControlFlowMode']; g = p['GroupingIdentifier']
        if m == 0: stack.append((g, ident))
        elif m == 1:
            if not stack or stack[-1][0] != g: problems.append(f'{i}: otherwise without matching block')
        elif m == 2:
            if not stack or stack[-1][0] != g: problems.append(f'{i}: end without matching block')
            else:
                stack.pop()
                if 'UUID' in p: uuids[p['UUID']] = i
print('actions:', len(A), '| open blocks at end:', len(stack), '| problems:', len(problems))
for x in problems[:30]: print('  ', x)
print('import questions:', d.get('WFWorkflowImportQuestions'))

sys.exit(1 if problems or stack else 0)
