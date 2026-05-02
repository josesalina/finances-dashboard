import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/layout/Layout";
import Dashboard from "./pages/Dashboard";
import Pipeline from "./pages/Pipeline";
import MonthReport from "./pages/MonthReport";
import Dividends from "./pages/Dividends";
import DividendConfig from "./pages/DividendConfig";
import Semaforos from "./pages/Semaforos";
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/months/:id" element={<MonthReport />} />
          <Route path="/dividends" element={<Dividends />} />
          <Route path="/semaforos" element={<Semaforos />} />
          <Route path="/dividend-config" element={<DividendConfig />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
