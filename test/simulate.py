"""A small interpreter for the actions "ELMS to Reminders" uses, so the
compiled .shortcut can be run against a feed and a fake Reminders list.

It models Shortcuts as I understand it (single-variable fields pass the
object, other text fields interpolate, Repeat Index and list indexes are
1-based, Get Value for Key reads dots as a path). It checks the logic of
the compiled file, not Apple's runtime.
"""
import json
import plistlib
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
OBJ = "￼"


class Stop(Exception):
    pass


class Reminder:
    def __init__(self, title, notes="", url=None, due=None, tags=None, alert=False):
        self.title, self.notes, self.url, self.due = title, notes, url, due
        self.tags, self.alert, self.completed = tags or [], alert, False

    def __repr__(self):
        due = self.due.strftime("%Y-%m-%d %H:%M") if self.due else None
        return f"<{'x' if self.completed else ' '} {self.title!r} due={due} tags={self.tags}>"


def text_of(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, datetime):
        return v.strftime("%b %d, %Y at %I:%M %p")
    if isinstance(v, dict):
        return json.dumps(v)
    if isinstance(v, list):
        return "\n".join(text_of(x) for x in v)
    if isinstance(v, Reminder):
        return v.title
    if isinstance(v, re.Match):
        return v.group(0)
    return str(v)


def as_dict(v):
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip().startswith("{"):
        return json.loads(v)
    if isinstance(v, list) and v:
        return as_dict(v[0])
    return {}


def first(v):
    return v[0] if isinstance(v, list) and v else (None if isinstance(v, list) else v)


def has_value(v):
    return not (v is None or v == "" or v == [] )


