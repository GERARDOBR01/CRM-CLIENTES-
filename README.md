# CRM Certeza — leads, diagnósticos y outreach por WhatsApp

CRM local de un solo usuario para prospección de servicios de automatización operativa.
Encuentra los mejores clientes, dice qué venderles, de qué les duele, y a quién hay que
hablarle **hoy**.

Python + Streamlit + SQLite. Sin servicios de pago, sin dependencias externas obligatorias.

```bash
python -m streamlit run app.py
```

(o doble clic en `run.bat`). Abre `http://localhost:8501`.

---

## Lo que hace cada vista

| Vista | Para qué |
|---|---|
| 🎯 **HOY** | Pantalla de entrada. Dice en una frase con quién hablar y por qué, lista los 7 leads que necesitan algo hoy con la razón visible, y reclama si hay leads calientes abandonados. |
| 📋 Leads | Tabla editable con todo, filtros por estatus/sector/plataforma, búsqueda, y el pipeline en dinero (bruto, ponderado y ganado). |
| 💬 Preparar mensaje | Detalle del lead: contexto, mensaje rellenado, copiar, abrir en WhatsApp (marca contactado solo), historial. |
| 🩺 Dolores y diagnósticos | Banco de dolores por sector ordenado por conversión + generador del HTML del diagnóstico. |
| 📥 Cargar leads | Sube `.xlsx`/`.csv`, vista previa, deduplicación y confirmación. |
| 📊 Métricas | Por sector: leads, tasa de respuesta, apertura del diagnóstico, cierre, ticket promedio y días de ciclo. |
| ⚙️ Datos y ajustes | Nombre, lada, URL de diagnósticos, Goatcounter, importar/exportar, respaldo completo, alta manual. |

---

## Pipeline de ventas

```
Sin contactar → Contactado → Diagnóstico enviado → Diagnóstico visto
              → Interesado → Propuesta enviada → Negociación
              → Cerrado - Ganado / Cerrado - Perdido
```

**El pipeline solo avanza.** Mandar un seguimiento a alguien que ya está en Negociación
no lo regresa a Contactado: eso borraría información que ya se ganó (`db.avanzar_estatus`).

Cada etapa tiene una probabilidad de cierre (`db.PROBABILIDAD_ESTATUS`) que alimenta el
**pipeline ponderado**. Es el número honesto: 10 leads recién contactados de $4,000 no
son $40,000, son $2,000 de expectativa.

### Valor estimado

| Entregable | Rango | Default |
|---|---|---|
| Diagnóstico | $3,500 – $5,000 | $4,000 |
| Sistema de verificación | $12,000 – $18,000 | $15,000 |
| Mensualidad | $1,500 – $2,500 | $2,000 |

`db.valor_sugerido(sector, estatus)` propone el valor; siempre es editable a mano.

---

## Score de lead

Calculado al vuelo, **nunca almacenado** (un score guardado sería mentira al día
siguiente). Devuelve 0-100 y una temperatura: 🔥 Caliente ≥60, 🌤️ Tibio ≥35, 🧊 Frío.

Señales: etapa del pipeline · si abrió el diagnóstico y cuántas veces · si respondió
alguna vez · días de silencio (con 2 días de gracia, después decae) · tamaño del trato.

Todos los pesos viven en `scoring.PESOS` y `scoring.UMBRALES`. Se ajustan ahí sin tocar
una línea de lógica.

## Calendario de follow-ups

`scoring.CALENDARIO` define a los cuántos días de silencio toca cada seguimiento, por
etapa. Cuanto más avanzado el lead, más corto el ciclo:

| Etapa | Toques (días de silencio) |
|---|---|
| Contactado | 3, 7, 14 |
| Diagnóstico enviado | 2, 5, 10 |
| Diagnóstico visto | 1, 3, 7 |
| Interesado | 2, 5, 9 |
| Propuesta enviada | 2, 5, 10 |
| Negociación | 2, 4, 7 |

La vista HOY dice cuál toca y trae la plantilla ya rellenada. Los mensajes escalan solos:
recordatorio suave → con valor → pregunta directa → cierre.

Cuando se agota la secuencia sin respuesta, la app **sugiere** mover a `Cerrado - Perdido`
— no lo hace sola. Esa decisión es tuya.

## Alerta de patrón

Si hay leads en `Diagnóstico visto`, `Interesado`, `Propuesta enviada` o `Negociación`
sin tocar en más de 5 días, HOY lo reclama arriba de todo:

> Tienes 3 leads calientes sin seguimiento. Antes de buscar prospectos nuevos, cierra estos.

Existe por un patrón concreto y documentado: seguir buscando prospectos nuevos en vez de
cerrar a los que ya levantaron la mano.

---

## Banco de dolores y generador de diagnósticos

