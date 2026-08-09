"""Generador de diagnósticos operativos en HTML.

Toma la estructura del diagnóstico original (expediente, paleta quirófano / esmalte,
Instrument Serif + IBM Plex) y la parametriza por lead: negocio, dirección, puertas de
entrada detectadas y hallazgos tomados del banco de dolores.

Dos cosas de este documento NO son parametrizables y no deben serlo:

1. **La nota de honestidad del pie.** Se omiten cifras de pérdida estimadas porque
   inventar un número sin datos no es diagnóstico, es publicidad. Es la pieza que
   más credibilidad da.
2. **La firma.** "Gerardo Barrera — Ingeniería de Software y Redes". Sin el título
   de "Ingeniero": es estudiante, y el framing honesto es deliberado.
"""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import date
from pathlib import Path

import config
import db

DIRECTORIO_SALIDA = config.ruta_diagnosticos()

FIRMA_NOMBRE = "Gerardo Barrera"
FIRMA_TITULO = "Ingeniería de Software y Redes · Sistemas de verificación y automatización operativa"

NOTA_HONESTIDAD = """<b>Sobre este documento.</b><br>
  Construido únicamente con información pública: perfiles, sitios web, herramientas
  visibles y reseñas de clientes. No hay acceso a datos internos, cifras ni sistemas
  del negocio.<br><br>
  Por lo mismo: los puntos marcados son <b>hipótesis estructurales</b>, no
  mediciones. Son los lugares donde este tipo de operación suele perder dinero.
  Cuáles aplican de verdad, y cuánto pesan, solo se sabe viéndolo por dentro.<br><br>
  Se omitieron deliberadamente cifras de pérdida estimadas. Inventar un número
  sin datos no es diagnóstico, es publicidad."""

PREMISA_DEFAULT = (
    "Un negocio pierde dinero por dos vías: la que ve en el estado de resultados y la "
    "que nunca aparece ahí. Esta segunda es el cliente que escribió, nadie alcanzó a "
    "contestar, y se fue con otro. No genera factura, no genera queja, no genera "
    "registro. Este documento marca dónde ocurre."
)

PROYECCION_DEFAULT = {
    "titulo": "El riesgo no es quedarse igual. Es crecer así.",
    "parrafos": [
        "Un embudo con fugas no falla despacio: falla proporcionalmente. Si mañana se "
        "duplica la inversión en anuncios, no se duplican los clientes — se duplica la "
        "fuga. Llega el doble de interés a las mismas bandejas, con el mismo equipo "
        "contestando.",
        "Y cada punto marcado arriba se agrava en la misma dirección: más mensajes sin "
        "responder, más presupuestos enfriándose en silencio, más coordinación manual "
        "sobre las mismas personas. El gasto en captación es visible de inmediato. "
        "El desperdicio, no.",
        "La secuencia correcta es inversa: primero se sella, después se escala. Sellar "
        "cuesta una fracción de lo que cuesta llenar un embudo roto.",
    ],
}


def slug(texto: str) -> str:
    """Nombre de carpeta seguro para URL a partir del nombre del negocio.

    >>> slug("Clinica Ejemplo")
    'clinica-ejemplo'
    >>> slug("Café  Ejemplo del Centro!")
    'cafe-ejemplo-del-centro'
    """
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn"
    )
    limpio = re.sub(r"[^a-zA-Z0-9]+", "-", sin_acentos.lower()).strip("-")
    return limpio or "diagnostico"


def parsear_puertas(texto: str) -> list[tuple[str, str]]:
    """Convierte el texto libre de puertas de entrada en pares (canal, detalle).

    Formato por línea: `Canal: detalle`. Si no hay dos puntos, todo va como canal.

    >>> parsear_puertas("Instagram: @ejemplo · 5,361 seg.\\nWhatsApp: 33 0000 0000")
    [('Instagram', '@ejemplo · 5,361 seg.'), ('WhatsApp', '33 0000 0000')]
    """
    puertas = []
    for linea in str(texto or "").splitlines():
        linea = linea.strip(" -•\t")
        if not linea:
            continue
        if ":" in linea:
            canal, detalle = linea.split(":", 1)
            puertas.append((canal.strip(), detalle.strip()))
        else:
            puertas.append((linea, ""))
    return puertas


