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
| 📋 Leads | Tabla editable con todo, filtros por estatus/sector/plataforma, búsqueda, y el pipeline en dinero (bruto, ponderado y ganado). En el celular, tarjetas en vez de tabla. |
| 💬 Preparar mensaje | Detalle del lead: contexto, **generador de mensajes**, copiar, abrir en WhatsApp (marca contactado solo), deshacer, historial. |
| 🩺 Dolores y diagnósticos | Banco de dolores por sector ordenado por conversión + generador del HTML del diagnóstico. |
| 📥 Cargar leads | Sube `.xlsx`/`.csv`, vista previa, deduplicación y confirmación. |
| 📊 Métricas | Dos pestañas: por sector (leads, respuesta, apertura, cierre, ticket, ciclo) y **por tipo de dolor** (qué argumento hace que contesten). |
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

**Esas probabilidades son estimaciones, no mediciones.** Todavía no hay cierres propios
con los cuales calcularlas; salieron como punto de partida. Sirven para comparar leads
entre sí, no como pronóstico de ingreso. En cuanto haya cierres reales se recalculan —
📊 Métricas ya lleva la tasa de cierre por sector.

### Valor estimado

| Entregable | Rango | Default |
|---|---|---|
| Diagnóstico | $3,500 – $5,000 | $4,000 |
| Sistema de verificación | $12,000 – $18,000 | $15,000 |
| Mensualidad | $1,500 – $2,500 | $2,000 |

`db.valor_sugerido(sector, estatus)` propone el valor; siempre es editable a mano.

---

## Generador de mensajes

Gerardo no tiene tiempo de redactar un mensaje por lead. El CRM lo arma, él lo revisa
y lo manda. **Nunca se envía solo.**

### Por qué está hecho así

Dos caminos que *parecen* solución y no lo son:

1. **Buscar palabras clave en `evidencia_dolor`.** Esa evidencia es prosa escrita para
   que Gerardo la lea antes de escribir. Detectar el dolor buscando substrings ahí es
   frágil: alguien redacta distinto y el gancho se cae **sin que nadie se entere**.
2. **Pedir un gancho escrito a mano por lead.** Solo mueve el trabajo manual de lugar:
   24 leads son 24 frases que redactar. Es el mismo problema con otro nombre.

Lo que sí funciona: **datos estructurados → plantilla → gancho generado**. Gerardo
captura hechos sueltos —dos menús, tres números y dos casillas— y la oración la arma
el generador. Se teclea, no se redacta.

### Cómo se arma el mensaje

```
1. Saludo      usa `tratamiento` si existe; si no, "Hola, buen día."
2. Identidad   "Soy Gerardo Barrera, estudio Ingeniería en Software…"
3. Gancho      la primera plantilla de su `tipo_dolor` que se pueda llenar
4. Servicio    1-2 fragmentos según `tipo_dolor`
5. Cierre      ofrece el diagnóstico y deja una salida explícita
```

Los ganchos viven en `plantillas_gancho.py` — **datos, no lógica**: se editan sin abrir
`mensajes.py`. Cada `tipo_dolor` **termina** en una plantilla sin campos requeridos, así
que ningún lead se queda sin mensaje por poco que se sepa de él. `test_consistencia.py`
lo verifica.

### Variación

20+ mensajes de la misma fórmula se notan si el fraseo es idéntico. Cada bloque fijo
tiene 4 variantes y la elección es **determinística según el `id` del lead**: el mismo
lead produce siempre el mismo mensaje (regenerarlo no sorprende), pero dos leads con el
mismo dolor no suenan igual. Los 25 leads reales producen 25 mensajes distintos.

Usa SHA-256 y no `hash()` de Python, que lleva sal aleatoria por proceso y daría un
mensaje distinto en cada arranque. Tampoco CRC32: reparte mal los bits bajos entre
cadenas casi iguales y salían pares idénticos.

### El destinatario cambia el mensaje

| `tipo_destinatario` | Qué recibe |
|---|---|
| `dueno` / `doctor` | Mensaje completo, de negocio. |
| `recepcion` | Corto, pide explícito que lo pasen a quien decide y aclara que no es venta de insumos ni publicidad. **No se le vende a recepción.** |
| `marketing` | Enfocado en captación y conversión, no en operación interna. |
| `desconocido` | La versión de `dueno`, que es la neutra. |

### Reglas de tono que el código hace cumplir

No son comentarios de buena voluntad: `test_consistencia.py` las prueba sobre **todas**
las combinaciones de dolor × destinatario × nivel de investigación, en los dos canales.

