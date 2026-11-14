from django.core.management.base import BaseCommand, CommandError

from crud.predicciones import predecir_stock, notificar_riesgos
from crud.sheets import sincronizar_stock, SheetsConfigError


class Command(BaseCommand):
    help = (
        "Recalcula las predicciones de reposición, genera notificaciones de insumos críticos y "
        "actualiza Google Sheets (programar con cron / Render Cron Job)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--sin-sheets", action="store_true",
                            help="Solo predicciones y notificaciones; no escribe en Google Sheets.")

    def handle(self, *args, **options):
        predicciones = predecir_stock()
        criticos = [p for p in predicciones if p["riesgo"] == "CRITICO"]
        nuevas = notificar_riesgos(predicciones)
        self.stdout.write(f"Predicciones: {len(predicciones)} insumos, {len(criticos)} críticos, "
                          f"{nuevas} notificaciones nuevas.")
        for p in criticos:
            self.stdout.write(f"  - {p['nombre']}: stock {p['stock']}, sugerido pedir {p['cantidad_sugerida']}")

        if options["sin_sheets"]:
            return
        try:
            r = sincronizar_stock()
        except SheetsConfigError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(
            f"Stock sincronizado ({r['total']} insumos): OK={r['OK']} BAJO={r['BAJO']} AGOTADO={r['AGOTADO']} -> {r['url']}"
        ))