def _esc(texto) -> str:
    return html.escape(str(texto or ""), quote=False)


def _bloque_puertas(puertas: list[tuple[str, str]]) -> str:
    if not puertas:
        return ""
    tarjetas = "\n".join(
        f'  <div class="puerta"><b>{_esc(canal)}</b><span>{_esc(detalle)}</span></div>'
        for canal, detalle in puertas
    )
    return (
        f'<p class="seccion-tit">01 — Puertas de entrada detectadas</p>\n'
        f'<div class="puertas rev" style="animation-delay:.08s">\n{tarjetas}\n</div>\n'
    )


def _bloque_hallazgos(hallazgos: list[dict]) -> str:
    """Cada hallazgo es una etapa del recorrido con su severidad."""
    if not hallazgos:
        return ""
    etapas = []
    for i, h in enumerate(hallazgos):
        grave = str(h.get("severidad", "GRAVE")).upper().startswith("GRAVE")
        clase_etapa = "fuga" if grave else "leve"
        clase_hallazgo = "" if grave else " obs"
        etiqueta = "Grave — bloqueante" if grave else "Observación"
        efecto = h.get("efecto") or ""
        bloque_efecto = f'\n      <span class="costo">{_esc(efecto)}</span>' if efecto else ""
        # El h3 es el nombre de la etapa del recorrido; el título del dolor es la
        # etiqueta interna del CRM. Si no hay etapa, se cae al título.
        encabezado = h.get("etapa") or h.get("titulo")
        contexto = h.get("contexto") or ""
        bloque_contexto = f'\n    <p>{_esc(contexto)}</p>' if contexto else ""
        etapas.append(
            f'  <div class="etapa {clase_etapa} rev" style="animation-delay:.{14 + i * 6:02d}s">\n'
            f'    <h3>{_esc(encabezado)}</h3>{bloque_contexto}\n'
            f'    <div class="hallazgo{clase_hallazgo}">\n'
            f'      <span class="sev">{etiqueta}</span>\n'
            f'      <p>{_esc(h.get("descripcion"))}</p>{bloque_efecto}\n'
            f"    </div>\n"
            f"  </div>"
        )
    cuerpo = "\n\n".join(etapas)
    return (
        f'<p class="seccion-tit">02 — Recorrido del cliente y puntos de fuga</p>\n'
        f'<div class="recorrido">\n\n{cuerpo}\n\n</div>\n'
    )


def ruta_tracking(token: str) -> str:
    """Ruta que se registra en Goatcounter para este lead.

    Se fija explícitamente en el snippet en vez de confiar en `?ref=`: Goatcounter
    ignora el query string por default, así que el token tiene que ir en el path.
    """
    return f"/dx/{token}"


def _snippet_tracking(sitio_goatcounter: str, token: str) -> str:
    """Contador de Goatcounter: sin cookies, sin datos personales, sin perfilar.

    Lo único que registra es que esta página se abrió y cuándo. No hay formularios,
    no hay identificadores del visitante, no hay terceros publicitarios.
    """
    if not sitio_goatcounter or not token:
        return (
            "<!-- Tracking desactivado: configura el sitio de Goatcounter en "
            "⚙️ Datos y ajustes del CRM y regenera este diagnóstico. -->"
        )
    dominio = sitio_goatcounter.strip().rstrip("/")
    if not dominio.startswith("http"):
        dominio = f"https://{dominio}"
    ruta = ruta_tracking(token)
    ajustes = html.escape(f'{{"path":"{ruta}","no_onload":false}}', quote=True)
    return (
        f'<script data-goatcounter="{html.escape(dominio, quote=True)}/count"\n'
        f"        data-goatcounter-settings='{ajustes}'\n"
        f'        async src="//gc.zgo.at/count.js"></script>\n'
        f'<noscript><img src="{html.escape(dominio, quote=True)}/count?p='
        f'{html.escape(ruta, quote=True)}" alt=""></noscript>'
    )