La tabla `dolores` guarda, por sector: etapa del recorrido, línea de contexto, título,
descripción, severidad (GRAVE / OBSERVACIÓN), efecto, y cuántas veces se usó y convirtió.
Se ordenan por tasa de conversión: **los dolores que más venden aparecen primero**.

Al generar un diagnóstico se marcan los dolores usados; cuando el lead pasa a
`Cerrado - Ganado`, esos dolores suben su `veces_convirtio`.

El generador (`diagnostico.py`) parametriza negocio, dirección, puertas de entrada,
titular, premisa y hallazgos, y escribe `diagnosticos/{slug}/index.html`. El CSS es
**idéntico** al del diagnóstico original (verificado carácter por carácter).

### Lo que no se parametriza, a propósito

1. **La nota de honestidad del pie.** Se omiten cifras de pérdida estimadas porque
   inventar un número sin datos no es diagnóstico, es publicidad. Es la pieza que más
   credibilidad da.
2. **La firma:** `Gerardo Barrera — Ingeniería de Software y Redes · Sistemas de
   verificación y automatización operativa`. Sin el título de "Ingeniero": es estudiante,
   y el framing honesto es deliberado.

---

## Tracking de apertura del diagnóstico

### Por qué Goatcounter

Los diagnósticos se publican en GitHub Pages, que es hosting estático: no hay backend
propio donde registrar la visita.

| Opción | Veredicto |
|---|---|
| **Goatcounter** | **Elegida.** Plan gratuito real para uso personal, sin cookies, con API para consultar los hits. Open source y auto-hospedable si algún día hace falta. |
| Plausible | Muy buena, pero hoy es de paga (solo prueba de 30 días). Un costo fijo mensual no se justifica para un CRM personal que arranca. |
| Endpoint propio | Control total, pero exige un servidor encendido 24/7 — justo el problema que este proyecto trata de evitar. |

### Cómo se activa

1. Crea una cuenta gratis en goatcounter.com.
2. Pon la URL de tu sitio (`https://tucuenta.goatcounter.com`) en ⚙️ Datos y ajustes.
3. Genera un token de API con permiso de *Read statistics* y guárdalo como
   `GOATCOUNTER_TOKEN` en `.streamlit/secrets.toml` o como variable de entorno.
4. Regenera los diagnósticos (el snippet se inyecta al generar) y usa
   **🔄 Sincronizar aperturas**.

Cada lead tiene un token único y su diagnóstico registra la ruta `/dx/{token}`. El token
va en el `path` y no en `?ref=` porque Goatcounter ignora el query string por default.

La primera apertura mueve el lead de `Diagnóstico enviado` a `Diagnóstico visto` y lo
anota en el historial.

**Sin Goatcounter la app funciona igual**: se marca la apertura a mano desde
🩺 Dolores y diagnósticos.

### Nota de privacidad

Esto mide **si se abrió una página propia que tú le enviaste al prospecto**, nada más.
Sin cookies, sin recolectar datos personales, sin perfilar a nadie y sin terceros
publicitarios. Lo único que se sabe es cuántas veces se abrió y cuándo.

---

## Cargar leads nuevos

Columnas que reconoce (**solo `negocio` es obligatoria**):

`negocio`, `contacto`, `categoria`, `sector`, `direccion`, `telefono`, `plataforma`,
`evidencia_dolor`, `mensaje_plantilla`, `track_recomendado`, `senales_investigacion`

- Encabezados reconocidos sin importar acentos, mayúsculas ni variantes (*Teléfono*,
  *Plataforma recomendada*, *Nombre del negocio*, *Giro*, *WhatsApp*, *Señales de
  investigación*). Lo que no reconoce lo ignora y te dice qué fue.
- **Nada se inserta sin vista previa**, con conteo de nuevos / duplicados / sin mensaje.
- **Duplicado = mismo `negocio` + mismo `telefono`** normalizado a puros dígitos
  (`+52 33-1578-0598` y `3315780598` son el mismo). Detecta duplicados contra la base y
  repetidos dentro del propio archivo.
- **Columna faltante no bloquea**: se deja vacía. Sin `mensaje_plantilla` el lead entra
  marcado 🟡 y su detalle muestra la plantilla genérica lista para personalizar.
- `sector` que no se reconozca cae en `Otro`.
- Los leads nuevos entran como `Sin contactar`.

`leads_ejemplo.csv` (datos ficticios) sirve de plantilla. El seed inicial desde
`leads_tracker.xlsx` dedup por **nombre de negocio** solamente, para que reimportar el
tracker original nunca duplique aunque hayas editado un teléfono en la app.

---

## La restricción de WhatsApp — no negociable

La app **prepara y organiza**, nunca envía sola. Construye la URL oficial
`https://wa.me/<numero>?text=<mensaje>` que abre WhatsApp con el texto ya escrito, y el
envío final lo das tú con un clic.

