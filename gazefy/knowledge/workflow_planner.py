"""LearnedWorkflowPlanner: current UIMap + workflows -> executable plan.

Matches a user's natural-language task request to a learned workflow,
fills slots from the request, resolves targets against the current UIMap,
and produces an executable step-by-step plan.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PlannedStep:
    """A single step in an executable plan."""

    action: str  # click, type, scroll, drag
    target_semantic_id: str = ""
    target_text: str = ""
    target_element_id: str = ""  # Resolved UIMap element ID
    value: str = ""  # For type actions
    expect: str = ""  # Expected outcome description
    details: dict = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """An executable plan produced by the planner."""

    workflow_name: str
    task_request: str
    slots: dict[str, str] = field(default_factory=dict)
    steps: list[PlannedStep] = field(default_factory=list)
    confidence: float = 0.0  # 0-1, how well the workflow matches
    fallback: bool = False  # True if no workflow matched, using LLM improvisation


class WorkflowPlanner:
    """Plans execution from learned workflows + current UIMap."""

    def __init__(self, pack_dir: Path):
        from gazefy.knowledge.task_store import TaskStore

        self._store = TaskStore(pack_dir)
        self._workflows = self._store.load_all()
        logger.info("Loaded %d workflows", len(self._workflows))

    def plan(
        self,
        task_request: str,
        ui_map=None,
        ontology_resolver=None,
    ) -> ExecutionPlan:
        """Create an execution plan from a task request.

        Args:
            task_request: Natural language task, e.g. "play test.mp4"
            ui_map: Current UIMap (for target resolution)
            ontology_resolver: OntologyResolver (for semantic matching)

        Returns:
            ExecutionPlan with resolved steps
        """
        # Step 1: Match task to a workflow
        match = self._match_workflow(task_request)

        if not match:
            logger.info("No matching workflow for: %s", task_request)
            return ExecutionPlan(
                workflow_name="",
                task_request=task_request,
                fallback=True,
            )

        workflow, confidence = match
        name = workflow.get("name", "")
        logger.info("Matched workflow '%s' (confidence=%.2f)", name, confidence)

        # Step 2: Fill slots from request
        slots = self._fill_slots(task_request, workflow)

        # Step 3: Build planned steps
        steps = []
        for step in workflow.get("steps", []):
            planned = PlannedStep(
                action=step.get("action", "click"),
                target_semantic_id=step.get("target", ""),
                expect=step.get("expect", ""),
                details=step.get("details", {}),
            )

            # Fill slot values
            slot_name = step.get("slot", "")
            if slot_name and slot_name in slots:
                planned.value = slots[slot_name]

            # Resolve target against UIMap
            if ui_map and planned.target_semantic_id:
                element_id = self._resolve_target(
                    planned.target_semantic_id, ui_map, ontology_resolver
                )
                if element_id:
                    planned.target_element_id = element_id
                    el = ui_map.elements.get(element_id)
                    if el:
                        planned.target_text = el.text

            steps.append(planned)

        return ExecutionPlan(
            workflow_name=name,
            task_request=task_request,
            slots=slots,
            steps=steps,
            confidence=confidence,
        )

    def _match_workflow(self, task_request: str) -> tuple[dict, float] | None:
        """Find the best matching workflow for a task request."""
        request_lower = task_request.lower()
        request_words = set(re.findall(r"[a-z0-9]+", request_lower))

        best_workflow = None
        best_score = 0.0

        for workflow in self._workflows.values():
            name = workflow.get("name", "").lower()
            intents = workflow.get("intent_examples", [])

            # Score by word overlap with name and intent examples
            score = 0.0
            name_words = set(re.findall(r"[a-z0-9]+", name))
            overlap = len(request_words & name_words)
            if name_words:
                score = overlap / len(name_words)

            # Check intent examples
            for intent in intents:
                intent_words = set(re.findall(r"[a-z0-9]+", intent.lower()))
                intent_overlap = len(request_words & intent_words)
                if intent_words:
                    intent_score = intent_overlap / len(intent_words)
                    score = max(score, intent_score)

            if score > best_score:
                best_score = score
                best_workflow = workflow

        if best_workflow and best_score > 0.3:
            return best_workflow, best_score
        return None

    def _fill_slots(self, task_request: str, workflow: dict) -> dict[str, str]:
        """Extract slot values from the task request."""
        slots = {}
        defined_slots = workflow.get("slots", [])

        for slot_def in defined_slots:
            name = slot_def.get("name", "")
            slot_type = slot_def.get("type", "string")

            if name == "file_path":
                # Extract file path from request
                # Match quoted strings or file-like patterns
                m = re.search(r'"([^"]+)"|\'([^\']+)\'|(\S+\.\w{2,4})', task_request)
                if m:
                    slots[name] = m.group(1) or m.group(2) or m.group(3)
            elif slot_type == "string":
                # Try to extract from quoted text
                m = re.search(r'"([^"]+)"|\'([^\']+)\'', task_request)
                if m:
                    slots[name] = m.group(1) or m.group(2)

        return slots

    def _resolve_target(
        self,
        target: str,
        ui_map,
        ontology_resolver=None,
    ) -> str:
        """Resolve a semantic target to a UIMap element ID."""
        # Direct semantic_id match via ontology
        if ontology_resolver:
            for eid, el in ui_map.elements.items():
                entry = ontology_resolver.resolve(el)
                if entry and entry.semantic_id == target:
                    return eid

        # Fallback: text match
        target_text = target.replace("_", " ").lower()
        for eid, el in ui_map.elements.items():
            if el.text and el.text.lower() == target_text:
                return eid

        # Partial text match
        for eid, el in ui_map.elements.items():
            if el.text and target_text in el.text.lower():
                return eid

        return ""

    @property
    def workflow_names(self) -> list[str]:
        return list(self._workflows.keys())