def parse_date(v):
    v = first(v)
    if isinstance(v, datetime) or v is None:
        return v
    s = text_of(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            return d.astimezone(NY) if d.tzinfo else d.replace(tzinfo=NY)
        except ValueError:
            pass
    try:
        return datetime.strptime(s, "%b %d, %Y at %I:%M %p").replace(tzinfo=NY)
    except ValueError:
        return None


ICU = [("yyyy", "%Y"), ("MMM", "%b"), ("MM", "%m"), ("EEE", "%a"), ("dd", "%d"),
       ("HH", "%H"), ("mm", "%M"), ("h", "%-I"), ("a", "%p"), ("d", "%-d")]


def icu_format(d, pattern):
    out, i = "", 0
    while i < len(pattern):
        for k, v in ICU:
            if pattern.startswith(k, i):
                out += d.strftime(v)
                i += len(k)
                break
        else:
            out += pattern[i]
            i += 1
    return out


class Machine:
    def __init__(self, plist_path, *, now, feed_text, reminders, files):
        self.d = plistlib.load(open(plist_path, "rb"))
        self.A = self.d["WFWorkflowActions"]
        self.now, self.feed_text, self.reminders, self.files = now, feed_text, reminders, files
        self.vars, self.outputs = {}, {}
        self.notifications = []
        self.repeat = []  # stack of (item, index)
        q = self.d.get("WFWorkflowImportQuestions", [])
        self.answers = {qq["ActionIndex"]: qq for qq in q}

    # ---- values -------------------------------------------------------
    def ref(self, v):
        t = v.get("Type")
        if t == "ActionOutput":
            val = self.outputs.get(v["OutputUUID"])
        elif t == "Variable":
            n = v["VariableName"]
            if n == "Repeat Item":
                val = self.repeat[-1][0]
            elif n == "Repeat Index":
                val = self.repeat[-1][1]
            else:
                val = self.vars.get(n)
        elif t == "CurrentDate":
            val = self.now
        else:
            raise NotImplementedError(t)
        for g in v.get("Aggrandizements", []):
            if g["Type"] == "WFDictionaryValueVariableAggrandizement":
                val = self.dict_get(val, g["DictionaryKey"])
            elif g["Type"] == "WFCoercionVariableAggrandizement":
                c = g["CoercionItemClass"]
                if c == "WFNumberContentItem":
                    val = self.to_number(val)
                elif c == "WFStringContentItem":
                    val = text_of(first(val)) if isinstance(val, list) and len(val) == 1 else text_of(val)
            else:
                raise NotImplementedError(g)
        return val

    def val(self, p):
        if isinstance(p, dict) and "WFSerializationType" in p:
            st, v = p["WFSerializationType"], p["Value"]
            if st == "WFTextTokenAttachment":
                return self.ref(v)
            if st == "WFTextTokenString":
                s, atts = v["string"], v.get("attachmentsByRange", {})
                if s == OBJ and len(atts) == 1:
                    return self.ref(next(iter(atts.values())))
                spans = sorted(((int(k[1:].split(",")[0]), a) for k, a in atts.items()), reverse=True)
                for i, a in spans:
                    s = s[:i] + text_of(self.ref(a)) + s[i + 1:]
                return s
            if st == "WFDictionaryFieldValue":
                return {self.val(it["WFKey"]): self.dict_item(it) for it in v["WFDictionaryFieldValueItems"]}
            if st == "WFQuantityFieldValue":
                return v
            raise NotImplementedError(st)
        return p

    def dict_item(self, it):
        t = it["WFItemType"]
        x = self.val(it["WFValue"])
        if t == 3:
            return self.to_number(x)
        return text_of(x)

    @staticmethod
    def to_number(v):
        v = first(v)
        if isinstance(v, (int, float)):
            return v
        m = re.search(r"-?\d+(\.\d+)?", text_of(v))
        return float(m.group()) if m else None

    @staticmethod
    def dict_get(d, key):
        cur = d
        for part in text_of(key).split("."):
            cur = as_dict(cur).get(part)
            if cur is None:
                return None
        return cur

    # ---- conditions -------------------------------------------------------
    def check(self, t):
        c = t["WFCondition"]
        x = self.val(t["WFInput"]["Variable"])
        if c == 100:
            return has_value(x)
        if c == 101:
            return not has_value(x)
        if c in (0, 1, 2, 3):
            a, b = self.to_number(x), self.to_number(self.val(t["WFNumberValue"]))
            if a is None or b is None:
                return False
            return {0: a < b, 1: a <= b, 2: a > b, 3: a >= b}[c]
        a, b = text_of(x), text_of(self.val(t.get("WFConditionalActionString", "")))
        return {4: a == b, 5: a != b, 8: a.startswith(b), 9: a.endswith(b),
                99: b in a, 999: b not in a}[c]

    def cond(self, p):
        tv = p["WFConditions"]["Value"]
        results = [self.check(t) for t in tv["WFActionParameterFilterTemplates"]]
        return any(results) if tv["WFActionParameterFilterPrefix"] == 0 else all(results)

    # ---- running -------------------------------------------------------
    def block_end(self, i):
        g, depth = self.A[i]["WFWorkflowActionParameters"]["GroupingIdentifier"], 0
        mid = None
        for j in range(i + 1, len(self.A)):
            p = self.A[j]["WFWorkflowActionParameters"]
            if p.get("GroupingIdentifier") == g:
                if p["WFControlFlowMode"] == 1:
                    mid = j
                elif p["WFControlFlowMode"] == 2:
                    return mid, j
        raise ValueError("unclosed block")

    def run(self):
        try:
            self.run_range(0, len(self.A))
        except Stop:
            pass

    def run_range(self, start, end):
        i = start
        while i < end:
            a = self.A[i]
            ident = a["WFWorkflowActionIdentifier"].replace("is.workflow.actions.", "")
            p = a["WFWorkflowActionParameters"]
            if ident == "conditional" and p["WFControlFlowMode"] == 0:
                mid, close = self.block_end(i)
                if self.cond(p):
                    self.run_range(i + 1, mid if mid is not None else close)
                elif mid is not None:
                    self.run_range(mid + 1, close)
                i = close + 1
                continue
            if ident == "repeat.each" and p["WFControlFlowMode"] == 0:
                _, close = self.block_end(i)
                items = self.val(p["WFInput"])
                items = items if isinstance(items, list) else ([] if items is None else [items])
                for n, item in enumerate(items, 1):
                    self.repeat.append((item, n))
                    self.run_range(i + 1, close)
                    self.repeat.pop()
                i = close + 1
                continue
            out = self.step(ident, p, i)
            if "UUID" in p and "WFControlFlowMode" not in p:
                self.outputs[p["UUID"]] = out
            i += 1

    def step(self, ident, p, i):
        v = self.val
        if ident in ("comment", "nothing"):
            return None
        if ident == "showresult":
            self.shown = text_of(v(p["Text"]))
            return None
        if ident == "count":
            x = v(p["Input"])
            if p.get("WFCountType") == "Characters":
                return len(text_of(x))
            if x is None:
                return 0
            return len(x) if isinstance(x, (list, dict)) else 1
        if ident == "gettext":
            if i in self.answers:
                return self.answers[i]["Answer"]
            return v(p.get("WFTextActionText", ""))
        if ident == "dictionary":
            return dict(v(p["WFItems"])) if "WFItems" in p else self.to_dict_input(v(p.get("WFInput")))
        if ident == "detect.dictionary":
            return self.to_dict_input(v(p.get("WFInput")))
        if ident == "setvariable":
            self.vars[p["WFVariableName"]] = v(p["WFInput"]) if "WFInput" in p else None
            return None
        if ident == "notification":
            self.notifications.append(v(p["WFNotificationActionBody"]))
            return None
        if ident == "exit":
            raise Stop()
        if ident == "text.replace":
            s, find = text_of(v(p.get("WFInput"))), p.get("WFReplaceTextFind", "")
            rep = p.get("WFReplaceTextReplace", "")
            if p.get("WFReplaceTextRegularExpression"):
                return re.sub(find, lambda m: m.expand(rep.replace("$", "\\")), s, flags=re.M)
            return s.replace(find, rep)
        if ident == "downloadurl":
            assert text_of(v(p["WFURL"])).startswith("https://umd.instructure.com/feeds/"), v(p["WFURL"])
            return self.feed_text
        if ident == "setitemname":
            return v(p["WFInput"])
        if ident == "detect.text":
            return text_of(v(p["WFInput"]))
        if ident == "documentpicker.open":
            return self.files.get(p["WFGetFilePath"])
        if ident == "documentpicker.save":
            self.files[p["WFFileDestinationPath"]] = json.dumps(v(p["WFInput"]))
            return None
        if ident == "date":
            if p.get("WFDateActionMode") == "Current Date":
                return self.now
            raise NotImplementedError(p)
        if ident == "format.date":
            d = parse_date(v(p["WFDate"]))
            return icu_format(d, p["WFDateFormat"]) if d else ""
        if ident == "detect.date":
            d = parse_date(text_of(v(p["WFInput"])))
            return [d] if d else []
        if ident == "number":
            return self.to_number(v(p["WFNumberActionNumber"]))
        if ident == "adjustdate":
            d = parse_date(v(p["WFDate"]))
            q = p["WFDuration"]["Value"]
            mag = self.to_number(v(q["Magnitude"]))
            assert q["Unit"] == "days"
            delta = timedelta(days=mag)
            return d - delta if p["WFAdjustOperation"] == "Subtract" else d + delta
        if ident == "text.match":
            s = text_of(v(p["text"]))
            flags = 0 if p.get("WFMatchTextCaseSensitive", True) else re.I
            return [m for m in re.finditer(p["WFMatchTextPattern"], s, flags)]
        if ident == "text.match.getgroup":
            ms = v(p["matches"])
            m = first(ms) if isinstance(ms, list) else ms
            if not isinstance(m, re.Match):
                return None
            g = m.group(int(p["WFGroupIndex"]))
            return g
        if ident == "getitemfromlist":
            lst = v(p["WFInput"])
            lst = lst if isinstance(lst, list) else [lst]
            lst = [x.group(0) if isinstance(x, re.Match) else x for x in lst]
            if p["WFItemSpecifier"] == "First Item":
                return lst[0] if lst else None
            n = int(self.to_number(v(p["WFItemIndex"])))
            return lst[n - 1] if 0 < n <= len(lst) else None
        if ident == "getvalueforkey":
            d = v(p["WFInput"])
            if p.get("WFGetDictionaryValueType") == "All Keys":
                return list(as_dict(d).keys())
            return self.dict_get(d, v(p["WFDictionaryKey"]))
        if ident == "setvalueforkey":
            d = dict(as_dict(v(p["WFDictionary"])))
            d[text_of(v(p["WFDictionaryKey"]))] = v(p["WFDictionaryValue"])
            return d
        # ---- Reminders ----
        if ident == "filter.reminders":
            return list(self.reminders)
        if ident == "properties.reminders":
            r = first(v(p["WFInput"]))
            return {"URL": r.url, "Title": r.title, "Notes": r.notes,
                    "Is Completed": r.completed, "Due Date": r.due}[p["WFContentItemPropertyName"]]
        if ident == "setters.reminders":
            r = first(v(p["WFInput"]))
            prop = p["WFContentItemPropertyName"]
            if prop == "Title":
                r.title = text_of(v(p["WFReminderContentItemTitle"]))
            elif prop == "Due Date":
                r.due = parse_date(v(p["WFReminderContentItemDueDate"]))
            elif prop == "Notes":
                r.notes = text_of(v(p["WFReminderContentItemNotes"]))
            elif prop == "Is Completed":
                r.completed = bool(p["WFReminderContentItemIsCompleted"])
            return None
        if ident == "addnewreminder":
            alert = text_of(v(p["WFAlertEnabled"])) == "Alert"
            tags = v(p.get("WFTags"))
            r = Reminder(text_of(v(p["WFCalendarItemTitle"])), text_of(v(p.get("WFCalendarItemNotes"))),
                         text_of(v(p.get("WFURL"))) or None,
                         parse_date(v(p["WFAlertCustomTime"])) if alert else None,
                         [text_of(tags)] if has_value(tags) else [], alert)
            self.reminders.append(r)
            return r
        raise NotImplementedError(ident)

    def to_dict_input(self, x):
        if x is None:
            return {}
        return as_dict(x)


def run(path, *, now, feed, reminders, files, link, settings=None):
    m = Machine(path, now=now, feed_text=feed, reminders=reminders, files=files)
    for idx in m.answers:
        m.answers[idx]["Answer"] = link
    if settings:
        items = m.A[1]["WFWorkflowActionParameters"]["WFItems"]["Value"]["WFDictionaryFieldValueItems"]
        for it in items:
            k = it["WFKey"]["Value"]["string"]
            if k in settings:
                it["WFValue"]["Value"]["string"] = str(settings[k])
    m.run()
    return m