No se usa whatsapp-web.js, Baileys ni Selenium sobre WhatsApp Web. Automatizar envíos a
contactos fríos con librerías no oficiales **viola los Términos de Servicio de
WhatsApp/Meta** y en la práctica termina en baneo permanente del número. No es un
tecnicismo: le pasa seguido a las cuentas que hacen outreach frío automatizado, y el
número es el canal de venta.

La única vía automatizada legítima es la **WhatsApp Business API oficial** (Meta o
Twilio), que exige verificación de negocio y plantillas pre-aprobadas. Fuera del alcance
hoy; vale la pena evaluarla como fase 2 si el volumen crece mucho.

---

## Acceso: local, red local y nube

### Local (funciona hoy)

`run.bat` levanta la app en modo headless y la deja corriendo. Para que arranque sola al
iniciar sesión en Windows: `Win+R` → `shell:startup` → pega ahí un acceso directo al
`.bat`.

### Desde el celular en la misma WiFi (funciona hoy, con la PC prendida)

`run.bat` ya escucha en `0.0.0.0`. Desde el teléfono, abre `http://<IP-de-la-PC>:8501`
(sacas la IP con `ipconfig`). Puede pedir permitir la app en el Firewall de Windows la
primera vez.

### Desde el celular sin la PC prendida — qué falta

Esto **todavía no está resuelto**, y es deliberado. Streamlit Community Cloud es gratis y
el proyecto ya está listo para él (sin rutas absolutas, config por variables de entorno,
`requirements.txt` limpio, muro de contraseña con `CRM_PASSWORD`). El problema es la
persistencia: **SQLite en Community Cloud no sobrevive los reinicios**.

| Opción | Veredicto |
|---|---|
| **Supabase / Postgres (plan gratis)** | **Recomendada.** Es la única que cumple "sin la PC prendida": los datos viven fuera del contenedor y sobreviven reinicios y redeploys. |
| SQLite local + sincronizar | Descartada. Si la PC está apagada no hay nada sirviendo la app — no puede cumplir el requisito, por más que se sincronice. |

**Por qué no está implementada todavía:** portar `db.py` a Postgres significa cambiar
placeholders, `AUTOINCREMENT` → `IDENTITY`, `INSERT OR IGNORE` → `ON CONFLICT`, y
`PRAGMA table_info` → `information_schema`. En esta máquina no hay Docker ni Postgres, así
que ese código **no se podría probar contra un motor real** antes de entregarlo. Un port
de base de datos hecho a ciegas, sobre el archivo que guarda el pipeline real, es la
forma más común de perder datos. Queda para una pasada dedicada, con la instancia de
Supabase ya creada para probar contra ella.

Mientras tanto: **⚙️ Datos y ajustes → 🗄️ Respaldo completo (ZIP)** exporta todas las
tablas a CSV. Ese respaldo es justamente lo que hace segura la migración cuando toque.

### Contraseña

Si `CRM_PASSWORD` está configurada (entorno o `st.secrets`), la app pide contraseña al
entrar. Si no lo está, no estorba — que es lo que quieres en localhost. **En la nube,
ponla sí o sí**: ahí hay datos de prospectos.

---

## Archivos

| Archivo | Qué es |
|---|---|
| `app.py` | La app de Streamlit (7 vistas). |
| `db.py` | Esquema, migraciones, CRUD, historial, dolores, pipeline en dinero. |
| `scoring.py` | Score de lead, calendario de follow-ups, razones de urgencia. |
| `diagnostico.py` | Generador del HTML del diagnóstico. |
| `tracking.py` | Cliente de Goatcounter + marcado manual de aperturas. |
| `metricas.py` | Métricas por sector. |
| `importador.py` | Lectura de xlsx/csv, mapeo de encabezados, dedup, vista previa. |
| `whatsapp.py` | Normaliza teléfonos a E.164 y arma los links `wa.me`. |
| `plantillas.py` | Variables de plantilla y mensajes de seguimiento. |
| `config.py` | Rutas y secretos por entorno, muro de contraseña. |
| `migrate_excel.py` | Seed inicial desde `leads_tracker.xlsx`. |
| `leads.db` | **Tus datos. No está en el repo. Es lo que hay que respaldar.** |

### Migraciones de esquema

`db.init_db()` es idempotente y **nunca borra datos**: agrega columnas con `ALTER TABLE`,
traduce valores viejos (el pipeline v1 de 6 estados se mapea al v2 de 9) y rellena campos
nuevos en filas existentes sin pisar ediciones manuales. Se puede correr en cada arranque
sin miedo.

---

## Privacidad y datos en el repo

Este repositorio **no contiene ni un dato real de cliente**. `leads.db`, cualquier `*.db`,
`leads_tracker.xlsx`, los CSV exportados, los diagnósticos generados y
`.streamlit/secrets.toml` están en `.gitignore`. Los datos de ejemplo
(`leads_ejemplo.csv`) son negocios inventados.
