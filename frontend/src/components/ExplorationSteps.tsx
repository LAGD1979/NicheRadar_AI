import { Link } from "react-router-dom";

export type StepKey = "discover" | "group" | "validate" | "produce" | "decide";

const STEPS: Array<{ key: StepKey; to: string; title: string; hint: string }> = [
  { key: "discover", to: "/runs", title: "Descubrir", hint: "Traer videos desde YouTube o vidIQ" },
  { key: "group", to: "/videos", title: "Elegir y agrupar", hint: "Asignar videos a un nicho y un formato" },
  { key: "validate", to: "/opportunities", title: "Validar en español", hint: "Competencia y demanda" },
  { key: "produce", to: "/opportunities", title: "Costo y factibilidad", hint: "Producción con IA" },
  { key: "decide", to: "/compare", title: "Comparar y decidir", hint: "De 2 a 8 oportunidades" },
];

// Guía de la ruta de exploración. Marca el paso actual y enlaza con los demás.
export function ExplorationSteps({ current }: { current: StepKey }) {
  const currentIndex = STEPS.findIndex((step) => step.key === current);
  return (
    <nav className="steps" aria-label="Ruta de exploración">
      <ol>
        {STEPS.map((step, index) => {
          const state = index < currentIndex ? "done" : index === currentIndex ? "current" : "todo";
          return (
            <li key={step.key} className={`step ${state}`}>
              <Link to={step.to} aria-current={state === "current" ? "step" : undefined}>
                <span className="step-number" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="step-text">
                  <span className="step-title">{step.title}</span>
                  <span className="step-hint">{step.hint}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
