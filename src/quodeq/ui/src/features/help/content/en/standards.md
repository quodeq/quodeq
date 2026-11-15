## Custom Standards

The **Standards** tab is where you decide what quality means for your project. Browse, edit, import, and create the rules quodeq evaluates against.

### The standards table

Every standard is one row. The header counts how many are active.

| Key | Value |
| --- | --- |
| Name | The standard's name, with a source line under it: the bodies a built-in is based on (for example *ISO 25010, CISQ*), or a custom standard's own source. |
| Type | `iso`, `wcag` and `quodeq` for the standards quodeq ships, `custom` for yours. |
| Principles and Requirements | How many of each the standard holds. |
| Version | For a built-in, the version quodeq ships. For a custom standard, the date of its last change as YYYY.MM.DD; hover it to see when it was created and last updated. |
| Enabled | A star: filled when the standard is on for this project, outlined when it is off. Click the star, or anywhere on the row, to turn it on or off. |

At the end of each row sit **View** (or **Edit** for a custom standard), **Duplicate**, **Download**, and for a custom standard **Delete**, which asks you to type the name before it removes a standard that has content.

### Built-in standards

quodeq ships with managed standards for the six ISO 25010 dimensions plus Clean Architecture, DDD Design, WCAG 2.2 Accessibility and AI Integration Security. Their structure is **read-only** and marked as *Managed*, but their numeric thresholds are editable (see below). To turn one off for a project, click its star.

### Where your choices are kept

Which standards are on, and any threshold overrides, are kept per project on this machine, in `~/.quodeq/projects/<id>/standards.json`. quodeq never writes them into the repository it evaluates. A sub-project evaluated with **Scope** shares its parent's settings. Projects set up by an older quodeq kept them in `.quodeq/standards-visibility.json` and `.quodeq/standards-overrides.json` inside the repository; those files are copied once, the first time the project is used, and are then left as they are.

### Customizing thresholds

Many requirements carry a number: max function lines, max parameters, and so on. You can change these per project without cloning the standard. Select the requirement and edit the value in its **Thresholds** section, which shows the default and the allowed range. Out-of-range values are rejected, and *Reset to default* removes the override. Custom standards can declare thresholds too.

The tree marks customized requirements with a dot and shows the value in effect in each label. Standards with overrides get an *N thresholds customized* badge. Evaluations judge against your values, not the shipped ones.

Overrides live with the project's other standards settings on this machine (see above). If they are missing or malformed, the defaults apply; a scan never fails because of them.

Changing a threshold rewrites the rule for that dimension, so previously analyzed files show as pending until the next scan re-evaluates them. Restoring the previous value brings the earlier results back without a re-scan. Other dimensions are unaffected.

> **Not the grade thresholds**
>
> The boundaries in the *Grade Formula* editor decide how scores map to letter grades. These thresholds decide when code violates a requirement.

### Creating your own

1. Click **New standard**.
2. Name it. A standard is its own dimension: it gets its own score and its own card, beside the built-in ones.
3. Add **principles** (categories) and inside each, **requirements** (the specific checks).
4. Set a severity per requirement: `critical`, `major`, or `minor`.
5. Save. The next evaluation picks it up automatically.

Custom standards are fully editable and can be duplicated, exported, or deleted at any time.

### Sharing standards

When an evaluations repository is connected (see *Shared Repository*), custom standards can travel through it too. A band above the table names the shared repository and when it last synced; **pull** fetches it again. The table gains a **Sync** column and the header also counts the standards that exist only in the shared repository.

| Key | Value |
| --- | --- |
| published | Your copy and the shared copy are the same, with when it was published. |
| changed | You edited the standard since it was published. **publish** sends your version. |
| update available | The shared copy is newer than yours. **update** replaces your copy with it. |
| changed · update available | Both sides changed. **publish** and **update** are both offered, and each asks before it overwrites the other side: publishing replaces the shared copy, updating discards your changes. |
| remote | The standard exists only in the shared repository. Its row is plain, says *remote only* with when it was published, and offers **install**. |

A custom standard that was never shared has an empty Sync cell and a **share** button. Built-in standards show *built-in* and have no sync actions, because everyone already has them. Only one sync runs at a time; if one fails, the row says why.

An installed standard arrives turned off, so it never changes what your projects evaluate until you click its star. Turning standards on or off is never shared: each machine keeps its own choice per project. When you publish a project, the custom standards its runs were scored with are published with it. A standard whose shared copy is newer than yours is skipped, and a notice names the skipped ones so you can update them here.

### Importing

Click **Import** to load a JSON file you wrote yourself or got from elsewhere. quodeq validates the shape and tells you what is wrong if it does not parse.

### Standard schema

```text
{
  "id": "react-best-practices",
  "name": "React Best Practices",
  "version": "1.0",
  "principles": [
    {
      "id": "P-REACT-A11Y",
      "name": "Accessibility",
      "description": "Components must be accessible by default.",
      "requirements": [
        {
          "id": "R-A11Y-1",
          "rule": "Interactive elements expose semantic roles.",
          "severity": "major"
        }
      ]
    }
  ]
}
```

- **id** unique slug, used as the filename. It is also the name of the dimension the standard is scored as: a custom standard does not roll up into a built-in dimension, it stands beside them.
- **principles** categories of evaluation. Each principle becomes a card on the Explorer page.
- **requirements** specific checks. Each one is what the AI cites when it reports a finding.

### Generating standards with AI

Any chat AI (Claude, ChatGPT, Gemini) can write a standard for you. Paste the schema above, describe what you want evaluated, and ask for a JSON file. Save the result and import it. A starter prompt:

```text
Generate a quodeq standard JSON file for evaluating React
component best practices. Cover accessibility, performance,
state management, and error boundaries. Use this schema:
{ ...paste schema above... }
```
