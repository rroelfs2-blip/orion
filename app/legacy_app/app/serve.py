from .main import app
from .routes.system import router as system_router
from .routes.connectors import router as connectors_router
app.include_router(system_router)
app.include_router(connectors_router)
from .routes.selftest import router as selftest_router
app.include_router(selftest_router)
