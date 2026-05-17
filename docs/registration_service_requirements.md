# Registration Service Software Requirements

## 0. Background For A New Team

### 0.1 What this ecosystem is

This document describes a new service that will work with a separate physical
machine project: a card-sorting robot for **Magic: The Gathering** trading cards.

Magic: The Gathering is a collectible card game with tens of thousands of
distinct card printings. A card may share the same gameplay identity across many
printings while differing by:

- set
- collector number
- artwork
- frame treatment
- language
- foil status
- promo treatment

For collection-building, "this is Lightning Bolt" is not always precise enough.
The system often needs to know **which exact printing** of Lightning Bolt is in
hand.

### 0.2 What Scryfall is

The ecosystem uses **Scryfall** identifiers as the practical identity standard
for Magic cards:

- A card concept may have an Oracle identity.
- A specific physical printing has a Scryfall printing ID.

The new service should ultimately create collection records at the **exact
printing** level, not just at the broad card-name level.

### 0.3 What already exists outside this new service

There is an existing sorter project that:

- controls machine motion, vacuum pickup, lights, and camera capture
- knows about piles of cards arranged on the machine bed
- can image top cards
- can run a recognition subsystem called **fuzzy-enigma**
- has a local operator web console
- persists run evidence and card-recognition metadata

The sorter project is intentionally a machine-control application. It should not
grow into the permanent source of truth for long-lived collection registration
data. The new service described here is meant to own that registration and
validation responsibility.

### 0.4 Why this service is needed

Fast machine motion and exact card validation have different constraints:

- The sorter should keep moving cards efficiently.
- Exact-printing validation may be slower, more computationally expensive, and
  sometimes require human judgment.

Therefore the sorter should submit image evidence and keep working, while the
new service performs deeper validation in the background and presents uncertain
cases to a human reviewer.

The registration service is also the owner of the raw submitted image after
intake. The sorter sends image data to the service; the service stores it,
associates it with a collection card record, and manages that record through
its unverified-to-verified lifecycle.

### 0.5 Plain-language example

Suppose the sorter images a card and thinks:

- "This is probably **Lightning Bolt**."

The registration service may later determine:

- "Yes, it is Lightning Bolt, but the exact printing is not yet known."

A reviewer may inspect the raw photo next to candidate printings and conclude:

- "This is Lightning Bolt from set `M11`, collector number `146`, non-foil."

Only then is the card considered fully registered in the collection database.

## 1. Scope And Product Boundary

### 1.1 What this document covers

This document covers the **new registration service**:

- intake of image-based registration jobs from a sorter
- background recognition and validation work
- human review of unresolved cards
- creation of trusted collection records

### 1.2 What this document does not cover

This document does **not** define the sorter-side machine-sequence framework.
That related but separate product track is specified in:

- `docs/sorter_sequence_requirements.md`

The two systems are intended to integrate, but they should be designed and
implemented independently enough that:

- the registration service can be built and deployed without rewriting the
  sorter runtime
- the sorter can adopt reusable machine sequences without requiring the
  registration service to exist first

### 1.3 First delivery target

The first thing to build from this document is the **registration service**.
Sorter-side integration may be developed in parallel, but it is a separate
deliverable and should not be treated as a hidden prerequisite for the service
architecture.

## 2. Purpose

Define the requirements for a separate registration and validation service that
works alongside the card sorter. The service may run on the same host as the
sorter or on another machine on the same local network.

Its job is to accept card-image evidence from the sorter, run background
max-accuracy validation, support human review of unresolved cards, and produce a
collection database whose card identities and printings are fully trusted.

## 3. Product Goals

- Create a trustworthy registration pipeline for physical card collections.
- Preserve the sorter as the machine-control system and keep the registration
  service as a separate concern.
- Allow fast machine throughput while slower validation work happens in the
  background.
- Support exact-printing resolution, not only card-name recognition.
- Keep the human review path explicit, auditable, and efficient.

## 4. Non-Goals

- Replacing the sorter runtime or machine-control stack.
- Requiring the registration service to run on the same host as the sorter.
- Requiring immediate final validation before the sorter can continue moving
  cards.
- Permanently retaining raw card images after validation in the first version.
- Building a general-purpose collection-management product beyond the
  registration workflow.

