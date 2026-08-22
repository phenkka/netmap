from . import (
    apply,
    auth,
    backup,
    baseline,
    configs,
    devices,
    graph,
    journal,
    settings,
    terminal,
)

PUBLIC = [auth.router]
GUARDED = [
    devices.router,
    configs.router,
    graph.router,
    settings.router,
    journal.router,
    apply.router,
    baseline.router,
    backup.router,
]
SOCKETS = [terminal.router]
