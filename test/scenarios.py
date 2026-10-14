"""Runs the built Shortcut through test/simulate.py against a synthetic ELMS
feed and checks what lands in a fake Reminders list.

Usage: python3 test/scenarios.py build/unsigned.shortcut
"""
import json, os, re, sys
from datetime import datetime
from simulate import run, NY

SHORTCUT = sys.argv[1] if len(sys.argv) > 1 else "build/unsigned.shortcut"
FEED = open(os.path.join(os.path.dirname(__file__), "fixtures", "synthetic-elms.ics")).read()
LINK = "webcal://elms.umd.edu/feeds/calendars/user_abcdefghijklmnopqrstuvwxyz0123456789ABCD.ics"
NOW = datetime(2026, 9, 28, 9, 0, tzinfo=NY)
failures = []

def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        failures.append(name)

def by_title(rems, title):
    return [r for r in rems if r.title == title]

# ---- Run 1: first sync ------------------------------------------------
rems, files = [], {}
m = run(SHORTCUT, now=NOW, feed=FEED, reminders=rems, files=files, link=LINK)
print("notifications:", m.notifications)
for r in rems: print("  ", r, "| notes:", repr(r.notes))
titles = sorted(r.title for r in rems)
check("creates reminders in the window", len(rems) > 5, titles)
check("no duplicate for the repeated Project 2 UID", len(by_title(rems, "Project 2")) == 1, titles)
check("escaped commas and semicolons unescaped", "Essay 1: Rhetoric, Audience; Purpose" in titles, titles)
check("folded title rejoined", "Final Project Proposal" in titles, titles)
check("title keeps inner brackets, drops course label", "Office hours [moved to IRB 1116]" in titles, titles)
p2 = by_title(rems, "Project 2")[0]
check("course tag without section", p2.tags == ["CMSC216"], p2.tags)
check("UTC 03:59Z shows as 11:59 PM New York the day before", p2.due and p2.due.strftime("%Y-%m-%d %H:%M") == "2026-09-29 23:59", p2.due)
check("notes say the due time", p2.notes == "Due Tue Sep 29, 11:59 PM", p2.notes)
check("URL is the ELMS link", p2.url and "assignment_4410001" in p2.url, p2.url)
check("cross-listed course takes the first code", by_title(rems, "Problem Set 3") == [] or by_title(rems, "Problem Set 3")[0].tags == ["CMSC216"])
adv = by_title(rems, "Advising appointment")
check("item with no course code has no tag", adv and adv[0].tags == [], adv)
check("old item (Syllabus quiz, Sep 1) not created", not by_title(rems, "Syllabus quiz"))
check("far item (Lab 7, Nov 1) inside 60 days created", bool(by_title(rems, "Lab 7")))
check("all-day item has a date", by_title(rems, "Reading response 3")[0].due is not None)
check("alert off: no alerts", not any(r.alert for r in rems))
mem = json.loads(files["ELMS Reminders/memory.json"])
check("memory saved with every created item", len(mem["items"]) == len(rems), (len(mem["items"]), len(rems)))
n1 = len(rems)

# ---- Run 2: nothing changed ------------------------------------------
before = [(r.title, r.due, r.completed, r.notes) for r in rems]
m = run(SHORTCUT, now=NOW, feed=FEED, reminders=rems, files=files, link=LINK)
check("second run is a no-op", [(r.title, r.due, r.completed, r.notes) for r in rems] == before and len(rems) == n1)

