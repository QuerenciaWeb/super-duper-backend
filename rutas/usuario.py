from typing import List, Optional
from ninja import Router
from ninja.errors import HttpError

from .auth import AuthBearer
from crud.usuario import (
    obtener_usuario,
    obtener_usuarios,
    actualizar_usuario,
    eliminar_usuario,
)
from esquemas.usuario import UsuarioResponse, UsuarioUpdate

router = Router()

@router.get("/", response=List[UsuarioResponse], auth=AuthBearer())
def leer_usuarios(request, skip: int = 0, limit: int = 100, buscar: Optional[str] = None):
    return obtener_usuarios(skip=skip, limit=limit, buscar=buscar)

@router.get("/{id_usuario}", response=UsuarioResponse, auth=AuthBearer())
def leer_usuario_por_id(request, id_usuario: str):
    db_usuario = obtener_usuario(id_usuario)
    if not db_usuario:
        raise HttpError(404, "Usuario no encontrado")
    return db_usuario

@router.put("/{id_usuario}", response=UsuarioResponse, auth=AuthBearer())
def modificar_usuario(request, id_usuario: str, usuario_update: UsuarioUpdate):
    if request.auth.tipo_usuario != 'administrador':
        raise HttpError(403, "No tienes permisos de administrador para realizar esta acción.")
    db_usuario = actualizar_usuario(id_usuario, usuario_update)
    if not db_usuario:
        raise HttpError(404, "Usuario no encontrado o no se pudo actualizar")
    return db_usuario

@router.delete("/{id_usuario}", auth=AuthBearer())
def borrar_usuario(request, id_usuario: str):
    if request.auth.tipo_usuario != 'administrador':
        raise HttpError(403, "No tienes permisos de administrador para realizar esta acción.")
    db_usuario = eliminar_usuario(id_usuario)
    if not db_usuario:
        raise HttpError(404, "Usuario no encontrado")
    return {"message": f"Usuario con ID {id_usuario} eliminado correctamente"}
