from ninja import Router
from django.db import IntegrityError
from esquemas.inventario import ProductoCreate, ProductoUpdate, ProductoResponse, CategoriaResponse
from crud.inventario import crear_producto, crear_plato_con_insumos, actualizar_producto, formatear_producto
from modelos.models import Producto, Categoria
from ninja.errors import HttpError
from rutas.auth import AuthBearer
from typing import List

menu_router = Router()

def verificar_admin(request):
    if request.auth.tipo_usuario != "administrador":
        raise HttpError(403, "Se requieren permisos de administrador.")

@menu_router.get("/platos", response=List[ProductoResponse], auth=AuthBearer())
def listar_menu(request):
    # Solo retorna los que NO son insumos (Platos Preparados)
    return [formatear_producto(p) for p in Producto.objects.filter(es_insumo=False).order_by("nombre")]

@menu_router.get("/insumos", response=List[ProductoResponse], auth=AuthBearer())
def listar_insumos_para_menu(request):
    """Retorna los productos de inventario (insumos) disponibles para asociar a un plato y descontar de stock"""
    return [formatear_producto(p) for p in Producto.objects.filter(es_insumo=True).order_by("nombre")]

@menu_router.post("/platos", response=ProductoResponse, auth=AuthBearer())
def agregar_plato(request, datos: ProductoCreate):
    verificar_admin(request)
    # Forzar que sea plato de menú
    datos.es_insumo = False
    
    # Si no tiene dni_producto asignado, generar uno automáticamente tipo PLATO-1, PLATO-2...
    if not datos.dni_producto or not str(datos.dni_producto).strip():
        num = Producto.objects.filter(es_insumo=False).count() + 1
        codigo = f"PLATO-{num}"
        while Producto.objects.filter(dni_producto=codigo).exists():
            num += 1
            codigo = f"PLATO-{num}"
        datos.dni_producto = codigo
    else:
        datos.dni_producto = str(datos.dni_producto).strip()
        if Producto.objects.filter(dni_producto=datos.dni_producto).exists():
            raise HttpError(400, f"Ya existe un plato con el código '{datos.dni_producto}'.")

    try:
        prod = crear_plato_con_insumos(datos)
        return formatear_producto(prod)
    except Categoria.DoesNotExist:
        raise HttpError(404, "Categoría no encontrada")
    except IntegrityError as e:
        raise HttpError(400, f"Error de integridad en base de datos: {str(e)}")

@menu_router.put("/platos/{id}", response=ProductoResponse, auth=AuthBearer())
def editar_plato(request, id: str, datos: ProductoUpdate):
    verificar_admin(request)
    try:
        # Asegurarnos de que existe y es plato
        p = Producto.objects.get(dni_producto=id, es_insumo=False)
        prod = actualizar_producto(id, datos)
        return formatear_producto(prod)
    except Producto.DoesNotExist:
        raise HttpError(404, "Plato no encontrado")
    except Categoria.DoesNotExist:
        raise HttpError(404, "Categoría no encontrada")
    except IntegrityError as e:
        raise HttpError(400, f"Error de integridad en base de datos: {str(e)}")

@menu_router.delete("/platos/{id}", auth=AuthBearer())
def eliminar_plato(request, id: str):
    verificar_admin(request)
    try:
        Producto.objects.get(dni_producto=id, es_insumo=False).delete()
        return {"success": True}
    except Producto.DoesNotExist:
        raise HttpError(404, "Plato no encontrado")

# Categorías para que se puedan elegir en el Frontend
@menu_router.get("/categorias", response=List[CategoriaResponse], auth=AuthBearer())
def listar_categorias(request):
    return Categoria.objects.all()
