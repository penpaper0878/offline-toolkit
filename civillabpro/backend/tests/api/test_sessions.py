"""Every route's database session ends before its response is sent, so a client never reads ahead of its own write."""

from fastapi.routing import APIRoute

from app.core.database import get_db
from app.main import create_app


def _sessions(dependant):
    for dep in dependant.dependencies:
        if dep.call is get_db:
            yield dep
        yield from _sessions(dep)


def _routes(routes):
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        inner = getattr(r, "original_router", None)  # an included router
        if inner is not None:
            yield from _routes(inner.routes)


def test_every_session_is_scoped_to_the_path_operation():
    routes = list(_routes(create_app().routes))
    checked = 0
    for route in routes:
        for dep in _sessions(route.dependant):
            checked += 1
            assert dep.scope == "function", f"{route.path}: Depends(get_db) must use scope='function' (commit before the response)"
    assert checked > 20
