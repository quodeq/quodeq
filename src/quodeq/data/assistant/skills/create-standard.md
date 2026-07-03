---
name: create-standard
description: Draft a new custom standard from a plain-language description
---
The user wants a new standard. Work in this order:
1. Ask (or infer from the conversation) the standard's goal, and check
   `list_standards` to avoid duplicating an existing one.
2. Structure it as 2-5 principles, each with 2-6 concrete, checkable
   requirements. Requirement text must describe verifiable behavior, not
   vague aspirations.
3. Call `draft_action` with `action_type: "create_standard"` and a payload:
   `{id, name, description, weight, source, principles: [{name, description,
   requirements: [{id, text, description, refs}]}]}`. Use a short kebab-case
   `id`, `weight: 1.0`, `source: "assistant"`.
4. Tell the user a draft card is ready for review; summarize the principles
   in one line each. Do not repeat the full JSON in your reply.
