import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { ExchangeTerminal } from './components/ExchangeTerminal';
import { Landing } from './components/Landing';
import { OmsApp } from './components/OmsApp';
import { ResearchApp } from './components/ResearchApp';

// Three independent apps, each at its own route with its own identity — tied together only by a
// landing hub. Not one mashed multi-tab app; a portfolio of separate, self-contained products.
// AuthProvider wraps them all so the signed-in JWT rides on every OMS API call.
export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/exchange" element={<ExchangeTerminal />} />
          <Route path="/oms" element={<OmsApp />} />
          <Route path="/research" element={<ResearchApp />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
