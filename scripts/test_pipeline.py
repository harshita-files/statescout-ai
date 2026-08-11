from graph.fingerprint import fingerprint,normalize_state
from graph.graph_store import GraphStore
from graph.cache import VisitedCache

graph = GraphStore()
cache = VisitedCache()

# Only for testing
cache.clear()

states = [
    {
        "dom": "<h1>Home</h1>",
        "url": "/",
        "ax": "Heading Home"
    },
    {
        "dom": "<h1>Login</h1>",
        "url": "/login",
        "ax": "Heading Login"
    },
    {
        "dom": '<h1 id="abc123456">Home</h1>',
        "url": "/",
        "ax": "Heading Home"
    }
]

print(normalize_state(
    "<h1>Home</h1>",
    "/",
    "Heading Home"
))

print("--------------------------------")

print(normalize_state(
    '<h1 id="abc123456">Home</h1>',
    "/",
    "Heading Home"
))

for state in states:

    fp = fingerprint(
        state["dom"],
        state["url"],
        state["ax"]
    )

    action = "visit"

    if cache.is_visited(fp, action):
        print(f"Skipping {state['url']} (already visited)")
        continue

    graph.create_state_node(fp, state["url"])

    cache.mark_visited(fp, action)

    print(f"Stored {state['url']}")

graph.close()