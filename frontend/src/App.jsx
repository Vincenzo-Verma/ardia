import ResearchForm from "./components/ResearchForm";

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-start pt-16 px-4">
      <h1 className="text-3xl font-bold text-gray-900 mb-2">Research Agent</h1>
      <p className="text-gray-500 text-sm mb-8">
        Submit a research question and receive a formatted report.
      </p>
      <ResearchForm />
    </div>
  );
}
