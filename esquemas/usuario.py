from ninja import Schema
from pydantic import EmailStr
from typing import Optional
from datetime import datetime


# ============================================================
# Esquemas de Usuario (ya existían)
# ============================================================
class UsuarioBase(Schema):
    nombre: str
    correo: EmailStr

class UsuarioCreate(UsuarioBase):
    dni: str
    contrasena: str
    tipo_usuario: str = 'normal'
    token: Optional[str] = None

class UsuarioUpdate(Schema):
    nombre: Optional[str] = None
    correo: Optional[EmailStr] = None
    contrasena: Optional[str] = None
    tipo_usuario: Optional[str] = None
    token: Optional[str] = None

class UsuarioResponse(Schema):
    dni: str
    nombre: str
    correo: EmailStr
    tipo_usuario: str
    token: Optional[str] = None

class UsuarioLogin(Schema):
    correo: EmailStr
    contrasena: str

class Token(Schema):
    access_token: str
    token_type: str


# ============================================================
# Esquemas de Token de Invitación (nuevos)
# ============================================================
class TokenInvitacionCreate(Schema):
    correo_destino: EmailStr
    tipo_usuario: str = 'administrador'
    dias_expiracion: int = 7  # Días hasta que expire el token

class TokenInvitacionResponse(Schema):
    id: int
    correo_destino: str
    token: str
    tipo_usuario: str
    usado: bool
    fecha_expiracion: datetime
