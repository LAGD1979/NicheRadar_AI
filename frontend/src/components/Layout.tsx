import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";

import { api } from "../api";

const NAV = [
  { to: "/", label: "Resumen" },
  { to: "/opportunities", label: "Oportunidades" },
  { to: "/videos", label: "Videos" },
  { to: "/compare", label: "Comparador" },
  { to: "/runs", label: "Corridas" },
  { to: "/settings", label: "Configuración" },
];

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
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.to === "/"}>
                  {item.label}
                </NavLink>
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