- Saludo antes del gancho — el prospecto no lo conoce de nada.
- **Nunca se mencionan reseñas negativas ni calificaciones**, aunque sean la mejor
  evidencia. A alguien que no te conoce lo ofende o lo asusta. Se nombra el problema
  estructural y él conecta. `num_resenas` se usa solo como señal de volumen.
- **Nunca se inventan cifras.** Solo se usan hechos capturados, y los aproximados se
  redondean **hacia abajo** para que "más de 900" sea literalmente cierto con 906.
- Nunca el título "Ingeniero" — es estudiante.
- Máximo 90 palabras (50 en DM). Si se pasa, el generador suelta primero el segundo
  servicio y luego acorta el cierre; la salida explícita nunca se toca.
- Todo el outreach habla **de usted**, incluidos los seguimientos.

### Variante DM

Los leads sin teléfono se contactan por DM, donde 90 palabras no se leen. El canal se
preselecciona solo y produce la versión de 50: saludo + gancho + una línea de oferta +
cierre. Sin detallar servicios — eso va en la respuesta, si contesta.

### Aprendizaje

Al enviar, se guarda en el historial **qué dolor y qué combinación de variantes** se
usó. 📊 Métricas → *Por tipo de dolor* muestra la tasa de respuesta de cada uno. Sin ese
dato no hay forma de saber qué mensajes funcionan, y vale más que cualquier suposición
sobre el tono correcto.

La columna **Con traza** dice cuántos contactos llevan ese registro. Mientras sea baja,
la tabla es indicio y no medición — y lo dice en pantalla.

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

### Cuando quedaste de escribirle un día

