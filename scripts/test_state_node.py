from graph.graph_store import GraphStore
from graph.fingerprint import fingerprint

graph = GraphStore()

dom = "<button>Login</button>"
url = "/login"
ax = "Login Button"

fp = fingerprint(dom, url, ax)

graph.create_state_node(fp, url)

print("State node created!")

graph.close()