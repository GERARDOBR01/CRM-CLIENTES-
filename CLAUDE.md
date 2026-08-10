# CRM Certeza — contexto del proyecto

Stack: Python 3.13 + Streamlit 1.58 + SQLite (local) / Postgres-Supabase (nube, pendiente).
Dueño: Gerardo Barrera. Windows 11, Ryzen 5 5600G.
Repo: `GERARDOBR01/CRM-CLIENTES-` (remote `origin`, rama `main`).

Objetivo de negocio: encontrar los mejores clientes, saber qué venderles, saber qué les
duele, y que contraten. Todo lo que se construya aquí sirve a eso.

## Reglas que no se rompen

- **NUNCA automatizar envío de WhatsApp** con librerías no oficiales (whatsapp-web.js,
  Baileys, Selenium sobre WhatsApp Web). Solo links `wa.me` click-to-chat. El envío final
  siempre lo hace Gerardo con un clic. Automatizar outreach frío viola los ToS de Meta y
  termina en baneo permanente del número — que es el canal de venta.
- **NUNCA subir `leads.db`, `.env` ni `.streamlit/secrets.toml` al repo.** Ni un dato real
  de cliente en el historial de git, que es para siempre.
- **NUNCA usar el título "Ingeniero" para Gerardo** — es estudiante. Correcto: "estudio
  Ingeniería en Software". La firma es
  `Gerardo Barrera — Ingeniería de Software y Redes · Sistemas de verificación y
  automatización operativa`.
- **Respaldar `leads.db` antes de cualquier migración de esquema.** Contiene prospectos
  reales con historial de contactos ya hechos; es irrecuperable.
- **Nunca mencionar reseñas negativas** en un mensaje a un prospecto, aunque sean la mejor
  evidencia. Ofende o asusta. Se nombra el problema estructural y él conecta.
- **Nunca inventar cifras** de pérdida ni porcentajes. La nota de honestidad al pie del
  diagnóstico (se omiten cifras estimadas porque inventar un número sin datos no es
  diagnóstico, es publicidad) **no se quita ni se suaviza** — es lo que más credibilidad da.
- `db.init_db()` es **idempotente y nunca borra**: migra con `ALTER TABLE` y mapeos de
  valores. Cualquier campo nuevo se agrega ahí, no recreando la tabla.
- El pipeline **solo avanza** (`db.avanzar_estatus`): mandar un seguimiento nunca regresa
  un lead a una etapa anterior.

## Comandos

```bash
python -m streamlit run app.py     # o doble clic en run.bat (headless, 0.0.0.0:8501)
python test_consistencia.py        # catálogos + reglas de tono del generador
python -m doctest db.py mensajes.py plantillas.py whatsapp.py importador.py -v
```

**Antes de dar por bueno un cambio de UI, revisa que no haya un Streamlit viejo
corriendo** (`netstat -ano | grep :8501`). Windows deja que dos procesos escuchen el
mismo puerto y reparte las conexiones entre ellos. Un proceso arrancado antes de tus
cambios re-ejecuta `app.py` (así que el título y el CSS se ven nuevos) pero **no
reimporta `db.py` ni los demás módulos**, así que falla con `AttributeError` redactado
en pantalla. Pasó en esta sesión y costó un rato: parecía un bug del código nuevo y era
un proceso de las 9:30 am.

## Mapa de archivos

| Archivo | Qué es |
|---|---|
| `app.py` | App Streamlit. Vistas: HOY, Leads, Preparar mensaje, Dolores/diagnósticos, Cargar, Métricas, Datos y ajustes. |
| `db.py` | Esquema, migraciones idempotentes, CRUD, historial, dolores, pipeline en dinero. |
| `scoring.py` | Score 0-100, temperatura, calendario de follow-ups, razones de urgencia. |
| `mensajes.py` | Generador algorítmico de mensajes de primer contacto (sección 6.5 del brief). |
| `plantillas_gancho.py` | Catálogo de ganchos, servicios y variantes. Editable sin tocar lógica. |
| `plantillas.py` | Variables de plantilla y mensajes de seguimiento. |
| `diagnostico.py` | Generador del HTML del diagnóstico. |
| `tracking.py` | Cliente Goatcounter + marcado manual de aperturas. |
| `metricas.py` | Métricas por sector y por tipo de dolor. |
| `importador.py` | Lectura xlsx/csv, mapeo de encabezados, dedup, vista previa. |
| `whatsapp.py` | Normaliza teléfonos a E.164 y arma links `wa.me`. |
| `config.py` | Rutas y secretos por entorno, muro de contraseña. |
| `leads.db` | **Los datos. No está en el repo. Es lo que hay que respaldar.** |

## Estado

**Sesión 2026-08-09 — cerrada.** Respaldos de esa sesión, todos con hash verificado:
`leads_backup_20260809_sesion_v2.db`, `leads_backup_pre_migracion_65_*.db`,
`leads_backup_pre_datos_*.db`. La base sobrevivió entera: 43 leads y 54 contactos antes
y después.

Ya funcionaba al empezar: pipeline de 9 etapas, migración v1→v2, sector, valor estimado y
pipeline ponderado, score + vista HOY con alerta de patrón, calendario de follow-ups,
banco de dolores, generador de diagnósticos con token, tracking Goatcounter, métricas por
sector, búsqueda, notas al historial, respaldo ZIP, muro de contraseña.

Hecho en esta sesión:

- [x] Campos 6.5 en `leads` + `fecha_proximo_seguimiento` (12a), por `ALTER TABLE`
- [x] Generador de mensajes (`mensajes.py` + `plantillas_gancho.py`), con las reglas de
      tono probadas sobre todas las combinaciones en `test_consistencia.py`
- [x] Hechos estructurados de los 25 leads de fitness/salud, extraídos de
      `senales_investigacion` y auditados contra invención de datos
- [x] UX móvil + PWA (`movil.py`, `static/`), verificado en navegador real a 390×844
- [x] Deshacer envío (12e) y fecha comprometida que manda sobre el calendario
- [x] Métricas por `tipo_dolor` con traza de qué gancho se usó en cada envío
- [x] **Bug corregido:** las métricas contaban los `Cerrado - Perdido` como "respondió"
      (los cerrados van al final del enum, así que `orden >= Interesado` los incluía).
      Daba 100 % de tasa de respuesta sobre 18 leads perdidos. Ahora hay
      `db.ESTATUS_CON_RESPUESTA` explícito — **no volver a derivar esto del orden.**
- [x] Todo el outreach habla de usted; los seguimientos tuteaban y no cuadraban con el
      generador

Pendiente:

- [ ] **Persistencia Postgres/Supabase (11 capa 2) — decisión de Gerardo.** Es lo único
      que falta para usar el CRM sin la PC prendida. Requiere una instancia real contra
      la cual probar: un port de base de datos a ciegas, sobre el archivo que guarda el
      pipeline real, es la forma más común de perder datos. Con la instancia creada es
      una pasada dedicada; el respaldo ZIP ya existe y es justo lo que la hace segura.
- [ ] Clasificar los 18 leads de sector `Otro` (tanda vieja, todos `Cerrado - Perdido`)
      si alguna vez se reactivan.
