import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { ChildProfile, ImagePipelineResult, LessonPlanResponse, SessionRecordRead } from '../types';
import '../styles.css';

function splitList(value: string): string[] {
  return value.split(/[，,\n]/).map((v) => v.trim()).filter(Boolean);
}

export function Dashboard() {
  const [children, setChildren] = useState<ChildProfile[]>([]);
  const [selectedChildId, setSelectedChildId] = useState<number | null>(null);
  const selectedChild = useMemo(() => children.find((c) => c.id === selectedChildId) ?? null, [children, selectedChildId]);

  const [childForm, setChildForm] = useState({
    code: `C-${Date.now().toString().slice(-4)}`,
    age: '8',
    diagnosis_level: 'ASD Level 2',
    attention_span_minutes: '5',
    communication_level: '能用短句表达需求',
    interests: '汽车, 恐龙',
    reinforcers: '汽车玩具, 贴纸',
    behavior_notes: '注意力容易下降，任务太长会逃避。',
    notes: 'MVP 示例孩子档案。正式环境建议只用匿名代号。',
  });

  const [targetSkill, setTargetSkill] = useState('认识苹果');
  const [concept, setConcept] = useState('苹果');
  const [neededCount, setNeededCount] = useState(10);
  const [variations, setVariations] = useState('颜色变式, 角度变式, 场景变式, 媒介变式');
  const [imageResult, setImageResult] = useState<ImagePipelineResult | null>(null);
  const [approvedIndexes, setApprovedIndexes] = useState<number[]>([]);
  const [lesson, setLesson] = useState<LessonPlanResponse | null>(null);
  const [record, setRecord] = useState({ independent_count: 0, prompted_count: 0, error_count: 0, notes: '' });
  const [savedRecord, setSavedRecord] = useState<SessionRecordRead | null>(null);
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.listChildren().then((items) => {
      setChildren(items);
      if (items.length > 0) setSelectedChildId(items[0].id);
    }).catch(() => setChildren([]));
  }, []);

  async function createChild() {
    setError('');
    try {
      const child = await api.createChild({
        code: childForm.code,
        age: Number(childForm.age) || null,
        diagnosis_level: childForm.diagnosis_level,
        attention_span_minutes: Number(childForm.attention_span_minutes) || null,
        communication_level: childForm.communication_level,
        interests: splitList(childForm.interests),
        reinforcers: splitList(childForm.reinforcers),
        behavior_notes: childForm.behavior_notes,
        notes: childForm.notes,
      });
      setChildren([child, ...children]);
      setSelectedChildId(child.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建失败');
    }
  }

  async function runImagePipeline() {
    if (!selectedChildId) return setError('请先选择孩子档案');
    setLoading(true);
    setError('');
    setImageResult(null);
    setApprovedIndexes([]);
    try {
      const images = await api.runImagePipeline({
        child_id: selectedChildId,
        target_skill: targetSkill,
        concept,
        needed_count: neededCount,
        prefer_real_photos: true,
        variation_requirements: splitList(variations),
      });
      setImageResult(images);
    } catch (e) {
      setError(e instanceof Error ? e.message : '运行失败');
    } finally {
      setLoading(false);
    }
  }

  function toggleApproved(index: number) {
    setApprovedIndexes((prev) => prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]);
  }

  async function saveApprovedImages() {
    if (!imageResult) return;
    setError('');
    try {
      await api.confirmImages({
        candidates: imageResult.candidates,
        approved_indexes: approvedIndexes,
        skill_target: targetSkill,
        concept,
      });
      alert('已保存到资源库。下次会优先复用，降低成本。');
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败');
    }
  }

  async function createLesson() {
    if (!selectedChildId) return setError('请先选择孩子档案');
    setLoading(true);
    setError('');
    setLesson(null);
    try {
      const generatedLesson = await api.createLesson({
        child_id: selectedChildId,
        target_skill: targetSkill,
        duration_minutes: 25,
        selected_image_asset_ids: [],
      });
      setLesson(generatedLesson);
    } catch (e) {
      setError(e instanceof Error ? e.message : '生成失败');
    } finally {
      setLoading(false);
    }
  }

  async function submitRecord() {
    if (!selectedChildId) return setError('请先选择孩子档案');
    setError('');
    try {
      const res = await api.createRecord({ child_id: selectedChildId, target_skill: targetSkill, ...record });
      setSavedRecord(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : '记录失败');
    }
  }

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">AI Special Education Teaching Copilot</p>
          <h1>1v1 特教备课资源打包系统</h1>
          <p>把能用代码完成的环节代码化：孩子档案、注意力拆课、泛化模板、强化轮换、记录评分。AI 只预留给复杂生成和图片 API。</p>
        </div>
        <div className="heroActions">
          <button onClick={runImagePipeline} disabled={loading}>运行图片流程</button>
          <button className="primary" onClick={createLesson} disabled={loading}>生成教学包</button>
        </div>
      </header>

      {error && <section className="error">{error}</section>}

      <section className="grid two">
        <div className="card">
          <h2>1. 孩子档案库</h2>
          <div className="formGrid">
            <input value={childForm.code} onChange={(e) => setChildForm({ ...childForm, code: e.target.value })} placeholder="孩子代号" />
            <input value={childForm.age} onChange={(e) => setChildForm({ ...childForm, age: e.target.value })} placeholder="年龄" />
            <input value={childForm.diagnosis_level} onChange={(e) => setChildForm({ ...childForm, diagnosis_level: e.target.value })} placeholder="诊断/支持等级" />
            <input value={childForm.attention_span_minutes} onChange={(e) => setChildForm({ ...childForm, attention_span_minutes: e.target.value })} placeholder="注意力分钟" />
          </div>
          <label>沟通能力</label>
          <input value={childForm.communication_level} onChange={(e) => setChildForm({ ...childForm, communication_level: e.target.value })} />
          <label>兴趣</label>
          <input value={childForm.interests} onChange={(e) => setChildForm({ ...childForm, interests: e.target.value })} />
          <label>强化物</label>
          <input value={childForm.reinforcers} onChange={(e) => setChildForm({ ...childForm, reinforcers: e.target.value })} />
          <button onClick={createChild}>保存孩子档案</button>
          <hr />
          <select value={selectedChildId ?? ''} onChange={(e) => setSelectedChildId(Number(e.target.value))}>
            <option value="">选择已有孩子</option>
            {children.map((child) => <option key={child.id} value={child.id}>{child.code} · {child.age ?? '?'}岁</option>)}
          </select>
          {selectedChild && <p className="hint">当前：{selectedChild.code}｜注意力 {selectedChild.attention_span_minutes ?? '?'} 分钟｜兴趣：{selectedChild.interests.join('、')}</p>}
        </div>

        <div className="card">
          <h2>2. 本节目标与图片需求</h2>
          <label>目标技能</label>
          <input value={targetSkill} onChange={(e) => setTargetSkill(e.target.value)} />
          <label>图片概念</label>
          <input value={concept} onChange={(e) => setConcept(e.target.value)} />
          <label>需要图片数量</label>
          <input value={neededCount} type="number" min={1} max={30} onChange={(e) => setNeededCount(Number(e.target.value))} />
          <label>泛化变式</label>
          <input value={variations} onChange={(e) => setVariations(e.target.value)} />
          <div className="pipeline">
            <span>资源库复用</span><b>→</b><span>找图API</span><b>→</b><span>生图Prompt/API</span><b>→</b><span>老师确认</span><b>→</b><span>存库</span>
          </div>
        </div>
      </section>

      <section className="card">
        <h2>3. 图片 Pipeline 结果</h2>
        {!imageResult && <p className="hint">点击“运行图片流程”后，这里会显示候选图。没有配置图片搜索 key 时会返回占位候选，方便开发 UI。</p>}
        {imageResult && (
          <div>
            <p><strong>策略：</strong>{imageResult.strategy_used}</p>
            {imageResult.notes.map((n, i) => <p className="hint" key={i}>• {n}</p>)}
            <div className="candidateGrid">
              {imageResult.candidates.map((img, idx) => (
                <div className={`candidate ${approvedIndexes.includes(idx) ? 'approved' : ''}`} key={idx} onClick={() => toggleApproved(idx)}>
                  {img.thumbnail_url ? <img src={img.thumbnail_url} alt={img.title} /> : <div className="placeholder">IMG</div>}
                  <strong>{img.title}</strong>
                  <small>{img.source_type} · {img.variation_type} · score {img.quality_score}</small>
                  {img.license_label && <small>{img.license_label}</small>}
                  {img.generation_prompt && <pre>{img.generation_prompt}</pre>}
                </div>
              ))}
            </div>
            <button className="primary" onClick={saveApprovedImages} disabled={approvedIndexes.length === 0}>保存选中图片到资源库</button>
          </div>
        )}
      </section>

      {lesson && (
        <section className="grid two">
          <div className="card">
            <h2>4. 教学流程</h2>
            {lesson.cost_saving_notes.map((n, i) => <p className="success" key={i}>✓ {n}</p>)}
            {lesson.segments.map((seg, i) => <div className="row" key={i}>{String(seg.order)}. {String(seg.title)}｜{String(seg.duration_minutes)}分钟<br />{String(seg.activity)}</div>)}
          </div>
          <div className="card">
            <h2>5. 教师脚本</h2>
            <ol>{lesson.teacher_script.map((line, i) => <li key={i}>{line}</li>)}</ol>
          </div>
          <div className="card">
            <h2>6. 泛化计划</h2>
            {lesson.generalization_plan.map((item, i) => (
              <div className="row" key={i}><strong>{String(item.dimension ?? item.type)}</strong><br />{Array.isArray(item.examples) ? item.examples.join(' / ') : ''}</div>
            ))}
          </div>
          <div className="card">
            <h2>7. 强化与课后记录</h2>
            <p className="hint">轮换：{lesson.reinforcement_plan.rotation.join('、')}</p>
            <ul>{lesson.reinforcement_plan.schedule.map((line, i) => <li key={i}>{line}</li>)}</ul>
            <ul>{lesson.reinforcement_plan.saturation_warnings.map((line, i) => <li key={i}>{line}</li>)}</ul>
            <div className="formGrid">
              <input type="number" value={record.independent_count} onChange={(e) => setRecord({ ...record, independent_count: Number(e.target.value) })} placeholder="独立完成" />
              <input type="number" value={record.prompted_count} onChange={(e) => setRecord({ ...record, prompted_count: Number(e.target.value) })} placeholder="提示完成" />
              <input type="number" value={record.error_count} onChange={(e) => setRecord({ ...record, error_count: Number(e.target.value) })} placeholder="错误" />
            </div>
            <input value={record.notes} onChange={(e) => setRecord({ ...record, notes: e.target.value })} placeholder="课后备注" />
            <button onClick={submitRecord}>保存课后记录</button>
            {savedRecord && <p className="success">已保存，掌握等级：Level {savedRecord.mastery_level}｜变化 {savedRecord.progress_delta}｜信心 {savedRecord.confidence_score}</p>}
          </div>
        </section>
      )}
    </main>
  );
}
