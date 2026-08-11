from graph.graph_store import GraphStore
from graph.fingerprint import fingerprint

graph = GraphStore()

home_fp = fingerprint(
    "<h1>Home</h1>",
    "/",
    "Home"
)

login_fp = fingerprint(
    "<h1>Login</h1>",
    "/login",
    "Login"
)

graph.create_state_node(home_fp, "/")
graph.create_state_node(login_fp, "/login")

graph.create_action_edge(
    home_fp,
    login_fp,
    "click_login"
)

graph.close()

print("Edge created!")