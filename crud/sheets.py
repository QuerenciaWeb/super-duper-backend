"""
Sincronización del estado del stock con una hoja de Google Sheets.

Configuración (variables de entorno, ver backend/.env):
    GOOGLE_SHEETS_ID                 ID de la hoja (la parte larga de la URL del spreadsheet).
    GOOGLE_SERVICE_ACCOUNT_FILE      Ruta al JSON de la cuenta de servicio.
    GOOGLE_SERVICE_ACCOUNT_JSON      (alternativa) contenido del JSON, útil en Render.
    STOCK_BAJO_UMBRAL                (opcional) por defecto 10, igual que las notificaciones.

La hoja debe compartirse (rol Editor) con el correo "client_email" de la cuenta de servicio.
"""
import json
import os
from datetime import datetime

from django.utils import timezone

from modelos.models import Producto, EntradaProducto
from crud.predicciones import predecir_stock

HOJA_STOCK = "Stock"
HOJA_RESUMEN = "Resumen"
HOJA_PREDICCIONES = "Predicciones"
ENCABEZADOS = ["Código", "Nombre", "Categoría", "Stock", "Estado", "Última entrada", "Cantidad última entrada"]
ENCABEZADOS_PRED = ["Código", "Nombre", "Stock", "Riesgo", "Tendencia", "Consumo diario", "Demanda próx. días",
                    "Días restantes", "Fecha agotamiento", "Cantidad sugerida", "Proveedor habitual"]


def construir_filas_predicciones(predicciones):
    def v(x):
        return "" if x is None else x
    return [[p["dni_producto"], p["nombre"], p["stock"], p["riesgo"], p["tendencia"], v(p["consumo_diario"]),
             v(p["demanda_horizonte"]), v(p["dias_restantes"]), v(p["fecha_agotamiento"]),
             v(p["cantidad_sugerida"]), v(p["proveedor_habitual"])] for p in predicciones]


class SheetsConfigError(Exception):
    """Falta configuración o dependencias para hablar con Google Sheets."""


def umbral_stock_bajo() -> int:
    try:
        return int(os.getenv("STOCK_BAJO_UMBRAL", "10"))
    except ValueError:
        return 10


def calcular_estado(stock: int, umbral: int) -> str:
    if stock <= 0:
        return "AGOTADO"
    if stock < umbral:
        return "BAJO"
    return "OK"


def construir_filas(umbral: int | None = None):
    """Devuelve (filas, resumen) con el estado actual de los insumos activos."""
    umbral = umbral if umbral is not None else umbral_stock_bajo()

    ultimas = {}
    for e in EntradaProducto.objects.order_by("fechaEntrada", "idEntrada"):
        ultimas[e.producto_id] = e  # la última iteración (la más reciente) gana

    filas = []
    resumen = {"OK": 0, "BAJO": 0, "AGOTADO": 0}
    productos = Producto.objects.filter(es_insumo=True).select_related("categoria").order_by("nombre")
    for p in productos:
        estado = calcular_estado(p.stock, umbral)
        resumen[estado] += 1
        ultima = ultimas.get(p.dni_producto)
        filas.append([
            str(p.dni_producto),
            p.nombre,
            p.categoria.nombre if p.categoria else "",
            p.stock,
            estado,
            ultima.fechaEntrada.isoformat() if ultima else "",
            ultima.cantidad if ultima else "",
        ])
    return filas, resumen


def _abrir_hoja():
    try:
        import gspread
    except ImportError as exc:  # pragma: no cover
        raise SheetsConfigError("Falta instalar 'gspread' (pip install -r requirements.txt).") from exc

    sheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheet_id:
        raise SheetsConfigError("Define GOOGLE_SHEETS_ID en las variables de entorno.")

    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    creds_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    try:
        if creds_json:
            cliente = gspread.service_account_from_dict(json.loads(creds_json))
        elif creds_file:
            cliente = gspread.service_account(filename=creds_file)
        else:
            raise SheetsConfigError(
                "Define GOOGLE_SERVICE_ACCOUNT_FILE o GOOGLE_SERVICE_ACCOUNT_JSON con las credenciales."
            )
    except (OSError, ValueError) as exc:
        raise SheetsConfigError(f"No se pudieron leer las credenciales de Google: {exc}") from exc
    return cliente.open_by_key(sheet_id)


def _hoja(spreadsheet, titulo: str, filas: int, columnas: int):
    import gspread
    try:
        return spreadsheet.worksheet(titulo)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=titulo, rows=max(filas, 100), cols=columnas)


def sincronizar_stock() -> dict:
    """Escribe el stock actual en la hoja 'Stock' y un resumen en 'Resumen'."""
    umbral = umbral_stock_bajo()
    filas, resumen = construir_filas(umbral)
    ahora = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")

    spreadsheet = _abrir_hoja()

    hoja_stock = _hoja(spreadsheet, HOJA_STOCK, len(filas) + 1, len(ENCABEZADOS))
    hoja_stock.clear()
    hoja_stock.update(range_name="A1", values=[ENCABEZADOS] + filas)
    hoja_stock.freeze(rows=1)
    hoja_stock.format("A1:G1", {"textFormat": {"bold": True}})

    hoja_resumen = _hoja(spreadsheet, HOJA_RESUMEN, 10, 2)
    hoja_resumen.clear()
    hoja_resumen.update(range_name="A1", values=[
        ["Última actualización", ahora],
        ["Umbral de stock bajo", umbral],
        ["Total de insumos", len(filas)],
        ["OK", resumen["OK"]],
        ["BAJO", resumen["BAJO"]],
        ["AGOTADO", resumen["AGOTADO"]],
    ])

    # Predicciones de reposición (si falla, el stock ya quedó actualizado)
    n_criticos = None
    try:
        predicciones = predecir_stock()
        filas_pred = construir_filas_predicciones(predicciones)
        hoja_pred = _hoja(spreadsheet, HOJA_PREDICCIONES, len(filas_pred) + 1, len(ENCABEZADOS_PRED))
        hoja_pred.clear()
        hoja_pred.update(range_name="A1", values=[ENCABEZADOS_PRED] + filas_pred)
        hoja_pred.freeze(rows=1)
        hoja_pred.format("A1:K1", {"textFormat": {"bold": True}})
        n_criticos = sum(1 for p in predicciones if p["riesgo"] == "CRITICO")
    except Exception as exc:  # noqa: BLE001
        n_criticos = None
        print(f"[sheets] No se pudo actualizar 'Predicciones': {exc}")

    return {"actualizado": ahora, "total": len(filas), "umbral": umbral, **resumen,
            "criticos_prediccion": n_criticos, "url": spreadsheet.url}
