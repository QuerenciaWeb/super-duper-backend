import os
from datetime import datetime, timedelta
from typing import Optional, List

from ninja import Router
from ninja.security import HttpBearer
from jose import JWTError, jwt
from django.contrib.auth.hashers import check_password
from django.http import Http404
from ninja.errors import HttpError
from django.db import transaction
from django.utils import timezone

from modelos.models import TokenInvitacion
from crud.usuario import crear_usuario, obtener_usuario_por_correo
from esquemas.usuario import (
    Token, UsuarioCreate, UsuarioLogin, UsuarioResponse,
    TokenInvitacionCreate, TokenInvitacionResponse
)

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

router = Router()

class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            correo: str = payload.get("sub")
            if correo is None:
                return None
            
            # Buscar el usuario en la BD
            usuario = obtener_usuario_por_correo(correo)
            if usuario is None:
                return None
            return usuario  # Esto se asigna a request.auth
        except JWTError:
            return None

# Helper para crear el Token JWT
def crear_token_acceso(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/register", response=UsuarioResponse, url_name="registrar")
def registrar(request, usuario: UsuarioCreate):
    # Validar si el correo electrónico ya está registrado
    db_usuario = obtener_usuario_por_correo(usuario.correo)
    if db_usuario:
        raise HttpError(400, "El correo electrónico ya está registrado.")
    
    # 1. Si se registra como normal, no se requiere ningún token
    if usuario.tipo_usuario == 'normal':
        return crear_usuario(usuario)
        
    # 2. Si se registra como administrador, sí se requiere token
    if not usuario.token:
        raise HttpError(400, "Se requiere un token de invitación para registrarse como administrador.")
        
    # 2.1. Validar contra el token de administrador por defecto ('ADMIN123')
    if usuario.token == "ADMIN123":
        usuario.tipo_usuario = 'administrador'
        return crear_usuario(usuario)
        
    # 2.2. Validar contra la base de datos de tokens de invitación
    with transaction.atomic():
        try:
            token_db = TokenInvitacion.objects.select_for_update().get(token=usuario.token)
        except TokenInvitacion.DoesNotExist:
            raise HttpError(400, "El token de invitación no existe.")
            
        if token_db.usado:
            raise HttpError(400, "Este token de invitación ya ha sido utilizado.")
            
        if token_db.correo_destino.lower() != usuario.correo.lower():
            raise HttpError(400, "El correo electrónico no coincide con el destinatario autorizado para este token.")
            
        if token_db.fecha_expiracion < timezone.now():
            raise HttpError(400, "El token de invitación ha expirado.")
            
        if token_db.tipo_usuario != 'administrador':
            raise HttpError(400, "Este token no autoriza el registro como administrador.")
            
        usuario.tipo_usuario = 'administrador'
        nuevo_usuario = crear_usuario(usuario, token_invitacion=token_db)
        
        token_db.usado = True
        token_db.save()
        
        return nuevo_usuario

@router.post("/login", response=Token, url_name="login")
def login(request, credenciales: UsuarioLogin):
    usuario = obtener_usuario_por_correo(credenciales.correo)
    if not usuario or not check_password(credenciales.contrasena, usuario.contrasena):
        raise HttpError(401, "Correo o contraseña incorrectos")
    
    tiempo_expiracion = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token_acceso = crear_token_acceso(
        data={"sub": usuario.correo}, expires_delta=tiempo_expiracion
    )
    
    return {"access_token": token_acceso, "token_type": "bearer"}

@router.get("/me", response=UsuarioResponse, auth=AuthBearer())
def perfil_usuario(request):
    # request.auth contiene el objeto Usuario devuelto por AuthBearer.authenticate()
    return request.auth


# ============================================================
# Gestión de Tokens de Invitación (solo administradores)
# ============================================================

@router.post("/generar-token", response=TokenInvitacionResponse, auth=AuthBearer())
def generar_token_invitacion(request, datos: TokenInvitacionCreate):
    """
    Genera un token de invitación para que un nuevo usuario pueda
    registrarse como administrador. Solo accesible para administradores.
    """
    # Verificar que el usuario autenticado sea administrador
    if request.auth.tipo_usuario != 'administrador':
        raise HttpError(403, "Solo los administradores pueden generar tokens de invitación.")

    # Verificar que no exista un token activo (no usado y no expirado) para ese correo
    token_existente = TokenInvitacion.objects.filter(
        correo_destino=datos.correo_destino,
        usado=False,
        fecha_expiracion__gt=timezone.now()
    ).first()

    if token_existente:
        raise HttpError(400,
            f"Ya existe un token activo para {datos.correo_destino}. "
            f"Token: {token_existente.token} (expira: {token_existente.fecha_expiracion.strftime('%d/%m/%Y %H:%M')})"
        )

    # Crear el token de invitación
    fecha_expiracion = timezone.now() + timedelta(days=datos.dias_expiracion)

    token_invitacion = TokenInvitacion(
        correo_destino=datos.correo_destino,
        tipo_usuario=datos.tipo_usuario,
        fecha_expiracion=fecha_expiracion
    )
    token_invitacion.save()  # El modelo genera el UUID automáticamente
    token_invitacion.refresh_from_db()  # Recargar para que el token sea string

    return token_invitacion


@router.get("/tokens", response=List[TokenInvitacionResponse], auth=AuthBearer())
def listar_tokens(request):
    """
    Lista todos los tokens de invitación generados.
    Solo accesible para administradores.
    """
    if request.auth.tipo_usuario != 'administrador':
        raise HttpError(403, "Solo los administradores pueden ver los tokens.")

    return TokenInvitacion.objects.all().order_by('-fecha_expiracion')

