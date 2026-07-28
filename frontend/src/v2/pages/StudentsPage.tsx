import { useEffect, useMemo, useState } from "react";
import { lessonKitApi } from "../api/lessonKitApi";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Tag } from "../components/Tag";
import { LearnerAvatar } from "../components/Avatar";
import type { LearnerProfile, LearnerRecord, RecentLesson } from "../types";

const filters = ["All", "Visual support", "AAC", "Communication", "Attention", "New"];

export function StudentsPage({
  onStartLesson,
  onCreateLearner,
  onFeedback,
}: {
  onStartLesson: (id: string) => void;
  onCreateLearner: () => void;
  onFeedback: (message: string) => void;
}) {
  const [learners, setLearners] = useState<LearnerProfile[]>([]);
  const [records, setRecords] = useState<Record<string, LearnerRecord[]>>({});
  const [lessons, setLessons] = useState<RecentLesson[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All");

  useEffect(() => {
    void lessonKitApi.getLearners().then(async (items) => {
      setLearners(items);
      setSelectedId((current) => current || items[0]?.id || "");
      const pairs = await Promise.all(items.map(async (item) => {
        try {
          return [item.id, await lessonKitApi.getRecordsForLearner(item.id)] as const;
        } catch {
          return [item.id, []] as const;
        }
      }));
      setRecords(Object.fromEntries(pairs));
    }).catch((error) => {
      onFeedback(error instanceof Error ? error.message : "Learners could not be loaded.");
    });
  }, [onFeedback]);

  useEffect(() => {
    if (!selectedId) return;
    void lessonKitApi.getRecentLessonsForLearner(selectedId)
      .then(setLessons)
      .catch(() => setLessons([]));
  }, [selectedId]);

  const filtered = useMemo(() => learners.filter((item) => {
    const matchesSearch = item.code.toLowerCase().includes(query.toLowerCase());
    const terms = [...item.tags, ...item.supportNeeds, item.communicationMode].join(" ").toLowerCase();
    const matchesFilter = filter === "All"
      || (filter === "New"
        ? item.profileReviewStatus !== "confirmed"
        : filter === "Visual support"
          ? terms.includes("visual")
          : terms.includes(filter.toLowerCase()));
    return matchesSearch && matchesFilter;
  }), [learners, query, filter]);
  const selected = learners.find((item) => item.id === selectedId) ?? learners[0];

  return (
    <section>
      <div className="v2-page-heading">
        <h1>Students</h1>
        <p>Manage learner profiles and start a personalized teaching kit.</p>
      </div>
      <div className="v2-students-layout">
        <Card>
          <div className="v2-toolbar">
            <label className="v2-search">
              <span>⌕</span>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search learners by code" />
            </label>
            <Button variant="secondary" onClick={onCreateLearner}>＋ New learner</Button>
          </div>
          <div className="v2-student-filters">
            {filters.map((item) => (
              <button key={item} className={filter === item ? "is-active" : ""} onClick={() => setFilter(item)}>{item}</button>
            ))}
          </div>
          <div className="v2-student-list">
            {filtered.map((learner) => (
              <button className={selected?.id === learner.id ? "is-selected" : ""} key={learner.id} onClick={() => setSelectedId(learner.id)}>
                <LearnerAvatar learnerId={learner.id} avatar={learner.avatar} alt="" size={62} />
                <div>
                  <strong>{learner.code}</strong>
                  <small>{learner.age > 0 ? `Age ${learner.age}` : "Age to confirm"}</small>
                  <p>{learner.notes || "Profile details awaiting teacher review."}</p>
                </div>
                <div className="v2-student-tags">
                  {learner.tags.slice(0, 2).map((tag) => <Tag tone={tag === "Attention" ? "amber" : tag === "AAC" ? "purple" : "blue"} key={tag}>{tag}</Tag>)}
                </div>
                <small>▤ {records[learner.id]?.length ?? 0} records<br />◷ {learner.profileReviewStatus === "confirmed" ? "Profile current" : "Review needed"}</small>
              </button>
            ))}
          </div>
        </Card>

        {selected && (
          <Card className="v2-profile-panel">
            <h2>Learner Profile</h2>
            <div className="v2-profile-title">
              <LearnerAvatar learnerId={selected.id} avatar={selected.avatar} alt={`${selected.code} avatar`} size={76} />
              <div>
                <h2>{selected.code}</h2>
                <p>{selected.age > 0 ? `Age ${selected.age}` : "Age to confirm"}</p>
                {selected.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}
              </div>
            </div>
            <dl className="v2-profile-details">
              <div><dt>◯ Primary communication</dt><dd>{selected.communicationMode || "To confirm"}</dd></div>
              <div><dt>♡ Support needs</dt><dd>{selected.supportNeeds.join(", ") || "To confirm"}</dd></div>
              <div><dt>☆ Interests</dt><dd>{selected.interests.join(", ") || "To confirm"}</dd></div>
              <div><dt>♢ Reinforcement preferences</dt><dd>{selected.reinforcementPreferences.join(", ") || "To confirm"}</dd></div>
              <div><dt>▤ Notes</dt><dd>{selected.notes || "No confirmed notes yet."}</dd></div>
            </dl>
            <div className="v2-mini-panels">
              <div>
                <strong>▤ &nbsp; Records on file</strong>
                <p>Profiles <b>{records[selected.id]?.length ?? 0}</b></p>
                <p>Support plans <b>{records[selected.id]?.filter((item) => item.fileType.toLowerCase().includes("iep") || item.fileType.toLowerCase().includes("support")).length ?? 0}</b></p>
                <button onClick={() => onFeedback(`${selected.code} has ${records[selected.id]?.length ?? 0} records on file.`)}>View all records ›</button>
              </div>
              <div>
                <strong>▣ &nbsp; Recent teaching kits</strong>
                {lessons.length
                  ? lessons.slice(0, 3).map((lesson) => <p key={lesson.id}>{lesson.title}<small>{lesson.date}</small></p>)
                  : <p>No teaching kits yet</p>}
                <button onClick={() => onFeedback(`${lessons.length} recent teaching kit${lessons.length === 1 ? "" : "s"} found.`)}>View all kits ›</button>
              </div>
            </div>
            <div className="v2-page-actions">
              <Button variant="secondary" onClick={() => onFeedback(`${selected.code} is ready for profile editing.`)}>✎ &nbsp; Edit learner</Button>
              <Button onClick={() => onStartLesson(selected.id)}>▷ &nbsp; Create teaching kit</Button>
            </div>
          </Card>
        )}
      </div>
    </section>
  );
}
