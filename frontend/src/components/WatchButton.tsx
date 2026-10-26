import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, ApiError } from "../api";

// Añade la oportunidad al seguimiento (prioridad media, revisión en 7 días). El resto se ajusta
// en la pantalla Seguimiento.
export function WatchButton({ opportunityId }: { opportunityId: string }) {
  const queryClient = useQueryClient();
  const watchlist = useQuery({ queryKey: ["watchlist"], queryFn: api.watchlist });
  const add = useMutation({
    mutationFn: () => api.watch(opportunityId, "MEDIUM", null),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
  if (watchlist.isPending || watchlist.isError) return null;
  const watching = watchlist.data.some((w) => w.opportunity_id === opportunityId);
  if (watching) {
    return (
      <p className="watch-state">
        <span className="pill ok">En seguimiento</span> <Link to="/watchlist">Ver seguimiento</Link>
      </p>
    );
  }
  return (
    <p className="watch-state">
      <button type="button" className="ghost" disabled={add.isPending} onClick={() => { add.mutate(); }}>
        {add.isPending ? "Añadiendo…" : "Añadir a seguimiento"}
      </button>
      {add.isError && (
        <span role="alert"> {add.error instanceof ApiError ? add.error.message : "No se pudo añadir."}</span>
      )}
    </p>
  );
}
