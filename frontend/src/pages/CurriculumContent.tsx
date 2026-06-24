import { useEffect, useState } from "react";
import { api } from "../api/client";
import { StatusMessage } from "../components/StatusMessage";
import type { CurriculumContent } from "../types";

export function CurriculumContentPage() {
  const [items, setItems] = useState<CurriculumContent[]>([]);
  const [title, setTitle] = useState("Apple receptive ID template");
  const [contentType, setContentType] = useState("goal_template");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .listCurriculum()
      .then(setItems)
      .catch((err) =>
        setError(
          err instanceof Error ? err.message : "Failed to load curriculum",
        ),
      );
  }, []);

  async function create() {
    try {
      const saved = await api.createCurriculum({
        title,
        content_type: contentType,
        content_json: {
          version: 1,
          notes: "Reusable teaching content template",
        },
        organization_id: null,
        status: "draft",
      });
      setItems([saved, ...items]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to create curriculum content",
      );
    }
  }

  return (
    <section className="card">
      <h2>Curriculum Content</h2>
      {error && <StatusMessage tone="error">{error}</StatusMessage>}
      <label>Title</label>
      <input value={title} onChange={(event) => setTitle(event.target.value)} />
      <label>Type</label>
      <select
        value={contentType}
        onChange={(event) => setContentType(event.target.value)}
      >
        <option value="goal_template">goal_template</option>
        <option value="lesson_template">lesson_template</option>
        <option value="card_template">card_template</option>
        <option value="generalization_template">generalization_template</option>
      </select>
      <button className="primary" onClick={create}>
        Create Content
      </button>
      {items.map((item) => (
        <div className="row" key={item.id}>
          {item.title} · {item.content_type} · {item.status}
        </div>
      ))}
    </section>
  );
}
