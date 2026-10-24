import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { Compare } from "./pages/Compare";
import { OpportunityDetail } from "./pages/OpportunityDetail";
import { Opportunities } from "./pages/Opportunities";
import { Runs } from "./pages/Runs";
import { Settings } from "./pages/Settings";
import { Summary } from "./pages/Summary";
import { Videos } from "./pages/Videos";

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Summary />} />
        <Route path="/opportunities" element={<Opportunities />} />
        <Route path="/opportunities/:id" element={<OpportunityDetail />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/videos" element={<Videos />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<p role="alert">Página no encontrada.</p>} />
      </Routes>
    </Layout>
  );
}
