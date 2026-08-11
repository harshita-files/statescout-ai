from graph.cache import VisitedCache

cache = VisitedCache()

cache.clear()

fp = "abc123"

print(cache.is_visited(fp, "click_login"))

cache.mark_visited(fp, "click_login")

print(cache.is_visited(fp, "click_login"))