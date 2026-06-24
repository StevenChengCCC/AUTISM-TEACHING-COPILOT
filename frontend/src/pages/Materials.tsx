import { useEffect, useState } from "react";
import { api } from "../api/client";
import { StatusMessage } from "../components/StatusMessage";
import type { ChildProfile, UploadedMaterial } from "../types";

type Props = { child: ChildProfile | null };

export function MaterialsPage({ child }: Props) {
  const [items, setItems] = useState<UploadedMaterial[]>([]);
  const [form, setForm] = useState({
    title: "Baseline notes",
    material_type: "txt",
    source_path: "",
    extracted_text: "",
    status: "uploaded",
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (!child) return;
    api
      .listMaterials(child.id)
      .then(setItems)
      .catch(() => setItems([]));
  }, [child]);

  async function saveMaterial() {
    if (!child) {
      setError("Select a child first.");
      return;
    }
    setError("");
    setSuccess("");
    try {
      const saved = await api.createMaterial({ child_id: child.id, ...form });
      setItems([saved, ...items]);
      setSuccess("Material attached to child profile.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save material");
    }
  }

  return (
    <section className="grid two">
      <div className="card">
        <h2>Materials / Uploaded资料</h2>
        {error && <StatusMessage tone="error">{error}</StatusMessage>}
        {success && <StatusMessage tone="success">{success}</StatusMessage>}
        <label>Title</label>
        <input
          value={form.title}
          onChange={(event) => setForm({ ...form, title: event.target.value })}
        />
        <label>Material type</label>
        <input
          value={form.material_type}
          onChange={(event) =>
            setForm({ ...form, material_type: event.target.value })
          }
        />
        <label>Source path</label>
        <input
          value={form.source_path}
          onChange={(event) =>
            setForm({ ...form, source_path: event.target.value })
          }
        />
        <label>Extracted text</label>
        <input
          value={form.extracted_text}
          onChange={(event) =>
            setForm({ ...form, extracted_text: event.target.value })
          }
        />
        <button className="primary" onClick={saveMaterial}>
          Attach Material
        </button>
      </div>
      <div className="card">
        <h2>Attached Materials</h2>
        {items.map((item) => (
          <div className="row" key={item.id}>
            <strong>{item.title}</strong>
            <br />
            {item.material_type} · {item.status}
            <small>
              PDF/DOCX extraction is planned; txt/md placeholder extraction is
              backend-only.
            </small>
          </div>
        ))}
      </div>
    </section>
  );
}
