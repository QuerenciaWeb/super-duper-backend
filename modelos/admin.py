from django.contrib import admin
from .models import TokenInvitacion

@admin.register(TokenInvitacion)
class TokenInvitacionAdmin(admin.ModelAdmin):
    list_display = ('correo_destino', 'token', 'tipo_usuario', 'usado', 'fecha_expiracion')
    list_filter = ('tipo_usuario', 'usado', 'fecha_expiracion')
    search_fields = ('correo_destino', 'token')
    readonly_fields = ('token',) # Hacer el token de solo lectura para evitar ediciones accidentales
