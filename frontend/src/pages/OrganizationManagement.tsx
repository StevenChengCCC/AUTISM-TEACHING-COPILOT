import { useEffect, useState } from "react";
import { api } from "../api/client";
import { StatusMessage } from "../components/StatusMessage";
import type { Organization } from "../types";

export function OrganizationManagementPage() {
  const [items, setItems] = useState<Organization[]>([]);
  const [name, setName] = useState("Demo Clinic");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .listOrganizations()
      .then(setItems)
      .catch((err) =>
        setError(
          err instanceof Error ? err.message : "Failed to load organizations",
        ),
      );
  }, []);

  async function create() {
    try {
      const saved = await api.createOrganization({ name, external_ref: null });
      setItems([saved, ...items]);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create organization",
      );
    }
  }

  return (
    <section className="card">
      <h2>Organization Management</h2>
      {error && <StatusMessage tone="error">{error}</StatusMessage>}
      <label>Name</label>
      <input value={name} onChange={(event) => setName(event.target.value)} />
      <button className="primary" onClick={create}>
        Create Organization
      </button>
      {items.map((item) => (
        <div className="row" key={item.id}>
          {item.name}
        </div>
      ))}
    </section>
  );
}
