from typing import List
from datetime import datetime, timedelta
import openpyxl
from django.db import IntegrityError
from django.http import HttpResponse
from ninja import Router
from ninja.errors import HttpError

from esquemas.inventario import (
    CategoriaSchema, CategoriaResponse,
    ProveedorSchema, ProveedorResponse,
    ProductoCreate, ProductoUpdate, ProductoResponse,
    EntradaProductoCreate, EntradaProductoResponse,
)
from crud.inventario import (
    crear_categoria, crear_proveedor,
    crear_producto, actualizar_producto, formatear_producto,
    registrar_entrada, formatear_entrada,
)
from modelos.models import Categoria, Proveedor, Producto, EntradaProducto
from rutas.auth import AuthBearer

inventario_router = Router()

def verificar_admin(request):
    if request.auth.tipo_usuario != "administrador":
        raise HttpError(403, "Se requieren permisos de administrador.")

# ==================== CATEGORIAS ====================
@inventario_router.get("/categorias", response=List[CategoriaResponse], auth=AuthBearer())
def listar_categorias(request):
    return Categoria.objects.all()

@inventario_router.post("/categorias", response=CategoriaResponse, auth=AuthBearer())
def agregar_categoria(request, datos: CategoriaSchema):
    verificar_admin(request)
    if Categoria.objects.filter(codigo=datos.codigo).exists():
        raise HttpError(400, f"Ya existe una categoría con el código '{datos.codigo}'.")
    return crear_categoria(datos)

# ==================== PROVEEDORES ====================
@inventario_router.get("/proveedores", response=List[ProveedorResponse], auth=AuthBearer())
def listar_proveedores(request):
    return Proveedor.objects.all()

@inventario_router.post("/proveedores", response=ProveedorResponse, auth=AuthBearer())
def agregar_proveedor(request, datos: ProveedorSchema):
    verificar_admin(request)
    if Proveedor.objects.filter(nit=datos.nit).exists():
        raise HttpError(400, f"Ya existe un proveedor con el NIT '{datos.nit}'.")
    return crear_proveedor(datos)

# ==================== PRODUCTOS ====================
@inventario_router.get("/productos", response=List[ProductoResponse], auth=AuthBearer())
def listar_productos(request):
    return [formatear_producto(p) for p in Producto.objects.filter(es_insumo=True).order_by("nombre")]

@inventario_router.post("/productos", response=ProductoResponse, auth=AuthBearer())
def agregar_producto(request, datos: ProductoCreate):
    verificar_admin(request)
    dni = str(datos.dni_producto).strip() if datos.dni_producto else ""
    if not dni:
        raise HttpError(400, "El DNI/Código del producto es obligatorio y no puede estar vacío.")

    if Producto.objects.filter(dni_producto=dni).exists():
        raise HttpError(400, f"Ya existe un producto registrado con el código '{dni}'. Si deseas modificarlo, usa la opción de editar.")

    datos.dni_producto = dni
    try:
        prod = crear_producto(datos)
        return formatear_producto(prod)
    except Categoria.DoesNotExist:
        raise HttpError(404, "Categoría no encontrada")
    except IntegrityError as e:
        raise HttpError(400, f"Error de integridad en base de datos: {str(e)}")

@inventario_router.put("/productos/{id}", response=ProductoResponse, auth=AuthBearer())
def editar_producto(request, id: str, datos: ProductoUpdate):
    verificar_admin(request)
    try:
        prod = actualizar_producto(id, datos)
        return formatear_producto(prod)
    except Producto.DoesNotExist:
        raise HttpError(404, "Producto no encontrado")
    except Categoria.DoesNotExist:
        raise HttpError(404, "Categoría no encontrada")
    except IntegrityError as e:
        raise HttpError(400, f"Error de integridad en base de datos: {str(e)}")

@inventario_router.delete("/productos/{id}", auth=AuthBearer())
def eliminar_producto(request, id: str):
    verificar_admin(request)
    try:
        Producto.objects.get(dni_producto=id).delete()
        return {"success": True}
    except Producto.DoesNotExist:
        raise HttpError(404, "Producto no encontrado")

# ==================== ENTRADAS DE INVENTARIO ====================
@inventario_router.get("/entradas", response=List[EntradaProductoResponse], auth=AuthBearer())
def listar_entradas(request):
    verificar_admin(request)
    return [formatear_entrada(e) for e in EntradaProducto.objects.all().order_by("-fechaEntrada", "-idEntrada")]

@inventario_router.post("/entradas", response=EntradaProductoResponse, auth=AuthBearer())
def registrar_nueva_entrada(request, datos: EntradaProductoCreate):
    verificar_admin(request)
    try:
        entrada = registrar_entrada(datos)
        return formatear_entrada(entrada)
    except Producto.DoesNotExist:
        raise HttpError(404, "Producto no encontrado")
    except Proveedor.DoesNotExist:
        raise HttpError(404, "Proveedor no encontrado")

# ==================== REPORTE EXCEL ====================
@inventario_router.get("/reporte/excel", auth=AuthBearer())
def exportar_reporte_excel(request):
    verificar_admin(request)
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reporte Inventario"
    
    ws.append(["DNI Producto", "Nombre", "Categoria", "Precio", "Stock Actual"])
    
    productos = Producto.objects.all().order_by('nombre')
    for p in productos:
        categoria_nombre = p.categoria.nombre if p.categoria else "Sin categoria"
        ws.append([p.dni_producto, p.nombre, categoria_nombre, float(p.precio), p.stock])
        
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = f'attachment; filename="reporte_inventario_{datetime.now().strftime("%Y%m%d")}.xlsx"'
    
    wb.save(response)
    return response
