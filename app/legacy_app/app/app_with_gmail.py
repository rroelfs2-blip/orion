from .main import app
import sys, traceback
try:
    from .routers import gmail as gmail_router
    app.include_router(gmail_router.router, prefix='', tags=['gmail'])
    print('[app_with_gmail] Gmail router ATTACHED', file=sys.stderr)
    try:
        pref = getattr(gmail_router.router, 'prefix', '')
        print(f'[app_with_gmail] router.prefix = {pref!r}', file=sys.stderr)
        for r in getattr(gmail_router.router, 'routes', []):
            try:
                methods = sorted(getattr(r, 'methods', []))
                print(f"[app_with_gmail] route: {r.path} methods={methods}", file=sys.stderr)
            except Exception as _:
                pass
    except Exception as _:
        pass
except Exception as e:
    print(f'[app_with_gmail] Gmail attach failed: {e}', file=sys.stderr)
    traceback.print_exc()
