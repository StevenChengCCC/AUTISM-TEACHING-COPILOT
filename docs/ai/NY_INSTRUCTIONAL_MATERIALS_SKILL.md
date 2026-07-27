# New York instructional-material skill

`ny_instructional_materials:v1` is a supplemental generation and evaluation
skill. It helps the product create complete, teacher-editable lesson materials
for New York special-education classrooms. It is not a legal-compliance engine
and does not create or change an IEP, placement, service, accommodation,
diagnosis, or behavior plan.

## What is binding and what is guidance

The skill keeps three source classes separate:

1. **New York requirements.** Part 200 and the State IEP process require
   individualized present levels, measurable academic and functional goals,
   criteria/procedures/schedules for progress measurement, and the programs,
   services, supplementary aids, accommodations, and modifications decided by
   the CSE or CPSE. The product may use teacher-confirmed information but may
   not invent or override it.
2. **New York instructional guidance.** NYSED guidance emphasizes access to the
   general curriculum, specially designed instruction, research-based
   strategies, self-advocacy, family partnership, assistive technology,
   generalization, progress monitoring, and culturally and linguistically
   sustaining practice.
3. **Optional instructional frameworks.** CAST UDL 3.0, CEC/CEEDAR
   High-Leverage Practices, and UNC NCAEP/AFIRM inform accessible
   representation, response options, explicit instruction, scaffolding,
   visual supports, prompting, reinforcement, task analysis, and
   generalization. They are not New York law and must be selected for the
   learner and target rather than applied as a universal autism recipe.

NYC Public Schools' AIMS, Nest, and Horizon pages describe different
program-specific student profiles and teaching approaches. Those descriptions
inform possible material features—visual schedules, organization systems,
authentic communication, self-advocacy, interests, positive proactive support,
and access to New York standards—but the product must not infer a program,
placement, or ABA plan from a learner record.

## Product behavior

The skill is loaded as a supplemental trusted instruction for:

- dynamic lesson-planning questions;
- lesson-package and printable-material generation;
- AI revision of one selected lesson section.

It also adds deterministic package checks for:

- a complete typed material set;
- the minimum bundle required for the instructional goal family;
- an item-level visual plan for every visual material;
- print-ready specifications;
- preserved communication and assistive access;
- teacher confirmation of New York curriculum alignment.

The minimum function-based bundles are:

- **Counting / early numeracy:** quantity cards, matching practice,
  reinforcement board, data sheet, and lesson summary.
- **Communication / requesting:** visual card, help card, scenario cards,
  reinforcement board, and data sheet.
- **Transition / self-care:** First–Then board, choice board, visual card,
  reinforcement board, and data sheet.
- **Emotional regulation / break communication:** emotion scale, break card,
  choice board, visual card, and data sheet.
- **Following directions:** visual card, First–Then board, sequence cards,
  reinforcement board, and data sheet.
- **Social participation:** social situation guide, scenario cards, choice
  board, visual card, and data sheet.
- **Classroom routines / independent work:** visual schedule, task-analysis
  cards, First–Then board, data sheet, and lesson summary.
- **Functional AAC:** core-word board, help card, choice board, scenario cards,
  and data sheet.
- **Early literacy:** visual card, matching practice, sequence cards, data
  sheet, and lesson summary.
- **Concepts / classification:** sorting practice, matching practice, visual
  card, data sheet, and lesson summary.
- **Play / leisure participation:** choice board, scenario cards, visual card,
  reinforcement board, and data sheet.
- **Community / safety / vocational routines:** task-analysis cards, visual
  schedule, scenario cards, help card, and data sheet.

These bundles are starting points selected by instructional function, not by
diagnosis. Teachers can add, remove, and edit materials. The typed catalog also
supports teacher cue cards, session summaries, and authorized handoff notes.
Every material type defines its instructional purpose, required content,
professional rules, teacher directions, accessible visual behavior, and
printable structure.

The material rules intentionally prioritize classroom-ready pages over long
rationale. When a selected material contains exact academic content, quantities,
numerals, equations, sequences, labels, cut lines, and answer keys are rendered
programmatically. Image generation supplies theme-appropriate artwork only.
A multi-card, choice, sequence, or quantity activity is not ready until every
required item is present.

## Sources reviewed for v1

- [NYSED Part 200.4](https://www.nysed.gov/special-education/section-2004-procedures-referral-evaluation-iep-development-placement-and-review)
- [NYSED Guide to Quality IEP Development and Implementation](https://www.nysed.gov/sites/default/files/programs/special-education/guide-to-quality-iep-development-and-implementation.pdf)
- [NYSED Blueprint for Improved Results for Students with Disabilities](https://www.nysed.gov/special-education/blueprint-improved-results-students-disabilities)
- [NYSED Culturally Responsive-Sustaining Education Framework](https://www.nysed.gov/crs/framework)
- [NYSED Assistive Technology for Students with Disabilities](https://www.nysed.gov/special-education/assistive-technology-students-disabilities)
- [NYCPS Specialized Programs for Students with Disabilities](https://www.schools.nyc.gov/learning/special-education/school-settings/specialized-programs)
- [CAST UDL Guidelines 3.0](https://udlguidelines.cast.org/)
- [CEC/CEEDAR High-Leverage Practices](https://highleveragepractices.org/four-areas-practice-k-12/instruction)
- [UNC AFIRM modules based on the NCAEP evidence review](https://afirm.fpg.unc.edu/afirm-modules/)

Source review date: 2026-07-27. Before promoting a new version, a New
York-certified special educator should review the rules and at least three
representative kits across ages, communication modes, and subjects.

## Recommended next skill layers

1. **Subject-and-grade standards resolver.** Store exact NYSED ELA, mathematics,
   science, and alternate-assessment identifiers separately from generative
   prompts. The teacher selects or confirms the standard.
2. **Additional material-type renderers.** Add more specialized layouts only
   where classroom testing shows that the existing quantity, matching,
   communication, sequence, schedule, task-analysis, social-situation,
   reinforcement, data, and summary renderers are insufficient.
3. **EBP selection assistant.** Use an AFIRM/NCAEP practice matrix keyed by
   learner age, observable target, setting, and teacher capacity. Recommend,
   never prescribe.
4. **AAC accessibility reviewer.** Check symbol consistency, motor access,
   response effort, partner instructions, and device availability without
   changing a speech-language plan.
5. **Bilingual material layer.** Support teacher-confirmed home language,
   English, bilingual labels, and family-facing wording; do not machine-translate
   specialized terms without review.
6. **Teacher outcome evaluator.** Track preparation time saved, print success,
   classroom usability, edit burden, and material reuse. These product metrics
   are more useful for this stage than a broad learner-progress dashboard.
