# LLM Bridge Context

This context defines the communication layer between Quodeq and Large Language Models (LLMs). It covers how instructions are prepared, how providers are managed, and how the AI's output is interpreted.

## Language

**Provider**:
The abstraction layer that enables switching between different AI engines (e.g., OpenAI, Anthropic, or local models via Ollama). It handles API connections, authentication, and protocol translation.

**Prompt Assembly**:
The sophisticated process of constructing a complete evaluation instruction. It combines:
- **Standards Text**: The rules being enforced.
- **Files Block**: The source code, often enriched with line numbers and role information.
- **Project Shape**: Metadata about the project's nature (e.g., CLI, Library, Web Service) to provide situational awareness to the LLM.
- **Evaluation Rules**: Constraints on how the LLM should behave and report.

**Context Enrichment**:
The technique of adding "situational awareness" to a prompt (via `ProjectShape` and `Role Labels`) to reduce false positives and improve the reasoning of the LLM based on the target environment.

**Finding Schema**:
The strictly defined JSON structure that the LLM must follow when reporting a violation or compliance. This ensures that the raw text from the model can be reliably parsed into domain objects.

**Response Parsing (Judgment Extraction)**:
The process of extracting structured, actionable data from the LLM's response, converting raw text/JSON into canonical `Judgment` and `Finding` entities.

## Relationships

- The **Evaluator** uses the **Prompt Assembly** to create instructions.
- The **Prompt Assembly** consumes **Project Shape** and **Role Labels** to enrich the context.
- The **Provider** executes the assembled prompt and receives the raw response.
- The **Response Parser** transforms the provider's output into **Findings** for the rest of the application.
