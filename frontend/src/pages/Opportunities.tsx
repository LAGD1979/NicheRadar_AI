import { useQuery } from "@tanstack/react-query";
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api";
import { ExplorationSteps } from "../components/ExplorationSteps";
import { formatDateTime, formatField, stateFor } from "../format";
import { MAX_COMPARE, canSelect, isCompareReady, toggleSelection } from "../selection";
import type { OpportunityItem } from "../types";

const PAGE_SIZE = 20;

const FILTERS: Array<{ key: string; label: string; options: Array<[string, string]> }> = [
  {
    key: "video_type",
    label: "Tipo de video",
    options: [["LONG", "Largo"], ["SHORT", "Short"], ["UNKNOWN", "Desconocido"]],
  },
  {
    key: "saturation_es",
    label: "Saturación ES",
    options: [["LOW", "Baja"], ["MEDIUM", "Media"], ["HIGH", "Alta"], ["UNKNOWN", "Desconocida"]],
  },
  {
    key: "spanish_demand_state",
    label: "Demanda ES",
    options: [["OBSERVED", "Observada"], ["INDICATIVE", "Indicativa"], ["UNPROVEN", "No demostrada"], ["NOT_OBSERVED", "No observada"]],
  },
  {
    key: "faceless_state",
    label: "Faceless",
    options: [["FACELESS_CONFIRMED", "Confirmado"], ["FACELESS_LIKELY", "Probable"], ["MIXED", "Mixto"], ["NOT_FACELESS", "No faceless"]],
  },
  {
    key: "rights_risk",
    label: "Riesgo de derechos",
    options: [["LOW", "Bajo"], ["MEDIUM", "Medio"], ["HIGH", "Alto"]],
  },
  {
    key: "confidence",
    label: "Confianza",
    options: [["HIGH", "Alta"], ["MEDIUM", "Media"], ["LOW", "Baja"], ["INSUFFICIENT", "Insuficiente"]],
  },
];

const SORTS: Array<[string, string]> = [
  ["name", "Nicho (A–Z)"],
  ["-name", "Nicho (Z–A)"],
  ["confidence", "Confianza (menor primero)"],
  ["-confidence", "Confianza (mayor primero)"],
  ["status", "Estado"],
];

const helper = createColumnHelper<OpportunityItem>();
const show = (value: unknown): string => formatField(value, stateFor(value));

export function Opportunities() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const page = Math.max(1, Number(params.get("page") ?? "1") || 1);
  const query = useQuery({
    queryKey: ["opportunities", params.toString()],
    queryFn: () => {
      const next = new URLSearchParams(params);
      next.set("page", String(page));
      next.set("page_size", String(PAGE_SIZE));
      if (!next.get("sort")) next.set("sort", "name");
      return api.opportunities(next);
    },
  });

  const columns = useMemo(
    () => [
      helper.display({
        id: "select",
        header: () => <span>Elegir</span>,
        cell: ({ row }) => {
          const id = row.original.id;
          const checked = selected.has(id);
          return (
            <input
              type="checkbox"
              checked={checked}
              disabled={!checked && !canSelect(selected, id)}
              aria-label={`Comparar ${row.original.niche} · ${row.original.format}`}
              onChange={() => { setSelected((s) => toggleSelection(s, id)); }}
            />
          );
        },
      }),
      helper.display({
        id: "name",
        header: "Nicho · formato",
        cell: ({ row }) => (
          <Link to={`/opportunities/${encodeURIComponent(row.original.id)}`}>
            {row.original.niche}
            <br />
            <small>{row.original.format}</small>
          </Link>
        ),
      }),
      helper.accessor("replication_state", { header: "Replicación", cell: (c) => show(c.getValue()) }),
      helper.accessor("saturation_es", { header: "Saturación ES", cell: (c) => show(c.getValue()) }),
      helper.accessor("spanish_demand_state", { header: "Demanda ES", cell: (c) => show(c.getValue()) }),
      helper.accessor("entry_decision", { header: "Decisión", cell: (c) => show(c.getValue()) }),
      helper.accessor("faceless_state", { header: "Faceless", cell: (c) => show(c.getValue()) }),
      helper.accessor("complexity_1_to_5", { header: "Complejidad (1–5)", cell: (c) => show(c.getValue()) }),
      helper.accessor("confidence", { header: "Confianza", cell: (c) => show(c.getValue()) }),
      helper.accessor("status", { header: "Estado", cell: (c) => show(c.getValue()) }),
      helper.accessor("observed_at", { header: "Observado", cell: (c) => formatDateTime(c.getValue()) }),
    ],
    [selected],
  );

  const table = useReactTable({
    data: query.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.id,
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    setParams(next);
  }

  function goToPage(target: number) {
    const next = new URLSearchParams(params);
    next.set("page", String(target));
    setParams(next);
  }

  const total = query.data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <section aria-labelledby="titulo-oportunidades">
      <ExplorationSteps current="validate" />
      <h1 id="titulo-oportunidades">Oportunidades</h1>
      <p className="hint">
        Cada fila es un nicho con un formato. Un dato vacío se muestra como «Sin dato», no como cero.
      </p>

      <form className="filters" onSubmit={(e) => { e.preventDefault(); }} aria-label="Filtros">
        <label>
          Buscar
          <input
            type="search"
            value={params.get("q") ?? ""}
            onChange={(e) => { setParam("q", e.target.value); }}
            placeholder="Nicho o formato"
          />
        </label>
        {FILTERS.map((f) => (
          <label key={f.key}>
            {f.label}
            <select value={params.get(f.key) ?? ""} onChange={(e) => { setParam(f.key, e.target.value); }}>
              <option value="">Todos</option>
              {f.options.map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label>
          Orden
          <select value={params.get("sort") ?? "name"} onChange={(e) => { setParam("sort", e.target.value); }}>
            {SORTS.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </label>
      </form>

      <div className="toolbar">
        <p aria-live="polite">
          {selected.size} de {MAX_COMPARE} seleccionadas
        </p>
        <button
          type="button"
          disabled={!isCompareReady([...selected])}
          onClick={() => { navigate(`/compare?ids=${[...selected].join(",")}`); }}
        >
          Comparar seleccionadas
        </button>
        <span className="export-links">
          Exportar con estos filtros:{" "}
          <a href={`/api/v1/exports/opportunities.csv?${params.toString()}`}>CSV</a>
          {" · "}
          <a href={`/api/v1/exports/opportunities.json?${params.toString()}`}>JSON</a>
        </span>
      </div>

      {query.isPending && <p>Cargando oportunidades…</p>}
      {query.isError && (
        <p role="alert">No se pudieron cargar las oportunidades ({query.error.message}).</p>
      )}
      {query.isSuccess && total === 0 && (
        <p className="empty">Sin resultados con estos filtros. Quite alguno para ver más oportunidades.</p>
      )}

      {query.isSuccess && total > 0 && (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                {table.getHeaderGroups().map((group) => (
                  <tr key={group.id}>
                    {group.headers.map((header) => (
                      <th key={header.id} scope="col">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="pager" aria-label="Paginación">
            <button type="button" disabled={page <= 1} onClick={() => { goToPage(page - 1); }}>
              Anterior
            </button>
            <span>
              Página {page} de {lastPage} · {total} oportunidades
            </span>
            <button type="button" disabled={page >= lastPage} onClick={() => { goToPage(page + 1); }}>
              Siguiente
            </button>
          </nav>
        </>
      )}
    </section>
  );
}
