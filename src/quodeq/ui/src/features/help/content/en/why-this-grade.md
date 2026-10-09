## Why This Grade

A principle's score comes from four stages. Each stage reads one part of the grade formula, and every part can be changed in **Settings**, *Grade formula*.

| Key | Value |
| --- | --- |
| 1. Rules, weighted by spread | One row per requirement of the standard that was broken. A rule weighs more the larger the share of files it is broken in, so a rule broken everywhere weighs far more than the same rule broken once. The standard's class for the requirement (critical, major or minor) sets its severity, not the model's rating. Repeats of a finding in the same file do not count. |
| 2. Base | The total weight of the broken rules sets the base score on a curve that falls fast at first and flattens later. Strictness K sets how fast. |
| 3. Lift | Compliance lifts the base toward 10. It is counted in the same unit as the violations, by how many files follow each rule, and compressed so a few good examples do not erase real problems. |
| 4. Ceiling and floor | The ceiling falls with the log of the total rule weight, so a principle with many broken rules cannot reach the top on compliance alone. The worst severity present sets a floor. The score is the lifted value held between floor and ceiling. |

The grade label is the threshold band the final score falls in. A principle with few observations is scored and marked thin: the number is honest, but it rests on little evidence. The dimension score weighs principles by how much of the code they were observed on, so a thin principle moves its dimension very little.

**Settings**, *Grade formula* shows these stages on your own run, with the parameters that move each one: pick a dimension and a principle, and the numbers follow the sliders.

> **What moves the score**
>
> Fixing a rule in every file moves the score most; fixing it in one file of many moves it a little. Dismissing a finding or fixing it never lowers that principle's score; a dimension re-weights its principles by how much was observed, so it can move either way by a little. A model repeating itself changes nothing.

The dimension score is the mean of its principles, each weighted by its observation. The project score is the weighted mean of dimension scores (*DIMENSIONS* tab).
