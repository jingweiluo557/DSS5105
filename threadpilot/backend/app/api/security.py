"""场景 3.1–3.3：管理写入与模型工具分离。"""
import secrets
from fastapi import Depends, Header, HTTPException, Request


def require_admin(request: Request, authorization: str = Header(default='')) -> None:
    """场景 3.2：数据管理调用必须携带独立管理令牌。"""
    token = request.app.state.settings.data_api_token.get_secret_value()
    if not token or not secrets.compare_digest(authorization, 'Bearer ' + token):
        raise HTTPException(401, {'code': 'UNAUTHORIZED', 'message': 'A configured DATA_API_TOKEN is required.'})


def confirm_write(x_confirm_write: str = Header(default=''), admin: None = Depends(require_admin)) -> None:
    """场景 3.2：身份验证后还需显式确认本次写入。"""
    if x_confirm_write.lower() != 'true':
        raise HTTPException(409, {'code': 'CONFIRMATION_REQUIRED', 'message': 'Review the write, then submit X-Confirm-Write: true.'})


def resolve_role(supplied: str, settings) -> str | None:
    """Sprint 2: two workspace keys. Returns 'manager', 'planner' or None (rejected).
    With no manager key configured everyone with the workspace key is a manager (previous behaviour)."""
    token = settings.api_access_token.get_secret_value()
    manager = getattr(settings, 'manager_access_token', None)
    manager = manager.get_secret_value() if manager else ''
    if manager and secrets.compare_digest(supplied.encode(), manager.encode()):
        return 'manager'
    if token and secrets.compare_digest(supplied.encode(), token.encode()):
        return 'manager' if not manager else 'planner'
    if not token and not manager:
        return 'manager'
    return None


def require_manager(request: Request) -> None:
    """A confirmation or a settings change needs the manager key when one is configured."""
    if getattr(request.state, 'role', 'manager') != 'manager':
        raise HTTPException(403, {'code': 'MANAGER_REQUIRED', 'message': 'A manager key is required to confirm this. The preview stays open.'})
