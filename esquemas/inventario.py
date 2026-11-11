from ninja import Schema
from typing import Optional, List
from datetime import date

# CATEGORIAS
class CategoriaSchema(Schema):
    codigo: str
    nombre: str
    descripcion: Optional[str] = None

class CategoriaResponse(Schema):
    codigo: str
    nombre: str
    descripcion: Optional[str] = None

# PROVEEDORES
class ProveedorSchema(Schema):
    nit: str
    nombre: str
    telefono: Optional[str] = None
    correo: Optional[str] = None

class ProveedorResponse(Schema):
    nit: str
    nombre: str
    telefono: Optional[str] = None
    correo: Optional[str] = None

# INSUMOS DE RECETA / DESCUENTO DE STOCK
class InsumoRecetaItem(Schema):
    producto_id: str
    cantidad: int

class InsumoRecetaDetalle(Schema):
    producto_id: str
    nombre: str
    cantidad: int

# PRODUCTOS
class ProductoCreate(Schema):
    dni_producto: Optional[str] = None
    nombre: str
    descripcion: Optional[str] = None
    precio: float = 0
    es_insumo: bool = True
    stock: int
    categoria_id: Optional[str] = None
    insumos: Optional[List[InsumoRecetaItem]] = None

class ProductoUpdate(Schema):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[float] = None
    stock: Optional[int] = None
    categoria_id: Optional[str] = None
    insumos: Optional[List[InsumoRecetaItem]] = None

class ProductoResponse(Schema):
    dni_producto: str
    nombre: str
    descripcion: Optional[str] = None
    precio: float
    es_insumo: bool
    stock: int
    categoria_id: Optional[str] = None
    categoria_nombre: Optional[str] = None
    ingredientes: Optional[List[InsumoRecetaDetalle]] = None

# ENTRADAS
class EntradaProductoCreate(Schema):
    cantidad: int
    precio_compra_unidad: float
    proveedor_id: str
    producto_id: str

class EntradaProductoResponse(Schema):
    idEntrada: int
    cantidad: int
    precio_compra_unidad: float
    costo_total: float
    fechaEntrada: date
    proveedor_id: str
    proveedor_nombre: Optional[str] = None
    producto_id: str
    producto_nombre: Optional[str] = None
