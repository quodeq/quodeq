## Grade Formula

The grade formula turns findings into scores and letter grades. You can tune every part of it: open **Settings**, find the *Grade formula* section, and press **open editor**. Changes preview live before anything is saved.

### Three tabs

| Key | Value |
| --- | --- |
| FORMULA | The four stages a principle's score goes through, one row each. Every row has that stage's sliders on the left and, on the right, the numbers of one principle of your selected run, recomputed as you drag. Grade labels close the tab. |
| TYPES | Every requirement type of the run: dimension, principle, code, severity, the weight the draft gives it, findings now, findings at the baseline run, open or closed. Read-only; a dimension picker narrows it. |
| DIMENSIONS | Optional per-dimension weights. When the toggle is off, the overall grade is a plain mean across dimensions. |

### The four stage rows

Pick a dimension and a principle in the header. The right column of each row reads that principle from your run: with the saved formula until you touch a slider, then with the draft, the final row saying what the saved formula gave ("was"). Without a project with a finished run the sliders still work and the column says so.

| Key | Value |
| --- | --- |
| 1. Rules, weighted by spread | Severity weights for critical, major and minor rules. One row is one requirement of the standard, not one finding. A rule weighs more the more files it is broken in, and its severity is the model's rating for each finding; the standard's suggested severity is shown to the model in its checklist, never applied afterwards. Repeats of a finding in the same file do not count. A readout shows how much a critical rule weighs relative to a minor one. Live: how many rules the principle broke and their total weight. |
| 2. Base | Strictness K, with the curve it draws. Live: the base score. |
| 3. Lift | Lift compress. Live: the principle's compliance rules, the share of the gap they lift, and the lifted score. |
| 4. Ceiling and floors | Ceiling scale and the severity floors for a worst rule that is minor or major. Live: the ceiling, the floor, and the final score with its grade. |
| GRADE LABELS | Drag the dividers (or focus one and use the arrow keys) between CRITICAL, POOR, ADEQUATE, GOOD, and EXEMPLARY to move the grade thresholds. |

### Preview, then apply

The preview strip recomputes your selected project's latest run with the draft parameters and shows before and after, per dimension. Nothing is stored until you press **APPLY**, which saves the formula and rescores every run in every project. **RESET Q²** returns to the built-in defaults, also rescoring everything. When a Quodeq update changes the formula itself, a formula you saved under the older one is retired: scores use the new defaults, the editor opens on them, and you can tune again from there.

> **Where you see the effect**
>
> Rescoring updates run detail pages, the accumulated overview, trend charts, and project cards. The grade labels at the end of the FORMULA tab drive every gauge and badge in the app.

### Every parameter

| Key | Value |
| --- | --- |
| Severity weights | How much a rule of each severity weighs per unit of file spread. Defaults 4.0 critical, 2.0 major, 0.25 minor; range 0.05 to 10. The major weight is the knob that moves grades most; the minor weight decides who reaches Exemplary; the critical weight barely matters because criticals are rare. Moves stage 1 and everything after it. |
| Strictness K | How fast the base score falls as rule mass grows. Default 0.08; range 0.01 to 1. Higher is harsher: raising it by 20% moves a grade by about 0.3 on average. Moves stage 2. |
| Lift compress | How much compliance evidence can lift the base. Default 2.2; range 1 to 4. Higher means compliance lifts less. Moves stage 3. |
| Ceiling scale | How fast the maximum score falls with the log of the rule mass. Default 0.5; range 0 to 2. Zero removes the ceiling. It is the main knob for the Exemplary share. Moves stage 4. |
| Severity floors | The lowest score possible when the worst rule is minor (default 5.0) or major (default 3.0). A critical rule always floors at 0. Minor must stay at or above major. Moves stage 4. |
| Grade thresholds | Where Exemplary, Good, Adequate and Poor start on the 0 to 10 scale. Defaults 9, 7, 5, 3; strictly decreasing. Changes the label, never the number. |
| Dimension weights | Per-dimension multipliers for the project score, range 0.1 to 3, on when the toggle is on. Changes the project score only. |

The *Why This Grade* page explains the same four stages in words.

Thin evidence no longer blocks a score. A principle with few observations is scored, marked as thin, and weighs little in its dimension, because the dimension score weighs each principle by how much of the code it was observed on. The formula's settings do not change which principles are marked thin.
