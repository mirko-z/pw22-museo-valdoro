"""Gestione utenti, riservata all'admin (RF05, RF06). Nessuna pagina front-end: si usa da Swagger."""

from fastapi import APIRouter

from app.core.deps import AdminUser, DbSession
from app.schemas.user import RoleUpdate, UserRead
from app.services.user_service import UserService

router = APIRouter(prefix="/api/users", tags=["utenti (admin)"])


@router.get("", response_model=list[UserRead], summary="Elenco degli utenti")
def list_users(_admin: AdminUser, db: DbSession) -> list[UserRead]:
    return [UserRead.model_validate(u) for u in UserService(db).list_users()]


@router.patch("/{user_id}/role", response_model=UserRead, summary="Cambia il ruolo di un utente")
def change_role(user_id: int, body: RoleUpdate, admin: AdminUser, db: DbSession) -> UserRead:
    return UserRead.model_validate(UserService(db).change_role(admin, user_id, body.role))
