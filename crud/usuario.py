from django.db.models import Q
from django.contrib.auth.hashers import make_password, check_password
from modelos.models import Usuario, TokenInvitacion
from esquemas.usuario import UsuarioCreate, UsuarioUpdate

def obtener_usuario(id_usuario: str):
    try:
        return Usuario.objects.get(dni=id_usuario)
    except Usuario.DoesNotExist:
        return None

def obtener_usuario_por_correo(correo: str):
    return Usuario.objects.filter(correo=correo).first()

def obtener_usuarios(skip: int = 0, limit: int = 100, buscar: str = None):
    qs = Usuario.objects.all()
    if buscar:
        qs = qs.filter(
            Q(dni__icontains=buscar) |
            Q(nombre__icontains=buscar) |
            Q(correo__icontains=buscar) |
            Q(tipo_usuario__icontains=buscar)
        )
    return qs[skip:skip+limit]

def crear_usuario(usuario: UsuarioCreate, token_invitacion: TokenInvitacion = None):
    contrasena_encriptada = make_password(usuario.contrasena)
    db_usuario = Usuario(
        dni=usuario.dni,
        nombre=usuario.nombre,
        correo=usuario.correo,
        contrasena=contrasena_encriptada,
        tipo_usuario=usuario.tipo_usuario,
        token=usuario.token,
        token_invitacion=token_invitacion
    )
    db_usuario.save()
    return db_usuario

def actualizar_usuario(id_usuario: str, usuario_update: UsuarioUpdate):
    db_usuario = obtener_usuario(id_usuario)
    if not db_usuario:
        return None
    
    update_data = usuario_update.dict(exclude_unset=True)
    if "contrasena" in update_data and update_data["contrasena"]:
        update_data["contrasena"] = make_password(update_data["contrasena"])
        
    for key, value in update_data.items():
        setattr(db_usuario, key, value)
        
    db_usuario.save()
    return db_usuario

def eliminar_usuario(id_usuario: str):
    db_usuario = obtener_usuario(id_usuario)
    if not db_usuario:
        return None
    db_usuario.delete()
    return db_usuario