# ---- Run 3: edits on both sides ---------------------------------------
by_title(rems, "WebAssign 5")[0].title = "WebAssign 5 (do early!)"            # you rename
hw4 = by_title(rems, "Homework 4")[0]; hw4.due = hw4.due.replace(day=5)       # you move
quiz = by_title(rems, "Quiz 3")[0]; rems.remove(quiz)                        # you delete
by_title(rems, "Midterm 1")[0].completed = True                              # you check off
feed3 = FEED
feed3 = feed3.replace("SUMMARY:Final Project Proposal [", "SUMMARY:Final Project Pitch [")  # ELMS renames
feed3 = feed3.replace("DTSTART:20261007T035900Z", "DTSTART:20261009T035900Z")                # ELMS moves Homework 4
feed3 = feed3.replace("SUMMARY:WebAssign 5 [", "SUMMARY:WebAssign Five [")                  # ELMS renames what you renamed
lab8 = re.search(r"BEGIN:VEVENT(?:(?!END:VEVENT)[\s\S])*?UID:event-assignment-4410009\r?\nEND:VEVENT\r?\n", feed3)
feed3 = feed3.replace(lab8.group(0), "")                                                     # ELMS drops Lab 8
m = run(SHORTCUT, now=NOW, feed=feed3, reminders=rems, files=files, link=LINK)
for r in rems: print("  ", r)
check("ELMS rename follows when you didn't rename", bool(by_title(rems, "Final Project Pitch")))
check("your rename survives ELMS's rename", bool(by_title(rems, "WebAssign 5 (do early!)")) and not by_title(rems, "WebAssign Five"))
hw4 = by_title(rems, "Homework 4")[0]
check("ELMS moving the date wins over your move", hw4.due.strftime("%Y-%m-%d %H:%M") == "2026-10-08 23:59", hw4.due)
check("deleted reminder isn't re-created", not by_title(rems, "Quiz 3"))
check("your checkmark is kept", by_title(rems, "Midterm 1")[0].completed)
lab8r = by_title(rems, "Lab 8")[0]
check("item dropped by ELMS gets completed", lab8r.completed)
check("…with a note", lab8r.notes.endswith("Removed from ELMS"), lab8r.notes)
check("no new duplicates", len(rems) == n1 - 1, (len(rems), n1))

# ---- Run 4: still no resurrection, idempotent -------------------------
before = [(r.title, r.due, r.completed, r.notes) for r in rems]
m = run(SHORTCUT, now=NOW, feed=feed3, reminders=rems, files=files, link=LINK)
check("next run changes nothing", [(r.title, r.due, r.completed, r.notes) for r in rems] == before)

# ---- Run 5: memory file lost: adopt, don't duplicate -------------------
files.clear()
m = run(SHORTCUT, now=NOW, feed=feed3, reminders=rems, files=files, link=LINK)
titles5 = [r.title for r in rems]
check("lost memory adopts existing reminders (no duplicates)", len(titles5) == len(set(titles5)) == n1, sorted(titles5))
check("…but a deleted one comes back (memory of deletes was lost)", bool(by_title(rems, "Quiz 3")))

# ---- Bad fetches never touch anything ----------------------------------
snap = [(r.title, r.due, r.completed) for r in rems]
m = run(SHORTCUT, now=NOW, feed="<html>Sign in</html>", reminders=rems, files=files, link=LINK)
check("a page instead of a calendar stops with a notification", m.notifications and "Couldn't read" in m.notifications[0] and [(r.title, r.due, r.completed) for r in rems] == snap)
m = run(SHORTCUT, now=NOW, feed="BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", reminders=rems, files=files, link=LINK)
check("an empty calendar stops without completing everything", [(r.title, r.due, r.completed) for r in rems] == snap and m.notifications)
m = run(SHORTCUT, now=NOW, feed=FEED, reminders=rems, files=files, link="")
check("no link: asks for it", m.notifications and "Paste your ELMS" in m.notifications[0])

# ---- Settings: alert at 09:00 on the due day, skip a course, no events --
rems2, files2 = [], {}
m = run(SHORTCUT, now=NOW, feed=FEED, reminders=rems2, files=files2, link=LINK,
        settings={"alert": "09:00", "skipCourses": "MATH240", "includeEvents": "no"})
check("skipCourses leaves MATH240 out", not any(r.tags == ["MATH240"] for r in rems2))
check("includeEvents no leaves calendar events out", not by_title(rems2, "Midterm 1") and not by_title(rems2, "Advising appointment"))
p2 = by_title(rems2, "Project 2")[0]
check("alert 09:00 sets the alert on the due day", p2.alert and p2.due.strftime("%Y-%m-%d %H:%M") == "2026-09-29 09:00", p2.due)
rems3, files3 = [], {}
m = run(SHORTCUT, now=NOW, feed=FEED, reminders=rems3, files=files3, link=LINK, settings={"alert": "-1d 18:00"})
p2 = by_title(rems3, "Project 2")[0]
check("alert -1d 18:00 sets it the evening before", p2.due.strftime("%Y-%m-%d %H:%M") == "2026-09-28 18:00", p2.due)

print("\n%d failure(s)" % len(failures))
sys.exit(1 if failures else 0)
