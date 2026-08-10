"""Catálogo del generador de mensajes: ganchos, servicios y fraseo.

Este archivo es **datos, no lógica**. Se edita para cambiar cómo suenan los mensajes
sin abrir `mensajes.py`. Ahí vive el armado; aquí, lo que se dice.

## Por qué está separado el gancho de la evidencia

`evidencia_dolor` es prosa redactada para que Gerardo la lea antes de escribir. Detectar
el dolor buscando palabras dentro de ese texto es frágil: alguien redacta distinto y el
gancho se cae sin que nadie se entere. Por eso el dolor se **clasifica** en `tipo_dolor`
(un enum) y los hechos se capturan **estructurados** (números y sí/no).

Tampoco se pide un gancho escrito a mano por lead: eso solo mueve el trabajo manual de
lugar — 24 leads serían 24 frases que redactar. Aquí Gerardo teclea números; la oración
la arma el generador.

## La regla que sostiene todo

Cada `tipo_dolor` **termina** con una plantilla sin campos requeridos. Así ningún lead se
queda sin mensaje, por poco que se sepa de él. Si agregas plantillas, la última de la
lista siempre debe tener `requiere: ()`. `mensajes.verificar_catalogo()` lo comprueba y
`test_consistencia.py` lo corre.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Ganchos: la primera plantilla cuyos campos requeridos estén llenos, gana.
# --------------------------------------------------------------------------- #
# Van de más específica a más genérica. Entre más datos haya del lead, más concreto
# suena el mensaje — y lo concreto es lo que hace que alguien conteste.
#
# Ninguna plantilla menciona reseñas negativas, calificaciones ni quejas, aunque sean
# la mejor evidencia: ofende o asusta a alguien que no te conoce. Se nombra el problema
# estructural y el prospecto conecta solo. `num_resenas` se usa únicamente como señal
# de VOLUMEN, nunca de calificación.

GANCHOS: dict[str, list[dict]] = {
    "multisede_sin_visibilidad": [
        {
            # `min` de 2 no es capricho: con num_sucursales = 1 la frase sale como
            # "Vi que tienen 1 sucursales", y además el argumento multisede no
            # aplica. Debajo queda la versión sin número.
            "texto": "Vi que tienen {num_sucursales} sucursales y todas comparten el mismo WhatsApp.",
            "requiere": ("num_sucursales",),
            "min": {"num_sucursales": 2},
        },
        {
            "texto": "Vi que manejan varias sucursales con un solo número de contacto.",
            "requiere": (),
        },
    ],
    "canales_sin_unificar": [
        {
            "texto": "Vi que usan {sistema_detectado} para agendar, pero los mensajes de "
                     "{canales_detectados} no entran ahí.",
            "requiere": ("sistema_detectado", "canales_detectados"),
        },
        {
            "texto": "Vi que ya tienen {sistema_detectado} para agendar, y que además les "
                     "escriben por otras vías que no llegan ahí.",
            "requiere": ("sistema_detectado",),
        },
        {
            "texto": "Vi que les llega gente por {canales_detectados}, cada canal por su lado.",
            "requiere": ("canales_detectados",),
        },
        {
            "texto": "Vi que tienen varias vías de contacto que no se conectan entre sí.",
            "requiere": (),
        },
    ],
    "seguimiento_manual": [
        # El brief pide esta plantilla requiriendo solo `num_profesionales`, pero la
        # frase afirma además que el horario es amplio. Decirlo sin el dato sería
        # inventar, así que exige los dos y justo debajo queda la versión que solo
        # necesita el número de profesionales.
        {
            # Igual que con las sucursales: con 1 saldría "son 1 profesionales", y el
            # argumento de coordinación entre varios ni siquiera aplica.
            "texto": "Vi que atienden con horario amplio y son {num_profesionales} profesionales.",
            "requiere": ("num_profesionales", "horario_extendido"),
            "min": {"num_profesionales": 2},
        },
        {
            "texto": "Vi que son {num_profesionales} profesionales atendiendo en paralelo.",
            "requiere": ("num_profesionales",),
            "min": {"num_profesionales": 2},
        },
        {
            # `num_resenas_aprox` redondea hacia abajo (906 → 900) para que "más de"
            # sea literalmente cierto. Y por debajo de 60 reseñas la frase "bastante
            # volumen" no se sostiene, así que ahí ni se usa.
            "texto": "Vi que manejan bastante volumen de consultas — más de "
                     "{num_resenas_aprox} reseñas lo dicen.",
            "requiere": ("num_resenas",),
            "min": {"num_resenas": 60},
        },
        {
            "texto": "Vi que atienden con un horario bastante amplio.",
            "requiere": ("horario_extendido",),
        },
        {
            "texto": "Vi cómo llevan el seguimiento de sus clientes.",
            "requiere": (),
        },
    ],
    "sin_datos": [
        {
            "texto": "Vi que mueven buen volumen — más de {num_resenas_aprox} reseñas lo "
                     "dicen — y me quedé pensando en cuánto de eso alcanzan a medir hoy.",
            "requiere": ("num_resenas",),
            "min": {"num_resenas": 60},
        },
        {
            "texto": "Vi que tienen {num_sucursales} sucursales operando en paralelo, cada una "
                     "con sus propios números.",
            "requiere": ("num_sucursales",),
            "min": {"num_sucursales": 2},
        },
        {
            "texto": "Vi que ya usan {sistema_detectado}, que guarda bastante información del "
                     "día a día.",
            "requiere": ("sistema_detectado",),
        },
        {
            "texto": "Vi cómo opera el negocio y me quedé con la duda de qué tanto se alcanza "
                     "a medir de lo que pasa cada semana.",
            "requiere": (),
        },
    ],
    "procesos_repetitivos": [
        {
            "texto": "Vi que son {num_profesionales} profesionales coordinándose todos los días.",
            "requiere": ("num_profesionales",),
            "min": {"num_profesionales": 2},
        },
        {
            "texto": "Vi que ya usan {sistema_detectado} y que aun así buena parte de la "
                     "coordinación diaria sigue siendo a mano.",
            "requiere": ("sistema_detectado",),
        },
        {
            "texto": "Vi que atienden con horario amplio, casi todos los días.",
            "requiere": ("horario_extendido",),
        },
        {
            "texto": "Vi la cantidad de coordinación diaria que lleva una operación como la suya.",
            "requiere": (),
        },
    ],
}


# --------------------------------------------------------------------------- #
# Servicio a mencionar según el dolor
# --------------------------------------------------------------------------- #
# Fragmentos que continúan la transición ("Justo en eso trabajo: …"). El primero es
# el servicio principal de la tabla del brief; el segundo lo aterriza en consecuencia
# concreta. Si el mensaje se pasa de largo, `mensajes.py` suelta el segundo primero.
#
# El catálogo está pensado para crecer sin tocar la lógica del generador: agregar un
# `tipo_dolor` es agregar una entrada aquí, otra en GANCHOS y otra en db.TIPOS_DOLOR.

SERVICIOS: dict[str, tuple[str, str]] = {
    "canales_sin_unificar": (
        # Sin repetir los nombres de los canales: el gancho acaba de decirlos, y
        # repetirlos a dos renglones suena a plantilla.
        "juntar todas esas vías de contacto en un solo lugar",
        "que quede registro de quién escribió y quién se quedó sin respuesta",
    ),
    "seguimiento_manual": (
        "poner recordatorios automáticos de seguimiento",
        "que nadie se quede sin respuesta porque se pasó el día",
    ),
    "sin_datos": (
        "ordenar los datos que el negocio ya genera",
        "dejar un reporte simple de lo que pasó cada semana",
    ),
    "procesos_repetitivos": (
        "automatizar con IA las tareas operativas que se repiten",
        "quitarle a su equipo el trabajo manual que no aporta",
    ),
    "multisede_sin_visibilidad": (
        # "montar" y no "armar": una de las transiciones es "Justo eso es lo que
        # armo:", y "armo: armar un tablero" es un ripio que se oye feo.
        "montar un tablero simple por sucursal",
        "poder comparar las sedes entre sí sin pedir reportes a mano",
    ),
}

# A marketing no le duele la operación interna: le duele la captación. Mismo dolor,
# otro ángulo.
SERVICIOS_MARKETING: dict[str, tuple[str, str]] = {
    "canales_sin_unificar": (
        "juntar los mensajes de todos los canales en un solo lugar",
        "poder medir de qué campaña llegó cada prospecto",
    ),
    "seguimiento_manual": (
        "dar seguimiento automático a los prospectos que ya levantaron la mano",
        "que la inversión en captación no se caiga en el último paso",
    ),
    "sin_datos": (
        "medir qué canal trae los clientes que sí cierran",
        "dejar de decidir presupuesto por corazonada",
    ),
    "procesos_repetitivos": (
        "automatizar la parte manual del embudo",
        "que el equipo dedique el tiempo a campañas y no a copiar datos",
    ),
    "multisede_sin_visibilidad": (
        "separar por sucursal de dónde llega cada prospecto",
        "saber qué sede convierte mejor lo que les mandan",
    ),
}


# --------------------------------------------------------------------------- #
# Bloques fijos, con variantes
# --------------------------------------------------------------------------- #
# 20+ mensajes de la misma fórmula se notan si el fraseo es idéntico. Cada bloque
# tiene varias versiones equivalentes y la elección es determinística según el `id`
# del lead: el mismo lead produce siempre el mismo mensaje (se puede regenerar sin
# sorpresas), pero dos leads distintos suenan distinto.

SALUDOS_SIN_TRATAMIENTO = (
    "Hola, buen día.",
    "Hola, ¿qué tal? Buen día.",
    "Buen día.",
    "Hola, ¿cómo está?",
)

SALUDOS_CON_TRATAMIENTO = (
    "Hola, {tratamiento}, buen día.",
    "{tratamiento}, buen día.",
    "Hola, {tratamiento}. ¿Cómo está?",
    "Buen día, {tratamiento}.",
)

# El título nunca es "Ingeniero": Gerardo es estudiante, y el framing honesto es
# deliberado — es parte de por qué la gente contesta.
IDENTIDADES = (
    "Soy {mi_nombre}, estudio Ingeniería en Software aquí en Guadalajara.",
    "Me llamo {mi_nombre}; estudio Ingeniería en Software aquí en Guadalajara.",
    "Soy {mi_nombre}, estudiante de Ingeniería en Software aquí en Guadalajara.",
    "Soy {mi_nombre} — estudio Ingeniería en Software aquí en la ciudad.",
)

TRANSICIONES = (
    "Justo en eso trabajo:",
    "A eso me dedico:",
    "Es justo lo que hago:",
    "Justo eso es lo que armo:",
)

# Todo cierre lleva salida explícita. Que sea fácil decir que no es lo que hace que
# valga la pena contestar.
CIERRES = (
    "Si le interesa, le preparo sin costo un diagnóstico corto de cómo se ve hoy. "
    "Si no es el momento, no hay problema.",
    "Le puedo mandar un diagnóstico breve, sin costo, para que lo vea con calma. "
    "Y si no es el momento, ningún problema.",
    "¿Le late si le preparo un diagnóstico corto, sin costo ni compromiso? "
    "Si no es el momento, no pasa nada.",
    "Si quiere, le mando sin costo un diagnóstico breve de cómo está eso hoy. "
    "Si no es el momento, aquí lo dejamos.",
)

# Versión corta, para cuando el mensaje se pasa del límite de palabras.
CIERRES_CORTOS = (
    "Si quiere le mando un diagnóstico corto, sin costo. Si no es el momento, no hay problema.",
    "Le paso un diagnóstico breve sin costo si le interesa. Si no, ningún problema.",
    "¿Le mando un diagnóstico corto sin costo? Y si no es el momento, no pasa nada.",
    "Le comparto un diagnóstico breve sin costo si le sirve. Si no, aquí lo dejamos.",
)


# --------------------------------------------------------------------------- #
# Recepción: no se le vende a recepción
# --------------------------------------------------------------------------- #
# Quien contesta no decide, y tratarlo como si decidiera quema el contacto. El único
# objetivo aquí es que el mensaje llegue a quien sí decide — por eso se pide explícito
# y se aclara qué NO es, que es lo que recepción filtra todo el día.

PETICIONES_RECEPCION = (
    "¿Me haría el favor de pasárselo a quien lleva la operación?",
    "¿Se lo podría hacer llegar a quien está a cargo del negocio?",
    "¿Me ayudaría a pasárselo al dueño o a quien lleve la administración?",
    "¿Podría hacérselo llegar a quien toma este tipo de decisiones?",
)

ACLARACIONES_RECEPCION = (
    "No vendo insumos ni publicidad.",
    "No es venta de insumos ni de publicidad.",
    "No ando vendiendo productos ni anuncios.",
    "No es publicidad ni venta de material.",
)

CIERRES_RECEPCION = (
    "Si no es algo que les interese, no hay problema — gracias de todos modos.",
    "Si no les interesa, ningún problema. Gracias por leerlo.",
    "Si no es el momento, no pasa nada. Gracias.",
    "Si no aplica para ustedes, sin problema — gracias por el apoyo.",
)


# --------------------------------------------------------------------------- #
# DM (Instagram y similares): 50 palabras
# --------------------------------------------------------------------------- #
# En un DM no se detallan servicios: eso va en la respuesta, si contesta. Aquí solo
# hay saludo, gancho, una línea de oferta y salida.

OFERTAS_DM = (
    "Armo sistemas para ordenar justo eso.",
    "Me dedico a ordenar justo esa parte.",
    "Trabajo en resolver justo eso.",
    "Es justo lo que hago.",
)

CIERRES_DM = (
    "¿Le mando un diagnóstico corto sin costo? Si no es el momento, no hay problema.",
    "Si quiere le paso un diagnóstico breve, sin costo. Si no, ningún problema.",
    "¿Le interesa un diagnóstico corto sin costo? Si no, no pasa nada.",
    "Le comparto un diagnóstico breve sin costo si le late. Si no, aquí lo dejamos.",
)


# --------------------------------------------------------------------------- #
# Límites
# --------------------------------------------------------------------------- #
MAX_PALABRAS = 90       # WhatsApp
MAX_PALABRAS_DM = 50    # Instagram y otros DM
