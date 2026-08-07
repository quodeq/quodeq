## Grade Formula

The grade formula turns findings into scores and letter grades. You can tune every part of it: open **Settings**, find the *Grade formula* section, and press **open editor**. Changes preview live before anything is saved.

```figure
component: image
caption: The Grade Formula editor. Parameter tabs on top, live preview strip below.
alt: Grade Formula editor showing the preview strip with per-dimension gauges, the severity weight sliders, and the APPLY and RESET buttons
srcDark: @gradeFormulaDark
srcLight: @gradeFormulaLight
```

### The four tabs

| Key | Value |
| --- | --- |
| SEVERITY | Weight sliders for critical, major, and minor violation types. A readout shows how much a critical finding currently weighs relative to a minor one. |
| CURVE | Shape controls for the scoring curve: strictness K (how fast violations hurt), lift compress (how much compliance evidence can lift), and ceiling scale (the maximum score under violation load). |
| BOUNDARIES | Drag the dividers (or focus one and use the arrow keys) between CRITICAL, POOR, ADEQUATE, GOOD, and EXEMPLARY to move the grade thresholds. Severity floors below set the worst score possible when no critical findings exist. |
| DIMENSIONS | Optional per-dimension weights. When the toggle is off, the overall grade is a plain mean across dimensions. |

```figure
component: GradeFormulaCurveFigure
caption: Default severity weights set how hard each finding pushes a score down the curve. Solid line is the base score, dashed is the ceiling.
```

### Preview, then apply

The preview strip recomputes your selected project's latest run with the draft parameters and shows before and after, per dimension. Nothing is stored until you press **APPLY**, which saves the formula and rescores every run in every project. **RESET Q²** returns to the built-in defaults, also rescoring everything.

> **Where you see the effect**
>
> Rescoring updates run detail pages, the accumulated overview, trend charts, and project cards. The grade labels from the BOUNDARIES tab drive every gauge and badge in the app.

The formula never touches the insufficient-evidence gate. Principles with too little evidence stay Insufficient regardless of your settings.
