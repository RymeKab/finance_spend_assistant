// Page layout: a header, the summary on the left and the chat on the right.
import { ChatPanel } from "./components/ChatPanel";
import { SummaryPanel } from "./components/SummaryPanel";

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Finance Spend Assistant</h1>
        <p>2025 vendor invoices · Global Procurement &amp; Spend Policy FIN-POL-014</p>
      </header>
      <main className="layout">
        <SummaryPanel />
        <ChatPanel />
      </main>
    </div>
  );
}