## 5. V1 Product Decisions

### 5.1 Identity-hint authority model

Sorter-provided identity hints are **priors, not authority**.

- A sorter-side Scryfall ID or recognition result should help rank service-side
  candidates.
- It must not override stronger evidence from max-accuracy validation or human
  review.
- The service shall preserve both the sorter hint and the service result so
  disagreements are inspectable.

### 5.2 Human validation policy

For v1, every card must receive **human final validation** before it becomes a
trusted collection record.

- `machine_validated` means the service believes it has a strong answer.
- `human_validated` means the exact printing is final and trusted.
- Machine-only auto-finalization is intentionally deferred until enough field
  evidence exists to define safe thresholds.

### 5.3 When exact printing is not determinable

If the exact printing cannot be determined from the available image:

- the card remains unresolved
- it does not enter the trusted collection database
- the reviewer may mark it as needing re-image or insufficient evidence
- the system may retain a weaker provisional card-identity hypothesis internally,
  but that provisional state is not a final collection record

### 5.4 Exact-printing search ownership

The registration service owns the **workflow and final truth** for exact-printing
resolution.

- Fuzzy-enigma is a recognition dependency that returns candidates and evidence.
- The service owns queue state, reviewer workflow, final decisions, and the
  canonical collection record.
- Exact-printing search UX belongs to the service, even if it uses fuzzy-enigma
  or Scryfall-like data sources under the hood.

### 5.5 V1 deployment target

The first implementation should optimize for **same-host deployment** with the
sorter, while keeping an HTTP API boundary so deployment on another LAN machine
remains possible later.

This implies:

- local-first operational simplicity for v1
- no hard-coded filesystem sharing assumptions between projects
- network-safe interfaces from the beginning

### 5.6 Suggested v1 technical posture

Unless a stronger scaling need appears, the first version should favor a light,
durable stack suitable for a household or single-operator installation:

- HTTP API service
- relational persistence
- local durable job queue / worker
- filesystem-backed raw-image storage

The requirements do not mandate a framework, but a v1 design should justify any
heavier distributed stack with a concrete need.

### 5.7 Meaning of collection database

For v1, the service is the **trusted registration ledger and system of record**
for cards it receives and later finalizes.

- Other applications may later ingest or sync from it.
- A future broader collection-management product may exist.
- This service should still retain enough canonical identity and provenance data
  to stand on its own as the authoritative registration source.
- A submitted card shall be represented in a collection immediately as an
  **unverified collection card**, then transition to a **verified collection
  card** once exact identity is finalized.

## 6. System Context

### 6.0 Physical sorter vocabulary

For readers unfamiliar with the machine:

- A **pile** is a physical stack position on the machine bed.
- The machine can move cards from one pile to another with a suction pickup.
- The machine uses a camera to inspect the top card of a pile.
- The machine may probe a pile to estimate its physical stack height.
- A registration run temporarily divides piles into:
  - **unregistered piles**: cards not yet processed in the current registration run
  - **registered piles**: cards already imaged and handed off to the registration
    service

### 6.1 Sorter responsibilities

The sorter:

- divides available piles into `unregistered` and `registered` groups
- scans pile occupancy
- probes pile heights
- redistributes cards into unregistered piles while respecting configured maximum
  stack height
- images each unregistered top card
- optionally performs an immediate recognition attempt
- moves the card into registered piles while evening their heights
- submits raw image evidence and any expected identity hint to the registration
  service asynchronously

### 6.2 Registration service responsibilities

The service:

- receives card-registration jobs from one or more sorters
- stores job metadata and raw image payloads on the service side
- creates unverified collection-card records associated with a target collection
- runs background max-accuracy fuzzy-enigma validation
- exposes queue and job state to the sorter web console
- supports human adjudication and exact-printing correction
- promotes unverified collection-card records into verified records once final
  validation is complete
- removes raw images once a card is fully validated unless retention is enabled

## 7. Primary Users

### 7.1 Operator

Uses the sorter web console to monitor registration runs, inspect validation
status, and review unresolved cards.

### 7.2 Reviewer

Uses the validation UI to compare the captured image against expected printings,
correct errors, and finalize exact identity decisions.

### 7.3 Maintainer

