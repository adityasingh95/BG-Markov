# Testing BG-Markov — a walkthrough

**You do not need to know anything about programming to do this.** You need about 45 minutes,
a Windows computer, and a willingness to write down anything that looks odd.

**What you are testing:** whether the app works and makes sense. Not whether its medical
advice is correct — that is decided elsewhere, and nothing you see here is real.

**Everything on screen is invented.** Every page carries a red bar reading
**DEMO DATA — not her records**. If you ever *don't* see that bar, stop and tell the operator.

---

## What to write down

Keep a note as you go. For anything that surprises you:

| Where | What you did | What you expected | What happened |
|---|---|---|---|
| | | | |

**Please record confusion, not just errors.** "I couldn't tell which button saved it" is more
useful than a crash. A crash is obvious to everyone; confusion is only visible to you, the
first time, and you only get one first time.

---

## 1. Starting it

1. Open the **BG-Markov** folder.
2. Double-click **`Start BG-Markov.cmd`**.
3. A black window opens with text in it. **Leave it open.** That window *is* the program.
4. Wait. **The first time takes about five minutes** and prints almost nothing while it
   downloads. It has not frozen.
5. Your web browser should open by itself.

**If it asks you to install Python:** it will show you the exact command and wait for you to
type `YES`. That is expected. When it finishes it will tell you to close the window and start
again — do that.

- [ ] The browser opened by itself
- [ ] There is a **red DEMO DATA bar** at the top
- [ ] The page is readable — text large enough, buttons obviously buttons

> **To stop it at any point: close the black window.** That is the only way, and it is safe.

---

## 2. Look at every page

Use the navigation to visit each one. On every single page, check the red bar is there.

| Page | Should show |
|---|---|
| Home | recent meals, a way to log a new one |
| Log a meal | a form |
| Calculator | a dose suggestion with its working shown |
| Corrections | a list of correction doses |
| Basal | the long-acting insulin history |
| Operator | counts and percentages |
| Operator → Shadow report | how a prediction model is scoring |
| Operator → Profile | the patient's settings |

- [ ] All eight pages load
- [ ] All eight show the red bar
- [ ] Nothing shows a page of code, or the word "Traceback"

**Note anything you cannot understand the purpose of.** That is a finding, not a failure on
your part.

---

## 3. Log a meal

1. Go to **Log a meal**.
2. Fill it in as if you had eaten about an hour ago. Use any numbers that seem plausible.
3. Save it.

- [ ] It saved without an error
- [ ] The meal appears in the list afterwards
- [ ] The time shown is **the time you said you ate**, not the time you filled the form in

★ **That last one matters more than it looks.** The app must record when you *ate*, not when
you *typed*. If those are the same and you filled the form in an hour later, that is a
significant finding — write it down.

Now try to break it:

- [ ] Save with the form completely empty — does it explain what is missing, or just fail?
- [ ] Enter a blood glucose of `9999` — is it refused, and does the message make sense?
- [ ] Enter a meal time in the future — what happens?
- [ ] Press Save twice quickly — do you get **one** meal or two?

---

## 4. The calculator

1. Open **Calculator**.
2. Enter a blood glucose and some carbohydrate.

- [ ] It shows a number of units
- [ ] It shows **why** — you can see what it added up
- [ ] Entering a **low** blood glucose (say 65) refuses to suggest a dose, and says why

★ That refusal is deliberate and important. If it *does* suggest a dose at 65, stop testing
and tell the operator immediately.

---

## 5. Clearing and restoring

1. Close the black window to stop the app.
2. Double-click **`Reset to empty.cmd`**. Type `YES` when asked.
3. Double-click **`Start BG-Markov.cmd`** again.

- [ ] The app still starts
- [ ] The pages are now mostly empty — no meals, no history
- [ ] It does not crash on the empty pages

★ **Section 5 is the least-tested part of the app.** The empty screens are what a real first
day looks like, and they are the ones nobody sees during development. Look carefully.

Then put the data back:

4. Close the black window.
5. Double-click **`Restore demo data.cmd`**.
6. Start the app again.

- [ ] The demonstration data is back
- [ ] The red bar is back

---

## 6. On a phone-sized screen

If you can, make the browser window narrow — about a third of your screen.

- [ ] Nothing is cut off
- [ ] You never have to scroll **sideways**
- [ ] Buttons are still big enough to tap

---

## Already known — please don't spend time on these

These are known and being worked on. Finding them again is not useful:

- The shadow report may say **"No model has been fitted yet"** even when one has been.
- There is **no button to approve a model** on any screen.
- The profile page **does not refresh** after you save it — reload manually.
- The 90-day evaluation period **never starts**, so some readiness figures stay at zero.

`docs/RUNBOOK.md` §4 has the full list if you want it.

---

## When you're done

Send the operator your notes — including the things you were unsure about. **"This felt
confusing but I got there in the end"** is exactly the kind of finding that never gets
reported and always matters.
