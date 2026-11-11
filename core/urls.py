from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI
from rutas.auth import router as auth_router
from rutas.usuario import router as usuario_router
from rutas.caja import caja_router
from rutas.wompi import wompi_router
from rutas.inventario import inventario_router
from rutas.menu import menu_router
from rutas.facturacion import facturacion_router
from rutas.configuracion import configuracion_router

api = NinjaAPI(
    title="Proyecto Querencia API",
    description="Backend para el aplicativo web Proyecto Querencia",
    version="1.0.0"
)

# Registrar routers
api.add_router("/auth", auth_router)
api.add_router("/usuarios", usuario_router)
api.add_router("/caja", caja_router)
api.add_router("/pagos", wompi_router)
api.add_router("/inventario", inventario_router)
api.add_router("/menu", menu_router)
api.add_router("/facturacion", facturacion_router)
api.add_router("/configuracion", configuracion_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