`fecha_proximo_seguimiento` es para cuando prometiste algo con fecha ("le mando el demo
el jueves"). **Manda sobre el calendario en los dos sentidos:** ese día el lead sale en
HOY aunque al calendario le faltaran días, y antes de ese día no te lo reclama aunque el
calendario ya lo pidiera. Quedar de escribir el jueves y escribir el martes queda peor
que no escribir. Al mandarle el mensaje, la fecha se limpia sola.

### Deshacer un envío

El botón de WhatsApp marca contactado en cuanto se toca, y en una pantalla de seis
pulgadas eso pasa sin querer. **↩️ Deshacer último envío** lo borra del historial,
regresa la fecha de contacto a la del envío anterior y, si era el único, devuelve el lead
a `Sin contactar`. Un lead que ya llegó a Negociación **no** se degrada por deshacer un
seguimiento: esa información se ganó aparte. No borra el rastro en silencio — deja una
nota diciendo que se deshizo.

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
titular, premisa y hallazgos, y escribe `diagnosticos/dx-{token}/index.html`. El CSS es
**idéntico** al del diagnóstico original (verificado carácter por carácter).

### Dónde se publican y por qué así

Los diagnósticos **no viven en este repo**: se copian a un repo aparte de portafolio con
GitHub Pages (📤 Publicar en el portafolio, configurando la carpeta local en ⚙️ Ajustes).
Así el repo del CRM queda solo con código y ningún nombre de cliente entra a su historial
de git, que es para siempre.

El botón solo copia archivos. El `git add / commit / push` lo das tú, para que nada salga
a internet sin que lo revises antes.

**La carpeta lleva un token aleatorio, no el nombre del negocio** (`dx-rSskwNBAokTMtKll`).
La URL es la única protección del documento: con el nombre dentro, cualquiera podría
adivinar links probando negocios. Además la página va con `noindex, nofollow`, así que no
aparece en buscadores. Quien tenga el link lo ve — mándalo solo al prospecto.

El token es estable: regenerar el diagnóstico de un lead no invalida un link ya enviado.

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
`evidencia_dolor`, `mensaje_plantilla`, `track_recomendado`, `senales_investigacion`,
`valor_estimado`

Y las del generador de mensajes: `tipo_dolor`, `tipo_destinatario`, `tratamiento`,
`num_sucursales`, `num_resenas`, `num_profesionales`, `sistema_detectado`,
`canales_detectados`, `horario_extendido`, `publico_extranjero`.

- Encabezados reconocidos sin importar acentos, mayúsculas ni variantes (*Teléfono*,
  *Plataforma recomendada*, *Nombre del negocio*, *Giro*, *WhatsApp*, *Señales de
  investigación*). Lo que no reconoce lo ignora y te dice qué fue.
- **Nada se inserta sin vista previa**, con conteo de nuevos / duplicados / sin mensaje.
- **Duplicado = mismo `negocio` + mismo `telefono`** normalizado a puros dígitos
  (`+52 33-1234-5678` y `3312345678` son el mismo). Detecta duplicados contra la base y
  repetidos dentro del propio archivo.
- **Columna faltante no bloquea**: se deja vacía. Sin `mensaje_plantilla` el lead entra
  marcado 🟡 y su detalle muestra la plantilla genérica lista para personalizar.
- `sector` que no se reconozca cae en `Otro`; `tipo_dolor` que no se reconozca queda
  **vacío** (= sin clasificar), y el detalle del lead lo marca para que lo elijas. Meterlo
  a la fuerza en una categoría produciría un gancho que no le corresponde al negocio.
- Los números vacíos entran como `NULL`, no como `0`: "no lo investigué" no es lo mismo
  que "tiene cero sucursales", y el generador elige plantilla según esa diferencia.
- Los sí/no aceptan lo que escriba un humano (`sí`, `x`, `TRUE`, `1`).
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

### En el celular: PWA y pantalla de pulgar (hecho)

El requisito real no era "que se vea en el teléfono", era: abrir → ver a quién seguir →
generar el mensaje → mandarlo, **en menos de 4 toques**. Streamlit no es mobile-first,
así que eso está trabajado explícitamente en `movil.py`:

- **"Agregar a pantalla de inicio"** (`static/manifest.json` + iconos). Se abre como
  app, sin barra de navegador. Requiere `enableStaticServing = true`, ya configurado.
- **Tarjetas en vez de tabla** en pantalla angosta. Una tabla de 17 columnas es
  inservible con el pulgar; en escritorio se sigue viendo la tabla completa.
- **Objetivos táctiles de 44 px** en botones, selects y campos.
- **Botón de WhatsApp a todo lo ancho** en cada tarjeta: es la acción más frecuente.
- Una sola columna, títulos compactos y sin desbordamiento horizontal.

Verificado en un navegador real a 390×844: sin scroll horizontal, botón más chico de
46 px, cero errores de JavaScript.

**Limitación conocida y aceptada:** sin señal no funciona nada. No hay modo offline y no
vale la pena construirlo en esta etapa.

**Sobre `st.cache_data` en las lecturas:** evaluado y descartado a propósito. Cachear no
reduce los *reruns* —que es lo que se siente con datos móviles—, solo abarata cada uno
del lado del servidor, y con 43 leads en SQLite local esa consulta ya cuesta
microsegundos. Lo que sí traería es invalidación: editas un lead y sigues viendo el
viejo. Riesgo real a cambio de nada medible. Vale la pena reconsiderarlo con Postgres
remoto, donde cada consulta sí cruza la red.

En móvil se renderizan la tabla y las tarjetas, y el CSS esconde la que no toca:
Streamlit no expone el ancho de pantalla del lado del servidor, así que decidirlo en CSS
es lo único que funciona sin recargar la página para medirla. Cuesta algo de ancho de
banda; a cambio, no hay un rerun extra al abrir la vista.

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
| `mensajes.py` | Generador de mensajes: fórmula, variación por lead, límites de palabras. |
| `plantillas_gancho.py` | Catálogo de ganchos, servicios y fraseo. **Datos, no lógica.** |
| `scoring.py` | Score de lead, calendario de follow-ups, razones de urgencia. |
| `movil.py` | PWA (manifest e iconos) y CSS de pantalla de celular. |
| `diagnostico.py` | Generador del HTML del diagnóstico. |
| `tracking.py` | Cliente de Goatcounter + marcado manual de aperturas. |
| `metricas.py` | Métricas por sector y por tipo de dolor. |
| `importador.py` | Lectura de xlsx/csv, mapeo de encabezados, dedup, vista previa. |
| `whatsapp.py` | Normaliza teléfonos a E.164 y arma los links `wa.me`. |
| `plantillas.py` | Variables de plantilla y mensajes de seguimiento. |
| `config.py` | Rutas y secretos por entorno, muro de contraseña. |
| `migrate_excel.py` | Seed inicial desde `leads_tracker.xlsx`. |
| `test_consistencia.py` | Consistencia de catálogos + reglas de tono del generador. |
| `static/` | Manifest e iconos de la PWA. |
| `leads.db` | **Tus datos. No está en el repo. Es lo que hay que respaldar.** |

### Pruebas

```bash
python test_consistencia.py     # catálogos coherentes + reglas de tono
python -m doctest db.py mensajes.py plantillas.py whatsapp.py importador.py -v
```

`test_consistencia.py` existe por bugs reales, no por completar cobertura: un campo
importable sin etiqueta reventaba la vista de carga con `KeyError`, y las reglas de tono
del generador se prueban sobre todas las combinaciones porque el caso que rompe siempre
es el del lead del que casi no se investigó nada.

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
