from . import auth, configs, devices, graph, terminal

PUBLIC = [auth.router]
GUARDED = [devices.router, configs.router, graph.router]
SOCKETS = [terminal.router]
