const BASE_URL = import.meta.env.VITE_API_URL;

export async function submitResearch(question, mode) {
  const response = await fetch(`${BASE_URL}/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, mode }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Failed to submit: ${text}`);
  }
  return response.json();
}

export async function pollStatus(jobId) {
  const response = await fetch(`${BASE_URL}/research/${jobId}`);
  if (!response.ok) throw new Error(`Poll failed: ${response.status}`);
  return response.json();
}

export function openStream(jobId) {
  return new EventSource(`${BASE_URL}/research/${jobId}/stream`);
}
