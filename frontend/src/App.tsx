import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppShell from "@/components/layout/AppShell";

import Login from "@/pages/Login";
import Datasets from "@/pages/Datasets";
import ReviewQueue from "@/pages/ReviewQueue";
import ReviewEditor from "@/pages/ReviewEditor";
import Chat from "@/pages/Chat";
import History from "@/pages/History";
import Insights from "@/pages/Insights";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* The sign-in page is shown without the sidebar */}
        <Route path="/login" element={<Login />} />

        {/* Everything else lives inside the shell (sidebar + server wake banner) */}
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/datasets" replace />} />
          <Route path="datasets" element={<Datasets />} />
          <Route path="review" element={<ReviewQueue />} />
          <Route path="review/:id" element={<ReviewEditor />} />
          <Route path="chat" element={<Chat />} />
          <Route path="history" element={<History />} />
          <Route path="insights" element={<Insights />} />
          <Route path="*" element={<Navigate to="/datasets" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
