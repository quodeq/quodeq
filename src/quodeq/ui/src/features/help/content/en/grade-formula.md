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
| 1. Types, weighted | Severity weights for critical, major and minor types. A type is one requirement code per principle and severity, not one finding; the model's own type tag only groups findings that carry no requirement code. A readout shows how much a critical type weighs relative to a minor one. Live: the principle's critical, major and minor type counts and their weighted sum. |
| 2. Base | Strictness K, with the curve it draws. Live: the base score. |
| 3. Lift | Lift compress. Live: the principle's compliance types, the share of the gap they lift, and the lifted score. |
| 4. Ceiling and floors | Ceiling scale and the severity floors for minor-only and majors-without-criticals. Live: the ceiling, the floor, and the final score with its grade. |
| GRADE LABELS | Drag the dividers (or focus one and use the arrow keys) between CRITICAL, POOR, ADEQUATE, GOOD, and EXEMPLARY to move the grade thresholds. |

### Preview, then apply

The preview strip recomputes your selected project's latest run with the draft parameters and shows before and after, per dimension. Nothing is stored until you press **APPLY**, which saves the formula and rescores every run in every project. **RESET Q²** returns to the built-in defaults, also rescoring everything.

> **Where you see the effect**
>
> Rescoring updates run detail pages, the accumulated overview, trend charts, and project cards. The grade labels at the end of the FORMULA tab drive every gauge and badge in the app.

### Every parameter

| Key | Value |
| --- | --- |
| Severity weights | How much one type of each severity counts toward the weighted type count. Defaults 4.0 critical, 1.5 major, 0.25 minor; range 0.05 to 10. Moves stage 1 and everything after it. |
| Strictness K | How fast the base score falls as weighted types grow. Default 0.12; range 0.01 to 1. Higher is harsher. Moves stage 2. |
| Lift compress | How much compliance evidence can lift the base. Default 1.8; range 1 to 4. Higher means compliance lifts less. Moves stage 3. |
| Ceiling scale | How fast the maximum score falls with the log of the weighted type count. Default 0.5; range 0 to 2. Zero removes the ceiling. Moves stage 4. |
| Severity floors | The lowest score possible when the worst finding is minor (default 8.0) or major (default 5.0). A critical finding always floors at 0. Minor must stay at or above major. Moves stage 4. |
| Grade thresholds | Where Exemplary, Good, Adequate and Poor start on the 0 to 10 scale. Defaults 9, 7, 5, 3; strictly decreasing. Changes the label, never the number. |
| Dimension weights | Per-dimension multipliers for the project score, range 0.1 to 3, on when the toggle is on. Changes the project score only. |

Three more arrive as the scoring converges: the grouping key (what counts as one type), a volume term (whether many findings of one type weigh more than one), and an advisory weight (how much advisory findings count). Each gets its place in the stage it moves when it lands: the first two in row 1, the third in row 3.

The *Why This Grade* page explains the same four stages in words.

The formula never touches the insufficient-evidence gate. Principles with too little evidence stay Insufficient regardless of your settings.
