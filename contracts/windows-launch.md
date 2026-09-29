# Windows managed-process launch contract

Authority: [E06/E08](../docs/architecture/system-contracts.md). This shared contract
covers every owned CephVR process on the rig, including controller/supervisor/GUI,
acquisition, VR, tracking, workers and native helpers. SpikeGLX is a separate remote
application and is never contained or killed here. No launcher is implemented or
Windows behavior verified.

## Application containment and automatic failure shutdown

The persistent application launcher creates one unnamed application Job Object with
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE before starting supervisor. The launcher stays
outside it and retains its sole non-inherited handle; never duplicate it into a child.
Place supervisor in this job at creation; its descendants inherit membership with
breakaway disabled. Register exact controller/supervisor process handles with the
launcher before operational work. Reuse the native launch helper; no second session
controller or polling/heartbeat service is introduced.

Controller/supervisor process exit, or a survivor's authenticated authority-loss
notification under E08, starts one nonextendable shutdown deadline. A local bounded
launcher control pipe carries generation-bound process registration and shutdown
notifications; it conveys no scientific data, policy updates, session mutation or
operator lease. The launcher reads `[shutdown].application_shutdown_backstop_s` from
supervisor_config.toml once at startup and retains it with the process handles before
acknowledging launch readiness; nothing is forwarded at Setup. OS process-handle exit
observations still work when both authorities fail. Reject wrong generations;
duplicate notifications cannot extend the first deadline.

The backstop must cover the health silence timeout, the larger of Cancel Setup or
trial-finalization initial budget plus the shared recovery budget, and three
sequential exit groups (backends/descendants concurrently, controller+GUI,
supervisor), each graceful_process_exit_s + terminate_process_exit_s. Setup computes
that sum from the TOMLs it loads and blocks with both numbers if the startup
backstop is smaller; editing the backstop requires an application restart. A
survivor preserves earlier absolute cleanup deadlines and does not spend this outer
allowance restarting work. Emergency reporting and E12's stop margin fit
within existing cleanup bounds. If shutdown already began, use the earlier deadline.

The survivor invokes ordinary full shutdown automatically and requests graceful child
exit before escalation. The launcher waits for an empty application job or the outer
deadline. At expiry it calls TerminateJobObject for remaining members, retaining the
handle to observe empty membership before closing it; kill-on-close is the crash/exit
backstop. Retain the application guard until job membership is empty; process absence
is not file-closure evidence. Keep unfinished markers/reports for next startup. Explicit
ShutdownApplication uses the same backstop, activated on retained shutdown intent.
Intentional GUI closure alone never closes the application job. Launcher crash itself
can close the last handle immediately; that is a crash backstop, not a graceful
shutdown guarantee. Remote SpikeGLX stopping depends on the controller's client and the link.

Windows requires a supported nested-job hierarchy and creation-time assignment;
unsupported hosts fail startup rather than run uncontained. Semantics follow
[Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and [nested jobs](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs).

## Launch registration and partial children

Supervisor `PlanLaunch` retains command ID, owner/child generations, executable,
role, work/parent operation, containment and stop method before creation. It opens a
unique per-launch Job Object and supplies its identity to the existing launching
owner. That job identifies partial children even if the owner fails before reporting
the returned PID. Keep its handle at the supervisor and owner; kill-on-close and
breakout are off for these per-launch jobs. They nest inside the application job;
only the launcher-held outer job has kill-on-close enabled. All job names/handles stay
internal, not in scientific configuration or session metadata.

The version-specific Windows launcher adapter uses CreateProcessW with an explicit
executable, a restricted inherited-handle list, CREATE_SUSPENDED and the creation-time
job-list attribute. Require the platform capability; never substitute a create-then-
assign sequence with an uncontained gap. Each planned job initially receives exactly
one child. Record process creation time + PID, retaining a process handle rather
than trusting PID later. Launch Python with the explicit installed interpreter and
a versioned `-m` bootstrap entry point using ordinary process arguments. Transfer
only declared registered bootstrap descriptors; never pickle objects or depend on
private multiprocessing/Popen internals. Named resources and typed RPCs already
carry worker state. The parent imports/initializes no child SDK or GPU runtime.
Native encoders/helpers use the same launch/containment helper without Python
bootstrap or CephVR heartbeat requirements; their owners monitor actual progress.

Owner `ConfirmLaunch` submits exact process evidence. Supervisor verifies membership,
executable and retained identity, and observes children through its existing process
monitor/job enumeration. A partial child discovered in the dedicated planned job
remains a tracked starting obligation, never Ready. If no unambiguous process can be
matched, retain the blocker and reconcile; do not guess from executable names/PIDs.
Creation failure reports no child only after checking the planned job is empty.

For Python, resume only the bootstrap after OS confirmation; it binds the private
endpoint and completes endpoint registration before importing SDK/GPU runtimes or
accepting operational work. Keep bootstrap imports limited to control/clock/launch
registration; device initialization starts only after registration acknowledgement.
The endpoint confirmation includes its [host-clock descriptor](host-clock.md);
validate and retain it before marking that Python process operational.
Native helpers resume only after confirmation and their owning backend's launch
boundary; acquisition FFmpeg launches at A08's ScheduleTrial acceptance and receives no frames before T. VR encoder launch/container
bindings remain owned by V12, not A08. Register each helper's actual graceful-stop
method and exact process handle; do not assume every helper uses stdin EOF.
Bootstrap work has no device/output-file/session side effects. Registration stages
share one deadline: PlanLaunch plus the health silence timeout (15 s, E08),
including application startup; expiry is a launch failure. Owner/supervisor loss
starts E08's automatic graceful shutdown; closing an inner job is never the cleanup
algorithm. The outer launcher job remains the bounded final backstop above. Close retained job/process handles only when obligations
and descendant exit are established. No extra readiness state is introduced.

## VR integration and failure ownership

The supervisor plans/launches the VR coordinator; that coordinator plans/launches
its renderer, which owns the saving-enabled FFmpeg child (V12). Each worker uses this
same helper for any subprocess it owns, including decoder/codec helpers where selected. A library
that creates unmanaged descendants cannot bypass registration or containment; bind
its supported managed launch path before allowing it in prepared execution. In-process
libraries remain owned resources, not additional registered processes.

Reuse the existing per-launch job and parent-tree membership checks within the one
application job; do not add backend-specific alternative containment mechanisms. Membership never proves display/GPU or
file readiness. A partial renderer launch cannot open stimulus windows before its
process registration is confirmed. Startup Idle additionally follows the
[VR startup contract](vr/startup.md); recording-only work remains saving-dependent.

Inner-job closure never requests termination. Supervisor loss invokes E06/E08's
automatic full shutdown; exact-generation termination follows graceful cleanup, with
the outer application job enforcing the final deadline. Process exit proves neither successful output closure nor that a
surviving descendant released a device. Preserve independent cleanup obligations.

Acquisition-specific FFmpeg stdin, file-sync and SDK rules remain in
[Windows resources](acquisition/windows-resources.md); VR resource bindings remain
in its [contract worklist](vr/README.md). No GPU isolation or throughput guarantee is
created by process containment.
