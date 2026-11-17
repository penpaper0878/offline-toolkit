"""Imports every ORM model so ``Base.metadata`` is complete (used by Alembic and the tests)."""

from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.projects import models as project_models  # noqa: F401
from app.modules.structural import models as structural_models  # noqa: F401
