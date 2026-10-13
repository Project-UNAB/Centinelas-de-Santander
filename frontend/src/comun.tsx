// Piezas compartidas por las vistas: colores de nivel, carga de datos, leyendas y bloques del panel.

import { useEffect, useState, type ReactNode } from 'react';
import type { Nivel } from './api';

export const NIVELES: Nivel[] = ['Bajo', 'Medio', 'Alto'];

// Verde, amarillo y rojo: siempre acompañados del nombre del nivel
export const COLOR_NIVEL: Record<Nivel, [number, number, number]> = {
  Bajo: [12, 163, 12],
  Medio: [250, 178, 25],
  Alto: [208, 59, 59],
};

export const css = (c: [number, number, number]) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`;

// En pantallas de muy alta densidad, dibujar cada píxel físico cuesta el doble o el triple
// sin que se note: se limita para que girar y acercar el relieve sea fluido
export const DENSIDAD_DE_PIXELES = Math.min(window.devicePixelRatio || 1, 1.5);

export const numero = (valor: number, decimales = 0) =>
  valor.toLocaleString('es-CO', { minimumFractionDigits: decimales, maximumFractionDigits: decimales });

export const porcentaje = (valor: number, decimales = 0) => `${numero(valor * 100, decimales)} %`;

/**
 * Pide datos a la API y expone el estado de la carga. Se piden una vez, o cada
 * vez que cambia la clave (por ejemplo, la zona): mientras llegan los nuevos no
 * se devuelven los anteriores, que serían de otra zona.
 */
export function useDatos<T>(pedir: () => Promise<T>, clave = '') {
  const [recibido, setRecibido] = useState<{ clave: string; datos: T } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vigente = true;
    setError(null);
    pedir()
      .then((datos) => vigente && setRecibido({ clave, datos }))
      .catch((e: Error) => vigente && setError(e.message));
    return () => {
      vigente = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clave]);

  return { datos: recibido?.clave === clave ? recibido.datos : null, error };
}

/** Pesos abreviados para que quepan en el panel: $ 1,4 billones, $ 2.747 millones, $ 850 mil. */
export function pesos(valor: number) {
  if (valor >= 1e12) return `$ ${numero(valor / 1e12, 1)} billones`;
  if (valor >= 1e6) return `$ ${numero(valor / 1e6, valor >= 1e8 ? 0 : 1)} millones`;
  if (valor >= 1e3) return `$ ${numero(valor / 1e3)} mil`;
  return `$ ${numero(valor)}`;
}

export function Estado({ error }: { error: string | null }) {
  if (error) {
    return (
      <div className="estado estado-error" role="alert">
        <strong>No se pudo conectar con el backend.</strong>
        <span>{error}</span>
        <span>Comprueba que la API esté en marcha y que VITE_API_URL apunte a ella.</span>
      </div>
    );
  }
  return <div className="estado">Cargando datos…</div>;
}

export function Leyenda({ titulo, descripciones }: { titulo: string; descripciones: Record<Nivel, string> }) {
  return (
    <div className="leyenda">
      <div className="leyenda-titulo">{titulo}</div>
      {NIVELES.map((nivel) => (
        <div className="leyenda-fila" key={nivel}>
          <span className="muestra" style={{ background: css(COLOR_NIVEL[nivel]) }} />
          <strong>{nivel}</strong>
          <span>{descripciones[nivel]}</span>
        </div>
      ))}
    </div>
  );
}

/** Leyenda del mapa de calor: degradado continuo con los tres niveles bajo él. */
export function LeyendaDeCalor({ titulo, descripciones }: { titulo: string; descripciones: Record<Nivel, string> }) {
  return (
    <div className="leyenda leyenda-calor">
      <div className="leyenda-titulo">{titulo}</div>
      <div className="degradado" />
      <div className="degradado-niveles">
        {NIVELES.map((nivel) => (
          <div key={nivel}>
            <strong>{nivel}</strong>
            <span>{descripciones[nivel]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function EtiquetaDeNivel({ nivel }: { nivel: Nivel }) {
  return (
    <span className="etiqueta-nivel">
      <span className="muestra" style={{ background: css(COLOR_NIVEL[nivel]) }} />
      {nivel}
    </span>
  );
}

// ------------------------------------------------------------------------------ bloques del panel
const TRAZOS = {
  capas: (
    <>
      <path d="M12 3 3 8l9 5 9-5-9-5Z" />
      <path d="m3 12.5 9 5 9-5M3 17l9 5 9-5" />
    </>
  ),
  reloj: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  sismo: <path d="M2 12h4l2-6 4 13 3-10 2 3h5" />,
  personas: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5M16 5.2a3.2 3.2 0 0 1 0 5.6M17.5 14.8c2.2.6 3.5 2.5 3.5 5.2" />
    </>
  ),
  punto: (
    <>
      <path d="M12 21s-6.5-6-6.5-11a6.5 6.5 0 0 1 13 0c0 5-6.5 11-6.5 11Z" />
      <circle cx="12" cy="10" r="2.3" />
    </>
  ),
  celda: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M4 12h16M12 4v16" />
    </>
  ),
  grafica: <path d="M3 20h18M6 20v-8M12 20V5M18 20v-5" />,
  casa: (
    <>
      <path d="M3.5 11 12 4l8.5 7" />
      <path d="M5.5 9.8V20h13V9.8M10 20v-5.5h4V20" />
    </>
  ),
  diana: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5.5M12 7.5v.5" />
    </>
  ),
};

export type NombreDeIcono = keyof typeof TRAZOS;

/** Icono de línea, del color del texto que lo rodea. Es decorativo: el título lo acompaña siempre. */
export function Icono({ nombre }: { nombre: NombreDeIcono }) {
  return (
    <svg className="icono" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {TRAZOS[nombre]}
    </svg>
  );
}

interface PropsDeBloque {
  icono: NombreDeIcono;
  titulo: ReactNode;
  /** De dónde salen los datos del bloque (por ejemplo «DANE · 2026»); se muestra como etiqueta */
  fuente?: string;
  children: ReactNode;
}

/** Recuadro del panel lateral: agrupa lo que va junto bajo un icono y un título. */
export function Bloque({ icono, titulo, fuente, children }: PropsDeBloque) {
  return (
    <section className="bloque">
      <header className="bloque-cabecera">
        <span className="bloque-icono">
          <Icono nombre={icono} />
        </span>
        <h3>{titulo}</h3>
        {fuente && <span className="fuente">{fuente}</span>}
      </header>
      {children}
    </section>
  );
}

/** Aclaración en letra pequeña, con un icono de información. */
export function Nota({ children }: { children: ReactNode }) {
  return (
    <p className="nota">
      <Icono nombre="info" />
      <span>{children}</span>
    </p>
  );
}
