// Las dos secciones de la aplicación: datos reales y simulados. Cada una ofrece las
// mismas dos vistas (por zona y nido 3D), que se eligen con un filtro.

import { useState } from 'react';
import VistaNido3D from './VistaNido3D';
import VistaRiesgo from './VistaRiesgo';
import VistaSimulador from './VistaSimulador';

type Vista = 'zona' | 'nido';

const VISTAS: { id: Vista; nombre: string }[] = [
  { id: 'zona', nombre: 'Riesgo por zona' },
  { id: 'nido', nombre: 'Nido 3D' },
];

/** Vista indicada en la dirección (#simulados/nido/los_santos) o, si no hay, la de por zona. */
const vistaInicial = (): Vista => VISTAS.find((v) => v.id === window.location.hash.split('/')[1])?.id ?? 'zona';

function SelectorDeVista({ vista, alCambiar }: { vista: Vista; alCambiar: (vista: Vista) => void }) {
  return (
    <div className="selector" role="group" aria-label="Vista">
      {VISTAS.map((v) => (
        <button key={v.id} className={v.id === vista ? 'activa' : undefined} aria-pressed={v.id === vista} onClick={() => alCambiar(v.id)}>
          {v.nombre}
        </button>
      ))}
    </div>
  );
}

/** Solo datos reales: el riesgo que predice el modelo con el catálogo del SGC y los sismos registrados. */
export function PaginaReales() {
  const [vista, setVista] = useState<Vista>(vistaInicial);
  const selector = <SelectorDeVista vista={vista} alCambiar={setVista} />;
  return vista === 'zona' ? <VistaRiesgo encabezado={selector} /> : <VistaNido3D modo="reales" encabezado={selector} />;
}

/** Solo simulados: la sacudida de un sismo hipotético y un catálogo sintético del nido. */
export function PaginaSimulados() {
  const [vista, setVista] = useState<Vista>(vistaInicial);
  const selector = <SelectorDeVista vista={vista} alCambiar={setVista} />;
  return vista === 'zona' ? <VistaSimulador encabezado={selector} /> : <VistaNido3D modo="simulados" encabezado={selector} />;
}
