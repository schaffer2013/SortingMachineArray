# Sorter Sequence Framework Requirements

## 1. Purpose

Define a reusable, editable machine-sequence framework for the card sorter.
This is a separate product track from the external registration service, even
though the first major test case is the registration workflow.

## 2. Background

The existing sorter application already has working machine behavior, but much
of its high-level flow is embedded directly in Python orchestration code:

- workflow-state transitions are hard-coded
- individual command sequences are built in dedicated functions
- adding a materially different workflow requires code edits across the runtime

The goal is not to replace safe typed machine primitives with arbitrary scripts.
The goal is to let the project define and redefine higher-level machine flows by
composing approved reusable steps.

## 3. Product Boundary

This framework belongs to the sorter project.

It should:

- define and execute machine programs
- remain independent of any one external service
- expose integration points for steps like asynchronous registration-job
  submission

It should not:

- become the permanent owner of collection data
- embed registration-service business logic that belongs outside the sorter
- allow unsafe arbitrary code execution through editable sequence files

## 4. Design Direction

Use a hybrid model:

- typed Python step implementations for safety and testability
- declarative sequence definitions for ordering, naming, parameters, and versioning

This allows machine flows to be reconfigured without making every step a
free-form script.

## 5. Required Capabilities

### 5.1 Sequence definitions

- Each sequence shall have a durable name and version.
- Sequence definitions shall be stored as configuration, not hard-coded only in
  application logic.
- A definition shall declare an ordered list of known step names and typed
  parameters.

### 5.2 Reusable steps

- Reusable steps shall be registered by stable names.
- Step implementations shall own hardware-safe logic, validation, and typed
  outputs.
- Initial reusable steps should cover:
  - pile grouping
  - pile scanning
  - pile probing
  - balancing / redistribution planning
  - card imaging
  - optional recognition
  - movement
  - asynchronous side-effect submission

### 5.3 Execution model

- The engine shall execute a named/versioned sequence against a runtime context.
- The context shall preserve:
  - current machine snapshot
  - calibration
  - per-step outputs
  - emitted execution events
- Sequence execution shall be inspectable and replayable enough for tests and
  operator diagnostics.

### 5.4 Future control flow

The framework should be designed to later support:

- conditionals
- loops
- retries
- explicit review states
- safe parallel side effects

These do not all need to ship in the first implementation if the initial
registration sequence can be represented honestly without them.

## 6. First Testbed Sequence: Registration

The first sequence shall model this registration flow:

1. Split piles into a 50/50 set of `unregistered` and `registered` piles.
2. Inspect every pile with the camera for occupancy.
3. Probe every pile to measure physical height.
4. Move all cards into the unregistered pile set while respecting maximum stack
   height and balancing pile heights.
5. For each unregistered card:
   - image top card
   - optionally run max-accuracy recognition
   - move the card to a registered pile while balancing destination height
   - emit an asynchronous registration-submission side effect

## 7. V1 Boundaries

The first implementation may be planning-oriented as long as it proves:

- a declarative sequence can be loaded
- typed reusable steps can execute in order
- outputs from one step can inform later steps
- the registration sequence can be represented clearly

Physical execution, remote submission, richer branching, and migration of the
existing sorter workflow may follow after the abstraction proves sound.

## 8. Acceptance Criteria

- A versioned registration sequence exists in config.
- The sequence can be loaded and executed through a common executor.
- Step outputs are recorded in a reusable execution context.
- The registration sequence expresses pile split, scan, probe, rebalance, and
  per-card pass planning.
- Tests demonstrate balanced group planning and sequence entrypoint behavior.

## 9. Follow-On Work

- Add richer control flow when the first real runtime sequence requires it.
- Connect step execution to real simulated movement.
- Add asynchronous integration-step abstractions for external service calls.
- Migrate existing hard-coded sorter workflows onto this framework once the
  registration sequence proves the model.