Configures service endpoints, retention policy, fuzzy-enigma mode, storage, and
collection exports.

## 8. Core Workflow

1. A registration run begins.
2. The sorter splits piles into an equal number of `unregistered` and
   `registered` piles.
3. The sorter camera checks whether each pile is empty.
4. The sorter probes each pile and records top height.
5. The sorter moves all cards into unregistered piles while:
   - staying under a configured maximum pile height
   - distributing cards to keep unregistered pile heights as even as practical
6. For each card in unregistered piles:
   - image the top card
   - optionally run immediate recognition
   - move the card into the registered pile set, distributed evenly
   - submit the raw image plus target collection context and any expected
     Scryfall identity hint to the registration service without blocking machine
     movement
7. The registration service:
   - persists the registration job and raw image
   - creates an unverified card record associated with the requested collection
   - runs max-accuracy fuzzy-enigma validation in the background
   - classifies confidence and review state
8. A reviewer resolves non-final cards through the validation UI.
9. Once exact identity and printing are finalized:
   - the existing unverified card record is marked verified and finalized in the
     collection database
   - the raw image is deleted by default

## 9. Functional Requirements

### 9.1 Service discovery and connectivity

- The sorter shall support a configurable registration-service base URL.
- The service may be hosted locally or elsewhere on the LAN.
- The sorter shall expose service-health state in the web console.
- The sorter shall continue registration runs when the service is temporarily
  unavailable by queueing unsent submissions locally.
- The service shall expose a health endpoint suitable for polling.

### 9.2 Registration job submission

- The sorter shall submit one job per card image.
- The sorter shall submit jobs with an HTTP `POST`.
- Each job shall include:
  - sorter run ID
  - card sequence number within the run
  - target collection ID
  - raw image payload
  - capture timestamp
  - source pile and destination pile
  - immediate recognition result when available
  - expected Scryfall ID or equivalent identity hint when available
  - optional expected printing metadata when available
- The service shall return a stable job ID.
- The service shall persist the raw image on receipt and create an unverified
  collection-card record associated with the target collection.
- Job submission shall be idempotent for retried requests from the same sorter
  card event.

### 9.3 Background validation

- The service shall run fuzzy-enigma in a max-accuracy mode independent of the
  sorter’s fast-path recognition mode.
- The service shall retain:
  - expected identity hint
  - service recognition result
  - candidate alternatives
  - confidence
  - exact-printing evidence when available
  - debug metadata needed for later inspection
- The service shall classify each job into at least:
  - `pending`
  - `processing`
  - `machine_validated`
  - `human_review_required`
  - `human_validated`
  - `rejected`
- In v1, `machine_validated` shall not by itself create a trusted collection
  record.

### 9.4 Human review UI

- The UI shall show:
  - raw captured image
  - current expected card/printing
  - machine candidate(s)
  - confidence and review reason
  - original sorter hint when present
- The UI shall display the raw image and expected exact printing side by side.
- “Expected exact printing” means the service should display a canonical image
  or equivalent reference for the currently believed exact Scryfall printing so
  the reviewer can compare the physical photo against the intended target.
- The reviewer shall be able to mark at least:
  - exactly correct
  - right card, wrong printing
  - wrong card
  - unreadable / insufficient evidence
- The reviewer shall be able to request or record:
  - re-image required
  - exact printing unresolved
- The UI shall provide guided next steps for “right card, wrong printing,” such
  as set, collector number, border, foil/non-foil, language, frame, or art clues
  needed to find the exact printing.
- The reviewer shall be able to search and choose the correct exact printing.
- The system shall preserve the original machine result and the final human
  correction separately.

### 9.5 Collection database

- The service shall create one collection-card record at intake time for each
  submitted card image.
- Newly created collection-card records shall:
  - be associated with a target collection
  - be marked `unverified`
  - reference the raw submitted image
  - reference the originating registration job
- Once exact identity is finalized, the same card record shall transition to
  `verified`.
- A verified record shall capture:
  - exact Scryfall printing ID
  - card name
  - set code
  - collector number
  - foil/non-foil when known
  - language when known
  - source run/job IDs
  - validation source (`machine` or `human`)
  - validation timestamp
- The service shall support querying cards by registration job, run, and final
  identity.
