# CephVR2.0

CephVR2.0 experiment-control software. Architecture and implementation contracts
have been reviewed. [ARCH-001](architecture.md#arch-001) now selects acquisition host
implementation following controller/supervisor development. Acquisition host implementation
and source review are complete; rig behavioral verification remains pending. See its [review record](reports/acquisition-implementation-review.md).
The [controller/supervisor review](reports/runtime-implementation-review.md)
and [rig test handoff](reports/runtime-rig-test-handoff.md) retain their validation limits.
See the [development guide](docs/development.md) for package layout, environment setup,
code checks and the distinction between local checks and Windows/rig verification.

## Start here

For development away from the rig, read the
[2026-09-29 hardware handoff](reports/rig-handoff-2026-09-29/README.md): current
identities, owner camera/rate assignments, driver-repair results, encoder limits,
dependency inventory and explicitly deferred installation inputs.

1. [Architecture overview and register](architecture.md): links to the authoritative
   [system contracts](docs/architecture/system-contracts.md) and backend records in
   `docs/architecture/`. Read these before changing a backend.
2. [Contributor and AI-agent guidance](AGENTS.md): how to use those decisions when
   changing the code and documentation.
3. [Backend discussion checklist](docs/backend-roadmap.md): the topics to cover for
   each backend.
4. [Experiment discussion guide](docs/experiment-backend-decisions.md): navigation
   for the first backend's decisions.
5. [Backend defaults](config/backends/README.md): commented TOML files containing
   the defaults selected so far, with one owner for shared policies. Controller, supervisor and
   acquisition startup validate their owning settings/policies; other backend loaders
   belong to their implementation stages.
6. [Shared control contracts](contracts/README.md) and
   [lifecycle tables](docs/experiment-control-transitions.md): the first contract
   draft, with backend-specific gaps marked. Compilation is not runtime validation;
   behavioral testing is planned on the rig after the main architecture is established.
7. [Development guide](docs/development.md): project setup and commands for the
   structure accepted in [ARCH-002](architecture.md#arch-002).

Refer to decisions by their permanent IDs and links, for example
[E01](docs/architecture/experiment.md#e01). Amend each decision in its owning architecture document and update the root register;
do not maintain decision copies in supporting guides.

## Reference projects

- `../reiter-cephalopod-vr-software/`: existing implementation and rig history.
- `../basler-vision-software/`: existing camera integration.

Reference code and historical measurements inform discussion; they do not
automatically establish CephVR2.0 requirements or current performance guarantees.
