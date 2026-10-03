## Why This Grade

A principle's score comes from four stages. Each stage reads one part of the grade formula, and every part can be changed in **Settings**, *Grade formula*.

| Key | Value |
| --- | --- |
| 1. Types, weighted | Findings are grouped into types: one requirement code per principle and severity. Each type weighs by its severity (critical, major, minor). More distinct types weigh more; more findings of the same type do not. |
| 2. Base | The weighted type count sets the base score on a curve that falls fast at first and flattens later. Strictness K sets how fast. |
| 3. Lift | Compliance evidence lifts the base toward 10 by the share of compliance types among all types, compressed so a few good examples do not erase real problems. |
| 4. Ceiling and floor | The ceiling falls with the log of the weighted type count, so a principle with many open types cannot reach the top on compliance alone. The worst severity present sets a floor. The score is the lifted value held between floor and ceiling. |

The grade label is the threshold band the final score falls in. A principle with too little evidence for its project size is *Insufficient* and has no score.

**Settings**, *Grade formula* shows these stages on your own run, with the parameters that move each one: pick a dimension and a principle, and the numbers follow the sliders.

> **What moves the score**
>
> Closing a whole requirement type moves the score. Fixing ten findings of one type that still has an eleventh does not. The Overview counts open types for that reason.

The dimension score is the mean of its graded principles. The project score is the weighted mean of dimension scores (*DIMENSIONS* tab).
