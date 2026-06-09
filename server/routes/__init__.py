from server.routes.auth import router as auth_router
from server.routes.trading import router as trading_router
from server.routes.monitor import router as monitor_router
from server.routes.settings import router as settings_router
from server.routes.emergency import router as emergency_router
from server.routes.market import router as market_router

routers = [auth_router, trading_router, monitor_router, settings_router, emergency_router, market_router]
