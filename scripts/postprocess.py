"""Fix what Cherri emits into the shapes real shortcuts use, then add the
import question for the ELMS link.

Usage: python3 scripts/postprocess.py "build/ELMS to Reminders.plist" build/unsigned.shortcut
"""
import plistlib, sys

NUMERIC = {0, 1, 2, 3}           # <, <=, >, >=
TEXTUAL = {4, 5, 8, 9, 99, 999}  # is, is not, begins/ends with, contains, does not contain
TEXT_COERCION = {'CoercionItemClass': 'WFStringContentItem', 'Type': 'WFCoercionVariableAggrandizement'}
NUMBER_COERCION = {'CoercionItemClass': 'WFNumberContentItem', 'Type': 'WFCoercionVariableAggrandizement'}

d = plistlib.load(open(sys.argv[1], 'rb'))
actions = d['WFWorkflowActions']

# Cherri compiles `@x = {}` to a Set Variable with no input. Give each one
# an explicit empty Dictionary, so later lookups and Set Dictionary Value
# start from a real dictionary.
import uuid
fixed = []
for a in actions:
    p = a['WFWorkflowActionParameters']
    if a['WFWorkflowActionIdentifier'] == 'is.workflow.actions.setvariable' and 'WFInput' not in p:
        u = str(uuid.uuid4()).upper()
        fixed.append({'WFWorkflowActionIdentifier': 'is.workflow.actions.dictionary',
                      'WFWorkflowActionParameters': {
                          'UUID': u, 'CustomOutputName': 'Empty Dictionary',
                          'WFItems': {'Value': {'WFDictionaryFieldValueItems': []},
                                      'WFSerializationType': 'WFDictionaryFieldValue'}}})
        p['WFInput'] = {'Value': {'OutputName': 'Empty Dictionary', 'OutputUUID': u, 'Type': 'ActionOutput'},
                        'WFSerializationType': 'WFTextTokenAttachment'}
        p['WFSerializationType'] = 'WFTextTokenAttachment'
    fixed.append(a)
empty_dicts = len(fixed) - len(actions)
actions[:] = fixed

def coerce(template, aggr):
    value = template['WFInput']['Variable']['Value']
    aggs = value.setdefault('Aggrandizements', [])
    if not any(a.get('Type') == 'WFCoercionVariableAggrandizement' for a in aggs):
        aggs.append(dict(aggr))

def only_attachment(token_string):
    """The single variable in a text field, as a content slot."""
    v = token_string['Value']
    assert v['string'] == '￼' and len(v['attachmentsByRange']) == 1, v
    return {'Value': next(iter(v['attachmentsByRange'].values())),
            'WFSerializationType': 'WFTextTokenAttachment'}

fixes = {'numeric': 0, 'text': 0, 'date': 0, 'int': 0, 'key': 0}

def dictionary_keys(v):
    """Cherri writes x['key'] on an untyped value as a property lookup;
    every one in this Shortcut means a dictionary key."""
    if isinstance(v, dict):
        for g in v.get('Aggrandizements', []):
            if g.get('Type') == 'WFPropertyVariableAggrandizement':
                key = g['PropertyName']
                g.clear()
                g.update({'DictionaryKey': key, 'Type': 'WFDictionaryValueVariableAggrandizement'})
                fixes['key'] += 1
        for x in v.values():
            dictionary_keys(x)
    elif isinstance(v, list):
        for x in v:
            dictionary_keys(x)
link_index = None
for i, a in enumerate(actions):
    ident = a['WFWorkflowActionIdentifier']
    p = a['WFWorkflowActionParameters']
    dictionary_keys(p)
    if ident == 'is.workflow.actions.conditional' and 'WFConditions' in p:
        for t in p['WFConditions']['Value']['WFActionParameterFilterTemplates']:
            c = t['WFCondition']
            if c in NUMERIC:
                rhs = t.pop('WFConditionalActionString', None)
                if isinstance(rhs, dict):
                    t['WFNumberValue'] = only_attachment(rhs)
                elif rhs is not None:
                    t['WFNumberValue'] = rhs
                coerce(t, NUMBER_COERCION)
                fixes['numeric'] += 1
            elif c in TEXTUAL:
                coerce(t, TEXT_COERCION)
                fixes['text'] += 1
    if ident == 'is.workflow.actions.format.date':
        v = p.get('WFDate')
        if isinstance(v, dict) and v.get('WFSerializationType') == 'WFTextTokenAttachment':
            p['WFDate'] = {'Value': {'attachmentsByRange': {'{0, 1}': v['Value']}, 'string': '￼'},
                           'WFSerializationType': 'WFTextTokenString'}
            fixes['date'] += 1
    if ident == 'is.workflow.actions.setters.reminders' and 'WFReminderContentItemIsCompleted' in p:
        p['WFReminderContentItemIsCompleted'] = int(p['WFReminderContentItemIsCompleted'])
        fixes['int'] += 1
    if ident == 'is.workflow.actions.gettext' and p.get('WFTextActionText') == 'PASTE_YOUR_ELMS_LINK':
        link_index = i

assert link_index is not None
actions[link_index]['WFWorkflowActionParameters']['WFTextActionText'] = ''
d['WFWorkflowImportQuestions'] = [{
    'ActionIndex': link_index,
    'Category': 'Parameter',
    'DefaultValue': '',
    'ParameterKey': 'WFTextActionText',
    'Text': 'Paste your ELMS calendar link. In ELMS, open Calendar, click Calendar Feed, and copy the link.',
}]
d['WFWorkflowName'] = 'ELMS to Reminders'
plistlib.dump(d, open(sys.argv[2], 'wb'), fmt=plistlib.FMT_BINARY)
print(fixes, 'empty dictionaries:', empty_dicts, 'import question on action', link_index)
