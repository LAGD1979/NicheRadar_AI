import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { api } from "../api";

const OVERVIEW = { to: "/", label: "Resumen" };
// El orden sigue la ruta de exploración: descubrir, agrupar, validar y decidir.
const EXPLORE = [
  { to: "/runs", label: "Corridas", step: "1" },
  { to: "/videos", label: "Videos", step: "2" },
  { to: "/opportunities", label: "Oportunidades", step: "3-4" },
  { to: "/compare", label: "Comparador", step: "5" },
];
const OTHERS = [{ to: "/settings", label: "Configuración" }];

const MANUALS_HREF = "/manual/index.html";

export function Layout({ children }: { children: ReactNode }) {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const showBanner = config.data?.synthetic_banner ?? true;

  return (
    <div className="shell">
      <header className="topbar">
        <strong className="brand">NicheRadar AI</strong>
        {showBanner && (
          <span className="demo-banner" role="status">
            DATOS SINTÉTICOS · DEMO
          </span>
        )}
      </header>
      <div className="body">
        <nav className="sidenav" aria-label="Principal">
          <ul>
            <li>
              <NavLink to={OVERVIEW.to} end>
                {OVERVIEW.label}
              </NavLink>
            </li>
            <li className="nav-group" aria-hidden="true">
              Exploración
            </li>
            {EXPLORE.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to}>
                  <span className="nav-step" aria-hidden="true">
                    {item.step}
                  </span>
                  {item.label}
                </NavLink>
              </li>
            ))}
            <li className="nav-group" aria-hidden="true">
              Sistema
            </li>
            {OTHERS.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to}>{item.label}</NavLink>
              </li>
            ))}
            {/* Los manuales son páginas estáticas: un enlace normal, no una ruta de la aplicación. */}
            <li>
              <a href={MANUALS_HREF}>Manuales</a>
            </li>
          </ul>
        </nav>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
