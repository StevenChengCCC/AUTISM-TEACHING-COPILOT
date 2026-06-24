import { useEffect, useState } from "react";
import { api } from "../api/client";
import { StatusMessage } from "../components/StatusMessage";
import type { ChildProfile, Teacher, TeacherChildAccess } from "../types";

type Props = { children: ChildProfile[] };

export function TeacherAccessManagementPage({ children }: Props) {
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [access, setAccess] = useState<TeacherChildAccess[]>([]);
  const [teacherName, setTeacherName] = useState("Teacher A");
  const [teacherId, setTeacherId] = useState("");
  const [childId, setChildId] = useState("");
  const [permissionLevel, setPermissionLevel] = useState("editor");
  const [error, setError] = useState("");

  async function refresh() {
    setTeachers(await api.listTeachers());
    setAccess(await api.listAccess());
  }

  useEffect(() => {
    refresh().catch((err) =>
      setError(err instanceof Error ? err.message : "Failed to load access"),
    );
  }, []);

  async function createTeacher() {
    const saved = await api.createTeacher({
      display_name: teacherName,
      role: "teacher",
      email: null,
      organization_id: null,
    });
    setTeachers([saved, ...teachers]);
  }

  async function grantAccess() {
    const saved = await api.createAccess({
      teacher_id: Number(teacherId),
      child_id: Number(childId),
      permission_level: permissionLevel,
    });
    setAccess([saved, ...access]);
  }

  return (
    <section className="grid two">
      <div className="card">
        <h2>Teacher Access</h2>
        {error && <StatusMessage tone="error">{error}</StatusMessage>}
        <label>Teacher name</label>
        <input
          value={teacherName}
          onChange={(event) => setTeacherName(event.target.value)}
        />
        <button className="primary" onClick={() => void createTeacher()}>
          Create Teacher
        </button>
        <label>Teacher</label>
        <select
          value={teacherId}
          onChange={(event) => setTeacherId(event.target.value)}
        >
          <option value="">Select teacher</option>
          {teachers.map((teacher) => (
            <option key={teacher.id} value={teacher.id}>
              {teacher.display_name}
            </option>
          ))}
        </select>
        <label>Child</label>
        <select
          value={childId}
          onChange={(event) => setChildId(event.target.value)}
        >
          <option value="">Select child</option>
          {children.map((child) => (
            <option key={child.id} value={child.id}>
              {child.code}
            </option>
          ))}
        </select>
        <label>Permission</label>
        <select
          value={permissionLevel}
          onChange={(event) => setPermissionLevel(event.target.value)}
        >
          <option value="viewer">viewer</option>
          <option value="editor">editor</option>
          <option value="admin">admin</option>
        </select>
        <button className="primary" onClick={() => void grantAccess()}>
          Grant Access
        </button>
      </div>
      <div className="card">
        <h2>Access Grants</h2>
        {access.map((item) => (
          <div className="row" key={item.id}>
            Teacher {item.teacher_id} → Child {item.child_id} ·{" "}
            {item.permission_level}
          </div>
        ))}
      </div>
    </section>
  );
}
