import { useEffect, useState } from 'react';
import { PaginaReales, PaginaSimulados } from './vistas/Paginas';
import VistaModelo from './vistas/VistaModelo';

const SECCIONES = [
  { id: 'reales', nombre: 'Datos reales', componente: PaginaReales },
  { id: 'simulados', nombre: 'Simulados', componente: PaginaSimulados },
  { id: 'modelo', nombre: 'Los modelos', componente: VistaModelo },
] as const;

type IdDeSeccion = (typeof SECCIONES)[number]['id'];

// La sección activa se guarda en la dirección (#simulados/nido/los_santos) para poder compartir el enlace
const seccionDeLaDireccion = (): IdDeSeccion =>
  SECCIONES.find((s) => s.id === window.location.hash.slice(1).split('/')[0])?.id ?? 'reales';

export default function App() {
  const [activa, setActiva] = useState<IdDeSeccion>(seccionDeLaDireccion);
  const Seccion = SECCIONES.find((s) => s.id === activa)!.componente;

  useEffect(() => {
    const alCambiar = () => setActiva(seccionDeLaDireccion());
    window.addEventListener('hashchange', alCambiar);
    return () => window.removeEventListener('hashchange', alCambiar);
  }, []);

  return (
    <div className="app">
      <header className="cabecera">
        <div className="marca">
          <h1>Centinelas de Santander</h1>
          <span>Riesgo sísmico en Los Santos · datos del Servicio Geológico Colombiano</span>
        </div>
        <nav className="pestanas" aria-label="Secciones">
          {SECCIONES.map((s) => (
            <button key={s.id} className={s.id === activa ? 'activa' : undefined} aria-current={s.id === activa ? 'page' : undefined} onClick={() => (window.location.hash = s.id)}>
              {s.nombre}
            </button>
          ))}
        </nav>
      </header>
      <main className="contenido">
        <Seccion />
      </main>
    </div>
  );
}
