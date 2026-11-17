"""Engineering kernel: pure, deterministic calculation code shared by every module.

Rules for this package (enforced by tests/unit/test_architecture.py):
  * no imports from FastAPI, Starlette, SQLAlchemy or any ``app.modules`` package;
  * every formula line carries the clause it comes from;
  * every limit is recorded as a check with an OK / Not OK verdict.
"""
