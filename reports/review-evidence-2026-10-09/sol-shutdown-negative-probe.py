"""Review-only probe: restore old shutdown before/after checkpoint behavior."""
def pytest_configure(config):
    from cephvr.supervisor.shutdown import ShutdownCoordinator
    async def no_observer(self, until_ns):
        return None
    ShutdownCoordinator._watch_controller_loss = no_observer
