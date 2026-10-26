// Consulta de outliers a vidIQ. La validación refleja la de la API (backend/app/api/v1/schemas.py).

export const VIDIQ_LANGUAGES: Array<[string, string]> = [
  ["en", "Inglés"],
  ["es", "Español"],
  ["pt", "Portugués"],
  ["fr", "Francés"],
  ["de", "Alemán"],
  ["it", "Italiano"],
  ["ja", "Japonés"],
  ["ko", "Coreano"],
  ["ru", "Ruso"],
  ["tr", "Turco"],
  ["pl", "Polaco"],
  ["uk", "Ucraniano"],
  ["ar", "Árabe"],
  ["hi", "Hindi"],
  ["th", "Tailandés"],
];

export const VIDIQ_WINDOWS: Array<[string, string]> = [
  ["thisWeek", "Esta semana"],
  ["thisMonth", "Este mes"],
  ["threeMonths", "Últimos 3 meses"],
  ["sixMonths", "Últimos 6 meses"],
  ["oneYear", "Último año"],
];

// Formatos que vidIQ reconoce (vidiq_trend_categories). Solo cambia el texto mostrado; el ID es el del proveedor.
export const VIDIQ_CATEGORIES: Array<[string, string]> = [
  ["24_hour_challenge", "Reto de 24 horas"],
  ["100_layers", "100 capas"],
  ["ambient", "Ambiente relajante"],
  ["apartment_tour", "Recorrido por un departamento"],
  ["asmr", "ASMR"],
  ["beginners_guide", "Guía para principiantes"],
  ["billionaire_romance", "Romance de multimillonarios"],
  ["blindfold_test", "Prueba con los ojos vendados"],
  ["body_transformation", "Transformación corporal"],
  ["building_in_game", "Construcción en un juego"],
  ["cheap_vs_expensive", "Barato contra caro"],
  ["closet_clean_out", "Limpieza de clóset"],
  ["compilation", "Recopilación"],
  ["conspiracy", "Teorías de conspiración"],
  ["cooking_recipe", "Receta de cocina"],
  ["cost_of_living", "Costo de vida"],
  ["countdown_timer", "Cuenta regresiva"],
  ["day_in_my_life", "Un día en mi vida"],
  ["diy", "Hágalo usted mismo"],
  ["dollar_vs", "Un dólar contra mil"],
  ["draw_my_life", "Dibujo mi vida"],
  ["eating_only", "Comer solo una cosa"],
  ["everything_wrong", "Todo lo que está mal en…"],
  ["fake_vs_real", "Falso contra real"],
  ["full_documentary", "Documental completo"],
  ["full_episode", "Episodio completo"],
  ["full_movie", "Película completa"],
  ["full_podcast_or_interview", "Pódcast o entrevista completa"],
  ["glow_up", "Transformación de imagen"],
  ["grwm", "Prepárate conmigo"],
  ["guess_the", "Adivina…"],
  ["haul", "Compras mostradas"],
  ["hide_and_seek", "Escondite"],
  ["honest_review", "Reseña honesta"],
  ["hot_ones_style", "Entrevista con picante"],
  ["how_to", "Cómo hacer"],
  ["i_got_caught", "Me atraparon"],
  ["i_survived", "Sobreviví"],
  ["i_tried", "Lo probé"],
  ["kids_songs", "Canciones infantiles"],
  ["last_to_leave", "El último en irse"],
  ["lets_play", "Partida comentada"],
  ["microphone_test", "Prueba de micrófonos"],
  ["morning_routine", "Rutina de la mañana"],
  ["mukbang", "Mukbang"],
  ["my_collection", "Mi colección"],
  ["mystery_box", "Caja misteriosa"],
  ["never_have_i_ever", "Yo nunca"],
  ["night_routine", "Rutina de la noche"],
  ["pov", "Punto de vista"],
  ["prank", "Broma"],
  ["prophetic_chosen_ones", "Profético / elegidos"],
  ["ranking_every", "Clasificar todo"],
  ["rating", "Calificación"],
  ["reaction", "Reacción"],
  ["remaking_recreating", "Recrear algo"],
  ["rich_vs_poor", "Rico contra pobre"],
  ["roast", "Parodia crítica (roast)"],
  ["room_makeover", "Renovación de habitación"],
  ["setup_tour", "Recorrido por un puesto de trabajo"],
  ["shopping_spree", "Compras sin límite"],
  ["side_hustle", "Ingresos extra"],
  ["speedrun", "Speedrun"],
  ["stream_marathon", "Maratón de transmisión"],
  ["storytime", "Historia contada"],
  ["study_with_me", "Estudia conmigo"],
  ["swap_lives", "Intercambio de vidas"],
  ["switching_to", "Cambiarme a…"],
  ["taste_test", "Prueba de sabor"],
  ["things_i_wish", "Cosas que ojalá hubiera sabido"],
  ["thrift_flip", "Renovar ropa de segunda mano"],
  ["tier_list", "Lista por niveles"],
  ["tips_tricks", "Consejos y trucos"],
  ["top_x", "Los mejores X"],
  ["travel_guide", "Guía de viaje"],
  ["travel_vlog", "Vlog de viaje"],
  ["trying_x_so_you_dont", "Lo pruebo para que usted no tenga que"],
  ["type_beat", "Pista instrumental (type beat)"],
  ["unboxing", "Desempaque"],
  ["video_essay", "Ensayo en video"],
  ["vtuber", "VTuber"],
  ["we_broke_up", "Terminamos"],
  ["weekly_vlog", "Vlog semanal"],
  ["what_i_eat", "Qué como en un día"],
  ["what_i_eat_athlete", "Qué como en un día (fitness)"],
  ["workout", "Entrenamiento"],
  ["x_hour_long", "De X horas de duración"],
  ["x_years_later", "X años después"],
  ["zodiac_tarot", "Zodiaco y tarot"],
];