PLANTILLA = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>Diagnóstico Operativo — {negocio}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{{
    --quirofano:#132E2B;
    --quirofano-alto:#1D423D;
    --quirofano-borde:#2C5A53;
    --esmalte:#F5F3EE;
    --sonda:#8FAAA4;
    --hemorragia:#CF4A31;
    --ambar:#D9A03C;
    --paso:clamp(18px,4.5vw,26px);
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  html{{-webkit-text-size-adjust:100%}}
  body{{
    background:var(--quirofano);
    color:var(--esmalte);
    font-family:'IBM Plex Sans',system-ui,sans-serif;
    font-weight:300;
    line-height:1.6;
    padding:var(--paso);
    max-width:820px;
    margin:0 auto;
    -webkit-font-smoothing:antialiased;
  }}

  /* ── Expediente: cabecera ── */
  .expediente{{
    border:1px solid var(--quirofano-borde);
    padding:calc(var(--paso)*0.85);
    margin-bottom:calc(var(--paso)*1.6);
  }}
  .folio{{
    font-family:'IBM Plex Mono',monospace;
    font-size:.66rem;
    letter-spacing:.16em;
    color:var(--sonda);
    text-transform:uppercase;
    display:flex;
    justify-content:space-between;
    flex-wrap:wrap;
    gap:.4rem;
    padding-bottom:.9rem;
    border-bottom:1px solid var(--quirofano-borde);
    margin-bottom:1.1rem;
  }}
  h1{{
    font-family:'Instrument Serif',Georgia,serif;
    font-weight:400;
    font-size:clamp(2rem,8vw,3.2rem);
    line-height:1.02;
    letter-spacing:-.015em;
    margin-bottom:.5rem;
  }}
  h1 em{{font-style:italic;color:var(--sonda)}}
  .sujeto{{
    font-family:'IBM Plex Mono',monospace;
    font-size:.72rem;
    letter-spacing:.1em;
    color:var(--sonda);
    text-transform:uppercase;
  }}
  .premisa{{
    margin-top:1.1rem;
    font-size:.95rem;
    max-width:56ch;
    color:#DCD9D2;
  }}

  /* ── Sección ── */
  .seccion-tit{{
    font-family:'IBM Plex Mono',monospace;
    font-size:.68rem;
    letter-spacing:.19em;
    text-transform:uppercase;
    color:var(--sonda);
    padding-bottom:.5rem;
    border-bottom:1px solid var(--quirofano-borde);
    margin:calc(var(--paso)*1.5) 0 calc(var(--paso)*0.9);
  }}

  /* ── Puertas de entrada ── */
  .puertas{{
    display:grid;
    grid-template-columns:repeat(auto-fill,minmax(148px,1fr));
    gap:.55rem;
  }}
  .puerta{{
    background:var(--quirofano-alto);
    border:1px solid var(--quirofano-borde);
    padding:.72rem .85rem;
  }}
  .puerta b{{
    display:block;
    font-weight:500;
    font-size:.88rem;
    margin-bottom:.12rem;
  }}
  .puerta span{{
    font-family:'IBM Plex Mono',monospace;
    font-size:.66rem;
    color:var(--sonda);
    letter-spacing:.03em;
  }}

  /* ── Recorrido: el signature ── */
  .recorrido{{position:relative;padding-left:2.4rem;margin-top:.4rem}}
  .recorrido::before{{
    content:"";
    position:absolute;
    left:.62rem;top:.7rem;bottom:.7rem;
    width:2px;
    background:var(--quirofano-borde);
  }}
  .etapa{{position:relative;padding:0 0 1.5rem 0}}
  .etapa::before{{
    content:"";
    position:absolute;
    left:-2.13rem;top:.42rem;
    width:11px;height:11px;
    border-radius:50%;
    background:var(--quirofano);
    border:2px solid var(--sonda);
  }}
  .etapa.fuga::before{{
    background:var(--hemorragia);
    border-color:var(--hemorragia);
    box-shadow:0 0 0 5px rgba(207,74,49,.16);
  }}
  .etapa.leve::before{{
    background:var(--ambar);
    border-color:var(--ambar);
    box-shadow:0 0 0 5px rgba(217,160,60,.14);
  }}
  .etapa h3{{
    font-family:'IBM Plex Sans',sans-serif;
    font-weight:500;
    font-size:1.02rem;
    letter-spacing:.005em;
    margin-bottom:.2rem;
  }}
  .etapa p{{font-size:.9rem;color:#C9C6BF;max-width:58ch}}

  /* ── Hallazgo ── */
  .hallazgo{{
    margin-top:.75rem;
    border-left:3px solid var(--hemorragia);
    background:rgba(207,74,49,.07);
    padding:.8rem .95rem;
  }}
  .hallazgo.obs{{
    border-left-color:var(--ambar);
    background:rgba(217,160,60,.07);
  }}
  .sev{{
    font-family:'IBM Plex Mono',monospace;
    font-size:.6rem;
    letter-spacing:.17em;
    text-transform:uppercase;
    color:var(--hemorragia);
    display:block;
    margin-bottom:.3rem;
    font-weight:500;
  }}
  .hallazgo.obs .sev{{color:var(--ambar)}}
  .hallazgo p{{font-size:.87rem;color:#DEDBD4;max-width:60ch}}
  .costo{{
    display:block;
    margin-top:.5rem;
    font-family:'IBM Plex Mono',monospace;
    font-size:.72rem;
    color:var(--esmalte);
    letter-spacing:.02em;
  }}

  /* ── Proyección ── */
  .proyeccion{{
    border:1px solid var(--hemorragia);
    padding:calc(var(--paso)*0.9);
    margin-top:calc(var(--paso)*0.6);
  }}
  .proyeccion h2{{
    font-family:'Instrument Serif',Georgia,serif;
    font-weight:400;
    font-size:clamp(1.5rem,5.5vw,2.1rem);
    line-height:1.14;
    margin-bottom:.6rem;
  }}
  .proyeccion p{{font-size:.92rem;color:#DEDBD4;max-width:58ch}}
  .proyeccion p + p{{margin-top:.7rem}}

  /* ── Notas ── */
  .notas{{
    margin-top:calc(var(--paso)*1.5);
    padding-top:1rem;
    border-top:1px solid var(--quirofano-borde);
    font-family:'IBM Plex Mono',monospace;
    font-size:.68rem;
    line-height:1.75;
    color:var(--sonda);
  }}
  .notas b{{color:var(--esmalte);font-weight:500}}
  .firma{{
    margin-top:1.3rem;
    font-family:'IBM Plex Sans',sans-serif;
    font-size:.82rem;
    color:#C9C6BF;
    font-weight:300;
  }}
  .firma strong{{color:var(--esmalte);font-weight:500;display:block;font-size:.92rem}}

  /* ── Entrada ── */
  .rev{{opacity:0;transform:translateY(9px);animation:sube .55s ease forwards}}
  @keyframes sube{{to{{opacity:1;transform:none}}}}
  @media (prefers-reduced-motion:reduce){{
    .rev{{animation:none;opacity:1;transform:none}}
  }}
</style>
</head>
<body>

<header class="expediente rev">
  <div class="folio">
    <span>Diagnóstico operativo</span>
    <span>Elaborado sin acceso interno</span>
  </div>
  <h1>{titular_1}<br><em>{titular_2}</em></h1>
  <p class="sujeto">Sujeto: {negocio}{direccion_sufijo}</p>
  <p class="premisa">
    {premisa}
  </p>
</header>

{bloque_puertas}
{bloque_hallazgos}
<p class="seccion-tit">03 — Dónde puede sangrar más</p>
<div class="proyeccion rev" style="animation-delay:.44s">
  <h2>{proyeccion_titulo}</h2>
  {proyeccion_parrafos}
</div>

<div class="notas rev" style="animation-delay:.5s">
  {nota_honestidad}
</div>

<p class="firma">
  <strong>{firma_nombre}</strong>
  {firma_titulo}
</p>

{tracking}
</body>
</html>
"""


def construir_html(
    negocio: str,
    direccion: str = "",
    puertas: list[tuple[str, str]] | None = None,
    hallazgos: list[dict] | None = None,
    titular: tuple[str, str] = ("Dónde sangra", "el embudo."),
    premisa: str = PREMISA_DEFAULT,
    proyeccion: dict | None = None,
    sitio_goatcounter: str = "",
    token: str = "",
) -> str:
    """Arma el HTML completo del diagnóstico. No escribe nada en disco."""
    proyeccion = proyeccion or PROYECCION_DEFAULT
    parrafos = "\n  ".join(f"<p>{_esc(p)}</p>" for p in proyeccion.get("parrafos", []))

    return PLANTILLA.format(
        negocio=_esc(negocio),
        direccion_sufijo=f" · {_esc(direccion)}" if direccion else "",
        titular_1=_esc(titular[0]),
        titular_2=_esc(titular[1]),
        premisa=_esc(premisa),
        bloque_puertas=_bloque_puertas(puertas or []),
        bloque_hallazgos=_bloque_hallazgos(hallazgos or []),
        proyeccion_titulo=_esc(proyeccion.get("titulo", "")),
        proyeccion_parrafos=parrafos,
        nota_honestidad=NOTA_HONESTIDAD,
        firma_nombre=FIRMA_NOMBRE,
        firma_titulo=FIRMA_TITULO,
        tracking=_snippet_tracking(sitio_goatcounter, token),
    )


def carpeta_publicacion(token: str) -> str:
    """Nombre de la carpeta pública del diagnóstico.

    Lleva el token y NO el nombre del negocio: la URL es la única protección del
    documento, así que tiene que ser impredecible. Con el nombre dentro, cualquiera
    podría adivinar links probando negocios.
    """
    return f"dx-{token}"


def generar_para_lead(
    lead: dict,
    dolores: list[dict],
    puertas_texto: str = "",
    titular: tuple[str, str] = ("Dónde sangra", "el embudo."),
    premisa: str = PREMISA_DEFAULT,
    directorio: Path | None = None,
) -> dict:
    """Escribe `diagnosticos/dx-{token}/index.html` y devuelve rutas y URL.

    El token se conserva si el lead ya tenía uno, para no invalidar un link ya
    enviado.
    """
    directorio = directorio or DIRECTORIO_SALIDA
    token = (lead.get("token_diagnostico") or "").strip() or nuevo_token()
    carpeta_slug = carpeta_publicacion(token)
    destino = Path(directorio) / carpeta_slug
    destino.mkdir(parents=True, exist_ok=True)

    sitio = db.get_ajuste("goatcounter_sitio", "")

    contenido = construir_html(
        negocio=lead.get("negocio", ""),
        direccion=lead.get("direccion", ""),
        puertas=parsear_puertas(puertas_texto),
        hallazgos=dolores,
        titular=titular,
        premisa=premisa,
        sitio_goatcounter=sitio,
        token=token,
    )
    archivo = destino / "index.html"
    archivo.write_text(contenido, encoding="utf-8")

    return {
        "archivo": archivo,
        "carpeta": destino,
        "slug": slug(lead.get("negocio", "")),  # solo para nombrar la descarga local
        "token": token,
        "url": url_publica(token),
        "generado_en": date.today().isoformat(),
    }


def nuevo_token() -> str:
    """Token impredecible. Es lo único que protege el documento: quien tenga el
    link lo ve, así que no puede contener el nombre del negocio ni adivinarse."""
    import secrets

    return secrets.token_urlsafe(12)


def url_publica(token: str) -> str:
    """URL final del diagnóstico, según la base configurada en ajustes."""
    base = (db.get_ajuste("base_url_diagnosticos", "") or "").strip().rstrip("/")
    ruta = f"/{carpeta_publicacion(token)}/"
    return f"{base}{ruta}" if base else ruta


def publicar(carpeta_generada: Path) -> Path:
    """Copia el diagnóstico al repo de portafolio configurado en ajustes.

    Solo copia archivos: el `git add/commit/push` lo haces tú, para que nada salga
    a internet sin que lo revises antes.
    """
    import shutil

    destino_base = (db.get_ajuste("ruta_repo_portafolio", "") or "").strip()
    if not destino_base:
        raise ValueError(
            "Falta la ruta del repo de portafolio en ⚙️ Datos y ajustes."
        )
    raiz = Path(destino_base).expanduser()
    if not raiz.exists():
        raise ValueError(f"La ruta del repo de portafolio no existe: {raiz}")

    destino = raiz / Path(carpeta_generada).name
    shutil.copytree(carpeta_generada, destino, dirs_exist_ok=True)
    return destino


if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
