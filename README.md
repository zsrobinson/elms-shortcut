# ELMS to Reminders

An Apple Shortcut that keeps a Reminders list in step with your [ELMS](https://umd.instructure.com) (Canvas) calendar feed. It runs on your iPhone with no server and no account. It works with any Canvas calendar feed; nothing beyond the link handling is specific to UMD.

- New ELMS assignments become reminders, tagged with the course code (`CMSC216`). Each one is due when it's due, with the ELMS link attached.
- If ELMS moves a due date, the reminder moves too, even if you moved it yourself.
- If ELMS renames an item, the reminder follows, unless you've renamed it.
- Reminders you delete stay deleted. Your checkmarks are never touched.
- If ELMS drops an item, its reminder is checked off with the note "Removed from ELMS".

## Install

You need iOS 18 or later.

1. **Get your ELMS link.** In ELMS, open **Calendar**, click **Calendar Feed** (bottom right), and copy the link. Treat it like a password: anyone with it can read your due dates.
2. **Make a list** in Reminders, for example "Assignments".
3. **Make the memory folder.** In Files, go to iCloud Drive → Shortcuts and make a folder named `ELMS Reminders`.
4. **Import the Shortcut.** Download [`ELMS to Reminders.shortcut`](ELMS%20to%20Reminders.shortcut) on your iPhone and open it. Tap **Set Up Shortcut**, paste your link when asked, then tap **Add Shortcut**.
5. **Point it at your list.** Open the Shortcut in the editor:
   - in **Add New Reminder**, tap the list and choose yours;
   - in **Find All Reminders**, tap **Add Filter**, then **List**, **is**, and your list. This one's optional; without it the Shortcut just runs slower.
6. **Run it once** by tapping it. Choose **Always Allow** for ELMS, Reminders and the Shortcuts folder.
7. **Make it automatic.** In Shortcuts, go to **Automation** → **+** and add:
   - **Time of Day**, for example at 7 AM, 1 PM, 7 PM and 11 PM, each set to **Run Immediately** with **Notify When Run** off;
   - **App** → Reminders → **Is Opened** → **Run Immediately**.

## Settings

The **Dictionary** at the top of the Shortcut holds the settings:

| Key | Default | Meaning |
|---|---|---|
| `alert` | `off` | `off`, `due` (alert at the due time), `09:00` (that time on the due day), or `-1d 18:00` (that time the day before) |
| `skipCourses` | `none` | Course codes to ignore, separated by spaces, like `UNIV100 CMSC000` |
| `includeEvents` | `yes` | Whether to include ELMS calendar events as well as assignments |
| `debug` | `no` | `yes` shows a report at the end of each run. It never includes your link. |

The window, 14 days back to 60 days ahead, is set in the two **Adjust Date** steps. Tap the numbers to change it.

To start over, delete `Shortcuts/ELMS Reminders/memory.json` in Files. The next run adopts the reminders you already have rather than making duplicates. Reminders you deleted may come back, though.

## How it works

Each run fetches the feed, reads each event's UID, title, course and due date, and compares three things:
- the feed;
- your list;
- `memory.json`, which records what ELMS said at the last sync.

That comparison is how it tells your edits apart from ELMS's. Reminders are matched by the ELMS link stored in their URL field. Reminders without one, such as ones you add yourself, are left alone.

If the download isn't a calendar, or the calendar comes back empty, the Shortcut stops without changing anything.

## Building from source

The Shortcut is written in [Cherri](https://github.com/electrikmilk/cherri) (v1.3.2) in [`src/elms-to-reminders.cherri`](src/elms-to-reminders.cherri).

```sh
scripts/build.sh                      # needs cherri on PATH
CHERRI=/path/to/cherri scripts/build.sh
```

The script:
1. compiles the source;
2. runs [`scripts/postprocess.py`](scripts/postprocess.py), which fixes the places where Cherri's output differs from what Shortcuts writes and adds the import question for the link;
3. checks the result with [`test/verify.py`](test/verify.py) and [`test/scenarios.py`](test/scenarios.py);
4. signs it, with `shortcuts sign` on a Mac or otherwise with RoutineHub's HubSign service.

The scenarios run the compiled file through a small interpreter ([`test/simulate.py`](test/simulate.py)) against a synthetic ELMS feed. They check:
- creating reminders, and that a second run changes nothing;
- edits on both sides;
- deletes and dropped items;
- a lost memory file;
- bad downloads;
- each setting.

The interpreter models Shortcuts as closely as I could. It isn't Apple's runtime, so test on a phone too.

The Reminders actions aren't part of Cherri, so they're defined at the top of the source. Their parameter names come from real shortcuts, harvested by [unqforge](https://github.com/anupml/unqforge).

## License

[MIT](LICENSE)
