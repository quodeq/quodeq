# Engine Context

This context defines the orchestration and pipeline management layer of Quodeq. The engine acts as the primary coordinator, managing the lifecycle of an evaluation run by bridging the analysis outputs with the final scoring and reporting stages.

**The engine is a consumer of the Core domain. It uses Core models to execute workflows but does not define the underlying domain rules.**

## Language

**Pipeline Runner**:
The component responsible for managing the full execution lifecycle of a `Run`. It orchestrates the transition from discovery through analysis to final scoring.

**Dimension Completion**:
A lifecycle milestone that occurs when all analysis for a specific ISO 25010 dimension is finished. This event triggers the dimension-specific scoring and report generation.

**Dimension Report**:
The finalized, persisted output for a completed dimension. It includes the calculated scores, grades, and the evidence collected during the analysis.

**Live Stream**:
A real-time data flow (typically via JSONL or similar stream formats) that provides immediate updates on findings and progress, enabling live UI feedback during the evaluation.

**Scoring Pipeline**:
The sequence of operations that takes raw evidence and applies the hierarchical scoring logic (defined in Core) to produce final results.

## Relationships

- The **Pipeline Runner** orchestrates the execution of multiple dimensions.
- Upon **Dimension Completion**, the engine triggers the **Scoring Pipeline**.
- The **Scoring Pipeline** produces the final **Dimension Report**.
- The **Live Stream** provides the continuous data needed for real-time visualization during the pipeline execution.

## Implementation Notes

- Much of the detailed execution logic (subagent management, stream parsing) is delegated to the **Analysis** layer. 
- The engine acts as the primary orchestrator that bridges analysis outputs with the final scoring and reporting stages, consuming **Core** entities to drive the process.
