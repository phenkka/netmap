from . import auth, configs, devices, graph, settings, terminal

PUBLIC = [auth.router]
GUARDED = [devices.router, configs.router, graph.router, settings.router]
SOCKETS = [terminal.router]