- The service shall support querying cards by collection and verification state.

### 9.6 Raw-image retention

- The service shall store raw images on the collection service after intake.
- The service shall delete raw images after final validation by default.
- The service shall support a future configurable retention policy when storage
  capacity allows.
- Deletion shall not remove metadata required for auditability.

### 9.7 Sorter web-console integration

- The sorter web console shall show:
  - service health
  - submission queue size
  - recent registration jobs
  - validation counts by state
- The web console shall link into the service validation UI for pending review
  items.
- The web console shall surface whether a sorter-side expected recognition was:
  - exactly matched
  - card-correct but printing-wrong
  - card-wrong
  - still unresolved

## 10. Non-Functional Requirements

### 10.1 Reliability

- Registration submissions shall survive temporary service outages.
- Background validation shall be resumable after service restarts.
- Human decisions shall be durable and auditable.

### 10.2 Performance

- Sorter motion must not block on remote max-accuracy validation.
- The service shall support asynchronous job processing.
- The UI shall remain usable with large review queues.

### 10.3 Security

- The service shall support authenticated requests from sorter clients.
- Image access shall be restricted to authorized users/services.
- LAN deployment shall not assume a trusted open network.

### 10.4 Observability

- The service shall expose logs and metrics for:
  - jobs accepted
  - jobs processed
  - validation outcomes
  - queue depth
  - retry counts
  - image deletion counts

## 11. Suggested API Surface

### 11.1 Sorter-facing

- `GET /health`
- `POST /registration-jobs`
- `GET /registration-jobs/{job_id}`
- `GET /runs/{run_id}/registration-summary`
- `GET /collections/{collection_id}/cards?verification_state=...`

### 11.2 Reviewer-facing

- `GET /review-queue`
- `GET /registration-jobs/{job_id}/review`
- `POST /registration-jobs/{job_id}/decision`
- `GET /cards/search`

## 12. Data Model Sketch

### 12.1 RegistrationJob

- `job_id`
- `sorter_run_id`
- `sorter_card_seq`
- `raw_image_uri`
- `collection_id`
- `captured_at`
- `source_pile`
- `destination_pile`
- `sorter_expected_scryfall_id`
- `sorter_recognition_payload`
- `service_recognition_payload`
- `status`
- `created_at`
- `updated_at`

### 12.2 ReviewDecision

- `decision_id`
- `job_id`
- `reviewer_id`
- `decision_kind`
- `final_scryfall_id`
- `notes`
- `created_at`

### 12.3 CollectionCard

- `collection_card_id`
- `job_id`
- `collection_id`
- `verification_state`
- `raw_image_uri`
- `scryfall_id`
- `name`
- `set_code`
- `collector_number`
- `foil`
- `language`
- `validation_source`
- `validated_at`

## 13. Remaining Open Questions

- What authentication model should be used even in same-host-first deployment?
- What local retry queue should the sorter use when the service is unavailable?
- Should raw images be retained for a configurable grace period after final
  validation before deletion?
- What exact set of card/printing clues should be mandatory in the human-review
  form for the first release?

## 14. Acceptance Criteria for a First Project

- A sorter can submit card-image jobs to a remote service endpoint.
- The service can process jobs asynchronously with fuzzy-enigma max-accuracy
  validation.
- The sorter web console can show service health and validation summaries.
- A reviewer can resolve pending jobs through side-by-side image comparison.
- Finalized decisions create collection records.
- Raw images are deleted after final validation under the default retention
  policy.

## 15. Suggested First Milestones

### Milestone 1: service skeleton

- health endpoint
- persistent database
- job submission endpoint
- local raw-image storage
- basic job-status API

### Milestone 2: background validation

- fuzzy-enigma integration in max-accuracy mode
- asynchronous queue worker
- candidate/result persistence
- machine validation states

### Milestone 3: human review

- review queue
- side-by-side comparison UI
- exact / wrong-printing / wrong-card / unreadable decisions
- final collection-card creation

### Milestone 4: sorter integration

- authenticated sorter client
- retry-safe asynchronous submission
- sorter-console service health and queue summary
- links from sorter UI into unresolved review items

### Milestone 5: retention and operations

- raw-image deletion after finalization
- metrics and logs
- backup/export strategy for finalized collection data