export const CREDITS_PER_CALL = 5;
export const MAX_CALLS_LIMIT = 20;

// "open": sin tema ni formato (descubrimiento sin sesgo). "format": una categoría. "topic": una palabra clave.
export type VidiqMode = "open" | "format" | "topic";

export interface VidiqForm {
  mode: VidiqMode;
  language: string;
  category: string;
  keyword: string;
  window: string;
  contentType: "long" | "short";
  maxSubscribers: number;
  minViews: number;
  limit: number;
  maxCalls: number;
}

export const INITIAL_VIDIQ_FORM: VidiqForm = {
  mode: "open",
  language: "en",
  category: "",
  keyword: "",
  window: "threeMonths",
  contentType: "long",
  maxSubscribers: 100000,
  minViews: 100000,
  limit: 20,
  maxCalls: 1,
};

export interface VidiqBody {
  kind: "vidiq";
  vidiq: {
    searches: Array<Record<string, unknown>>;
    max_calls: number;
  };
}

export type VidiqResult = { ok: true; body: VidiqBody } | { ok: false; error: string };

export function buildVidiqRequest(form: VidiqForm): VidiqResult {
  if (form.mode === "format" && !VIDIQ_CATEGORIES.some(([id]) => id === form.category)) {
    return { ok: false, error: "Elija un formato de la lista." };
  }
  const keyword = form.keyword.trim();
  if (form.mode === "topic" && (keyword.length < 2 || keyword.length > 200)) {
    return { ok: false, error: "El tema debe tener entre 2 y 200 caracteres." };
  }
  if (form.contentType === "short" && form.language !== "en") {
    return { ok: false, error: "Los Shorts solo están disponibles en inglés." };
  }
  if (!Number.isInteger(form.maxCalls) || form.maxCalls < 1 || form.maxCalls > MAX_CALLS_LIMIT) {
    return { ok: false, error: `Las consultas deben estar entre 1 y ${String(MAX_CALLS_LIMIT)}.` };
  }
  if (!Number.isInteger(form.limit) || form.limit < 1 || form.limit > 50) {
    return { ok: false, error: "Los resultados por consulta deben estar entre 1 y 50." };
  }
  if (form.maxSubscribers < 0 || form.minViews < 0) {
    return { ok: false, error: "Los filtros no pueden ser negativos." };
  }
  const search: Record<string, unknown> = {
    language: form.language,
    content_type: form.contentType,
    published_within: form.window,
    max_subscribers: form.maxSubscribers,
    min_views: form.minViews,
    limit: form.limit,
  };
  if (form.mode === "format") search.trend_categories = [form.category];
  if (form.mode === "topic") search.keyword = keyword;
  return { ok: true, body: { kind: "vidiq", vidiq: { searches: [search], max_calls: form.maxCalls } } };
}

export function estimatedCredits(maxCalls: number): number {
  return maxCalls * CREDITS_PER_CALL;
}
